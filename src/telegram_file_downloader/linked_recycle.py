"""Cloud-first recycling of an explicitly previewed local counterpart."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

from .storage import RecycleBin, file_version, inside
from .xiaomi_cloud import XiaomiError


class LinkedRecycle:
    def __init__(self, store, cloud, local_index):
        self.store, self.cloud, self.local = store, cloud, local_index

    def save(self, plan):
        self.store.put("xiaomi_recycle:" + plan["token"], plan)

    def preview(self, connection, album, ids):
        owner = self.cloud.local_owner(connection)
        with self.store.db:
            self.store.db.execute("""DELETE FROM kv WHERE key LIKE 'xiaomi_recycle:%'
                AND json_extract(value,'$.created')<? AND json_extract(value,'$.cloud_done')=0""", (time.time() - 86400,))
            self.store.db.execute("""DELETE FROM kv WHERE key LIKE 'xiaomi_recycle:%'
                AND json_extract(value,'$.created')<? AND json_extract(value,'$.cloud_done')=1
                AND (json_extract(value,'$.local_done')=1 OR json_extract(value,'$.local.status')<>'ready')""",
                (time.time() - 15 * 86400,))
        items, selected = [], set()
        for media_id in dict.fromkeys(ids):
            item = self.cloud.selected_media(connection, album, media_id)
            local = self.local.recycle_preview(owner, album, item)
            key = (local["root_id"], local["path"])
            if local["status"] == "ready":
                if key in selected:
                    local.update(status="kept", detail="同一本地文件已列入前面的回收项，此项只回收云端")
                selected.add(key)
            plan = dict(token=uuid4().hex, owner=owner, connection=connection, album=album, id=media_id,
                        name=item["name"], local=local, created=time.time(), cloud_done=False, local_done=False, error="")
            self.save(plan)
            items.append(dict(local, token=plan["token"]))
        return {"items": items}

    def pending(self, connection):
        owner = self.cloud.local_owner(connection)
        rows = self.store.db.execute("""SELECT value FROM kv WHERE key LIKE 'xiaomi_recycle:%'
            AND json_extract(value,'$.owner')=? AND json_extract(value,'$.cloud_done')=1
            AND json_extract(value,'$.local_done')=0 AND json_extract(value,'$.local.status')='ready'""", (owner,))
        return [self.result(json.loads(row[0])) for row in rows]

    @staticmethod
    def result(plan):
        return dict(token=plan["token"], id=plan["id"], name=plan["name"], cloud_done=plan["cloud_done"],
                    local_done=plan["local_done"], local=plan["local"], error=plan["error"])

    async def execute(self, connection, media_id, token):
        owner = self.cloud.local_owner(connection)
        plan = self.store.get("xiaomi_recycle:" + token)
        if not plan or plan["owner"] != owner or plan["id"] != media_id:
            raise XiaomiError("回收预览已失效，请重新确认", 409)
        if not plan["cloud_done"]:
            if plan["connection"] != connection or plan["created"] < time.time() - 86400:
                raise XiaomiError("回收预览已过期，请重新确认", 409)
            if plan["local"]["status"] == "ready":
                source = self.local.source(owner, plan["album"])
                if not source or source["id"] != plan["local"]["root_id"]:
                    raise XiaomiError("本地目录绑定已变化，请重新确认", 409)
                self.selected_file(plan["local"])
            await self.cloud.recycle(connection, media_id)
            plan["cloud_done"] = True
            self.save(plan)
        if plan["local"]["status"] == "ready" and not plan["local_done"]:
            try:
                local = plan["local"]
                with RecycleBin(Path(local["root"])) as recycle:
                    record = recycle.db.execute("SELECT state FROM items WHERE id=?", (token,)).fetchone()
                    if not record:
                        path = self.selected_file(local)
                        recycle.move(path, token, "xiaomi_cloud")
                    elif record["state"] == "pending":
                        recycle.move(self.selected_file(local), token, "xiaomi_cloud")
                plan["local_done"], plan["error"] = True, ""
                with self.local.db:
                    self.local.db.execute("DELETE FROM files WHERE root_id=? AND path=?", (local["root_id"], local["path"]))
            except (OSError, ValueError) as exc:
                plan["error"] = "云端已回收，本地回收未完成：" + str(exc)
            except sqlite3.Error as exc:
                plan["error"] = "本地回收记录或目录索引写入失败，请检查数据目录：" + str(exc)
            self.save(plan)
        return self.result(plan)

    @staticmethod
    def selected_file(local):
        path = inside(Path(local["root"]), local["path"])
        if not path.is_file() or file_version(path.stat()) != local["version"]:
            raise ValueError("本地文件已变化，已保留原文件，请重新确认")
        return path

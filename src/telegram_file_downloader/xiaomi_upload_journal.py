"""Durable upload receipts in the console data volume; no account credentials."""
from __future__ import annotations

import json


class UploadJournal:
    def __init__(self, store):
        self.db = store.db
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS xiaomi_upload_jobs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, album TEXT NOT NULL,
                root TEXT NOT NULL, created REAL NOT NULL, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS xiaomi_upload_owner ON xiaomi_upload_jobs(owner,album,created);
            CREATE TABLE IF NOT EXISTS xiaomi_upload_items (
                job TEXT NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL,
                status TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(job,name));
            CREATE INDEX IF NOT EXISTS xiaomi_upload_file ON xiaomi_upload_items(name,version,status);
        """)
        self.db.commit()
        rows = self.db.execute("SELECT id,data FROM xiaomi_upload_jobs").fetchall()
        for row in rows:
            job = json.loads(row["data"])
            check = job.get("verification")
            if job["state"] not in {"complete", "stopped"} or check and check["active"]:
                job.update(state="stopped", error="程序重启中断了此批次；已保存回执，可重新核对或找回上传记录", revision=job["revision"] + 1)
                if check:
                    check.update(active=False, error="核对被重启中断，请重新核对")
                with self.db:
                    self.db.execute("UPDATE xiaomi_upload_jobs SET data=? WHERE id=?", (json.dumps(job), row["id"]))
                    for item_row in self.db.execute("SELECT name,data FROM xiaomi_upload_items WHERE job=? AND status='uploading'", (row["id"],)).fetchall():
                        item = json.loads(item_row["data"])
                        item.update(status="waiting", error="上传被重启中断，云端结果尚待确认")
                        self.save_item(row["id"], item)

    def save_item(self, job_id, item):
        self.db.execute("""INSERT INTO xiaomi_upload_items VALUES (?,?,?,?,?)
                        ON CONFLICT(job,name) DO UPDATE SET version=excluded.version,
                        status=excluded.status,data=excluded.data""",
                        (job_id, item["name"], item["version"], item["status"], json.dumps(item)))

    def save(self, job, item=None, *, initial=False):
        data = {key: value for key, value in job.items() if key not in {"connection", "gate", "items"}}
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO xiaomi_upload_jobs VALUES (?,?,?,?,?,?)",
                            (job["id"], job["owner"], job["album"], job["root"], job["created"], json.dumps(data)))
            if initial:
                for entry in job["items"]:
                    self.save_item(job["id"], entry)
            elif item is not None:
                self.save_item(job["id"], item)

    def load(self, owner, job_id="", album=""):
        query, args = "SELECT data FROM xiaomi_upload_jobs WHERE owner=?", [owner]
        if job_id:
            query += " AND id=?"
            args.append(job_id)
        elif album:
            query += " AND album=?"
            args.append(album)
        row = self.db.execute(query + " ORDER BY created DESC LIMIT 1", args).fetchone()
        if not row:
            return None
        job = json.loads(row[0])
        job["items"] = [json.loads(row[0]) for row in self.db.execute(
            "SELECT data FROM xiaomi_upload_items WHERE job=? ORDER BY rowid", (job["id"],))]
        for item in job["items"]:
            if "receipt" in item:
                item["receipt"] = tuple(item["receipt"])
        return job

    def history(self, owner, album):
        rows = self.db.execute("""SELECT j.data, COUNT(i.name) AS total,
            SUM(CASE WHEN i.status='verified' AND json_extract(i.data,'$.kind')='image' THEN 1 ELSE 0 END) AS eligible
            FROM xiaomi_upload_jobs j LEFT JOIN xiaomi_upload_items i ON i.job=j.id
            WHERE j.owner=? AND j.album=? GROUP BY j.id ORDER BY j.created DESC""", (owner, album))
        return [dict(id=data["id"], album=data["album"], created=data["created"], mode=data["mode"],
                     state=data["state"], total=row["total"], eligible=row["eligible"] or 0)
                for row in rows for data in [json.loads(row["data"])]]

    def confirmed(self, owner, album, root):
        return {(row["name"], row["version"]) for row in self.db.execute("""
            SELECT i.name,i.version FROM xiaomi_upload_items i JOIN xiaomi_upload_jobs j ON j.id=i.job
            WHERE j.owner=? AND j.album=? AND j.root=? AND i.status IN ('verified','recycled')""", (owner, album, root))}

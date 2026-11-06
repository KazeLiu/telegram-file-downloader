"""Docker-side handoff commands used by the Windows host script; no web credentials."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .storage import RETENTION_SECONDS, RecycleBin, inside


def recycle_roots(data_dir, download_dir):
    roots = {"downloads": download_dir}
    database = data_dir / "xiaomi-local.sqlite3"
    if database.is_file():
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            for root_id, path in db.execute("SELECT id,path FROM roots"):
                if Path(path) not in roots.values():
                    roots[root_id] = Path(path)
    return roots


def due_items(roots):
    items, errors = [], []
    for root_id, root in roots.items():
        try:
            database = inside(root, ".tg-trash/index.sqlite3")
            if not database.is_file():
                continue
            with RecycleBin(root) as recycle:
                for row in recycle.db.execute("SELECT * FROM items WHERE state='exporting' OR (state='trashed' AND created<=?)",
                                              (time.time() - RETENTION_SECONDS,)).fetchall():
                    _, file = recycle._paths(row)
                    if row["state"] == "trashed" and (not file.is_file() or file.stat().st_mtime > time.time() - RETENTION_SECONDS):
                        continue
                    items.append(dict(root=root_id, directory=str(root), id=row["id"], original=row["original"],
                                      state=row["state"], path=file.relative_to(root).as_posix()))
        except (OSError, ValueError, sqlite3.Error) as exc:
            errors.append(dict(root=root_id, directory=str(root), error=str(exc)))
    return {"items": items, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "claim", "done", "cancel"))
    parser.add_argument("--root", default="downloads")
    parser.add_argument("--id")
    args = parser.parse_args()
    roots = recycle_roots(Path(os.environ["DATA_DIR"]).resolve(), Path(os.environ["DOWNLOAD_DIR"]).resolve())
    try:
        if args.action == "list":
            result = due_items(roots)
        else:
            if args.root not in roots or not args.id:
                raise ValueError("请选择已登记的回收目录和记录")
            with RecycleBin(roots[args.root]) as recycle:
                if args.action == "claim":
                    result = recycle.prepare_windows(args.id)
                else:
                    recycle.finish_windows(args.id, args.action == "done")
                    result = {"ok": True}
        print(json.dumps(result, ensure_ascii=True))
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Windows recycle handoff failed: {exc}\n")


if __name__ == "__main__":
    main()

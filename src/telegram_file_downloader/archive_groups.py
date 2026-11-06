"""Logical archive sets do not change download paths or partial checkpoints."""
from collections import defaultdict

from .archives import resource_name, volume_info

CLOSED_ARCHIVES = {"extracted", "organized", "manual_extracted"}
ACTIVE_ARCHIVES = {"downloading", "waiting", "retrying", "extracting", "organizing"}


def archive_set_updates(tasks):
    buckets = defaultdict(list)
    for task in tasks:
        volume = task.get("volume") or volume_info(task["filename"])
        if not volume:
            continue
        signature = task.get("volume_signature") or f"{volume['base'].casefold()}:{volume['scheme']}:unknown"
        task = {**task, "volume": volume, "volume_signature": signature}
        buckets[(task["scope"], signature)].append(task)
    for tasks in buckets.values():
        original = defaultdict(list)
        for task in tasks:
            original[task.get("group_id") or f"file:{task['id']}"].append(task)
        closed, opened = [], []
        for members in original.values():
            (closed if any(item["status"] in CLOSED_ARCHIVES for item in members) else opened).append(members)
        pending = [item for members in opened for item in members]
        open_ids = {item["id"] for item in pending}
        indices = [item["volume"]["index"] for item in pending]
        ambiguous = len(set(indices)) != len(indices)
        sets = closed + (opened if ambiguous else ([pending] if pending else []))
        for members in sets:
            key = f"archive-set:{min(item['id'] for item in members)}"
            warning = "同名记录有重复卷号，已保留原批次，未跨批次合并" if ambiguous and members[0]["id"] in open_ids else ""
            for task in members:
                yield task["id"], dict(volume=task["volume"], volume_signature=task["volume_signature"],
                                      archive_set=key, archive_group_warning=warning)


def task_view(task, members):
    ordered = sorted(members, key=lambda item: ((item.get("volume") or {}).get("index", 0), item["id"]))
    result = dict(task)
    priority = ["downloading", "retrying", "waiting", "extracting", "organizing", "failed", "processing_failed",
                "extraction_failed", "waiting_volumes", "interrupted", "queued", "paused", "downloaded",
                "manual_extracted", "organized", "extracted", "completed"]
    statuses = {item["status"] for item in ordered}
    result.update(group_count=len(ordered), group_size=sum(item["size"] for item in ordered),
                  group_downloaded=sum(item["downloaded"] for item in ordered),
                  display_status=next((status for status in priority if status in statuses), task["status"]),
                  archive_name=resource_name(task["filename"]) if len(ordered) > 1 else task["filename"],
                  group_members=[{key: item.get(key) for key in ("id", "filename", "status", "downloaded", "size", "average_speed")}
                                 for item in ordered])
    return result

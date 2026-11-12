"""Read-only playback of media inside registered local gallery roots."""
from __future__ import annotations

import mimetypes
import heapq
import json
import os
from pathlib import Path

from .image_library import IMAGE_EXTENSIONS
from .storage import file_version, inside, internal_directory, is_link
from .xiaomi_local import folder_entries


VIDEO_TYPES = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
    ".mov": "video/quicktime", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
}


def media_kind(name):
    suffix = Path(name).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_TYPES:
        return "video"
    return None


def gallery_root(galleries, root_id):
    source = next((item for item in galleries if item["id"] == root_id), None)
    if not source:
        raise ValueError("图库已不存在，请刷新图库后重新选择")
    root = Path(source["path"])
    inside(root)
    if not root.is_dir():
        raise ValueError("图库目录不可访问，请检查挂载和读取权限")
    return root


def queue(galleries, roots, kind):
    items, seen = [], set()
    for root_id in dict.fromkeys(roots):
        root = gallery_root(galleries, root_id)
        for entry in folder_entries(root):
            if entry is None:
                continue
            name, size, relative, version = entry
            item_kind = media_kind(name)
            if not item_kind or not size or kind != "mixed" and item_kind != kind:
                continue
            path = inside(root, relative)
            if path in seen:
                continue
            seen.add(path)
            items.append(dict(root=root_id, path=relative, name=name, kind=item_kind, version=version))
    return sorted(items, key=lambda item: (item["path"].casefold(), item["root"], item["path"]))


def queue_batches(galleries, roots, kind):
    """Yield sorted metadata in batches without waiting for a full recursive scan."""
    registered = {root_id: gallery_root(galleries, root_id) for root_id in dict.fromkeys(roots)}
    root_ids = list(registered)
    earlier = {root_id: [registered[previous] for previous in root_ids[:index]] for index, root_id in enumerate(root_ids)}
    pending = [("", root_id, "", True) for root_id in registered]
    heapq.heapify(pending)
    seen, batch = set(), []
    try:
        while pending:
            _, root_id, relative, directory = heapq.heappop(pending)
            root = registered[root_id]
            path = inside(root, relative)
            if any(path.is_relative_to(previous) for previous in earlier[root_id]):
                continue
            try:
                if directory:
                    with os.scandir(path) as entries:
                        for entry in entries:
                            if internal_directory(entry.name) or is_link(entry):
                                continue
                            child = f"{relative}/{entry.name}" if relative else entry.name
                            is_directory = entry.is_dir(follow_symlinks=False)
                            if is_directory or entry.is_file(follow_symlinks=False) and media_kind(entry.name):
                                heapq.heappush(pending, (child.casefold(), root_id, child, is_directory))
                    continue
                item_kind = media_kind(relative)
                if path in seen or kind != "mixed" and item_kind != kind:
                    continue
                info = path.stat()
                if not info.st_size:
                    continue
            except FileNotFoundError:
                continue
            seen.add(path)
            batch.append(dict(root=root_id, path=relative, name=path.name, kind=item_kind, version=file_version(info), identity=os.path.normcase(str(path))))
            if len(batch) == 20:
                yield json.dumps({"items": batch}) + "\n"
                batch = []
        yield json.dumps({"items": batch, "done": True}) + "\n"
    except (OSError, ValueError) as exc:
        yield json.dumps({"error": str(exc)}) + "\n"


def selected_media(galleries, root_id, relative, version):
    root = gallery_root(galleries, root_id)
    if any(internal_directory(part) for part in Path(relative).parts) or not media_kind(relative):
        raise ValueError("请选择图库中的图片或视频")
    file = inside(root, relative)
    if not file.is_file():
        raise ValueError("文件已不存在，请重新开始播放以刷新列表")
    if file_version(file.stat()) != version:
        raise ValueError("文件已变化，请重新开始播放以刷新列表")
    mime = VIDEO_TYPES.get(file.suffix.lower()) or mimetypes.guess_type(file.name)[0]
    return file, mime

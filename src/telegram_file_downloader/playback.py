"""Read-only playback of media inside registered local gallery roots."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from .image_library import IMAGE_EXTENSIONS
from .storage import file_version, inside, internal_directory
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

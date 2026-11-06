"""Flatten only an explicitly selected tree, with a durable move journal."""
from __future__ import annotations

import logging
import asyncio
import os
from pathlib import Path

from .files import safe_filename

LOGGER = logging.getLogger(__name__)


def inside(root: Path, value: str = "") -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("请选择下载目录内的路径")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (current.exists() and getattr(current.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("不允许操作链接目录或文件")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("路径超出下载目录")
    return current


def entries(root: Path, source: Path):
    if not source.is_dir():
        raise ValueError("选择的文件夹不存在")
    for directory, folders, files in os.walk(source, followlinks=False):
        folders[:] = sorted(name for name in folders if Path(directory) != root or (
            name != ".tg-work" and not name.startswith(".tg-extract-")))
        for name in [*folders, *sorted(files)]:
            item = Path(directory) / name
            inside(root, str(item.relative_to(root)))
            if item.is_file():
                yield item


def browse(root, value="", page=1, search=""):
    folder = inside(root, value)
    if not folder.is_dir() or (Path(value).parts and Path(value).parts[0] == ".tg-work"):
        raise ValueError("文件夹不存在或属于工作流内部目录")
    items = []
    for entry in folder.iterdir():
        if (folder == root and (entry.name == ".tg-work" or entry.name.startswith(".tg-extract-"))) or entry.is_symlink():
            continue
        if search.casefold() not in entry.name.casefold():
            continue
        stat = entry.stat()
        if getattr(stat, "st_file_attributes", 0) & 0x400:
            continue
        items.append(dict(name=entry.name, path=entry.relative_to(root).as_posix(), directory=entry.is_dir(),
                          size=stat.st_size if entry.is_file() else None, modified=stat.st_mtime))
    items.sort(key=lambda item: (not item["directory"], item["name"].casefold()))
    return dict(path=folder.relative_to(root).as_posix(), root=str(root), items=items[(page - 1) * 100:page * 100],
                total=len(items), page=page)


def make_plan(root: Path, source: Path, prefix: str, delete_pdf=False, protect_partials=True):
    moves, pdfs, reserved = [], [], set()
    for file in entries(root, source):
        if protect_partials and file.name.endswith((".part", ".part-journal")):
            raise ValueError("目录中有尚未完成的下载，请等待完成后再整理")
        if delete_pdf and file.suffix.lower() == ".pdf":
            pdfs.append(str(file))
            continue
        parts = list(file.relative_to(source).parts)
        # An archive often already contains a folder named after the resource.
        if prefix and parts[0] != prefix:
            parts.insert(0, prefix)
        name = safe_filename("-".join(parts))
        if len(name.encode("utf-8")) > 240:
            raise ValueError(f"整理后的文件名过长，请先缩短目录名：{file.name}")
        target = root / name
        if file == target:
            continue
        serial = 2
        while target.exists() or target.name.casefold() in reserved:
            target = root / f"{Path(name).stem} ({serial}){Path(name).suffix}"
            serial += 1
        reserved.add(target.name.casefold())
        moves.append(dict(source=str(file), target=str(target), done=False))
    return dict(source=str(source), moves=moves, pdfs=pdfs, deleted=[], complete=False)


async def execute_plan(root: Path, plan, save, on_phase=None):
    if on_phase:
        on_phase("organize")
    for move in plan["moves"]:
        if move["done"]:
            continue
        source, target = Path(move["source"]), Path(move["target"])
        inside(root, str(source.relative_to(root)))
        inside(root, str(target.relative_to(root)))
        if source.exists():
            if target.exists():
                if not source.samefile(target):
                    raise ValueError("预览后目标文件已存在，请重新预览；没有覆盖文件")
            else:
                # Same mounted filesystem: link creates an exclusive target without overwriting.
                os.link(source, target)
            source.unlink()
        elif not target.is_file():
            raise ValueError("整理中断后找不到源文件和目标文件，请检查挂载")
        move["done"] = True
        save(plan)
        LOGGER.info("organize moved source=%s target=%s", source, target)
        await asyncio.sleep(0)
    if on_phase:
        on_phase("pdf")
    for name in plan["pdfs"]:
        if name in plan["deleted"]:
            continue
        file = inside(root, str(Path(name).relative_to(root)))
        file.unlink(missing_ok=True)
        plan["deleted"].append(name)
        save(plan)
        LOGGER.info("organize deleted PDF path=%s", file)
        await asyncio.sleep(0)
    source = Path(plan["source"])
    for directory, _, _ in os.walk(source, topdown=False, followlinks=False):
        folder = Path(directory)
        if folder != root and folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
    plan["complete"] = True
    save(plan)
    return dict(moved=len(plan["moves"]), deleted_pdfs=len(plan["deleted"]), output=str(root))

"""Flatten only an explicitly selected tree, with a durable move journal."""
from __future__ import annotations

import logging
import asyncio
import os
import time
from heapq import nsmallest
from pathlib import Path

from .files import safe_filename

LOGGER = logging.getLogger(__name__)
CLEANUP_EXTENSIONS = frozenset({".psd", ".txt"})


def is_cleanup_file(name):
    return Path(name).suffix.lower() in CLEANUP_EXTENSIONS


def cleanup_lists(plan):
    # Old manual confirmations keep their exact PSD-only lists.
    return (plan.get("cleanup_files", plan.get("psds", [])),
            plan.get("deleted_files", plan.get("deleted_psds", [])))


def cleanup_counts(plan):
    planned, deleted = cleanup_lists(plan)
    return dict(cleanup_total=len(planned), cleanup_done=len(deleted),
                psd_total=sum(Path(name).suffix.lower() == ".psd" for name in planned),
                txt_total=sum(Path(name).suffix.lower() == ".txt" for name in planned),
                deleted_psds=sum(Path(name).suffix.lower() == ".psd" for name in deleted),
                deleted_txts=sum(Path(name).suffix.lower() == ".txt" for name in deleted))


def plan_counts(plan):
    return dict(move_total=len(plan.get("moves", [])),
                moved_files=sum(bool(move["done"]) for move in plan.get("moves", [])), **cleanup_counts(plan))


def restore_progress(plan, progress):
    for move in plan["moves"][:progress.get("move_cursor", 0)]:
        move["done"] = True
    planned, deleted = cleanup_lists(plan)
    known = set(deleted)
    deleted.extend(name for name in planned[:progress.get("cleanup_cursor", 0)] if name not in known)
    return plan


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


def is_link(entry):
    return entry.is_symlink() or (os.name == "nt" and entry.stat(follow_symlinks=False).st_file_attributes & 0x400)


def entries(root: Path, source: Path, directories=None, skip_root_files=False):
    if not source.is_dir():
        raise ValueError("选择的文件夹不存在")
    pending = [source]
    while pending:
        folder = pending.pop()
        # Validate ancestors once per directory; execution revalidates every affected path.
        inside(root, str(folder.relative_to(root)))
        if directories is not None and folder != root:
            directories.append(str(folder))
        folders, files = [], []
        with os.scandir(folder) as scan:
            for entry in scan:
                if folder == root and (entry.name == ".tg-work" or entry.name.startswith(".tg-extract-")):
                    continue
                directory = entry.is_dir(follow_symlinks=False)
                if folder == root and skip_root_files and not directory and not (
                    is_cleanup_file(entry.name) or entry.name.endswith((".part", ".part-journal"))
                ):
                    continue
                if is_link(entry):
                    raise ValueError("不允许操作链接目录或文件")
                if directory:
                    folders.append(entry.name)
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry.name)
        yield from (folder / name for name in sorted(files))
        pending.extend(folder / name for name in sorted(folders, reverse=True))


def browse(root, value="", page=1, search=""):
    folder = inside(root, value)
    if not folder.is_dir() or (Path(value).parts and Path(value).parts[0] == ".tg-work"):
        raise ValueError("文件夹不存在或属于工作流内部目录")
    total = 0
    needle = search.casefold()
    def candidates():
        nonlocal total
        with os.scandir(folder) as scan:
            for entry in scan:
                if folder == root and (entry.name == ".tg-work" or entry.name.startswith(".tg-extract-")):
                    continue
                if needle not in entry.name.casefold() or is_link(entry):
                    continue
                total += 1
                yield entry, entry.is_dir(follow_symlinks=False)
    selected = nsmallest(page * 100, candidates(), key=lambda item: (not item[1], item[0].name.casefold(), item[0].name))
    items = []
    for entry, directory in selected[(page - 1) * 100:]:
        stat = entry.stat(follow_symlinks=False)
        items.append(dict(name=entry.name, path=(folder / entry.name).relative_to(root).as_posix(), directory=directory,
                          size=stat.st_size if entry.is_file(follow_symlinks=False) else None, modified=stat.st_mtime))
    return dict(path=folder.relative_to(root).as_posix(), root=str(root), items=items, total=total, page=page)


def flatten_target(root, source, file, prefix, reserved):
    parts = list(file.relative_to(source).parts)
    if prefix and parts[0] != prefix:
        parts.insert(0, prefix)
    name = safe_filename("-".join(parts))
    if len(name.encode("utf-8")) > 240:
        raise ValueError(f"整理后的文件名过长，请先缩短目录名：{file.name}")
    target = root / name
    if file == target:
        return None
    serial = 2
    while target.name.casefold() in reserved:
        target = root / f"{Path(name).stem} ({serial}){Path(name).suffix}"
        serial += 1
    reserved.add(target.name.casefold())
    return target


def make_plan(root: Path, source: Path, prefix: str, delete_psd=False, protect_partials=True):
    started = time.monotonic()
    LOGGER.info("organize plan scanning source=%s", source)
    moves, cleanup, directories = [], [], []
    with os.scandir(root) as scan:
        reserved = {entry.name.casefold() for entry in scan}
    for file in entries(root, source, directories, skip_root_files=True):
        if protect_partials and file.name.endswith((".part", ".part-journal")):
            raise ValueError("目录中有尚未完成的下载，请等待完成后再整理")
        if delete_psd and is_cleanup_file(file):
            cleanup.append(str(file))
            continue
        if file.parent == root:
            continue
        target = flatten_target(root, source, file, prefix, reserved)
        if target is None:
            continue
        moves.append(dict(source=str(file), target=str(target), done=False))
    LOGGER.info("organize plan ready source=%s moves=%s cleanup=%s directories=%s elapsed=%.3fs",
                source, len(moves), len(cleanup), len(directories), time.monotonic() - started)
    return dict(source=str(source), directories=directories, moves=moves, cleanup="psd_txt",
                cleanup_files=cleanup, deleted_files=[], complete=False)


def upgrade_cleanup_plan(root, plan, prefix, delete_psd):
    """Upgrade automatic plans only; manual confirmations must not grow."""
    if plan.get("cleanup") == "psd_txt":
        return plan
    source = Path(plan["source"])
    with os.scandir(root) as scan:
        reserved = {entry.name.casefold() for entry in scan}
    reserved.update(Path(move["target"]).name.casefold() for move in plan["moves"])
    if plan.get("flatten", True):
        for name in plan.get("pdfs", []):
            file = inside(root, str(Path(name).relative_to(root)))
            if file.is_file() and name not in plan.get("deleted", []):
                target = flatten_target(root, source, file, prefix, reserved)
                if target:
                    plan["moves"].append(dict(source=str(file), target=str(target), done=False))
    moved_sources = {move["source"] for move in plan["moves"]}
    pending, deleted = cleanup_lists(plan)
    cleanup = [*pending, *(move["target"] for move in plan["moves"] if is_cleanup_file(move["source"]))]
    if source.is_dir():
        cleanup.extend(str(file) for file in entries(root, source) if is_cleanup_file(file) and str(file) not in moved_sources)
    plan.setdefault("legacy_deleted_pdfs", len(plan.get("deleted", [])))
    plan.update(cleanup="psd_txt", cleanup_files=list(dict.fromkeys(cleanup)) if delete_psd else list(deleted),
                deleted_files=list(deleted), complete=False)
    plan.pop("pdfs", None)
    plan.pop("deleted", None)
    plan.pop("psds", None)
    plan.pop("deleted_psds", None)
    LOGGER.info("organize upgraded automatic cleanup to PSD/TXT; remaining PDFs preserved")
    return plan


async def execute_plan(root: Path, plan, save, on_phase=None, save_progress=None):
    planned, deleted = cleanup_lists(plan)
    deleted_set = set(deleted)
    # Retain both cursors when a resumed job is already in the cleanup phase.
    progress = dict(
        move_cursor=next((i for i, move in enumerate(plan["moves"]) if not move["done"]), len(plan["moves"])),
        cleanup_cursor=next((i for i, name in enumerate(planned) if name not in deleted_set), len(planned)),
        **plan_counts(plan))
    if on_phase:
        on_phase("organize")
    for index, move in enumerate(plan["moves"]):
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
        progress.update(move_cursor=index + 1, moved_files=progress["moved_files"] + 1)
        if save_progress:
            save_progress(progress)
        else:
            save(plan)
        LOGGER.info("organize moved source=%s target=%s", source, target)
        await asyncio.sleep(0)
    if on_phase:
        on_phase("cleanup")
    for index, name in enumerate(planned):
        if name in deleted_set:
            continue
        file = inside(root, str(Path(name).relative_to(root)))
        if not is_cleanup_file(file):
            raise ValueError("清理清单中包含非 PSD/TXT 文件，已停止清理")
        file.unlink(missing_ok=True)
        deleted.append(name)
        deleted_set.add(name)
        counter = "deleted_psds" if file.suffix.lower() == ".psd" else "deleted_txts"
        progress.update(cleanup_cursor=index + 1, cleanup_done=progress["cleanup_done"] + 1)
        progress[counter] += 1
        if save_progress:
            save_progress(progress)
        else:
            save(plan)
        LOGGER.info("organize deleted cleanup file type=%s path=%s", file.suffix.lower(), file)
        await asyncio.sleep(0)
    source = Path(plan["source"])
    directories = reversed(plan["directories"]) if "directories" in plan else (
        directory for directory, _, _ in os.walk(source, topdown=False, followlinks=False))
    for directory in directories:
        folder = Path(directory)
        inside(root, str(folder.relative_to(root)))
        if folder != root and folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
    plan["complete"] = True
    save(plan)
    return dict(moved=len(plan["moves"]), output=str(root), **cleanup_counts(plan))

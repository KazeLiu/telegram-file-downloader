"""Extract into an isolated directory; never delete an archive on an uncertain result."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from .files import collision_safe_path


class ExtractionError(ValueError):
    pass


def seven_zip() -> str | None:
    executable = shutil.which("7zz") or shutil.which("7z")
    if not executable and os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "7-Zip/7z.exe"
        if candidate.is_file():
            executable = str(candidate)
    return executable


def multipart(name: str) -> bool:
    return bool(re.search(r"(?:\.part\d+\.rar|\.r\d\d|\.z\d\d|\.(?:zip|rar|7z)\.\d+)$", name, re.I))


async def _command(executable, *args):
    process = await asyncio.create_subprocess_exec(executable, *args, stdin=asyncio.subprocess.DEVNULL,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        output, _ = await process.communicate()
    except asyncio.CancelledError:
        process.terminate()
        await process.wait()
        raise
    return process.returncode, output.decode("utf-8", errors="replace")


def _validate_listing(listing: str):
    paths = []
    unpacked = 0
    for record in re.split(r"\r?\n\r?\n", listing):
        values = dict(line.split(" = ", 1) for line in record.splitlines() if " = " in line)
        name = values.get("Path")
        if not name:
            continue
        normalized = name.replace("\\", "/")
        win = PureWindowsPath(name)
        if (PurePosixPath(normalized).is_absolute() or win.drive or win.root
                or ".." in normalized.split("/") or ":" in normalized or "\x00" in name):
            raise ExtractionError("压缩包含有越界路径，已保留原包")
        attributes = values.get("Attributes", "")
        if (values.get("Symbolic Link") or values.get("Hard Link")
                or re.search(r"(?:^|\s)[lbcps]", attributes) or "Reparse" in values):
            raise ExtractionError("压缩包含有链接或特殊文件，已保留原包")
        paths.append(normalized)
        unpacked += int(values.get("Size", "0"))
    if not paths:
        raise ExtractionError("无法读取压缩包文件列表，已保留原包")
    return unpacked


async def extract_archive(archive: Path, passwords: list[str]) -> Path:
    executable = seven_zip()
    if not executable:
        raise ExtractionError("未找到 7-Zip；原包已保留。Windows 请安装 7-Zip 后重试")
    if multipart(archive.name):
        raise ExtractionError("分卷压缩包已下载；为避免缺卷误删，请收齐后手动解压")
    # No password is attempted first. Never include subprocess output/arguments in errors: it can contain secrets.
    for password in dict.fromkeys(["", *passwords]):
        code, listing = await _command(executable, "l", "-slt", "-ba", "-sccUTF-8", f"-p{password}", "--", str(archive))
        if code:
            continue
        code, metadata = await _command(executable, "l", "-slt", "-sccUTF-8", f"-p{password}", "--", str(archive))
        if code:
            continue
        if (re.search(r"(?m)^(?:Volume|Multivolume) = \+\r?$", metadata)
                or any(int(value) > 1 for value in re.findall(r"(?m)^Volumes = (\d+)", metadata))):
            raise ExtractionError("检测到分卷压缩包；请收齐后手动解压，原包已保留")
        unpacked = _validate_listing(listing)
        if shutil.disk_usage(archive.parent).free < unpacked:
            raise ExtractionError("解压空间不足，已保留原包")
        staging = Path(tempfile.mkdtemp(prefix=".tg-extract-", dir=archive.parent))
        try:
            code, _ = await _command(executable, "x", "-y", "-aoa", "-sccUTF-8", f"-p{password}",
                                     f"-o{staging}", "--", str(archive))
            if code:
                continue
            for root, directories, files in os.walk(staging, followlinks=False):
                for name in [*directories, *files]:
                    item = Path(root) / name
                    reparse = getattr(item.lstat(), "st_file_attributes", 0) & 0x400
                    if item.is_symlink() or reparse or not item.resolve().is_relative_to(staging.resolve()):
                        raise ExtractionError("解压结果含有不安全链接，已保留原包")
            target = collision_safe_path(archive.parent, archive.stem + "_解压")
            staging.rename(target)
            return target
        finally:
            if staging.exists():
                # staging is a fresh directory created by this function inside archive.parent.
                shutil.rmtree(staging)
    raise ExtractionError("解压失败：密码不匹配、压缩包损坏或缺卷；原包已保留")

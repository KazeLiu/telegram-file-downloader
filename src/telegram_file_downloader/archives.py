"""Extract into an isolated directory; never delete an archive on an uncertain result."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from .files import collision_safe_path


STREAM_EXTENSIONS = frozenset({".gz", ".gzip", ".bz2", ".bzip2", ".xz", ".zst", ".zstd", ".lzma", ".z"})
ARCHIVE_EXTENSIONS = STREAM_EXTENSIONS | frozenset({
    ".zip", ".rar", ".7z", ".tar", ".tgz", ".tbz", ".tbz2", ".txz", ".tzst", ".tlz", ".taz",
    ".cab", ".arj", ".lzh", ".lha",
})
TAR_WRAPPER_SUFFIXES = (
    ".tar.gzip", ".tar.bzip2", ".tar.zstd", ".tar.lzma", ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst", ".tar.z",
    ".tgz", ".tbz", ".tbz2", ".txz", ".tzst", ".tlz", ".taz",
)


class ExtractionError(ValueError):
    pass


class VolumesPending(ExtractionError):
    pass


def volume_info(name: str):
    patterns = [
        (r"^(.+\.7z|.+\.zip)\.(\d+)$", "numeric"),
        (r"^(.+)\.part(\d+)\.rar$", "rar_part"),
        (r"^(.+)\.r(\d\d)$", "rar_old"),
        (r"^(.+)\.z(\d\d)$", "zip_old"),
    ]
    for pattern, scheme in patterns:
        match = re.match(pattern, name, re.I)
        if match:
            base, number = match.groups()
            index = int(number) + (2 if scheme == "rar_old" else 0)
            return dict(base=base, scheme=scheme, index=index, split=True)
    if name.lower().endswith((".rar", ".zip")):
        return dict(base=name[:-4], scheme="rar_old" if name.lower().endswith(".rar") else "zip_old",
                    index=1 if name.lower().endswith(".rar") else 0, split=False)
    return None


def resource_name(name: str):
    volume = volume_info(name)
    if volume and volume["split"]:
        name = volume["base"]
    for suffix in sorted([*TAR_WRAPPER_SUFFIXES, *ARCHIVE_EXTENSIONS], key=len, reverse=True):
        if name.lower().endswith(suffix):
            return name[:-len(suffix)]
    return name


def seven_zip() -> str | None:
    executable = shutil.which("7zz") or shutil.which("7z")
    if not executable and os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "7-Zip/7z.exe"
        if candidate.is_file():
            executable = str(candidate)
    return executable


def multipart(name: str) -> bool:
    stem, _, volume = name.lower().rpartition(".")
    return bool(re.search(r"(?:\.part\d+\.rar|\.r\d\d|\.z\d\d)$", name, re.I)
                or (volume.isdigit() and Path(stem).suffix in ARCHIVE_EXTENSIONS))


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
        if size := values.get("Size"):
            unpacked += int(size)
    if not paths:
        raise ExtractionError("无法读取压缩包文件列表，已保留原包")
    return unpacked


def _validate_extracted(directory: Path):
    resolved = directory.resolve()
    for root, directories, files in os.walk(directory, followlinks=False):
        for name in [*directories, *files]:
            item = Path(root) / name
            reparse = getattr(item.lstat(), "st_file_attributes", 0) & 0x400
            if item.is_symlink() or reparse or not item.resolve().is_relative_to(resolved):
                raise ExtractionError("解压结果含有不安全链接，已保留原包")


async def _expand_tar(executable: str, archive: Path, staging: Path) -> Path:
    code, listing = await _command(executable, "l", "-ttar", "-slt", "-ba", "-sccUTF-8", "--", str(archive))
    if code:
        raise ExtractionError("组合压缩包中的 TAR 无法读取，已保留原包")
    if shutil.disk_usage(staging).free < _validate_listing(listing):
        raise ExtractionError("展开 TAR 的空间不足，已保留原包")
    contents = Path(tempfile.mkdtemp(prefix=".tg-tar-", dir=staging))
    code, _ = await _command(executable, "x", "-ttar", "-y", "-aoa", "-sccUTF-8", f"-o{contents}", "--", str(archive))
    if code:
        raise ExtractionError("组合压缩包中的 TAR 解压失败，已保留原包")
    _validate_extracted(contents)
    return contents


async def extract_archive(archive: Path, passwords: list[str], source_name: str | None = None, allow_volumes=False) -> Path:
    executable = seven_zip()
    if not executable:
        raise ExtractionError("未找到 7-Zip；原包已保留。Windows 请安装 7-Zip 后重试")
    if multipart(archive.name) and not allow_volumes:
        raise ExtractionError("分卷压缩包已下载；为避免缺卷误删，请收齐后手动解压")
    # No password is attempted first. Never include subprocess output/arguments in errors: it can contain secrets.
    missing_volume = False
    for password in dict.fromkeys(["", *passwords]):
        password_args = (f"-p{password}",) if password else ()
        code, listing = await _command(executable, "l", "-slt", "-ba", "-sccUTF-8", *password_args, "--", str(archive))
        if code:
            missing_volume |= bool(re.search(r"missing volume|cannot find|can't find|unexpected end|is not a complete", listing, re.I))
            continue
        code, metadata = await _command(executable, "l", "-slt", "-sccUTF-8", *password_args, "--", str(archive))
        if code:
            missing_volume |= bool(re.search(r"missing volume|cannot find|can't find|unexpected end|is not a complete", metadata, re.I))
            continue
        if not allow_volumes and (re.search(r"(?m)^(?:Volume|Multivolume) = \+\r?$", metadata)
                or any(int(value) > 1 for value in re.findall(r"(?m)^Volumes = (\d+)", metadata))):
            raise ExtractionError("检测到分卷压缩包；请收齐后手动解压，原包已保留")
        unpacked = _validate_listing(listing)
        code, result = await _command(executable, "t", "-sccUTF-8", *password_args, "--", str(archive))
        if code:
            missing_volume |= bool(re.search(r"missing volume|cannot find|can't find|unexpected end|is not a complete", result, re.I))
            continue
        if shutil.disk_usage(archive.parent).free < unpacked:
            raise ExtractionError("解压空间不足，已保留原包")
        staging = Path(tempfile.mkdtemp(prefix=".tg-extract-", dir=archive.parent))
        try:
            code, _ = await _command(executable, "x", "-y", "-aoa", "-sccUTF-8", *password_args,
                                     f"-o{staging}", "--", str(archive))
            if code:
                continue
            _validate_extracted(staging)
            format_name = source_name or archive.name
            wrapper_suffix = next((suffix for suffix in TAR_WRAPPER_SUFFIXES if format_name.lower().endswith(suffix)), None)
            output = staging
            if wrapper_suffix or archive.suffix.lower() in STREAM_EXTENSIONS:
                entries = list(staging.iterdir())
                inner = entries[0] if len(entries) == 1 and entries[0].is_file() else None
                if wrapper_suffix or (inner and inner.suffix.lower() == ".tar"):
                    if inner is None:
                        raise ExtractionError("组合压缩包没有唯一的 TAR 文件，已保留原包")
                    output = await _expand_tar(executable, inner, staging)
            stem = resource_name(format_name)
            target = collision_safe_path(archive.parent, stem)
            output.rename(target)
            return target
        finally:
            if staging.exists():
                # staging is a fresh directory created by this function inside archive.parent.
                shutil.rmtree(staging)
    if allow_volumes and missing_volume:
        raise VolumesPending("等待后续分卷：压缩工具未确认整组完整；已有分卷全部保留")
    raise ExtractionError("解压失败：密码不匹配、压缩包损坏或缺卷；原包已保留")

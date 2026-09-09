from __future__ import annotations

import mimetypes
import re
from pathlib import Path

WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", Path(name).name).rstrip(" .")
    if not cleaned:
        cleaned = "telegram_file"
    if Path(cleaned).stem.upper() in WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def message_filename(message: object) -> str:
    telegram_file = getattr(message, "file", None)
    supplied_name = getattr(telegram_file, "name", None)
    if supplied_name:
        return safe_filename(str(supplied_name))

    extension = getattr(telegram_file, "ext", None)
    if not extension:
        mime_type = getattr(telegram_file, "mime_type", None)
        extension = mimetypes.guess_extension(mime_type or "") or ".bin"
    if not str(extension).startswith("."):
        extension = f".{extension}"
    message_id = getattr(message, "id", "unknown")
    return safe_filename(f"telegram_{message_id}{extension}")


def collision_safe_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    original = directory / safe_filename(filename)
    if not original.exists() and not original.with_name(f"{original.name}.part").exists():
        return original

    stem = original.stem
    suffix = original.suffix
    index = 2
    while True:
        candidate = directory / f"{stem} ({index}){suffix}"
        partial = candidate.with_name(f"{candidate.name}.part")
        if not candidate.exists() and not partial.exists():
            return candidate
        index += 1


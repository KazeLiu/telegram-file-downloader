from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


class ConfigError(ValueError):
    """Raised when local configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    api_id: int
    api_hash: str
    chat: int | str
    download_dir: Path
    wanted_links_file: Path
    data_dir: Path
    allowed_extensions: frozenset[str]

    @property
    def session_path(self) -> Path:
        return self.data_dir / "telegram"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "telegram_file_watcher.log"


def _absolute_path(value: str, field: str) -> Path:
    expanded = Path(os.path.expandvars(value)).expanduser()
    if not expanded.is_absolute():
        raise ConfigError(f"{field} must be an absolute path: {value}")
    return expanded


def _parse_chat(value: str) -> int | str:
    value = value.strip()
    if not value:
        raise ConfigError("TELEGRAM_CHAT is required")
    try:
        return int(value)
    except ValueError:
        return value


def _parse_extensions(value: str | None) -> frozenset[str]:
    if not value or not value.strip():
        raise ConfigError("ALLOWED_EXTENSIONS is required and cannot be empty")

    extensions: set[str] = set()
    for raw_extension in value.split(","):
        extension = raw_extension.strip().lower()
        if not extension:
            raise ConfigError("ALLOWED_EXTENSIONS contains an empty entry")
        if not extension.startswith("."):
            extension = f".{extension}"
        if len(extension) == 1 or any(char in extension for char in "\\/\\:*?\"<>|") or any(char.isspace() for char in extension):
            raise ConfigError(f"Invalid extension in ALLOWED_EXTENSIONS: {raw_extension}")
        extensions.add(extension)
    return frozenset(extensions)


def config_from_mapping(values: Mapping[str, str | None], project_dir: Path) -> AppConfig:
    missing = [
        key
        for key in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_CHAT", "DOWNLOAD_DIR")
        if not values.get(key)
    ]
    if missing:
        raise ConfigError(f"Missing configuration: {', '.join(missing)}")

    try:
        api_id = int(str(values["TELEGRAM_API_ID"]).strip())
    except ValueError as exc:
        raise ConfigError("TELEGRAM_API_ID must be a number") from exc
    if api_id <= 0:
        raise ConfigError("TELEGRAM_API_ID must be greater than zero")

    api_hash = str(values["TELEGRAM_API_HASH"]).strip()
    if api_hash == "replace_with_your_api_hash":
        raise ConfigError("Replace the example TELEGRAM_API_HASH with your real API hash")

    download_dir = _absolute_path(str(values["DOWNLOAD_DIR"]), "DOWNLOAD_DIR")
    wanted_value = values.get("WANTED_LINKS_FILE")
    wanted_file = (
        _absolute_path(str(wanted_value), "WANTED_LINKS_FILE")
        if wanted_value
        else download_dir / "wanted_tracks.txt"
    )

    return AppConfig(
        api_id=api_id,
        api_hash=api_hash,
        chat=_parse_chat(str(values["TELEGRAM_CHAT"])),
        download_dir=download_dir,
        wanted_links_file=wanted_file,
        data_dir=_absolute_path(str(values.get("DATA_DIR") or project_dir / "data"), "DATA_DIR"),
        allowed_extensions=_parse_extensions(values.get("ALLOWED_EXTENSIONS")),
    )


def load_config(project_dir: Path | None = None) -> AppConfig:
    root = (project_dir or Path.cwd()).resolve()
    env_path = root / ".env"
    if not env_path.exists():
        raise ConfigError(f"Configuration file not found: {env_path}")

    file_values = dotenv_values(env_path)
    merged: dict[str, str | None] = {**file_values}
    for key in (
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_CHAT",
        "DOWNLOAD_DIR",
        "DATA_DIR",
        "WANTED_LINKS_FILE",
        "ALLOWED_EXTENSIONS",
    ):
        if key in os.environ:
            merged[key] = os.environ[key]
    return config_from_mapping(merged, root)

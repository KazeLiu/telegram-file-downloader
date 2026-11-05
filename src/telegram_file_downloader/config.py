from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values


PROXY_ENV_KEYS = (
    "TELEGRAM_PROXY_TYPE",
    "TELEGRAM_PROXY_HOST",
    "TELEGRAM_PROXY_PORT",
    "TELEGRAM_PROXY_USERNAME",
    "TELEGRAM_PROXY_PASSWORD",
)


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
    history_start_date: datetime | None = None
    proxy: dict[str, object] | None = None

    @property
    def session_path(self) -> Path:
        return self.data_dir / "telegram"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "telegram_file_downloader.log"


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


def configuration_path(project_dir: Path) -> Path:
    return Path(os.environ.get("ENV_FILE_PATH") or project_dir / ".env")


def proxy_from_mapping(values: Mapping[str, str | None]) -> dict[str, object] | None:
    if not any(values.get(key) for key in PROXY_ENV_KEYS):
        return None

    proxy_type = (values.get("TELEGRAM_PROXY_TYPE") or "socks5").strip().lower()
    host = (values.get("TELEGRAM_PROXY_HOST") or "").strip()
    port_text = (values.get("TELEGRAM_PROXY_PORT") or "").strip()
    if proxy_type not in {"socks5", "http"}:
        raise ConfigError("TELEGRAM_PROXY_TYPE must be socks5 or http")
    if not host or not port_text:
        raise ConfigError("Set both TELEGRAM_PROXY_HOST and TELEGRAM_PROXY_PORT; the proxy will not fall back to a direct connection")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ConfigError("TELEGRAM_PROXY_PORT must be a number") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("TELEGRAM_PROXY_PORT must be between 1 and 65535")

    proxy: dict[str, object] = {"proxy_type": proxy_type, "addr": host, "port": port, "rdns": True}
    if username := values.get("TELEGRAM_PROXY_USERNAME"):
        proxy["username"] = username
    if password := values.get("TELEGRAM_PROXY_PASSWORD"):
        proxy["password"] = password
    return proxy


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

    history_start_date = None
    if value := values.get("HISTORY_START_DATE"):
        try:
            history_start_date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if history_start_date.tzinfo is None:
                history_start_date = history_start_date.replace(tzinfo=timezone.utc)
            history_start_date = history_start_date.astimezone(timezone.utc)
        except ValueError as exc:
            raise ConfigError("HISTORY_START_DATE must be an ISO date or timestamp") from exc
        if history_start_date > datetime.now(timezone.utc):
            raise ConfigError("HISTORY_START_DATE cannot be in the future")

    return AppConfig(
        api_id=api_id,
        api_hash=api_hash,
        chat=_parse_chat(str(values["TELEGRAM_CHAT"])),
        download_dir=download_dir,
        wanted_links_file=wanted_file,
        data_dir=_absolute_path(str(values.get("DATA_DIR") or project_dir / "data"), "DATA_DIR"),
        allowed_extensions=_parse_extensions(values.get("ALLOWED_EXTENSIONS")),
        history_start_date=history_start_date,
        proxy=proxy_from_mapping(values),
    )


def load_config(project_dir: Path | None = None) -> AppConfig:
    root = (project_dir or Path.cwd()).resolve()
    env_path = configuration_path(root)
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
        "HISTORY_START_DATE",
        *PROXY_ENV_KEYS,
    ):
        if key in os.environ:
            merged[key] = os.environ[key]
    return config_from_mapping(merged, root)

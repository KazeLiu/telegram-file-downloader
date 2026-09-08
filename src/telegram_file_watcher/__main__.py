from __future__ import annotations

import logging
import ctypes
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import ConfigError, load_config
from .state import AppState, ConnectionStatus
from .tray import TrayApplication
from .watcher import WatcherController

ERROR_ALREADY_EXISTS = 183
_INSTANCE_MUTEX = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def acquire_single_instance() -> bool:
    """Keep one watcher process per signed-in Windows user."""
    global _INSTANCE_MUTEX
    _INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(
        None,
        False,
        "Local\\TelegramFileWatcher-8C79800E-42D7-4C5B-9A20-FA2CE01982AB",
    )
    return bool(_INSTANCE_MUTEX) and ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def main() -> None:
    if not acquire_single_instance():
        return
    root = project_root()
    state = AppState()
    fallback_log = root / "data" / "telegram_file_watcher.log"
    configure_logging(fallback_log)

    try:
        config = load_config(root)
        config.download_dir.mkdir(parents=True, exist_ok=True)
        controller = WatcherController(config, state)
        download_dir = config.download_dir
    except (ConfigError, OSError) as exc:
        logging.getLogger(__name__).exception("Configuration failed")
        state.set_error(f"Configuration error: {exc}\n\nRun setup.ps1 to configure the watcher.")
        state.set_status(ConnectionStatus.DISCONNECTED)
        controller = None
        download_dir = root

    TrayApplication(state, download_dir, controller).run()


if __name__ == "__main__":
    main()

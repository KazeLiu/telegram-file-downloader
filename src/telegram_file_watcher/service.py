from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from .config import load_config
from .state import AppState
from .watcher import TelegramWatcher


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )


async def run() -> None:
    config = load_config(Path.cwd())
    configure_logging(config.log_path)
    watcher = TelegramWatcher(config, AppState())
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, watcher.request_shutdown)
    await watcher.run()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

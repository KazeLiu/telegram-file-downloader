"""Persistent, bounded logs; no request bodies or credentials."""
from __future__ import annotations

import logging
import re
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path


class RedactedFormatter(logging.Formatter):
    def format(self, record):
        text = super().format(record)
        text = re.sub(r"(https?|socks5)://[^\s/@]+(?::[^\s/@]*)?@", r"\1://[redacted]@", text)
        return re.sub(r"(?i)((?:api_hash|password|token|phone_code_hash)[\s=:'\"]+)[^\s,'\"}]+", r"\1[redacted]", text)


def configure_logs(data_dir):
    directory = data_dir / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not any(getattr(handler, "collector_log", False) for handler in logger.handlers):
        formatter = RedactedFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        file = RotatingFileHandler(directory / "collector.log", maxBytes=5 * 1024 * 1024,
                                   backupCount=5, encoding="utf-8")
        file.collector_log = True
        file.setFormatter(formatter)
        logger.addHandler(file)
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        logger.addHandler(stream)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    # Xiaomi's QR and storage URLs contain access tickets in their query strings.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return directory


def read_log(directory: Path, name="collector.log"):
    if name not in {"collector.log", *(f"collector.log.{i}" for i in range(1, 6))}:
        raise ValueError("无效的日志文件")
    file = directory / name
    if not file.is_file():
        return ""
    with file.open(encoding="utf-8", errors="replace") as handle:
        return "".join(deque(handle, maxlen=500))

"""Routine per-file detail stays in the bounded file, not the Docker console."""
import io
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_file_downloader.diagnostics import configure_logs
from telegram_file_downloader.storage import RecycleBin, restore_batch


class LogLevelsChecks(unittest.TestCase):
    def test_file_detail_console_summary_and_warnings(self):
        root = logging.getLogger()
        handlers, level = root.handlers[:], root.level
        names = ["telethon", "httpx", *("telegram_file_downloader." + name for name in ("storage", "xiaomi_cloud", "xiaomi_batch"))]
        levels = {name: logging.getLogger(name).level for name in names}
        root.handlers = []
        try:
            with tempfile.TemporaryDirectory() as directory, patch("sys.stderr", new_callable=io.StringIO) as console:
                root_dir = Path(directory).resolve()
                logs = configure_logs(root_dir)
                configure_logs(root_dir)
                self.assertEqual(len(root.handlers), 2)
                photo = root_dir / "photo.jpg"
                photo.write_bytes(b"test")
                with RecycleBin(root_dir) as recycle:
                    recycle.move(photo, "a" * 32, "xiaomi_upload")
                restore_batch(root_dir, ["a" * 32])
                logging.getLogger("telegram_file_downloader.xiaomi_batch").info("batch finished moved=1000")
                logging.getLogger("telegram_file_downloader.xiaomi_cloud").warning("connection failed token=secret")
                for handler in root.handlers:
                    handler.flush()
                content = (logs / "collector.log").read_text(encoding="utf-8")
                self.assertIn("recycle moved", content)
                self.assertIn("recycle restored", content)
                self.assertNotIn("recycle moved", console.getvalue())
                self.assertNotIn("recycle restored", console.getvalue())
                for text in (content, console.getvalue()):
                    self.assertIn("recycle restore batch finished restored=1 failed=0", text)
                    self.assertIn("batch finished moved=1000", text)
                    self.assertIn("connection failed", text)
                    self.assertNotIn("secret", text)
                for handler in root.handlers:
                    handler.close()
        finally:
            root.handlers, root.level = handlers, level
            for name, value in levels.items():
                logging.getLogger(name).setLevel(value)

# Telegram History Implementation Plan

**Goal:** Recover files sent during downtime without losing or duplicating tracked downloads.

**Architecture:** SQLite checkpoints in DATA_DIR; ordered history scans share one
download path with durable file intent. Polling also recovers silently missed updates.

**Tech stack:** Python, sqlite3, asyncio, Telethon 1.44, pytest.

- [ ] Add history persistence in `src/telegram_file_downloader/history.py`.
  Persist start date, message checkpoint, completed scan date and download intent.
- [ ] Add HISTORY_START_DATE parsing in `config.py` and `.env.example`.
- [ ] Update `downloader.py` to reuse reserved paths after interruption and
  recognize a completed rename before checkpoint advancement.
- [ ] Update `processor.py` to await downloads and report success; remove the
  startup-time filter. Advance ordered progress only after success or deliberate skip.
- [ ] Replace ephemeral event-only watching in `watcher.py` with ordered scans,
  bounded shutdown, automatic retries, and readable progress logs.
- [ ] Add isolated regression tests under `tests/test_history.py` and
  `tests/test_recovery.py`. Run `.venv/Scripts/python.exe -m pytest -q`.
- [ ] Document recovery, failure behavior, persisted files, migration and rebuild.
  Set this installation's bootstrap date from the existing logs, without changing credentials.
- [ ] Run compile checks and git diff checks. Attempt Docker validation if available.

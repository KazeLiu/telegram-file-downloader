# Telegram History Implementation Plan

**Goal:** Recover files sent during downtime without losing or duplicating tracked downloads.

**Architecture:** SQLite checkpoints in DATA_DIR; ordered history scans share one
download path with durable file intent. Polling also recovers silently missed updates.

**Tech stack:** Python, sqlite3, asyncio, Telethon 1.44, pytest.

- [x] Add history persistence in `src/telegram_file_downloader/history.py`.
  Persist start date, message checkpoint, completed scan date and download intent.
- [x] Add HISTORY_START_DATE parsing in `config.py` and `.env.example`.
- [x] Update `downloader.py` to reuse reserved paths after interruption and
  recognize a completed rename before checkpoint advancement.
- [x] Update `processor.py` to await downloads and report success; remove the
  startup-time filter. Advance ordered progress only after success or deliberate skip.
- [x] Replace ephemeral event-only watching in `watcher.py` with ordered scans,
  bounded shutdown, automatic retries, and readable progress logs.
- [x] Add isolated regression tests under `tests/test_recovery.py` covering both
  persistence and watcher integration. Run `.venv/Scripts/python.exe -m pytest -q`.
- [x] Document recovery, failure behavior, persisted files, migration and rebuild.
  Set this installation's bootstrap date from the existing logs, without changing credentials.
- [x] Run compile checks and git diff checks. Docker Compose configuration validates;
  engine unavailable, so container build and live Telegram recovery are not verified.

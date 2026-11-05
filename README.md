# Telegram File Downloader

[中文部署说明（本地适配版）](README.zh-CN.md) · [Upstream and selection notes](UPSTREAM.md)

This fork publishes `ghcr.io/kazeliu/telegram-file-downloader:latest`. Use
`compose.web.yaml` for the browser-managed console, or `compose.ghcr.yaml` for the legacy CLI. The
original upstream setup below is retained; the Chinese guide covers the fork's
proxy-enabled deployment and Windows-native option.

The web console adds persistent login/settings, proxy configuration, media rules,
download history, progress receipts, and safe ZIP/RAR/7z extraction. See
[the web deployment guide](WEB_GUIDE.zh-CN.md). The original CLI instructions follow.

A Docker service that watches one Telegram channel or group through your own Telegram account and saves files into a folder you choose. It downloads only extensions in your allow-list. The default allow-list is music-focused, but you can use any file extension.

The watcher remembers its progress and catches up on messages sent while Docker or your connection was offline.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine with Docker Compose.
- A Telegram account that belongs to the channel or group to watch.
- Telegram API credentials from [my.telegram.org/apps](https://my.telegram.org/apps). These are **not** bot tokens.

## Setup

1. Copy the example configuration:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edit `.env` with a text editor. Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `HOST_DOWNLOAD_DIR`, and `HOST_DATA_DIR`.

   `HOST_DOWNLOAD_DIR` is the folder where allowed files will be saved. `HOST_DATA_DIR` is a separate, private folder for the Telegram login session, download history, and logs. Both must be absolute host paths.

   Windows example:

   ```dotenv
   HOST_DOWNLOAD_DIR=C:\Users\YourName\Music\Telegram
   HOST_DATA_DIR=C:\Users\YourName\AppData\Local\telegram-file-downloader
   ```

   macOS/Linux example:

   ```dotenv
   HOST_DOWNLOAD_DIR=/Users/your-name/Music/Telegram
   HOST_DATA_DIR=/Users/your-name/.local/share/telegram-file-downloader
   ```

3. Sign in and select the channel or group:

   ```powershell
   docker compose run --rm watcher telegram-file-downloader-configure
   ```

   Enter Telegram's login code and, if enabled, your two-step-verification password. The command lists your available channels and groups, then writes the selected chat ID into `.env`.

4. Start the watcher:

   ```powershell
   docker compose up -d
   ```

## Choose which files to download

Set `ALLOWED_EXTENSIONS` in `.env` to a comma-separated allow-list. Extensions are case-insensitive and may include or omit the leading period. The default list contains common music formats, but you may include **any** extension, such as `.pdf`, `.jpg`, `.mp4`, `.zip`, or a proprietary format.

```dotenv
ALLOWED_EXTENSIONS=.mp3,.flac,.wav,.m4a,.aac,.ogg,.opus,.aiff,.alac
```

For example, to download PDFs, images, videos, and ZIP archives instead:

```dotenv
ALLOWED_EXTENSIONS=pdf,jpg,png,mp4,mkv,zip
```

After changing this setting, recreate the service:

```powershell
docker compose up -d --force-recreate
```

Files with other extensions (and files without extensions) are skipped. Successful downloads retain Telegram filenames, never overwrite existing files, and use a temporary `.part` suffix until complete.

## Daily operation

```powershell
# See service and Telegram logs
docker compose logs -f watcher

# Stop it
docker compose down

# Start it again
docker compose up -d

# Change account or watched chat
docker compose run --rm watcher telegram-file-downloader-configure
docker compose up -d --force-recreate
```

The image exposes no web ports. Your Telegram session, download history, and logs remain only in `HOST_DATA_DIR`; downloads remain only in `HOST_DOWNLOAD_DIR`.

## Telegram proxy

Both interactive sign-in and the watcher support the same optional proxy settings:

```dotenv
TELEGRAM_PROXY_TYPE=socks5
TELEGRAM_PROXY_HOST=host.docker.internal
TELEGRAM_PROXY_PORT=YOUR_ACTUAL_PROXY_PORT
TELEGRAM_PROXY_USERNAME=
TELEGRAM_PROXY_PASSWORD=
```

Supported types are `socks5` and `http`. Use `127.0.0.1` for a proxy on the same
computer when running natively; `host.docker.internal` is for a Docker Desktop
container accessing its host. Set the actual numeric port before running. Leave
all proxy fields empty to retain direct access. Partially configured proxies are
rejected rather than silently bypassed.

The local `compose.local.yaml` profile reads `/config/.env` through
`ENV_FILE_PATH`. It mounts the configuration directory, so the setup command can
atomically save the chosen chat. See the Chinese guide for this profile; the
original `compose.yaml` layout is unchanged.

## Catch-up and download history

Progress is stored in `HOST_DATA_DIR/download_history.sqlite3`, separately for each
Telegram account and chat. Keep this directory when stopping, rebuilding, or
recreating Docker. The watcher reads messages oldest first at startup and checks
for new messages every five seconds. It resumes from saved message IDs, so messages
with the same timestamp are not lost.

On the **first run with tracking**, set an optional recovery date in `.env`:

```dotenv
HISTORY_START_DATE=2026-09-24T13:15:16Z
```

A date alone means midnight UTC. An empty setting starts tracking when first
enabled. Once a checkpoint exists for that account/chat, this setting is ignored;
future restarts resume automatically. An upgrade from the old watcher has no
checkpoint: use the old logs to choose a recovery date. Files downloaded by the old
version have no completion records, so an overlapping initial scan can create
numbered copies, but will never intentionally overwrite existing files. Messages
deleted from Telegram before catch-up are unavailable.

Rebuild and start after updating the code or setting the initial date:

```powershell
docker compose up -d --build
docker compose logs -f watcher
```

Logs show the tracking start date, saved message ID/date, and latest completed scan
time. The checkpoint advances only when a file is safely saved, or a message has no
allowed attachment. If a download fails after three attempts, catch-up pauses at
that message and retries after 30 seconds; later messages cannot conceal the
failure by advancing the checkpoint. Interrupted transfers reuse their reserved
`.part` path on restart. Completed tracked downloads are not downloaded again.

Previously skipped extensions are not replayed when the allow-list changes.
Moving or deleting a downloaded file does not reset its completion record. Run
one watcher per data directory, and retain the same download mount when resuming
an interrupted transfer.

## Security

`.env` contains Telegram credentials and is intentionally ignored by Git. `HOST_DATA_DIR` contains a reusable Telegram login session. Do not commit, share, or upload either of them. Use only Telegram chats you are permitted to access and download from.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

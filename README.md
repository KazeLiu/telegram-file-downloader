# Telegram Music Watcher

A Docker service that watches one Telegram channel or group through your own Telegram account and saves new music files into a folder you choose. It downloads only extensions in your allow-list; the default list is music-focused.

The watcher never scans existing history. It handles only messages received after it starts.

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

   `HOST_DOWNLOAD_DIR` is the folder where music will be saved. `HOST_DATA_DIR` is a separate, private folder for the Telegram login session and logs. Both must be absolute host paths.

   Windows example:

   ```dotenv
   HOST_DOWNLOAD_DIR=C:\Users\YourName\Music\Telegram
   HOST_DATA_DIR=C:\Users\YourName\AppData\Local\telegram-music-watcher
   ```

   macOS/Linux example:

   ```dotenv
   HOST_DOWNLOAD_DIR=/Users/your-name/Music/Telegram
   HOST_DATA_DIR=/Users/your-name/.local/share/telegram-music-watcher
   ```

3. Sign in and select the channel or group:

   ```powershell
   docker compose run --rm watcher telegram-file-watcher-configure
   ```

   Enter Telegram's login code and, if enabled, your two-step-verification password. The command lists your available channels and groups, then writes the selected chat ID into `.env`.

4. Start the watcher:

   ```powershell
   docker compose up -d
   ```

## Choose which files to download

Set `ALLOWED_EXTENSIONS` in `.env` to a comma-separated allow-list. Extensions are case-insensitive and may include or omit the leading period.

```dotenv
ALLOWED_EXTENSIONS=.mp3,.flac,.wav,.m4a,.aac,.ogg,.opus,.aiff,.alac
```

For example, to include a DJ archive too:

```dotenv
ALLOWED_EXTENSIONS=mp3,flac,wav,zip
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
docker compose run --rm watcher telegram-file-watcher-configure
docker compose up -d --force-recreate
```

The image exposes no web ports. Your Telegram session and logs remain only in `HOST_DATA_DIR`; downloads remain only in `HOST_DOWNLOAD_DIR`.

## Security

`.env` contains Telegram credentials and is intentionally ignored by Git. `HOST_DATA_DIR` contains a reusable Telegram login session. Do not commit, share, or upload either of them. Use only Telegram chats you are permitted to access and download from.

## Development

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
docker compose build
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

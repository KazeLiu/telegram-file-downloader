# Docker-First Public Release Design

## Goal

Turn Telegram File Watcher into a public, Docker-first application. A user configures their Telegram credentials, watched Telegram channel or group, host download folder, persistent application-data folder, and an allow-list of attachment extensions through a local `.env` file. The initial default allow-list is music-focused.

## Scope

The release supports Docker Compose on any host that can run Docker. It watches one Telegram group or channel through the user's own Telegram account and downloads only new attachments with allowed file extensions. It is intentionally headless; it does not provide a tray application or web dashboard.

## User workflow

1. Clone the repository and copy `.env.example` to `.env`.
2. Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `HOST_DOWNLOAD_DIR`, `HOST_DATA_DIR`, and, if desired, `ALLOWED_EXTENSIONS` in `.env`.
3. Run `docker compose run --rm configure`.
4. Complete Telegram's interactive sign-in prompts and choose a group or channel from the presented eligible chats. The setup command saves the selected chat ID into `.env`.
5. Start the service with `docker compose up -d`.
6. Change settings by editing `.env`, rerunning the configure command when changing accounts or watched chat, then recreating the service.

## Configuration

The public `.env.example` documents these settings:

- `TELEGRAM_API_ID`: Telegram application API ID; required.
- `TELEGRAM_API_HASH`: Telegram application API hash; required and secret.
- `TELEGRAM_CHAT`: selected Telegram channel or group ID; written by configure and required by the watcher.
- `HOST_DOWNLOAD_DIR`: absolute host directory mounted at `/downloads`; required.
- `HOST_DATA_DIR`: absolute host directory mounted at `/data`; required. It holds the Telegram session and logs.
- `ALLOWED_EXTENSIONS`: comma-separated extension allow-list. Entries may include or omit the leading period and are normalized to lowercase. The default is `.mp3,.flac,.wav,.m4a,.aac,.ogg,.opus,.aiff,.alac`.
- `WANTED_LINKS_FILE`: optional path inside `/downloads`; it defaults to `/downloads/wanted_tracks.txt`.

`.env`, login sessions, logs, downloaded files, and local data directories remain ignored by Git. README explicitly instructs users never to publish their `.env` or Telegram session.

## Docker architecture

`Dockerfile` packages the Python application and its pinned runtime dependencies in a small Python base image. It creates and uses an unprivileged application user.

`compose.yaml` defines one service image with two named bind mounts derived from `.env`:

- `${HOST_DOWNLOAD_DIR}:/downloads`
- `${HOST_DATA_DIR}:/data`

The service passes only container paths to the application (`DOWNLOAD_DIR=/downloads`, `DATA_DIR=/data`). The container does not need a host network port. It uses a restart policy suitable for a long-lived watcher.

The same image exposes two commands: the default watcher command and the interactive `configure` command. The latter receives a TTY and stdin through Docker Compose so Telegram login codes and optional two-factor passwords can be entered locally.

## Application behavior

The configuration layer validates required credentials, chat selection, container download/data paths, and the extension list. Empty allow-lists and invalid extension tokens fail at startup with actionable errors. Docker Compose is responsible for applying the user-supplied absolute host paths as bind mounts.

The setup command lists eligible Telegram groups and channels, accepts a numbered selection, and writes its numeric ID to the user-owned `.env`. Existing saved API values may be reused; API hashes are not echoed.

For each incoming attachment, the processor derives the safe filename using the existing filename rules. It extracts and normalizes the extension. Attachments without an allowed extension are skipped and logged with their filename and extension. Allowed attachments retain existing collision-safe names and `.part` temporary-file behavior. Only messages received after startup are considered. Link capture remains supported and is documented as optional behavior rather than a downloader.

## Errors and recovery

- Missing or invalid `.env` values stop the command with the field name and a correction hint.
- Failed Telegram authorization leaves the service stopped; the README directs users to rerun `docker compose run --rm configure`.
- A disconnected service reports the failure in its mounted log and Docker logs; Docker restarts it according to the compose policy.
- An unavailable or unwritable bind mount causes an explicit startup failure instead of silently writing inside the container.
- Invalid chat selection in configure re-prompts without changing the saved configuration.

## Public repository

The repository includes a clear README with prerequisites, setup, Docker commands, configuration reference, lifecycle commands, log inspection, security guidance, limitations, and development instructions. It adds a standard open-source license selected by the maintainer. GitHub repository publishing itself requires the owner's account and is performed after local checks pass.

## Verification

Unit tests cover extension-list parsing and validation, filtering allowed and disallowed attachment names (including case variations and extensionless files), and existing filename/collision rules. Configuration tests cover the new settings and container paths. The suite continues to cover downloader, link, processor, and state behavior.

Manual release checks build the Docker image, run the configure command with a test account or inspect its interactive startup, and verify the service starts through Compose with mounted folders. README commands are checked against the compose file.

## Out of scope

- Native tray controls or desktop installers.
- A web configuration dashboard.
- Multiple simultaneous watched chats.
- Downloading links from YouTube, Discogs, or any other site.
- Non-music defaults, although users may add any extensions to the allow-list.

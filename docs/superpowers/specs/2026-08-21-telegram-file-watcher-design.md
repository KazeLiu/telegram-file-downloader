# Telegram File Watcher Design

## Purpose

Build a Windows tray application that signs in as the user's Telegram account, watches one selected Telegram group, and downloads files from new messages to a local inbox. The application also records Discogs and YouTube links in a text file for later use.

The application must support large lossless audio files. It must not rename or otherwise process downloaded files because an existing downstream watcher handles that work.

## Scope

The first version will:

- monitor one configured Telegram group;
- process only messages received while the watcher is running;
- download every Telegram attachment that exposes downloadable media;
- preserve the filename supplied by Telegram;
- append Discogs and YouTube links found in message text or captions to a wanted-tracks text file;
- avoid overwriting an existing local file;
- avoid adding the same link to the text file more than once;
- expose connection state and basic controls through a Windows notification-area icon; and
- start automatically when the user signs in to Windows.

It will not download media from Discogs or YouTube, inspect historical Telegram messages, infer artist/track metadata, rename files, organize artist folders, or run as a Windows service.

## Chosen Approach

Use Python and Telethon as a Telegram user client. A user client supports the large files expected here and can observe messages in groups already accessible to the user's account. A standard hosted Telegram bot is not suitable because of its file-download constraints. Automating Telegram Desktop is rejected because it would depend on fragile UI state.

The app will be a single user-level process with a tray interface. When the process is not running, there is no tray icon. While running, the tray menu reports `Connecting`, `Connected`, or `Disconnected`.

## Components

### Configuration

A local `.env` file contains:

- Telegram API ID and API hash;
- target group ID or public username;
- absolute download directory; and
- absolute wanted-links file path.

Secrets and the persistent Telegram session are excluded from Git. An example environment file documents the required fields without real credentials.

### Telegram Client

On first launch, Telethon interactively requests the user's phone number, Telegram verification code, and two-step-verification password when applicable. It stores a local session for later launches.

After authentication, the client resolves the configured group and subscribes to new-message events for that group only. It does not perform an initial history scan.

### File Downloader

For each new message with downloadable media, the downloader:

1. obtains the Telegram-provided filename;
2. chooses a non-conflicting path in the configured inbox;
3. downloads to a temporary partial path;
4. atomically renames the completed partial file to its final name; and
5. records success or failure in the local log.

If the filename already exists, the downloader adds a numeric suffix before the extension, such as `track (2).flac`. Existing files are never overwritten. If Telegram provides no filename, a stable fallback based on the message ID and detected extension is used.

Downloads are processed serially in the first version. This avoids saturating the connection or creating collisions when several large files arrive together.

### Wanted-Link Recorder

Message text and captions are scanned for HTTP or HTTPS links whose host is YouTube, `youtu.be`, or Discogs. Each normalized URL is appended on its own line to the configured text file. Existing entries are loaded into a set so duplicate URLs are not appended again.

A message containing both media and links triggers both behaviors.

### Tray Interface

The tray icon runs in the same process as the Telegram watcher. Its menu includes:

- a disabled status row showing `Connecting`, `Connected`, or `Disconnected`;
- `Open download folder`;
- `Reconnect`;
- `Show latest error` (disabled when no error exists); and
- `Quit`.

Tray commands communicate safely with the asynchronous Telegram loop. Closing a setup or error dialog does not stop the watcher. Choosing `Quit` closes the Telegram connection and exits cleanly.

### Windows Startup and Setup

A setup script creates a project-local Python virtual environment, installs pinned dependencies, creates the user's `.env` from the example when needed, and creates a per-user Startup-folder shortcut or launcher. Administrator access is not required.

The startup launcher uses the virtual environment's windowless Python executable so no console window remains open. A separate development launcher keeps a console visible for first-time authentication and troubleshooting.

## Data Flow

1. Windows sign-in launches the tray application.
2. The app loads and validates configuration, then shows `Connecting`.
3. Telethon restores the saved session and resolves the target group.
4. Successful connection changes the tray status to `Connected`.
5. Each new group message is handed independently to the link recorder and file downloader.
6. Link entries are appended immediately. Attachments are queued and downloaded serially through temporary files.
7. Connection loss changes the status to `Disconnected`; recovery changes it back to `Connected`.

## Error Handling and Recovery

- Invalid or missing configuration produces a clear local error and keeps the tray application available for inspection.
- Network and Telegram disconnections are logged and retried automatically with bounded backoff.
- An individual failed download does not stop later messages. It is retried a limited number of times and leaves no completed-looking output file.
- Partial files remain identifiable by a temporary suffix and may be retried or cleaned safely on a later run.
- Permission and disk-space failures are recorded as the latest tray-visible error.
- A small rotating log prevents unbounded log growth.
- The app does not claim to be active when its Telegram client is disconnected.

## Security and Privacy

- Telegram credentials, verification codes, two-step-verification passwords, and session data remain on the local PC.
- Secrets and session files are covered by `.gitignore`.
- The app sends no data to services other than Telegram and does not open or fetch posted Discogs/YouTube URLs.
- Log messages avoid credentials and authentication tokens.

## Verification

Automated tests will cover:

- Discogs and YouTube URL detection;
- rejection of unrelated URLs;
- duplicate-link suppression;
- collision-safe destination naming;
- fallback names for unnamed media;
- configuration validation; and
- processing a message containing both a link and an attachment.

Manual acceptance checks will verify:

1. first-run Telegram authentication succeeds;
2. the configured group is resolved correctly;
3. a newly posted large file downloads under its original name;
4. an existing same-named file is not overwritten;
5. Discogs and YouTube links are appended without media download;
6. old group messages are not processed;
7. the tray status reflects connection loss and recovery;
8. tray menu actions work; and
9. the watcher starts automatically after the next Windows sign-in.

## Success Criteria

The feature is complete when the installed tray app reliably starts at Windows sign-in, reports its Telegram connection state, downloads every new attachment from the configured group without overwriting existing files, and records unique Discogs/YouTube links in the configured text file.

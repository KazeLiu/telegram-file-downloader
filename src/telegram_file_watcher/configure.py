from __future__ import annotations

import asyncio
import getpass
import os
from pathlib import Path

from dotenv import dotenv_values, set_key
from telethon import TelegramClient


def project_root() -> Path:
    return Path.cwd()


def prompt(current: str | None, label: str, secret: bool = False) -> str:
    suffix = " [saved]" if current and secret else (f" [{current}]" if current else "")
    reader = getpass.getpass if secret else input
    while True:
        value = reader(f"{label}{suffix}: ").strip()
        if value:
            return value
        if current:
            return current
        print("A value is required.")


async def configure() -> None:
    root = project_root()
    env_path = root / ".env"
    existing = dotenv_values(env_path) if env_path.exists() else {}

    print("\nTelegram File Watcher setup")
    print("Create Telegram API credentials at https://my.telegram.org/apps before continuing.\n")
    api_id_text = prompt(existing.get("TELEGRAM_API_ID"), "Telegram API ID")
    try:
        api_id = int(api_id_text)
    except ValueError as exc:
        raise SystemExit("Telegram API ID must be a number.") from exc
    api_hash = prompt(existing.get("TELEGRAM_API_HASH"), "Telegram API hash", secret=True)

    data_dir = Path(os.environ.get("DATA_DIR", root / "data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(data_dir / "telegram"), api_id, api_hash)

    print("\nSigning in to Telegram. Codes and passwords remain on this PC.")
    await client.start()
    try:
        dialogs = [
            dialog
            async for dialog in client.iter_dialogs()
            if dialog.is_group or dialog.is_channel
        ]
        if not dialogs:
            raise SystemExit("No Telegram groups or channels were found for this account.")

        print("\nChoose the channel or group to watch:")
        for index, dialog in enumerate(dialogs, start=1):
            kind = "channel" if dialog.is_channel and not dialog.is_group else "group"
            print(f"  {index:>3}. {dialog.name} [{kind}]  (ID: {dialog.id})")

        while True:
            selection = input("Group number: ").strip()
            try:
                chosen = dialogs[int(selection) - 1]
                break
            except (ValueError, IndexError):
                print("Enter one of the group numbers shown above.")

        env_path.touch(exist_ok=True)
        set_key(env_path, "TELEGRAM_API_ID", str(api_id), quote_mode="never")
        set_key(env_path, "TELEGRAM_API_HASH", api_hash, quote_mode="never")
        set_key(env_path, "TELEGRAM_CHAT", str(chosen.id), quote_mode="never")

        print(f"\nConfigured chat: {chosen.name}")
        if os.environ.get("IN_DOCKER") == "true":
            print("Download and data folders are configured with HOST_DOWNLOAD_DIR and HOST_DATA_DIR in .env.")
        else:
            default_download = existing.get("DOWNLOAD_DIR") or str(Path.home() / "Downloads" / "Telegram Inbox")
            download_dir = Path(prompt(default_download, "Download folder")).expanduser().resolve()
            default_links = existing.get("WANTED_LINKS_FILE") or str(download_dir / "wanted_tracks.txt")
            wanted_file = Path(prompt(default_links, "Wanted-links text file")).expanduser().resolve()
            set_key(env_path, "DOWNLOAD_DIR", str(download_dir), quote_mode="auto")
            set_key(env_path, "WANTED_LINKS_FILE", str(wanted_file), quote_mode="auto")
            download_dir.mkdir(parents=True, exist_ok=True)
            wanted_file.parent.mkdir(parents=True, exist_ok=True)
            print(f"Downloads: {download_dir}")
            print(f"Wanted links: {wanted_file}")
    finally:
        await client.disconnect()


def main() -> None:
    asyncio.run(configure())


if __name__ == "__main__":
    main()

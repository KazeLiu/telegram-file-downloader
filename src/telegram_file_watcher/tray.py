from __future__ import annotations

import ctypes
import os
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from .state import AppState, ConnectionStatus
from .watcher import WatcherController


def create_status_icon(status: ConnectionStatus) -> Image.Image:
    colors = {
        ConnectionStatus.CONNECTED: "#22a447",
        ConnectionStatus.CONNECTING: "#e0a318",
        ConnectionStatus.DISCONNECTED: "#c83d3d",
    }
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((5, 5, 59, 59), fill=colors[status], outline="white", width=4)
    draw.polygon(((25, 19), (49, 32), (25, 45)), fill="white")
    return image


def show_message(title: str, message: str, error: bool = False) -> None:
    flags = 0x10 if error else 0x40
    ctypes.windll.user32.MessageBoxW(None, message, title, flags)


class TrayApplication:
    def __init__(
        self,
        state: AppState,
        download_dir: Path,
        controller: WatcherController | None,
    ) -> None:
        self.state = state
        self.download_dir = download_dir
        self.controller = controller
        self.icon = pystray.Icon(
            "telegram-file-watcher",
            create_status_icon(state.status),
            "Telegram File Watcher",
            menu=pystray.Menu(
                pystray.MenuItem(self._status_text, None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open download folder", self._open_folder),
                pystray.MenuItem("Reconnect", self._reconnect, enabled=lambda item: self.controller is not None),
                pystray.MenuItem("Show latest error", self._show_error, enabled=self._has_error),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ),
        )
        self.state.set_listener(self._state_changed)

    def _status_text(self, _item) -> str:
        return f"Status: {self.state.status.value}"

    def _has_error(self, _item) -> bool:
        return self.state.latest_error is not None

    def _state_changed(self) -> None:
        self.icon.icon = create_status_icon(self.state.status)
        self.icon.title = f"Telegram File Watcher — {self.state.status.value}"
        self.icon.update_menu()

    def _open_folder(self, _icon, _item) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.download_dir)

    def _reconnect(self, _icon, _item) -> None:
        if self.controller:
            self.state.set_status(ConnectionStatus.CONNECTING)
            self.controller.reconnect()

    def _show_error(self, _icon, _item) -> None:
        message = self.state.latest_error or "No error has been recorded."
        threading.Thread(
            target=show_message,
            args=("Telegram File Watcher", message, True),
            daemon=True,
        ).start()

    def _quit(self, icon, _item) -> None:
        if self.controller:
            self.controller.stop()
        icon.stop()

    def run(self) -> None:
        if self.controller:
            self.controller.start()
        self.icon.run()


from __future__ import annotations

import threading
from enum import Enum
from typing import Callable


class ConnectionStatus(str, Enum):
    CONNECTING = "Connecting"
    CONNECTED = "Connected"
    DISCONNECTED = "Disconnected"


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = ConnectionStatus.CONNECTING
        self._latest_error: str | None = None
        self._listener: Callable[[], None] | None = None

    @property
    def status(self) -> ConnectionStatus:
        with self._lock:
            return self._status

    @property
    def latest_error(self) -> str | None:
        with self._lock:
            return self._latest_error

    def set_listener(self, listener: Callable[[], None]) -> None:
        with self._lock:
            self._listener = listener

    def set_status(self, status: ConnectionStatus) -> None:
        with self._lock:
            changed = status != self._status
            self._status = status
            listener = self._listener
        if changed and listener:
            listener()

    def set_error(self, message: str) -> None:
        with self._lock:
            self._latest_error = message
            listener = self._listener
        if listener:
            listener()

    def clear_error(self) -> None:
        with self._lock:
            changed = self._latest_error is not None
            self._latest_error = None
            listener = self._listener
        if changed and listener:
            listener()


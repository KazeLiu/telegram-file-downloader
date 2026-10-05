from __future__ import annotations

import re
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

URL_PATTERN = re.compile(r"https?://[^\s<>\[\]{}\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?)]}"


def _supported_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    return (
        host == "youtu.be"
        or host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "discogs.com"
        or host.endswith(".discogs.com")
    )


def normalize_supported_url(raw_url: str) -> str | None:
    candidate = raw_url.rstrip(TRAILING_PUNCTUATION)
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if not _supported_host(parsed.hostname):
        return None

    hostname = parsed.hostname.lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError:
        return None
    netloc = hostname
    if port and not ((parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)):
        netloc = f"{hostname}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def extract_supported_links(text: str | None) -> list[str]:
    if not text:
        return []
    links: list[str] = []
    seen: set[str] = set()
    for match in URL_PATTERN.finditer(text):
        normalized = normalize_supported_url(match.group(0))
        if normalized and normalized not in seen:
            seen.add(normalized)
            links.append(normalized)
    return links


class LinkRecorder:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._known: set[str] | None = None

    def _load(self) -> set[str]:
        if self._known is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self._known = {
                    line.strip()
                    for line in self.path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                }
            else:
                self._known = set()
        return self._known

    def append_from_text(self, text: str | None) -> list[str]:
        added: list[str] = []
        with self._lock:
            known = self._load()
            for link in extract_supported_links(text):
                if link not in known:
                    added.append(link)
            if added:
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    for link in added:
                        handle.write(f"{link}\n")
                known.update(added)
        return added

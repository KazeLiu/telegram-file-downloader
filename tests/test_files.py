from pathlib import Path
from types import SimpleNamespace

from telegram_file_watcher.files import collision_safe_path, message_filename, safe_filename


def test_preserves_normal_filename() -> None:
    message = SimpleNamespace(id=42, file=SimpleNamespace(name="Artist - Track.flac", ext=".flac"))
    assert message_filename(message) == "Artist - Track.flac"


def test_fallback_filename_uses_message_id_and_extension() -> None:
    message = SimpleNamespace(id=42, file=SimpleNamespace(name=None, ext=".ogg", mime_type="audio/ogg"))
    assert message_filename(message) == "telegram_42.ogg"


def test_safe_filename_removes_windows_path_characters() -> None:
    assert safe_filename('bad<name>:track?.flac') == "bad_name__track_.flac"
    assert safe_filename("CON.txt") == "_CON.txt"


def test_collision_adds_number_without_overwriting(tmp_path: Path) -> None:
    (tmp_path / "track.flac").write_bytes(b"existing")
    (tmp_path / "track (2).flac.part").write_bytes(b"partial")

    assert collision_safe_path(tmp_path, "track.flac") == tmp_path / "track (3).flac"


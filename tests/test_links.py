from pathlib import Path

from telegram_file_watcher.links import LinkRecorder, extract_supported_links


def test_extracts_discogs_and_youtube_links_only() -> None:
    text = (
        "Wanted: https://www.discogs.com/release/123-Test, "
        "https://youtu.be/abc123?t=4 and https://example.com/nope"
    )

    assert extract_supported_links(text) == [
        "https://www.discogs.com/release/123-Test",
        "https://youtu.be/abc123?t=4",
    ]


def test_normalizes_host_and_removes_fragment() -> None:
    assert extract_supported_links("HTTPS://YOUTUBE.COM/watch?v=abc#music") == [
        "https://youtube.com/watch?v=abc"
    ]


def test_rejects_invalid_port_without_crashing() -> None:
    assert extract_supported_links("https://youtube.com:not-a-port/watch?v=abc") == []


def test_recorder_does_not_append_duplicates(tmp_path: Path) -> None:
    output = tmp_path / "wanted.txt"
    recorder = LinkRecorder(output)

    assert recorder.append_from_text("https://youtu.be/abc") == ["https://youtu.be/abc"]
    assert recorder.append_from_text("again https://youtu.be/abc") == []
    assert output.read_text(encoding="utf-8").splitlines() == ["https://youtu.be/abc"]

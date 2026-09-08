from pathlib import Path

import pytest

from telegram_file_watcher.config import ConfigError, config_from_mapping


def valid_values(tmp_path: Path) -> dict[str, str]:
    return {
        "TELEGRAM_API_ID": "1234",
        "TELEGRAM_API_HASH": "real_hash",
        "TELEGRAM_CHAT": "-1001234567890",
        "DOWNLOAD_DIR": str(tmp_path / "downloads"),
        "DATA_DIR": str(tmp_path / "data"),
        "ALLOWED_EXTENSIONS": ".mp3,flac",
        "WANTED_LINKS_FILE": str(tmp_path / "wanted.txt"),
    }


def test_loads_valid_configuration(tmp_path: Path) -> None:
    config = config_from_mapping(valid_values(tmp_path), tmp_path)
    assert config.api_id == 1234
    assert config.chat == -1001234567890
    assert config.download_dir == tmp_path / "downloads"
    assert config.allowed_extensions == frozenset({".mp3", ".flac"})


def test_wanted_file_defaults_inside_download_folder(tmp_path: Path) -> None:
    values = valid_values(tmp_path)
    del values["WANTED_LINKS_FILE"]
    config = config_from_mapping(values, tmp_path)
    assert config.wanted_links_file == tmp_path / "downloads" / "wanted_tracks.txt"


def test_reports_missing_values(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="TELEGRAM_CHAT"):
        config_from_mapping({"TELEGRAM_API_ID": "1", "TELEGRAM_API_HASH": "hash"}, tmp_path)


def test_rejects_invalid_extension_list(tmp_path: Path) -> None:
    values = valid_values(tmp_path)
    values["ALLOWED_EXTENSIONS"] = ".mp3,,.flac"
    with pytest.raises(ConfigError, match="empty entry"):
        config_from_mapping(values, tmp_path)

from __future__ import annotations

import pytest

from cyber_recall.config import Config


def test_load_valid_config(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[paths]
notes_dir = "notes"
database_path = "data/cyber-recall.db"

[study]
daily_new_limit = 15

[llm]
enabled = true
base_url = "http://localhost:11434"
model = "qwen2.5"
api_key = ""
""",
        encoding="utf-8",
    )
    root = config_path.resolve().parent
    config = Config.load(config_path)
    assert config.notes_dir == root / "notes"
    assert config.database_path == root / "data" / "cyber-recall.db"
    assert config.study.daily_new_limit == 15
    assert config.llm.enabled is True
    assert config.llm.model == "qwen2.5"


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Config.load(tmp_path / "does-not-exist.toml")


def test_partial_config_uses_defaults(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[paths]\nnotes_dir = "notes"\n', encoding="utf-8")
    config = Config.load(config_path)
    assert config.database_path.name == "cyber-recall.db"
    assert config.study.daily_new_limit == 20
    assert config.llm.enabled is False

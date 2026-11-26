from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_FILENAME = "config.toml"


@dataclass(frozen=True)
class StudyConfig:
    daily_new_limit: int = 20


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool = False
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1"
    api_key: str = ""


@dataclass(frozen=True)
class Config:
    notes_dir: Path
    database_path: Path
    study: StudyConfig
    llm: LLMConfig

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG_FILENAME) -> Config:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with config_path.open("rb") as fh:
            raw = tomllib.load(fh)

        # Relative paths are resolved against the config file's directory.
        root = config_path.resolve().parent

        paths = raw.get("paths", {})
        notes_dir = Path(paths.get("notes_dir", "notes"))
        database_path = Path(paths.get("database_path", "data/cyber-recall.db"))

        study = StudyConfig(**raw.get("study", {}))
        llm = LLMConfig(**raw.get("llm", {}))

        return cls(
            notes_dir=root / notes_dir,
            database_path=root / database_path,
            study=study,
            llm=llm,
        )

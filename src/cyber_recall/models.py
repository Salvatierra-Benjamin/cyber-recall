from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CardType(str, Enum):
    GLOSSARY = "glossary"
    RECALL = "recall"


class Direction(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"


class ReviewMode(str, Enum):
    FLASHCARD = "flashcard"
    QUIZ = "quiz"
    MATCHING = "matching"
    LLM = "llm"


@dataclass(slots=True)
class Card:
    id: str
    deck: str
    source_file: str
    card_type: str
    module: str
    unit: str
    front: str
    back: str
    archived: bool = False
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class CardState:
    card_id: str
    direction: str = Direction.FORWARD.value
    repetitions: int = 0
    interval_days: int = 0
    ease_factor: float = 2.5
    lapses: int = 0
    due_at: str = ""
    last_reviewed_at: str | None = None


@dataclass(slots=True)
class ReviewLog:
    card_id: str
    direction: str
    mode: str
    rating: int
    reviewed_at: str
    elapsed_ms: int | None = None
    id: int | None = None


@dataclass(slots=True)
class StudyFilter:
    deck: str | None = None
    module: str | None = None
    unit: str | None = None
    card_type: str | None = None
    direction: str | None = None

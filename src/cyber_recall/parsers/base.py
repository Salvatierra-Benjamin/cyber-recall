from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# Markdown construct patterns used to reduce formatted text to plain text.
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_INLINE_CODE = re.compile(r"`([^`]*)`")

# Words kept lowercase in the middle of a title-cased module name.
_SMALL_WORDS = frozenset(
    {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
)


def strip_markdown(text: str) -> str:
    """Reduce Markdown formatting to plain text (links, code spans, bold, italics)."""
    t = text
    t = _IMAGE.sub(r"\1", t)
    t = _LINK.sub(r"\1", t)
    t = _INLINE_CODE.sub(r"\1", t)
    t = t.replace("**", "")
    t = t.replace("*", "")
    t = t.replace("_", " ")
    return t


def normalize(text: str) -> str:
    """Return a canonical, case-insensitive, whitespace-collapsed form used for IDs."""
    t = strip_markdown(text)
    t = t.lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def clean_bold(text: str) -> str:
    """Remove a single outer pair of ``**`` markers, preserving inner formatting."""
    t = text.strip()
    if t.startswith("**") and t.endswith("**") and len(t) >= 4:
        return t[2:-2]
    return t


def make_card_id(deck: str, card_type: str, module: str, unit: str, front: str) -> str:
    """Deterministic card id: first 16 hex chars of a sha256 composite key.

    The key deliberately includes deck, card type, module and unit so that terms
    repeated across different contexts (e.g. ``TTL``, ``CIA Triad``, ``DMZ``) never
    collide, per the SM-2 plan.
    """
    raw = "|".join((deck, card_type, normalize(module), normalize(unit), normalize(front)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def derive_deck(h1_title: str) -> str:
    """Derive a deck name from an H1 title such as ``PreSecurity — TryHackMe Glossary``."""
    title = strip_markdown(h1_title).strip()
    for sep in (" — ", " – ", " - "):
        if sep in title:
            head = title.split(sep, 1)[0].strip()
            if head:
                return head
    for suffix in (" Glossary", " glossary", " (Unified Notes)", " (Unified notes)"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title


def _title_case(text: str) -> str:
    words = text.split()
    out: list[str] = []
    for idx, word in enumerate(words):
        lower = word.lower()
        if idx != 0 and lower in _SMALL_WORDS:
            out.append(lower)
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return " ".join(out)


def canonicalize_module(name: str) -> str:
    """Normalize a module name to a single canonical form shared by every source.

    The glossary uses ``Module 2 — Computer Fundamentals`` (em-dash + Title Case)
    while the unified notes use ``Module 2 - Computer fundamentals`` (hyphen +
    lowercase). Without this, the same module would be stored under two different
    names, breaking exact-match filters and the card-id hash.
    """
    name = re.sub(r"\s*[—–]\s*", " - ", name)  # em/en dash -> hyphen
    name = re.sub(r"\s+", " ", name).strip()
    return _title_case(name)


@dataclass(slots=True)
class ParsedCard:
    """A card extracted from a Markdown source, before it is persisted to SQLite."""

    deck: str
    source_file: str
    card_type: str
    module: str
    unit: str
    front: str
    back: str
    front_clean: str

    @property
    def id(self) -> str:
        return make_card_id(self.deck, self.card_type, self.module, self.unit, self.front)


@dataclass(slots=True)
class ParseResult:
    """Result of parsing a single Markdown file."""

    cards: list[ParsedCard] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    deck: str = ""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from cyber_recall.db.repository import Repository, utc_now_iso
from cyber_recall.models import Card
from cyber_recall.parsers.base import ParsedCard
from cyber_recall.parsers.glossary import parse_glossary
from cyber_recall.parsers.unified import parse_unified

_GLOSSARY_MARKER = re.compile(
    r"\|\s*Term\s*\|\s*Unit\s*\|\s*Definition\s*\|", re.IGNORECASE
)
_ACTIVE_RECALL_MARKER = re.compile(r"active recall", re.IGNORECASE)


def detect_file_type(text: str, filename: str = "") -> str:
    """Classify a Markdown file as 'glossary', 'unified', or 'unknown'."""
    if _GLOSSARY_MARKER.search(text):
        return "glossary"
    if _ACTIVE_RECALL_MARKER.search(text):
        return "unified"
    lower = filename.lower()
    if "glossary" in lower:
        return "glossary"
    if "unified" in lower:
        return "unified"
    return "unknown"


@dataclass(slots=True)
class SyncReport:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    archived: int = 0
    total_cards: int = 0
    warnings: list[str] = field(default_factory=list)
    cards_by_module: dict[str, int] = field(default_factory=dict)
    cards_by_type: dict[str, int] = field(default_factory=dict)


def _to_card(parsed: ParsedCard) -> Card:
    now = utc_now_iso()
    return Card(
        id=parsed.id,
        deck=parsed.deck,
        source_file=parsed.source_file,
        card_type=parsed.card_type,
        module=parsed.module,
        unit=parsed.unit,
        front=parsed.front,
        back=parsed.back,
        archived=False,
        created_at=now,
        updated_at=now,
    )


def _content_changed(existing: Card, incoming: Card) -> bool:
    return (
        existing.deck != incoming.deck
        or existing.source_file != incoming.source_file
        or existing.card_type != incoming.card_type
        or existing.module != incoming.module
        or existing.unit != incoming.unit
        or existing.front != incoming.front
        or existing.back != incoming.back
        or existing.archived != incoming.archived
    )


def sync_notes(notes_dir: str | Path, repo: Repository) -> SyncReport:
    """Recursively parse Markdown notes under ``notes_dir`` and sync them into SQLite.

    Returns a report of added/updated/unchanged/archived cards plus any warnings.
    """
    notes_dir = Path(notes_dir)
    report = SyncReport()

    if not notes_dir.exists():
        report.warnings.append(f"Notes directory not found: {notes_dir}")
        return report

    root = notes_dir.parent
    parsed_cards: list[ParsedCard] = []

    for path in sorted(notes_dir.rglob("*.md")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            report.warnings.append(f"Failed to read {rel}: {exc}")
            continue

        file_type = detect_file_type(text, path.name)
        if file_type == "glossary":
            result = parse_glossary(text, rel)
        elif file_type == "unified":
            result = parse_unified(text, rel)
        else:
            report.warnings.append(f"Skipped unrecognized file: {rel}")
            continue

        report.warnings.extend(result.warnings)
        parsed_cards.extend(result.cards)

    now = utc_now_iso()
    seen_ids: set[str] = set()

    for parsed in parsed_cards:
        card = _to_card(parsed)
        seen_ids.add(card.id)
        existing = repo.get_card(card.id)
        if existing is None:
            repo.upsert_card(card, now)
            report.added += 1
        elif _content_changed(existing, card):
            repo.upsert_card(card, now)
            report.updated += 1
        else:
            report.unchanged += 1

    # Soft-archive any active card that no longer appears in the parsed set,
    # including cards whose whole source file was deleted from notes/.
    for existing in repo.list_cards():
        if existing.id not in seen_ids:
            repo.set_archived(existing.id, True, now)
            report.archived += 1

    report.total_cards = repo.count_cards()
    for parsed in parsed_cards:
        report.cards_by_module[parsed.module] = report.cards_by_module.get(parsed.module, 0) + 1
        report.cards_by_type[parsed.card_type] = report.cards_by_type.get(parsed.card_type, 0) + 1

    return report

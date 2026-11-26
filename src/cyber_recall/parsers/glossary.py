from __future__ import annotations

import re

from cyber_recall.parsers.base import (
    ParseResult,
    ParsedCard,
    canonicalize_module,
    clean_bold,
    derive_deck,
)

_H1 = re.compile(r"^#\s+(.*)$")
_H2 = re.compile(r"^##\s+(.*)$")
_TABLE_HEADER = re.compile(
    r"^\s*\|.*Term.*\|.*Unit.*\|.*Definition.*\|\s*$", re.IGNORECASE
)
_HORIZONTAL_RULE = re.compile(r"^---+\s*$")

_SEPARATOR_CELL = re.compile(r":?-{3,}:?")


def _split_row(line: str) -> list[str]:
    """Split a pipe-table row into cells, dropping the empty edge cells from the syntax."""
    return [part.strip() for part in line.split("|") if part.strip() != ""]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL.fullmatch(c) for c in cells)


def parse_glossary(text: str, source_file: str) -> ParseResult:
    """Parse a glossary Markdown file (H2 modules + ``Term | Unit | Definition`` tables).

    Term cells may contain inline Markdown (``**term**``, `` `code` ``). The outer
    ``**`` is kept in ``front`` (raw) and stripped for ``front_clean``.
    """
    cards: list[ParsedCard] = []
    warnings: list[str] = []
    deck = ""
    module = ""
    in_table = False

    for line_no, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()

        m = _H1.match(line)
        if m:
            deck = derive_deck(m.group(1))
            in_table = False
            continue

        m = _H2.match(line)
        if m:
            module = canonicalize_module(m.group(1).strip())
            in_table = False
            continue

        if _TABLE_HEADER.match(line):
            in_table = True
            continue

        if in_table:
            # A blank line, horizontal rule, or any heading closes the current table.
            if not stripped or _HORIZONTAL_RULE.match(stripped) or stripped.startswith("#"):
                in_table = False
                continue

            cells = _split_row(line)
            if _is_separator_row(cells):
                continue

            if len(cells) < 3:
                warnings.append(
                    f"{source_file}:{line_no}: skipped malformed glossary row: {stripped!r}"
                )
                continue

            term = cells[0]
            unit = cells[1]
            definition = " ".join(cells[2:]).strip()

            if not term or not definition:
                warnings.append(
                    f"{source_file}:{line_no}: skipped row with empty term or definition"
                )
                continue

            cards.append(
                ParsedCard(
                    deck=deck,
                    source_file=source_file,
                    card_type="glossary",
                    module=module,
                    unit=unit,
                    front=term,
                    back=definition,
                    front_clean=clean_bold(term),
                )
            )

    return ParseResult(cards=cards, warnings=warnings, deck=deck)

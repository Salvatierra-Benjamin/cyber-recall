from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

from cyber_recall.parsers.base import (
    ParseResult,
    ParsedCard,
    canonicalize_module,
    clean_bold,
    derive_deck,
)

_H1 = re.compile(r"^#\s+(.*)$")
_H2 = re.compile(r"^##\s+(.*)$")
_H3 = re.compile(r"^###\s+(.*)$")

# An Active Recall section is introduced by an H4/H5 heading whose text contains
# "active recall" (case-insensitive).
_ACTIVE_RECALL_HEADER = re.compile(r"^(#{4,5})\s+.*active recall.*$", re.IGNORECASE)
_HORIZONTAL_RULE = re.compile(r"^---+\s*$")
_TOC = re.compile(r"^table of contents$", re.IGNORECASE)

# Question markers.
_NUMBERED_Q = re.compile(r"^\s*(\d+)\.\s+\*\*(.+?)\*\*\s*$")
_BOLD_PARAGRAPH = re.compile(r"^\*\*(.+?)\*\*(.*)$")
_BULLET_Q = re.compile(r"^\s*-\s+\*\*(.+?)\*\*\s*(.*)$")
_H5_Q = re.compile(r"^#{5}\s+(.*)$")

# Answer markers.
_BULLET_ANSWER = re.compile(r"^\s*-\s*\*+\s*Answer\s*:\*+\s*(.*)$", re.IGNORECASE)
_BOLD_ANSWER = re.compile(r"^\*\*Answer\s*:\*\*\s*(.*)$", re.IGNORECASE)
_BLOCKQUOTE = re.compile(r"^>\s?(.*)$")
_BLOCKQUOTE_ANSWER_PREFIX = re.compile(r"^\*\*Answer\s*:\*\*\s*", re.IGNORECASE)

# Question numbering / label cleanup.
_QNUM = re.compile(r"^\d+(?:\.\d+)*[.):]?\s+")
_QLABEL = re.compile(r"^(?:Question|Q)\s*:\s*", re.IGNORECASE)


@dataclass(slots=True)
class _Q:
    text: str
    inline_answer: str | None


def _strip_question_number(q: str) -> str:
    q = q.strip()
    q = _QNUM.sub("", q, count=1).strip()
    q = _QLABEL.sub("", q, count=1).strip()
    return q


def _match_question(line: str) -> _Q | None:
    """Return a question match for a line, or None if the line is not a question."""
    # Variant E: per-question H5 heading.
    m = _H5_Q.match(line)
    if m:
        return _Q(_strip_question_number(clean_bold(m.group(1))), None)

    # Variant A: numbered list with a fully-bold question.
    m = _NUMBERED_Q.match(line)
    if m:
        return _Q(_strip_question_number(clean_bold(m.group(2))), None)

    # Variant D: bullet with "**N.N. Question:** ..." label.
    m = _BULLET_Q.match(line)
    if m:
        bold = m.group(1).strip()
        rest = m.group(2).strip()
        if re.match(r"^\d", bold):
            combined = (bold + " " + rest).strip() if rest else bold
            return _Q(_strip_question_number(combined), None)

    # Variant B/C: bold paragraph question (possibly with a same-line answer).
    m = _BOLD_PARAGRAPH.match(line)
    if m:
        bold = m.group(1).strip()
        rest = m.group(2).strip()
        # A line that is exactly "**Answer:**" is an answer, never a question.
        if re.match(r"^Answer\s*:\s*$", bold, re.IGNORECASE):
            return None
        # Same-line "Answer:" label glued to the bold question.
        if re.search(r"\bAnswer\s*:\s*$", bold, re.IGNORECASE):
            q = re.sub(r"\bAnswer\s*:\s*$", "", bold, flags=re.IGNORECASE).strip()
            return _Q(_strip_question_number(q), rest or None)
        if rest:
            # Same-line answer without a label (e.g. inline code).
            return _Q(_strip_question_number(clean_bold(bold)), rest)
        return _Q(_strip_question_number(clean_bold(bold)), None)

    return None


def _join_answer(chunks: list[str]) -> str:
    while chunks and not chunks[0].strip():
        chunks.pop(0)
    while chunks and not chunks[-1].strip():
        chunks.pop()
    return "\n".join(chunks).strip()


def _parse_active_recall(
    lines: list[str],
    start: int,
    cards: list[ParsedCard],
    warnings: list[str],
    deck: str,
    module: str,
    unit: str,
    source_file: str,
) -> int:
    """Parse the Q&A pairs of one Active Recall section, returning the next index."""
    n = len(lines)
    i = start
    pending: str | None = None
    chunks: list[str] = []
    # ans_mode: None | "blockquote" | "bullet" | "bold" | "paragraph"
    ans_mode: str | None = None
    list_indent = 0
    in_code = False
    code_lines: list[str] = []

    def close_code_block() -> None:
        nonlocal in_code, code_lines
        if code_lines:
            block = textwrap.dedent("\n".join(code_lines)).strip()
            if block:
                chunks.extend(block.split("\n"))
        code_lines = []
        in_code = False

    def flush() -> None:
        nonlocal pending, chunks, ans_mode, list_indent, in_code, code_lines
        if pending is None:
            return
        if in_code:
            close_code_block()
        back = _join_answer(chunks)
        if back:
            cards.append(
                ParsedCard(
                    deck=deck,
                    source_file=source_file,
                    card_type="recall",
                    module=module,
                    unit=unit,
                    front=pending,
                    back=back,
                    front_clean=pending,
                )
            )
        else:
            warnings.append(f"{source_file}: empty answer for question: {pending!r}")
        pending = None
        chunks = []
        ans_mode = None
        list_indent = 0
        in_code = False
        code_lines = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Code fences first, so lines inside code (e.g. '---', '#') are never
        # mistaken for terminators or headings.
        if stripped.startswith("```"):
            if pending is not None:
                code_lines.append(line)
                if in_code:
                    close_code_block()
                else:
                    in_code = True
            i += 1
            continue

        if in_code:
            if pending is not None:
                code_lines.append(line)
            i += 1
            continue

        # Section terminators.
        if _HORIZONTAL_RULE.match(stripped) or _H2.match(line) or _H3.match(line):
            flush()
            return i  # outer loop re-processes the terminator line

        # A new question flushes the previous card.
        q = _match_question(line)
        if q is not None:
            flush()
            pending = q.text
            chunks = [q.inline_answer] if q.inline_answer else []
            ans_mode = "paragraph" if q.inline_answer else None
            list_indent = 0
            i += 1
            continue

        # Answer content for the open question.
        if pending is not None:
            bq = _BLOCKQUOTE.match(line)
            if bq is not None:
                ans_mode = "blockquote"
                content = _BLOCKQUOTE_ANSWER_PREFIX.sub("", bq.group(1)).strip()
                if content:
                    chunks.append(content)
                i += 1
                continue

            m = _BULLET_ANSWER.match(line)
            if m is not None:
                ans_mode = "bullet"
                list_indent = len(line) - len(line.lstrip())
                if m.group(1).strip():
                    chunks.append(m.group(1).strip())
                i += 1
                continue

            m = _BOLD_ANSWER.match(line)
            if m is not None:
                ans_mode = "bold"
                if m.group(1).strip():
                    chunks.append(m.group(1).strip())
                i += 1
                continue

            # Blank line: never part of the answer.
            if not stripped:
                i += 1
                continue

            # Plain paragraph. Only two cases are genuine answer content:
            #   1. the first content after a question (Variant B paragraph answer);
            #   2. an indented continuation of a bullet/list-item answer.
            # Anything else (a flush-left paragraph after a completed answer) is
            # trailing narrative noise.
            indent = len(line) - len(line.lstrip())
            if ans_mode is None:
                ans_mode = "paragraph"
                chunks.append(stripped)
            elif ans_mode == "bullet" and indent > list_indent:
                chunks.append(stripped)
            i += 1
            continue

        i += 1

    if in_code:
        close_code_block()
    flush()
    return n


def parse_unified(text: str, source_file: str) -> ParseResult:
    """Parse a unified-notes Markdown file (H2 modules, H3 units, Active Recall Q&A)."""
    lines = text.split("\n")
    cards: list[ParsedCard] = []
    warnings: list[str] = []
    deck = ""
    module = ""
    unit = ""

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Skip fenced code blocks entirely: their contents can contain '#',
        # '##' or '###' comment lines that would otherwise be mistaken for
        # Markdown headings.
        if stripped.startswith("```"):
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                i += 1
            i += 1  # skip the closing fence
            continue

        m = _H1.match(line)
        if m:
            deck = derive_deck(m.group(1))
            i += 1
            continue

        m = _H2.match(line)
        if m:
            title = m.group(1).strip()
            module = "" if _TOC.match(title) else canonicalize_module(title)
            unit = ""
            i += 1
            continue

        m = _H3.match(line)
        if m:
            unit = m.group(1).strip()
            i += 1
            continue

        if _ACTIVE_RECALL_HEADER.match(line):
            i = _parse_active_recall(lines, i + 1, cards, warnings, deck, module, unit, source_file)
            continue

        i += 1

    return ParseResult(cards=cards, warnings=warnings, deck=deck)

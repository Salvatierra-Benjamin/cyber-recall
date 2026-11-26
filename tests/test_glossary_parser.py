from __future__ import annotations

from pathlib import Path

from cyber_recall.parsers.base import make_card_id, normalize
from cyber_recall.parsers.glossary import parse_glossary

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = "notes/PreSecurity/glossary.md"


def _load() -> str:
    return (FIXTURES / "glossary_sample.md").read_text(encoding="utf-8")


def test_parses_deck_from_h1_with_em_dash():
    result = parse_glossary(_load(), SOURCE)
    assert result.deck == "PreSecurity"


def test_parses_all_glossary_rows():
    result = parse_glossary(_load(), SOURCE)
    # 4 rows in Module 1 + 3 rows in Module 6.
    assert len(result.cards) == 7


def test_module_and_unit_are_assigned():
    result = parse_glossary(_load(), SOURCE)
    dirb = next(c for c in result.cards if "dirb" in c.front)
    assert dirb.module == "Module 1 - Introduction to Cyber Security"
    assert dirb.unit == "Introduction to Cybersecurity"
    assert dirb.card_type == "glossary"
    assert dirb.source_file == SOURCE


def test_raw_and_clean_term():
    result = parse_glossary(_load(), SOURCE)
    dirb = next(c for c in result.cards if "dirb" in c.front)
    assert dirb.front == "**`dirb`**"
    assert dirb.front_clean == "`dirb`"


def test_slash_term_keeps_inner_code_in_clean():
    result = parse_glossary(_load(), SOURCE)
    ls = next(c for c in result.cards if c.front.startswith("**`ls`"))
    assert ls.front == "**`ls` / `ls -l` / `ls -al`**"
    assert ls.front_clean == "`ls` / `ls -l` / `ls -al`"


def test_ignores_blockquote_intro_and_separator_rows():
    result = parse_glossary(_load(), SOURCE)
    # The intro blockquote and the | --- | --- | --- | rows must not become cards.
    assert len(result.cards) == 7
    assert all(c.unit != "Unit" for c in result.cards)


def test_duplicate_term_ttl_produces_distinct_ids():
    result = parse_glossary(_load(), SOURCE)
    ttls = [c for c in result.cards if "TTL" in c.front]
    assert len(ttls) == 2
    assert ttls[0].id != ttls[1].id


def test_identical_term_across_modules_produces_distinct_ids():
    # DMZ and XSS appear once each here, but SIEM is repeated across the real data.
    # Build two cards with an identical term in different modules/units directly.
    id_a = make_card_id("PreSecurity", "glossary", "Module A", "Unit A", "**CIA Triad**")
    id_b = make_card_id("PreSecurity", "glossary", "Module B", "Unit B", "**CIA Triad**")
    assert id_a != id_b


def test_card_id_is_deterministic_and_16_hex_chars():
    result = parse_glossary(_load(), SOURCE)
    first = result.cards[0]
    again = parse_glossary(_load(), SOURCE).cards[0]
    assert first.id == again.id
    assert len(first.id) == 16
    int(first.id, 16)  # raises if not hex


def test_no_warnings_on_clean_input():
    result = parse_glossary(_load(), SOURCE)
    assert result.warnings == []


def test_normalize_is_case_and_markdown_insensitive():
    assert normalize("**`dirb`**") == "dirb"
    assert normalize("  **LS**  / `ls -l`  ") == "ls / ls -l"


def test_canonicalize_module_unifies_dash_and_case():
    from cyber_recall.parsers.base import canonicalize_module

    assert canonicalize_module("Module 2 — Computer Fundamentals") == "Module 2 - Computer Fundamentals"
    assert canonicalize_module("Module 2 - Computer fundamentals") == "Module 2 - Computer Fundamentals"
    assert canonicalize_module("Module 6 — How the Web Works") == "Module 6 - How the Web Works"
    assert canonicalize_module("Module 6 - How the Web works") == "Module 6 - How the Web Works"


def test_glossary_and_unified_share_canonical_module_names():
    from cyber_recall.parsers.unified import parse_unified

    glossary = parse_glossary(_load(), SOURCE)
    unified = parse_unified(
        (FIXTURES / "unified_sample.md").read_text(encoding="utf-8"),
        "notes/PreSecurity/PreSecurity-TryHackMe-Unified.md",
    )

    g_mods = {c.module for c in glossary.cards}
    u_mods = {c.module for c in unified.cards}
    # Module 1 appears in both files; canonical form must match.
    assert "Module 1 - Introduction to Cyber Security" in g_mods
    assert "Module 1 - Introduction to Cyber Security" in u_mods

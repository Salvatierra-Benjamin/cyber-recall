from __future__ import annotations

from pathlib import Path

from cyber_recall.db.repository import Repository
from cyber_recall.parsers.sync import detect_file_type, sync_notes

FIXTURES = Path(__file__).parent / "fixtures"

GLOSSARY = (FIXTURES / "glossary_sample.md").read_text(encoding="utf-8")
UNIFIED = (FIXTURES / "unified_sample.md").read_text(encoding="utf-8")


def _write_notes(root: Path, glossary: str = GLOSSARY, unified: str = UNIFIED) -> Path:
    notes_dir = root / "notes"
    pre = notes_dir / "PreSecurity"
    pre.mkdir(parents=True, exist_ok=True)
    (pre / "glossary.md").write_text(glossary, encoding="utf-8")
    (pre / "PreSecurity-TryHackMe-Unified.md").write_text(unified, encoding="utf-8")
    return notes_dir


def test_detect_file_type():
    assert detect_file_type(GLOSSARY) == "glossary"
    assert detect_file_type(UNIFIED) == "unified"
    assert detect_file_type("# Just notes\nNo markers here.\n") == "unknown"
    # Filename heuristic fallback.
    assert detect_file_type("# No structural markers\n", "my_glossary.md") == "glossary"
    assert detect_file_type("# No structural markers\n", "some_unified.md") == "unified"


def test_sync_adds_all_cards(tmp_path):
    notes_dir = _write_notes(tmp_path)
    repo = Repository.in_memory()
    report = sync_notes(notes_dir, repo)

    assert report.added == 7 + 12  # 7 glossary + 12 recall
    assert report.updated == 0
    assert report.unchanged == 0
    assert report.archived == 0
    assert report.total_cards == 19
    assert report.warnings == []


def test_source_file_is_relative_to_project_root(tmp_path):
    notes_dir = _write_notes(tmp_path)
    repo = Repository.in_memory()
    sync_notes(notes_dir, repo)
    sources = {c.source_file for c in repo.list_cards()}
    assert sources == {
        "notes/PreSecurity/glossary.md",
        "notes/PreSecurity/PreSecurity-TryHackMe-Unified.md",
    }


def test_sync_is_idempotent(tmp_path):
    notes_dir = _write_notes(tmp_path)
    repo = Repository.in_memory()
    sync_notes(notes_dir, repo)
    report = sync_notes(notes_dir, repo)
    assert report.added == 0
    assert report.updated == 0
    assert report.unchanged == 19
    assert report.archived == 0


def test_removed_card_is_soft_archived(tmp_path):
    notes_dir = _write_notes(tmp_path)
    repo = Repository.in_memory()
    sync_notes(notes_dir, repo)

    # Remove one glossary term and re-sync.
    shortened = GLOSSARY.replace(
        "| **XSS (Cross-Site Scripting)** | How Websites Work | Injection vulnerability achieving arbitrary JavaScript execution. |\n",
        "",
    )
    _write_notes(tmp_path, glossary=shortened)
    report = sync_notes(notes_dir, repo)

    assert report.archived == 1
    archived = repo.list_cards_for_source("notes/PreSecurity/glossary.md", include_archived=True)
    xss = next(c for c in archived if "XSS" in c.front)
    assert xss.archived is True


def test_archived_card_is_reactivated_with_state_preserved(tmp_path):
    notes_dir = _write_notes(tmp_path)
    repo = Repository.in_memory()
    sync_notes(notes_dir, repo)

    xss = next(c for c in repo.list_cards() if "XSS" in c.front)
    from cyber_recall.models import CardState

    # Simulate study progress before the card disappears.
    repo.upsert_state(
        CardState(
            card_id=xss.id,
            direction="forward",
            repetitions=4,
            interval_days=10,
            ease_factor=2.1,
            lapses=2,
            due_at="2026-01-01T00:00:00+00:00",
        )
    )

    shortened = GLOSSARY.replace(
        "| **XSS (Cross-Site Scripting)** | How Websites Work | Injection vulnerability achieving arbitrary JavaScript execution. |\n",
        "",
    )
    _write_notes(tmp_path, glossary=shortened)
    sync_notes(notes_dir, repo)

    # Re-add the term and sync again.
    _write_notes(tmp_path)
    sync_notes(notes_dir, repo)

    reactivated = repo.get_card(xss.id)
    assert reactivated is not None
    assert reactivated.archived is False
    state = repo.get_state(xss.id)
    assert state.repetitions == 4
    assert state.ease_factor == 2.1


def test_changed_definition_preserves_review_state(tmp_path):
    notes_dir = _write_notes(tmp_path)
    repo = Repository.in_memory()
    sync_notes(notes_dir, repo)

    dirb = next(
        c for c in repo.list_cards() if c.card_type == "glossary" and "`dirb`" in c.front
    )
    from cyber_recall.models import CardState

    repo.upsert_state(
        CardState(card_id=dirb.id, repetitions=3, interval_days=5, due_at="2026-01-01T00:00:00+00:00")
    )

    updated_def = GLOSSARY.replace(
        "A command-line web server scanner that brute-forces URLs with wordlists.",
        "A NEW definition for the scanner.",
    )
    _write_notes(tmp_path, glossary=updated_def)
    report = sync_notes(notes_dir, repo)

    assert report.updated == 1
    assert report.added == 0
    after = repo.get_card(dirb.id)
    assert after.back == "A NEW definition for the scanner."
    assert repo.get_state(dirb.id).repetitions == 3


def test_deleted_file_archives_all_its_cards(tmp_path):
    notes_dir = _write_notes(tmp_path)
    repo = Repository.in_memory()
    sync_notes(notes_dir, repo)

    # Delete the whole glossary file; its 7 cards must become archived orphans.
    (notes_dir / "PreSecurity" / "glossary.md").unlink()
    report = sync_notes(notes_dir, repo)

    assert report.archived == 7
    assert report.added == 0
    assert report.total_cards == 12
    assert all(c.card_type == "recall" for c in repo.list_cards())
    glossary_cards = repo.list_cards_for_source(
        "notes/PreSecurity/glossary.md", include_archived=True
    )
    assert len(glossary_cards) == 7
    assert all(c.archived for c in glossary_cards)


def test_unrecognized_file_is_skipped_with_warning(tmp_path):
    notes_dir = tmp_path / "notes"
    (notes_dir / "misc").mkdir(parents=True)
    (notes_dir / "misc" / "random.md").write_text("# Random notes\nNo markers.\n", encoding="utf-8")
    repo = Repository.in_memory()
    report = sync_notes(notes_dir, repo)
    assert report.added == 0
    assert any("unrecognized" in w for w in report.warnings)


def test_missing_notes_dir_reports_warning(tmp_path):
    repo = Repository.in_memory()
    report = sync_notes(tmp_path / "does-not-exist", repo)
    assert report.total_cards == 0
    assert any("not found" in w for w in report.warnings)

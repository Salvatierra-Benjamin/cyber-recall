from __future__ import annotations

import sqlite3

import pytest

from cyber_recall.db.repository import Repository, utc_now_iso
from cyber_recall.models import Card, CardState, ReviewLog, StudyFilter


def make_card(**overrides) -> Card:
    defaults = dict(
        id="card-1",
        deck="PreSecurity",
        source_file="notes/PreSecurity/glossary.md",
        card_type="glossary",
        module="Module 5 — Network Fundamentals",
        unit="Packets & Frames",
        front="TTL",
        back="Time to Live",
    )
    defaults.update(overrides)
    return Card(**defaults)


def test_schema_tables_created():
    repo = Repository.in_memory()
    rows = repo.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    tables = {r["name"] for r in rows}
    assert {"cards", "card_state", "review_logs"} <= tables


def test_foreign_keys_enabled():
    repo = Repository.in_memory()
    assert repo.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_foreign_key_enforced_on_review_log():
    repo = Repository.in_memory()
    log = ReviewLog(
        card_id="missing",
        direction="forward",
        mode="flashcard",
        rating=3,
        reviewed_at=utc_now_iso(),
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_review(log)


def test_upsert_new_card_creates_forward_state():
    repo = Repository.in_memory()
    card = make_card()
    repo.upsert_card(card)
    assert repo.get_card(card.id) is not None
    state = repo.get_state(card.id, "forward")
    assert state is not None
    assert state.repetitions == 0
    assert state.interval_days == 0
    assert state.due_at != ""


def test_upsert_existing_card_preserves_state():
    repo = Repository.in_memory()
    card = make_card()
    repo.upsert_card(card)

    # Simulate real study progress before the content update.
    progress = CardState(
        card_id=card.id,
        direction="forward",
        repetitions=3,
        interval_days=15,
        ease_factor=2.3,
        lapses=1,
        due_at=utc_now_iso(),
        last_reviewed_at=utc_now_iso(),
    )
    repo.upsert_state(progress)

    card.back = "New definition"
    repo.upsert_card(card)

    updated = repo.get_card(card.id)
    assert updated.back == "New definition"

    after = repo.get_state(card.id, "forward")
    assert after.repetitions == 3
    assert after.interval_days == 15
    assert after.ease_factor == 2.3
    assert after.lapses == 1


def test_upsert_is_idempotent_row_count():
    repo = Repository.in_memory()
    card = make_card()
    repo.upsert_card(card)
    repo.upsert_card(card)
    assert repo.count_cards() == 1
    assert len(repo.list_cards()) == 1


def test_list_cards_filters():
    repo = Repository.in_memory()
    a = make_card(id="a", module="M1", unit="U1", card_type="glossary")
    b = make_card(id="b", module="M1", unit="U2", card_type="glossary")
    c = make_card(id="c", module="M2", unit="U3", card_type="recall")
    for card in (a, b, c):
        repo.upsert_card(card)

    assert len(repo.list_cards(StudyFilter(module="M1"))) == 2
    assert len(repo.list_cards(StudyFilter(card_type="recall"))) == 1
    assert len(repo.list_cards(StudyFilter(unit="U2"))) == 1
    assert len(repo.list_cards(StudyFilter(deck="PreSecurity"))) == 3


def test_list_cards_excludes_archived():
    repo = Repository.in_memory()
    repo.upsert_card(make_card(id="a"))
    repo.upsert_card(make_card(id="b", archived=True))
    assert len(repo.list_cards()) == 1


def test_save_and_read_review():
    repo = Repository.in_memory()
    card = make_card()
    repo.upsert_card(card)
    log = ReviewLog(
        card_id=card.id,
        direction="forward",
        mode="flashcard",
        rating=3,
        elapsed_ms=1200,
        reviewed_at=utc_now_iso(),
    )
    log_id = repo.save_review(log)
    assert log_id is not None and log_id > 0

    logs = repo.list_reviews(card.id)
    assert len(logs) == 1
    assert logs[0].rating == 3
    assert logs[0].mode == "flashcard"
    assert logs[0].elapsed_ms == 1200


def test_connect_creates_parent_directory(tmp_path):
    db_path = tmp_path / "nested" / "data" / "cyber-recall.db"
    repo = Repository.connect(db_path)
    try:
        assert db_path.exists()
        assert repo.count_cards() == 0
    finally:
        repo.close()


def test_context_manager_closes_connection(tmp_path):
    db_path = tmp_path / "ctx.db"
    with Repository.connect(db_path) as repo:
        assert repo.count_cards() == 0
    with pytest.raises(sqlite3.ProgrammingError):
        repo.conn.execute("SELECT 1")

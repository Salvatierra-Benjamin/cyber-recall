from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cyber_recall.core.scheduler import _start_of_day_iso, build_session_queue, record_review
from cyber_recall.core.sm2 import RATING_EASY, RATING_GOOD, preview_intervals
from cyber_recall.db.repository import Repository
from cyber_recall.models import Card, CardState, ReviewLog, StudyFilter

NOW = datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()
PAST = (NOW - timedelta(days=2)).isoformat()
FUTURE = (NOW + timedelta(days=5)).isoformat()

MOD1 = "Module 1 - Introduction to Cyber Security"


def make_card(card_id: str, **overrides) -> Card:
    defaults = dict(
        id=card_id,
        deck="PreSecurity",
        source_file="notes/PreSecurity/glossary.md",
        card_type="glossary",
        module=MOD1,
        unit="Intro",
        front=f"front-{card_id}",
        back="back",
    )
    defaults.update(overrides)
    return Card(**defaults)


def _state(card_id: str, **overrides) -> CardState:
    defaults = dict(
        card_id=card_id,
        direction="forward",
        repetitions=0,
        interval_days=0,
        ease_factor=2.5,
        lapses=0,
        due_at=PAST,
        last_reviewed_at=PAST,
    )
    defaults.update(overrides)
    return CardState(**defaults)


def _seed_scenario(repo: Repository) -> None:
    """rel: relearning and due; due: scheduled and due; future: not due; fresh: new."""
    for card in (make_card("rel"), make_card("due"), make_card("future"), make_card("fresh")):
        repo.upsert_card(card, NOW_ISO)

    repo.upsert_state(_state("rel", lapses=2, interval_days=0, due_at=PAST))
    repo.upsert_state(_state("due", repetitions=3, interval_days=6, lapses=0, due_at=PAST))
    repo.upsert_state(_state("future", repetitions=2, interval_days=10, lapses=0, due_at=FUTURE))
    # "fresh" keeps the auto-created forward state (never reviewed).


def _ids(queue) -> list[str]:
    return [item.card.id for item in queue]


def test_normal_queue_priority_order():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10)
    assert _ids(queue) == ["rel", "due", "fresh"]


def test_normal_queue_excludes_future_card():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10)
    assert "future" not in _ids(queue)


def test_new_card_keeps_its_never_reviewed_state():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10)
    fresh = next(item for item in queue if item.card.id == "fresh")
    assert fresh.state is not None
    assert fresh.state.last_reviewed_at is None


def test_new_cards_limited_by_daily_limit():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=0)
    assert _ids(queue) == ["rel", "due"]


def test_new_quota_reduced_by_introduced_today():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    # "due" was first reviewed today, consuming one slot of the daily budget.
    repo.save_review(
        ReviewLog(
            card_id="due",
            direction="forward",
            mode="flashcard",
            rating=3,
            reviewed_at=NOW_ISO,
        )
    )
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=1)
    assert _ids(queue) == ["rel", "due"]


def test_reviews_from_yesterday_do_not_consume_todays_budget():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    repo.save_review(
        ReviewLog(
            card_id="due",
            direction="forward",
            mode="flashcard",
            rating=3,
            reviewed_at=(NOW - timedelta(days=1)).isoformat(),
        )
    )
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=1)
    assert _ids(queue) == ["rel", "due", "fresh"]


def test_cram_includes_future_and_relearning():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10, cram=True)
    assert _ids(queue) == ["rel", "due", "future", "fresh"]


def test_normal_mode_excludes_relearning_not_due_yet():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    # Failed 5 minutes ago: still in relearning, due in 5 more minutes.
    repo.upsert_state(_state("rel", lapses=1, interval_days=0, due_at=FUTURE))
    normal = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10)
    assert _ids(normal) == ["due", "fresh"]
    cram = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10, cram=True)
    assert _ids(cram) == ["rel", "due", "future", "fresh"]


def test_due_cards_ordered_by_due_at():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    # "fresh" becomes a due card 10 days overdue (older than "due").
    repo.upsert_state(
        _state(
            "fresh",
            repetitions=1,
            interval_days=2,
            lapses=0,
            due_at=(NOW - timedelta(days=10)).isoformat(),
            last_reviewed_at=PAST,
        )
    )
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10)
    assert _ids(queue) == ["rel", "fresh", "due"]


def test_filter_by_module():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    repo.upsert_card(make_card("other", module="Module 2 - Computer Fundamentals"), NOW_ISO)
    queue = build_session_queue(
        repo, StudyFilter(module=MOD1), NOW, daily_new_limit=10
    )
    assert _ids(queue) == ["rel", "due", "fresh"]


def test_filter_by_card_type():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    repo.upsert_card(make_card("recall1", card_type="recall"), NOW_ISO)
    queue = build_session_queue(repo, StudyFilter(card_type="glossary"), NOW, daily_new_limit=10)
    assert "recall1" not in _ids(queue)


def test_reverse_direction_treats_everything_as_new():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(direction="reverse"), NOW, daily_new_limit=10)
    # No reverse states exist, so all cards are new (in repository order).
    assert _ids(queue) == ["due", "fresh", "future", "rel"]
    for item in queue:
        assert isinstance(item.state, CardState)
        assert item.state.direction == "reverse"
        assert item.state.last_reviewed_at is None
        # Every state must be usable directly by the SM-2 helpers.
        assert preview_intervals(item.state)[0] == (1, "10m")


# ---- cram mode does not limit new cards ----


def test_cram_does_not_limit_new_cards():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=0, cram=True)
    assert _ids(queue) == ["rel", "due", "future", "fresh"]


def test_cram_does_not_query_introduced_today():
    # Cram must not even need the daily-budget query: a filter with only a fresh
    # card returns it with limit 0.
    repo = Repository.in_memory()
    repo.upsert_card(make_card("only"), NOW_ISO)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=0, cram=True)
    assert _ids(queue) == ["only"]


# ---- reverse is glossary-only ----


def test_reverse_excludes_recall_cards():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    repo.upsert_card(make_card("recall1", card_type="recall"), NOW_ISO)
    queue = build_session_queue(repo, StudyFilter(direction="reverse"), NOW, daily_new_limit=10)
    assert "recall1" not in _ids(queue)
    assert set(_ids(queue)) == {"due", "fresh", "future", "rel"}


def test_reverse_with_recall_filter_returns_empty():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(
        repo, StudyFilter(direction="reverse", card_type="recall"), NOW, daily_new_limit=10
    )
    assert queue == []


def test_reverse_does_not_mutate_filter():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    study_filter = StudyFilter(direction="reverse")
    build_session_queue(repo, study_filter, NOW, daily_new_limit=10)
    assert study_filter.card_type is None
    assert study_filter.direction == "reverse"


# ---- record_review ----


def test_record_review_normal_updates_state_and_logs():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10)
    item = next(i for i in queue if i.card.id == "fresh")

    new_state = record_review(repo, item, RATING_GOOD, "flashcard", NOW, elapsed_ms=1200)

    assert new_state.repetitions == 1
    assert new_state.interval_days == 1
    persisted = repo.get_state("fresh", "forward")
    assert persisted.repetitions == 1
    assert persisted.last_reviewed_at == NOW.isoformat()
    logs = repo.list_reviews("fresh")
    assert len(logs) == 1
    assert logs[0].rating == RATING_GOOD
    assert logs[0].mode == "flashcard"
    assert logs[0].elapsed_ms == 1200


def test_record_review_consumes_daily_new_budget():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    repo.upsert_card(make_card("fresh2"), NOW_ISO)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10)
    item = next(i for i in queue if i.card.id == "fresh")

    record_review(repo, item, RATING_GOOD, "flashcard", NOW)

    # Reviewing "fresh" consumed today's budget: with limit 1 no new cards remain.
    rebuilt = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=1)
    assert "fresh2" not in _ids(rebuilt)


def test_record_review_cram_does_not_persist():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    queue = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10, cram=True)
    item = next(i for i in queue if i.card.id == "fresh")

    returned = record_review(repo, item, RATING_EASY, "flashcard", NOW, cram=True)

    assert returned == item.state
    # No state update persisted.
    persisted = repo.get_state("fresh", "forward")
    assert persisted.last_reviewed_at is None
    assert persisted.repetitions == 0
    # No review log written.
    assert repo.list_reviews("fresh") == []
    # Daily budget not consumed: "fresh" still qualifies as new.
    rebuilt = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=1)
    assert "fresh" in _ids(rebuilt)


def test_record_review_invalid_rating_raises():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    item = build_session_queue(repo, StudyFilter(), NOW, daily_new_limit=10)[0]
    with pytest.raises(ValueError):
        record_review(repo, item, 5, "flashcard", NOW)
    with pytest.raises(ValueError):
        record_review(repo, item, 0, "flashcard", NOW)
    with pytest.raises(ValueError):
        record_review(repo, item, True, "flashcard", NOW, cram=True)


# ---- local-day boundary (timezone-aware) ----


def test_start_of_day_respects_local_timezone():
    utc_minus_3 = timezone(timedelta(hours=-3))
    now = datetime(2026, 11, 26, 9, 0, tzinfo=utc_minus_3)
    # 00:00 in UTC-3 == 03:00 UTC.
    assert _start_of_day_iso(now) == "2026-11-26T03:00:00+00:00"


def test_start_of_day_for_utc_unchanged():
    assert _start_of_day_iso(NOW) == "2026-11-26T00:00:00+00:00"


def test_new_budget_uses_local_day_boundary():
    repo = Repository.in_memory()
    _seed_scenario(repo)
    utc_minus_3 = timezone(timedelta(hours=-3))
    # Review logged at 02:00 UTC == 23:00 the PREVIOUS day in UTC-3.
    reviewed_utc = datetime(2026, 11, 26, 2, 0, tzinfo=timezone.utc)
    repo.save_review(
        ReviewLog(
            card_id="due",
            direction="forward",
            mode="flashcard",
            rating=3,
            reviewed_at=reviewed_utc.isoformat(),
        )
    )
    now_local = datetime(2026, 11, 26, 9, 0, tzinfo=utc_minus_3)
    queue = build_session_queue(repo, StudyFilter(), now_local, daily_new_limit=1)
    # That review belongs to the previous local day, so the budget stays intact.
    assert "fresh" in _ids(queue)

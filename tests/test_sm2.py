from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cyber_recall.core.sm2 import (
    AGAIN_DELAY_MINUTES,
    MIN_EASE_FACTOR,
    RATING_AGAIN,
    RATING_EASY,
    RATING_GOOD,
    RATING_HARD,
    calculate_next_review,
    format_delta,
    preview_intervals,
)
from cyber_recall.models import CardState

NOW = datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc)


def make_state(**overrides) -> CardState:
    defaults = dict(
        card_id="card-1",
        direction="forward",
        repetitions=0,
        interval_days=0,
        ease_factor=2.5,
        lapses=0,
        due_at="2026-11-26T00:00:00+00:00",
        last_reviewed_at=None,
    )
    defaults.update(overrides)
    return CardState(**defaults)


# ---- interval progression ----


def test_good_on_new_card_sets_interval_1_day():
    state = calculate_next_review(make_state(), RATING_GOOD, NOW)
    assert state.repetitions == 1
    assert state.interval_days == 1
    assert state.lapses == 0
    assert state.due_at == (NOW + timedelta(days=1)).isoformat()


def test_easy_on_new_card_sets_interval_3_days():
    state = calculate_next_review(make_state(), RATING_EASY, NOW)
    assert state.repetitions == 1
    assert state.interval_days == 3


def test_hard_on_new_card_sets_interval_1_day():
    state = calculate_next_review(make_state(), RATING_HARD, NOW)
    assert state.repetitions == 1
    assert state.interval_days == 1


def test_second_review_intervals_per_rating():
    base = make_state(repetitions=1, interval_days=1)
    assert calculate_next_review(base, RATING_HARD, NOW).interval_days == 4
    assert calculate_next_review(base, RATING_GOOD, NOW).interval_days == 6
    assert calculate_next_review(base, RATING_EASY, NOW).interval_days == 8


def test_third_review_hard_interval():
    state = calculate_next_review(make_state(repetitions=2, interval_days=6), RATING_HARD, NOW)
    assert state.interval_days == 7  # round(6 * 1.2)


def test_third_review_good_interval_uses_ease_factor():
    state = calculate_next_review(
        make_state(repetitions=2, interval_days=6, ease_factor=2.5), RATING_GOOD, NOW
    )
    assert state.interval_days == 15  # round(6 * 2.5)


def test_third_review_easy_interval():
    state = calculate_next_review(
        make_state(repetitions=2, interval_days=6, ease_factor=2.5), RATING_EASY, NOW
    )
    assert state.interval_days == 20  # round(6 * 2.6 * 1.3)


def test_hard_interval_never_below_one_day():
    state = calculate_next_review(make_state(repetitions=3, interval_days=1), RATING_HARD, NOW)
    assert state.interval_days == 1  # max(1, round(1 * 1.2))


# ---- ease factor ----


def test_good_keeps_ease_factor():
    state = calculate_next_review(make_state(), RATING_GOOD, NOW)
    assert state.ease_factor == pytest.approx(2.5)


def test_easy_raises_ease_factor():
    state = calculate_next_review(make_state(), RATING_EASY, NOW)
    assert state.ease_factor == pytest.approx(2.6)


def test_hard_lowers_ease_factor_slightly():
    state = calculate_next_review(make_state(), RATING_HARD, NOW)
    assert state.ease_factor == pytest.approx(2.36)  # 2.5 - 0.14


def test_again_lowers_ease_factor():
    state = calculate_next_review(make_state(), RATING_AGAIN, NOW)
    assert state.ease_factor == pytest.approx(1.96)  # 2.5 - 0.54


def test_ease_factor_never_below_minimum():
    state = calculate_next_review(make_state(ease_factor=1.31), RATING_AGAIN, NOW)
    assert state.ease_factor == pytest.approx(MIN_EASE_FACTOR)  # 1.3


# ---- again / lapses ----


def test_again_resets_repetitions_and_increments_lapses():
    state = calculate_next_review(
        make_state(repetitions=5, interval_days=20, lapses=1), RATING_AGAIN, NOW
    )
    assert state.repetitions == 0
    assert state.interval_days == 0
    assert state.lapses == 2
    assert state.due_at == (NOW + timedelta(minutes=AGAIN_DELAY_MINUTES)).isoformat()


# ---- timestamps and purity ----


def test_last_reviewed_at_is_now():
    state = calculate_next_review(make_state(), RATING_GOOD, NOW)
    assert state.last_reviewed_at == NOW.isoformat()


def test_input_state_is_not_mutated():
    original = make_state(repetitions=4, interval_days=10, ease_factor=2.2, lapses=1)
    snapshot = make_state(repetitions=4, interval_days=10, ease_factor=2.2, lapses=1)
    calculate_next_review(original, RATING_GOOD, NOW)
    assert original == snapshot


def test_direction_is_preserved():
    state = calculate_next_review(make_state(direction="reverse"), RATING_GOOD, NOW)
    assert state.direction == "reverse"


def test_invalid_rating_raises():
    with pytest.raises(ValueError):
        calculate_next_review(make_state(), 5, NOW)
    with pytest.raises(ValueError):
        calculate_next_review(make_state(), 0, NOW)


def test_bool_rating_raises():
    # In Python True == 1, so booleans must be rejected explicitly.
    with pytest.raises(ValueError):
        calculate_next_review(make_state(), True, NOW)
    with pytest.raises(ValueError):
        calculate_next_review(make_state(), False, NOW)


# ---- previews ----


def test_preview_intervals_for_new_card():
    previews = preview_intervals(make_state())
    assert previews == [
        (RATING_AGAIN, "10m"),
        (RATING_HARD, "1d"),
        (RATING_GOOD, "1d"),
        (RATING_EASY, "3d"),
    ]


def test_preview_intervals_for_reviewed_card():
    previews = preview_intervals(make_state(repetitions=2, interval_days=6, ease_factor=2.5))
    labels = dict(previews)
    assert labels[RATING_AGAIN] == "10m"
    assert labels[RATING_HARD] == "7d"
    assert labels[RATING_GOOD] == "15d"
    assert labels[RATING_EASY] == "20d"


def test_preview_intervals_accepts_optional_now():
    # The plan specifies both preview_intervals(state) and preview_intervals(state, now).
    assert preview_intervals(make_state(), NOW) == preview_intervals(make_state())


def test_format_delta():
    assert format_delta(timedelta(minutes=10)) == "10m"
    assert format_delta(timedelta(days=1)) == "1d"
    assert format_delta(timedelta(days=6)) == "6d"

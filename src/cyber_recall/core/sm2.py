from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cyber_recall.models import CardState

# User-facing ratings (the four review buttons).
RATING_AGAIN = 1
RATING_HARD = 2
RATING_GOOD = 3
RATING_EASY = 4

# SM-2 quality values (q) mapped from the four buttons.
_QUALITY = {RATING_AGAIN: 1, RATING_HARD: 3, RATING_GOOD: 4, RATING_EASY: 5}

# Fixed interval for the second successful review, per rating.
_SECOND_INTERVAL = {RATING_HARD: 4, RATING_GOOD: 6, RATING_EASY: 8}

MIN_EASE_FACTOR = 1.3
AGAIN_DELAY_MINUTES = 10

_RATINGS = (RATING_AGAIN, RATING_HARD, RATING_GOOD, RATING_EASY)


def _utc_iso(dt: datetime) -> str:
    """Return an ISO-8601 UTC string (naive datetimes are treated as UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _apply(
    rating: int,
    repetitions: int,
    interval_days: int,
    ease_factor: float,
    lapses: int,
) -> tuple[int, int, float, int]:
    """Apply one SM-2 step, returning (repetitions, interval_days, ease_factor, lapses)."""
    quality = _QUALITY[rating]
    ease = max(
        MIN_EASE_FACTOR,
        ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
    )

    if rating == RATING_AGAIN:
        # Failed: reset the learning curve, lapse, and re-review soon.
        return 0, 0, ease, lapses + 1

    reps = repetitions + 1
    if reps == 1:
        interval = 3 if rating == RATING_EASY else 1
    elif reps == 2:
        interval = _SECOND_INTERVAL[rating]
    elif rating == RATING_HARD:
        interval = max(1, round(interval_days * 1.2))
    elif rating == RATING_GOOD:
        interval = round(interval_days * ease)
    else:  # RATING_EASY
        interval = round(interval_days * ease * 1.3)
    return reps, interval, ease, lapses


def calculate_next_review(state: CardState, rating: int, now: datetime) -> CardState:
    """Return the new CardState produced by reviewing `state` with `rating` at `now`.

    Pure function: the input state is never mutated. Timestamps are stored as
    ISO-8601 UTC strings, consistent with the rest of the system.
    """
    if isinstance(rating, bool) or rating not in _QUALITY:
        raise ValueError(f"rating must be one of 1-4, got {rating!r}")

    reps, interval, ease, lapses = _apply(
        rating, state.repetitions, state.interval_days, state.ease_factor, state.lapses
    )

    if rating == RATING_AGAIN:
        due = now + timedelta(minutes=AGAIN_DELAY_MINUTES)
    else:
        due = now + timedelta(days=interval)

    return CardState(
        card_id=state.card_id,
        direction=state.direction,
        repetitions=reps,
        interval_days=interval,
        ease_factor=ease,
        lapses=lapses,
        due_at=_utc_iso(due),
        last_reviewed_at=_utc_iso(now),
    )


def preview_intervals(
    state: CardState, now: datetime | None = None
) -> list[tuple[int, str]]:
    """Return (rating, label) pairs describing when each rating would reschedule the card.

    Example for a fresh card: ``[(1, "10m"), (2, "1d"), (3, "1d"), (4, "3d")]``.

    ``now`` is accepted for API compatibility with both plan signatures
    (Section 4.2 and Phase 3) but is not used: the labels are relative delays.
    """
    previews: list[tuple[int, str]] = []
    for rating in _RATINGS:
        if rating == RATING_AGAIN:
            delta = timedelta(minutes=AGAIN_DELAY_MINUTES)
        else:
            _, interval, _, _ = _apply(
                rating, state.repetitions, state.interval_days, state.ease_factor, state.lapses
            )
            delta = timedelta(days=interval)
        previews.append((rating, format_delta(delta)))
    return previews


def format_delta(delta: timedelta) -> str:
    """Format a review delay as a compact human label like ``10m`` or ``6d``."""
    minutes = max(0, int(delta.total_seconds() // 60))
    if minutes < 1440:
        return f"{minutes}m"
    return f"{round(minutes / 1440)}d"

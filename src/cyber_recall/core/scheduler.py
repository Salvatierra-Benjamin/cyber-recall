from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from cyber_recall.core.sm2 import (
    RATING_AGAIN,
    RATING_EASY,
    RATING_GOOD,
    RATING_HARD,
    calculate_next_review,
)
from cyber_recall.db.repository import Repository
from cyber_recall.models import Card, CardState, ReviewLog, StudyFilter

_VALID_RATINGS = (RATING_AGAIN, RATING_HARD, RATING_GOOD, RATING_EASY)


@dataclass(slots=True)
class QueueItem:
    """One entry of a study queue: the card plus its state for the session direction.

    ``state`` is always a concrete ``CardState`` (never ``None``), so it can be
    passed directly to :func:`preview_intervals` and :func:`calculate_next_review`.
    A card never reviewed in this direction carries an in-memory state with
    ``last_reviewed_at is None``.
    """

    card: Card
    state: CardState


def _utc_iso(dt: datetime) -> str:
    """Return an ISO-8601 UTC string (naive datetimes are treated as UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _start_of_day_iso(now: datetime) -> str:
    """Return the UTC ISO timestamp of local midnight (start of `now`'s day)."""
    base = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    day_start = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start.astimezone(timezone.utc).isoformat()


def build_session_queue(
    repo: Repository,
    study_filter: StudyFilter,
    now: datetime,
    daily_new_limit: int,
    cram: bool = False,
) -> list[QueueItem]:
    """Build the session queue.

    Priority order (normal mode):

    1. Relearning cards due now (recently failed, waiting for their re-review);
    2. Due cards (``due_at <= now``);
    3. New cards (never reviewed in this direction), up to ``daily_new_limit``
       minus the new cards already introduced today.

    The reverse direction only applies to glossary cards (plan Section 5.2):
    recall cards are excluded. In cram mode, due dates AND the daily new-card
    budget are ignored; the caller must not apply SM-2 updates for cram reviews
    (see :func:`record_review`).
    """
    direction = study_filter.direction or "forward"
    now_iso = _utc_iso(now)

    query_filter = study_filter
    if direction == "reverse":
        if study_filter.card_type == "recall":
            return []
        if study_filter.card_type is None:
            # Reverse flashcards are glossary-only; never mutate the caller's filter.
            query_filter = replace(study_filter, card_type="glossary")

    relearning: list[QueueItem] = []
    due: list[QueueItem] = []
    future: list[QueueItem] = []
    new: list[QueueItem] = []

    for card, state in repo.list_cards_with_state(query_filter, direction):
        if state is None:
            # No state for this direction yet: materialize a fresh in-memory
            # state (not persisted until the first real review).
            state = CardState(
                card_id=card.id,
                direction=direction,
                due_at=now_iso,
                last_reviewed_at=None,
            )
        if state.last_reviewed_at is None:
            new.append(QueueItem(card=card, state=state))
        elif state.interval_days == 0:
            # Reviewed and failed: in the relearning loop.
            relearning.append(QueueItem(card=card, state=state))
        elif state.due_at <= now_iso:
            due.append(QueueItem(card=card, state=state))
        else:
            future.append(QueueItem(card=card, state=state))

    relearning.sort(key=lambda item: item.state.due_at)
    due.sort(key=lambda item: item.state.due_at)
    future.sort(key=lambda item: item.state.due_at)
    # `new` keeps the repository order (deck, module, unit, id).

    if cram:
        # Cram ignores due dates and the daily new-card budget.
        return relearning + due + future + new

    introduced_today = repo.count_new_cards_introduced_since(direction, _start_of_day_iso(now))
    new_quota = max(0, daily_new_limit - introduced_today)

    pending = [item for item in relearning if item.state.due_at <= now_iso]
    return pending + due + new[:new_quota]


def record_review(
    repo: Repository,
    item: QueueItem,
    rating: int,
    mode: str,
    now: datetime,
    elapsed_ms: int | None = None,
    cram: bool = False,
) -> CardState:
    """Record a review for a queue item and return the resulting card state.

    Normal mode: applies SM-2 via :func:`calculate_next_review`, persists the
    new state and appends a review log. Cram mode: validates the rating but
    persists nothing — SM-2 stays untouched and the daily new-card budget is
    not consumed; ``item.state`` is returned unchanged.
    """
    if isinstance(rating, bool) or rating not in _VALID_RATINGS:
        raise ValueError(f"rating must be one of 1-4, got {rating!r}")

    if cram:
        return item.state

    new_state = calculate_next_review(item.state, rating, now)
    repo.upsert_state(new_state)
    repo.save_review(
        ReviewLog(
            card_id=item.card.id,
            direction=item.state.direction,
            mode=mode,
            rating=rating,
            elapsed_ms=elapsed_ms,
            reviewed_at=new_state.last_reviewed_at,
        )
    )
    return new_state

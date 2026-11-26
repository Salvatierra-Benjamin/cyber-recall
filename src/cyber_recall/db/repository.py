from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType

from cyber_recall.db.schema import create_connection, initialize_schema
from cyber_recall.models import Card, CardState, ReviewLog, StudyFilter


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class Repository:
    """SQLite-backed persistence for cards, card state, and review logs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    @classmethod
    def connect(cls, path: str | Path) -> Repository:
        db_path = Path(path)
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = create_connection(str(db_path))
        initialize_schema(conn)
        return cls(conn)

    @classmethod
    def in_memory(cls) -> Repository:
        conn = create_connection(":memory:")
        initialize_schema(conn)
        return cls(conn)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def __enter__(self) -> Repository:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ---- cards ----

    def upsert_card(self, card: Card, now: str | None = None) -> None:
        """Insert a new card (plus its initial forward state) or update an existing one.

        Existing cards keep their `card_state` and `review_logs` intact; only the card
        row is refreshed. New cards get a forward `card_state` due immediately.
        """
        now = now or utc_now_iso()
        with self.conn:
            existing = self.conn.execute(
                "SELECT id FROM cards WHERE id = ?", (card.id,)
            ).fetchone()
            if existing is None:
                self.conn.execute(
                    """
                    INSERT INTO cards
                        (id, deck, source_file, card_type, module, unit, front, back, archived, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (card.id, card.deck, card.source_file, card.card_type, card.module,
                     card.unit, card.front, card.back, int(card.archived), now, now),
                )
                self._ensure_state(card.id, now)
            else:
                self.conn.execute(
                    """
                    UPDATE cards
                    SET deck = ?, source_file = ?, card_type = ?, module = ?, unit = ?,
                        front = ?, back = ?, archived = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (card.deck, card.source_file, card.card_type, card.module, card.unit,
                     card.front, card.back, int(card.archived), now, card.id),
                )

    def _ensure_state(self, card_id: str, now: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO card_state
                (card_id, direction, repetitions, interval_days, ease_factor, lapses, due_at)
            VALUES (?, 'forward', 0, 0, 2.5, 0, ?)
            """,
            (card_id, now),
        )

    def get_card(self, card_id: str) -> Card | None:
        row = self.conn.execute(
            "SELECT * FROM cards WHERE id = ?", (card_id,)
        ).fetchone()
        return self._row_to_card(row) if row is not None else None

    def list_cards(self, study_filter: StudyFilter | None = None) -> list[Card]:
        query = "SELECT * FROM cards WHERE archived = 0"
        params: list[object] = []
        if study_filter is not None:
            for column, value in (
                ("deck", study_filter.deck),
                ("module", study_filter.module),
                ("unit", study_filter.unit),
                ("card_type", study_filter.card_type),
            ):
                if value is not None:
                    query += f" AND {column} = ?"
                    params.append(value)
        query += " ORDER BY deck, module, unit, id"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_card(r) for r in rows]

    def count_cards(self, study_filter: StudyFilter | None = None) -> int:
        return len(self.list_cards(study_filter))

    def list_cards_with_state(
        self, study_filter: StudyFilter | None = None, direction: str = "forward"
    ) -> list[tuple[Card, CardState | None]]:
        """Return (card, state) pairs for active cards in the given direction.

        Cards with no state for `direction` (never reviewed that way) yield
        ``None`` as their state.
        """
        query = """
            SELECT c.*,
                   cs.direction       AS cs_direction,
                   cs.repetitions     AS cs_repetitions,
                   cs.interval_days   AS cs_interval_days,
                   cs.ease_factor     AS cs_ease_factor,
                   cs.lapses          AS cs_lapses,
                   cs.due_at          AS cs_due_at,
                   cs.last_reviewed_at AS cs_last_reviewed_at
            FROM cards c
            LEFT JOIN card_state cs ON cs.card_id = c.id AND cs.direction = ?
            WHERE c.archived = 0
        """
        params: list[object] = [direction]
        if study_filter is not None:
            for column, value in (
                ("c.deck", study_filter.deck),
                ("c.module", study_filter.module),
                ("c.unit", study_filter.unit),
                ("c.card_type", study_filter.card_type),
            ):
                if value is not None:
                    query += f" AND {column} = ?"
                    params.append(value)
        query += " ORDER BY c.deck, c.module, c.unit, c.id"
        rows = self.conn.execute(query, params).fetchall()

        pairs: list[tuple[Card, CardState | None]] = []
        for row in rows:
            card = self._row_to_card(row)
            if row["cs_direction"] is None:
                pairs.append((card, None))
            else:
                state = CardState(
                    card_id=row["id"],
                    direction=row["cs_direction"],
                    repetitions=row["cs_repetitions"],
                    interval_days=row["cs_interval_days"],
                    ease_factor=row["cs_ease_factor"],
                    lapses=row["cs_lapses"],
                    due_at=row["cs_due_at"],
                    last_reviewed_at=row["cs_last_reviewed_at"],
                )
                pairs.append((card, state))
        return pairs

    def count_new_cards_introduced_since(self, direction: str, since: str) -> int:
        """Count cards whose first review in `direction` happened at or after `since`."""
        row = self.conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT card_id
                FROM review_logs
                WHERE direction = ?
                GROUP BY card_id
                HAVING MIN(reviewed_at) >= ?
            ) AS introduced
            """,
            (direction, since),
        ).fetchone()
        return int(row[0])

    def list_cards_for_source(self, source_file: str, include_archived: bool = False) -> list[Card]:
        query = "SELECT * FROM cards WHERE source_file = ?"
        params: list[object] = [source_file]
        if not include_archived:
            query += " AND archived = 0"
        query += " ORDER BY id"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_card(r) for r in rows]

    def set_archived(self, card_id: str, archived: bool, now: str | None = None) -> None:
        now = now or utc_now_iso()
        with self.conn:
            self.conn.execute(
                "UPDATE cards SET archived = ?, updated_at = ? WHERE id = ?",
                (int(archived), now, card_id),
            )

    # ---- card state ----

    def get_state(self, card_id: str, direction: str = "forward") -> CardState | None:
        row = self.conn.execute(
            "SELECT * FROM card_state WHERE card_id = ? AND direction = ?",
            (card_id, direction),
        ).fetchone()
        return self._row_to_state(row) if row is not None else None

    def upsert_state(self, state: CardState) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO card_state
                    (card_id, direction, repetitions, interval_days, ease_factor, lapses, due_at, last_reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_id, direction) DO UPDATE SET
                    repetitions = excluded.repetitions,
                    interval_days = excluded.interval_days,
                    ease_factor = excluded.ease_factor,
                    lapses = excluded.lapses,
                    due_at = excluded.due_at,
                    last_reviewed_at = excluded.last_reviewed_at
                """,
                (state.card_id, state.direction, state.repetitions, state.interval_days,
                 state.ease_factor, state.lapses, state.due_at, state.last_reviewed_at),
            )

    # ---- review logs ----

    def save_review(self, log: ReviewLog) -> int:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO review_logs (card_id, direction, mode, rating, elapsed_ms, reviewed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (log.card_id, log.direction, log.mode, log.rating, log.elapsed_ms, log.reviewed_at),
            )
        return int(cur.lastrowid)

    def list_reviews(self, card_id: str) -> list[ReviewLog]:
        rows = self.conn.execute(
            "SELECT * FROM review_logs WHERE card_id = ? ORDER BY id", (card_id,)
        ).fetchall()
        return [self._row_to_log(r) for r in rows]

    # ---- row mappers ----

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> Card:
        return Card(
            id=row["id"],
            deck=row["deck"],
            source_file=row["source_file"],
            card_type=row["card_type"],
            module=row["module"],
            unit=row["unit"],
            front=row["front"],
            back=row["back"],
            archived=bool(row["archived"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_state(row: sqlite3.Row) -> CardState:
        return CardState(
            card_id=row["card_id"],
            direction=row["direction"],
            repetitions=row["repetitions"],
            interval_days=row["interval_days"],
            ease_factor=row["ease_factor"],
            lapses=row["lapses"],
            due_at=row["due_at"],
            last_reviewed_at=row["last_reviewed_at"],
        )

    @staticmethod
    def _row_to_log(row: sqlite3.Row) -> ReviewLog:
        return ReviewLog(
            id=row["id"],
            card_id=row["card_id"],
            direction=row["direction"],
            mode=row["mode"],
            rating=row["rating"],
            elapsed_ms=row["elapsed_ms"],
            reviewed_at=row["reviewed_at"],
        )

"""
Lightweight, idempotent schema migration for SQLite / PostgreSQL.

`Base.metadata.create_all()` creates missing *tables* (e.g. `feedback`) but never alters existing ones, so
databases created by an earlier version would miss the new nullable columns. `migrate()` therefore
inspects the live schema and issues `ALTER TABLE ... ADD COLUMN` only for columns that are absent. It is
safe to run on every start-up (a second run changes nothing) and never drops or rewrites data.

After the columns exist, `backfill()` fills the new data for existing rows:
  * cover_url / page_count / isbn for the known seeded titles (only where the value is still NULL),
  * mood_tags derived from genres / keywords / length (only where NULL),
  * a `read` feedback row for every existing rating and a `saved` row for every wishlist item
    (so the new feedback-driven features immediately see the user's history).
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, selectinload

from .models import Book, Feedback, Review, WishlistItem
from .moods import derive_mood_tags

log = logging.getLogger("uvicorn.error")

# table -> {column: SQL type}.  Every new column is nullable so ALTER TABLE is always valid.
NEW_COLUMNS: dict[str, dict[str, str]] = {
    "books": {"cover_url": "VARCHAR(500)", "page_count": "INTEGER", "mood_tags": "JSON"},
    "users": {"favorite_moods": "JSON", "onboarded_at": "DATETIME"},
}


def migrate(engine: Engine) -> list[str]:
    """Add missing columns. Returns the list of 'table.column' that were added."""
    added: list[str] = []
    insp = inspect(engine)
    for table, cols in NEW_COLUMNS.items():
        if not insp.has_table(table):
            continue  # create_all() will build it with every column
        existing = {c["name"] for c in insp.get_columns(table)}
        for name, sqltype in cols.items():
            if name in existing:
                continue
            ddl_type = sqltype
            if engine.dialect.name == "postgresql":
                ddl_type = {"DATETIME": "TIMESTAMP"}.get(sqltype, sqltype)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl_type}'))
            added.append(f"{table}.{name}")
    if added:
        log.info("NextRead migration added columns: %s", ", ".join(added))
    return added


def backfill(db: Session) -> dict[str, int]:
    """Fill the new data for pre-existing rows. Idempotent: only touches NULL / missing values."""
    from .seed import CATALOG_EXTRAS  # local import: seed imports models

    counts = {"books_enriched": 0, "mood_tags": 0, "feedback_read": 0, "feedback_saved": 0}
    for b in db.scalars(select(Book).options(selectinload(Book.genres))):
        extra = CATALOG_EXTRAS.get(b.title)
        changed = False
        if extra:
            if b.cover_url is None and extra.get("cover_url"):
                b.cover_url, changed = extra["cover_url"], True
            if b.page_count is None and extra.get("page_count"):
                b.page_count, changed = extra["page_count"], True
            if b.isbn is None and extra.get("isbn") and not db.scalar(select(Book.id).where(Book.isbn == extra["isbn"])):
                b.isbn, changed = extra["isbn"], True
        if changed:
            counts["books_enriched"] += 1
        if b.mood_tags is None:
            b.mood_tags = derive_mood_tags([g.name for g in b.genres], b.title, b.description, b.page_count)
            counts["mood_tags"] += 1
    db.flush()

    have = {(u, b) for u, b in db.execute(select(Feedback.user_id, Feedback.book_id))}
    for r in db.execute(select(Review.user_id, Review.book_id, Review.created_at)):
        if (r.user_id, r.book_id) not in have:
            db.add(Feedback(user_id=r.user_id, book_id=r.book_id, action="read", created_at=r.created_at))
            have.add((r.user_id, r.book_id))
            counts["feedback_read"] += 1
    for w in db.execute(select(WishlistItem.user_id, WishlistItem.book_id, WishlistItem.added_at)):
        if (w.user_id, w.book_id) not in have:
            db.add(Feedback(user_id=w.user_id, book_id=w.book_id, action="saved", created_at=w.added_at))
            have.add((w.user_id, w.book_id))
            counts["feedback_saved"] += 1
    db.commit()
    return counts

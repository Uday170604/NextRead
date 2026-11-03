"""Shared helpers used by several routers."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Author, Book, Genre, Publisher, Review, User, WishlistItem
from .moods import derive_mood_tags
from .schemas import BookOut


def get_or_create_named(db: Session, model, name: str):
    name = name.strip()
    obj = db.scalar(select(model).where(func.lower(model.name) == name.lower()))
    if not obj:
        obj = model(name=name)
        db.add(obj)
        db.flush()
    return obj


def find_existing_names(db: Session, model, names: list[str]) -> list:
    """Case-insensitive lookup of existing rows; unknown names are ignored (no row creation)."""
    wanted = {n.strip().lower() for n in names if n and n.strip()}
    if not wanted:
        return []
    return list(db.scalars(select(model).where(func.lower(model.name).in_(wanted))))


def like_pattern(q: str) -> str:
    """Escape LIKE wildcards so user input '%' or '_' is matched literally."""
    q = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{q}%"


def apply_book_fields(db: Session, book: Book, data) -> None:
    book.title = data.title.strip()
    book.isbn = (data.isbn or "").strip() or None
    book.description = data.description
    book.publication_year = data.publication_year
    book.publisher = get_or_create_named(db, Publisher, data.publisher) if data.publisher else None
    book.authors = [get_or_create_named(db, Author, a) for a in dict.fromkeys(a.strip() for a in data.authors if a.strip())]
    book.genres = [get_or_create_named(db, Genre, g) for g in dict.fromkeys(g.strip()[:80] for g in data.genres if g.strip())]
    book.cover_url = data.cover_url
    book.page_count = data.page_count
    book.mood_tags = data.mood_tags if data.mood_tags is not None else derive_mood_tags(
        [g.name for g in book.genres], book.title, book.description, book.page_count)


def rating_stats(db: Session, book_ids: list[int]) -> dict[int, tuple[float, int]]:
    """Average rating / count per book, ignoring reviews hidden by moderators."""
    if not book_ids:
        return {}
    rows = db.execute(
        select(Review.book_id, func.avg(Review.rating), func.count())
        .where(Review.book_id.in_(book_ids), Review.is_hidden.is_(False))
        .group_by(Review.book_id)
    )
    return {b: (round(float(a), 2), c) for b, a, c in rows}


def serialize_books(db: Session, books: list[Book], user: User | None = None) -> list[BookOut]:
    ids = [b.id for b in books]
    stats = rating_stats(db, ids)
    wished: set[int] = set()
    mine: dict[int, int] = {}
    if user and ids:
        wished = set(db.scalars(select(WishlistItem.book_id).where(WishlistItem.user_id == user.id, WishlistItem.book_id.in_(ids))))
        mine = dict(db.execute(select(Review.book_id, Review.rating).where(Review.user_id == user.id, Review.book_id.in_(ids))).all())
    out = []
    for b in books:
        avg, cnt = stats.get(b.id, (None, 0))
        out.append(BookOut(
            id=b.id, title=b.title, isbn=b.isbn, description=b.description, publication_year=b.publication_year,
            publisher=b.publisher.name if b.publisher else None,
            authors=[a.name for a in b.authors], genres=[g.name for g in b.genres],
            cover_url=b.cover_url, page_count=b.page_count, mood_tags=list(b.mood_tags or []),
            avg_rating=avg, ratings_count=cnt,
            in_wishlist=(b.id in wished) if user else None, my_rating=mine.get(b.id) if user else None,
        ))
    return out

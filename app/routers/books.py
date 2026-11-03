import difflib
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_optional_user
from ..models import Author, Book, Genre, Review, User
from ..moods import MOODS, parse_mood_keys
from ..recommender import Engine
from ..schemas import BookOut, BookPage, CompareOut, MoodInfo, Suggestion
from ..services import like_pattern, serialize_books

router = APIRouter(tags=["Books"])


@router.get("/books", response_model=BookPage, summary="Browse & search books")
def list_books(
    q: str | None = Query(None, description="keyword in title, description, author or ISBN"),
    genre: str | None = None,
    author: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    min_rating: float | None = Query(None, ge=1, le=5),
    pages_min: int | None = Query(None, ge=1),
    pages_max: int | None = Query(None, ge=1),
    mood: str | None = Query(None, description="one or more mood keys (comma separated); books matching any are returned"),
    sort: Literal["title", "year", "rating", "popular"] = "title",
    skip: int = Query(0, ge=0),
    limit: int = Query(12, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    stats = (
        select(Review.book_id, func.avg(Review.rating).label("avg"), func.count().label("cnt"))
        .where(Review.is_hidden.is_(False)).group_by(Review.book_id).subquery()
    )
    stmt = select(Book).outerjoin(stats, stats.c.book_id == Book.id)
    if q:
        like = like_pattern(q)
        stmt = stmt.where(or_(Book.title.ilike(like, escape="\\"), Book.description.ilike(like, escape="\\"),
                              Book.isbn.ilike(like, escape="\\"), Book.authors.any(Author.name.ilike(like, escape="\\"))))
    if genre:
        stmt = stmt.where(Book.genres.any(func.lower(Genre.name) == genre.lower()))
    if author:
        stmt = stmt.where(Book.authors.any(Author.name.ilike(like_pattern(author), escape="\\")))
    if year_from is not None:
        stmt = stmt.where(Book.publication_year >= year_from)
    if year_to is not None:
        stmt = stmt.where(Book.publication_year <= year_to)
    if min_rating is not None:
        stmt = stmt.where(stats.c.avg >= min_rating)
    if pages_min is not None:
        stmt = stmt.where(Book.page_count >= pages_min)
    if pages_max is not None:
        stmt = stmt.where(Book.page_count <= pages_max)
    if mood:
        try:
            keys = parse_mood_keys(mood)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        if keys:
            stmt = stmt.where(or_(*[cast(Book.mood_tags, String).like(f'%"{k}"%') for k in keys]))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {
        "title": Book.title.asc(),
        "year": Book.publication_year.desc(),
        "rating": func.coalesce(stats.c.avg, 0).desc(),
        "popular": func.coalesce(stats.c.cnt, 0).desc(),
    }[sort]
    stmt = stmt.options(selectinload(Book.authors), selectinload(Book.genres), selectinload(Book.publisher))
    books = db.scalars(stmt.order_by(order, Book.id).offset(skip).limit(limit)).all()
    return BookPage(items=serialize_books(db, list(books), user), total=total, skip=skip, limit=limit,
                    did_you_mean=_did_you_mean(db, q) if q and total == 0 else None)


_WORD = re.compile(r"[\w'’-]+")


def _did_you_mean(db: Session, q: str) -> str | None:
    """'harry poter' -> 'harry potter'. Whole-phrase match first, then word-by-word correction."""
    titles = list(db.scalars(select(Book.title)))
    names = titles + list(db.scalars(select(Author.name))) + list(db.scalars(select(Genre.name)))
    low = {n.lower(): n for n in names}
    ql = q.strip().lower()
    if not ql or ql in low:
        return None
    whole = difflib.get_close_matches(ql, list(low), n=1, cutoff=0.6)
    if whole:
        return low[whole[0]]
    vocab = {w for n in low for w in _WORD.findall(n)}
    fixed, changed = [], False
    for w in _WORD.findall(ql):
        if w in vocab or len(w) < 3:
            fixed.append(w)
            continue
        m = difflib.get_close_matches(w, list(vocab), n=1, cutoff=0.75)
        fixed.append(m[0] if m else w)
        changed = changed or bool(m)
    return " ".join(fixed) if changed else None


@router.get("/moods", response_model=list[MoodInfo], summary="Mood / intent chips")
def moods():
    return [MoodInfo(key=m.key, label=m.label, emoji=m.emoji, blurb=m.blurb) for m in MOODS.values()]


@router.get("/books/suggest", response_model=list[Suggestion], summary="Instant search suggestions (title / author / genre)")
def suggest(q: str = Query(min_length=1, max_length=80), limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    like, prefix = like_pattern(q), like_pattern(q)[1:]
    out: list[Suggestion] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, text: str, book_id: int | None = None) -> None:
        if (kind, text.lower()) not in seen and len(out) < limit:
            seen.add((kind, text.lower()))
            out.append(Suggestion(type=kind, text=text, book_id=book_id))

    for b in db.execute(select(Book.id, Book.title).where(Book.title.ilike(like, escape="\\"))
                        .order_by(Book.title.ilike(prefix, escape="\\").desc(), Book.title).limit(limit)):
        add("title", b.title, b.id)
    for n in db.scalars(select(Author.name).where(Author.name.ilike(like, escape="\\")).order_by(Author.name).limit(4)):
        add("author", n)
    for n in db.scalars(select(Genre.name).where(Genre.name.ilike(like, escape="\\")).order_by(Genre.name).limit(3)):
        add("genre", n)
    return out


@router.get("/books/compare", response_model=CompareOut, summary="Compare two books side by side")
def compare(a: int, b: int, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    if a == b:
        raise HTTPException(422, "Pick two different books to compare")
    ba, bb = db.get(Book, a), db.get(Book, b)
    if not ba or not bb:
        raise HTTPException(404, "Book not found")
    oa, ob = serialize_books(db, [ba, bb], user)
    shared = lambda x, y: [v for v in x if v in y]  # noqa: E731
    fit: dict[str, int | None] = {"a": None, "b": None}
    better, why = None, ""
    if user:
        engine = Engine(db)
        ctx = engine.context(user)
        ra, rb = ctx.rec(a), ctx.rec(b)
        fit = {"a": ra.match_pct, "b": rb.match_pct}
        diff = ra.match_pct - rb.match_pct
        better = "tie" if abs(diff) < 3 else "a" if diff > 0 else "b"
        win, lose, rw = (oa, ob, ra) if diff >= 0 else (ob, oa, rb)
        why = (f"“{oa.title}” and “{ob.title}” are about equally close to your taste." if better == "tie" else
               f"“{win.title}” fits you better ({max(ra.match_pct, rb.match_pct)}% vs {min(ra.match_pct, rb.match_pct)}%): {rw.reason[0].lower() + rw.reason[1:]}.")
    else:
        ra_, rb_ = oa.avg_rating or 0, ob.avg_rating or 0
        better = "tie" if abs(ra_ - rb_) < 0.15 else "a" if ra_ > rb_ else "b"
        why = "Log in to see which one fits your taste. " + (
            "Readers rate them about the same." if better == "tie" else
            f"Readers currently rate “{(oa if better == 'a' else ob).title}” higher.")
    return CompareOut(a=oa, b=ob, shared_genres=shared(oa.genres, ob.genres), shared_authors=shared(oa.authors, ob.authors),
                      shared_moods=shared(oa.mood_tags, ob.mood_tags), fit=fit, better_fit=better, why=why)


@router.get("/books/{book_id}", response_model=BookOut, summary="View book details")
def get_book(book_id: int, db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return serialize_books(db, [book], user)[0]


@router.get("/books/{book_id}/similar", response_model=list[BookOut], summary="Books similar to this one")
def similar_books(book_id: int, limit: int = Query(6, ge=1, le=20), db: Session = Depends(get_db),
                  user: User | None = Depends(get_optional_user)):
    if not db.get(Book, book_id):
        raise HTTPException(404, "Book not found")
    engine = Engine(db)
    ids = [b for b, _ in engine.similar_books(book_id, limit)]
    books = {b.id: b for b in db.scalars(select(Book).where(Book.id.in_(ids)))}
    return serialize_books(db, [books[i] for i in ids if i in books], user)


@router.get("/genres", response_model=list[str], summary="List all genres")
def genres(db: Session = Depends(get_db)):
    return list(db.scalars(select(Genre.name).order_by(Genre.name)))


@router.get("/authors", response_model=list[str], summary="List all authors")
def authors(db: Session = Depends(get_db)):
    return list(db.scalars(select(Author.name).order_by(Author.name)))

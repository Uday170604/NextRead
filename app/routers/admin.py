import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Book, Feedback, Review, User, WishlistItem
from ..schemas import AdminReviewOut, AdminUserOut, AnalyticsOut, BookIn, BookOut, Stats
from ..services import apply_book_fields, like_pattern, rating_stats, serialize_books

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


# ---------- book management ----------
@router.post("/books", response_model=BookOut, status_code=status.HTTP_201_CREATED, summary="Add a book")
def add_book(data: BookIn, db: Session = Depends(get_db)):
    if data.isbn and db.scalar(select(Book).where(Book.isbn == data.isbn)):
        raise HTTPException(409, "A book with this ISBN already exists")
    book = Book()
    apply_book_fields(db, book, data)
    db.add(book)
    db.commit()
    return serialize_books(db, [book])[0]


@router.put("/books/{book_id}", response_model=BookOut, summary="Update a book")
def update_book(book_id: int, data: BookIn, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    apply_book_fields(db, book, data)
    db.commit()
    return serialize_books(db, [book])[0]


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a book")
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    db.delete(book)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/import/openlibrary", summary="Import books from the Open Library API (external data source)")
def import_openlibrary(query: str = Query(min_length=2), limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    try:
        resp = httpx.get("https://openlibrary.org/search.json", timeout=15,
                         params={"q": query, "limit": limit, "fields": "title,author_name,first_publish_year,subject,isbn,publisher,cover_i,number_of_pages_median"})
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"External book API unavailable: {exc}")
    return _import_docs(db, docs)


def _import_docs(db: Session, docs: list[dict]) -> dict:
    created, skipped = 0, 0
    for d in docs:
        title = (d.get("title") or "").strip()
        authors = d.get("author_name") or []
        genres = (d.get("subject") or [])[:3] or ["General"]
        if not title or not authors:
            skipped += 1
            continue
        isbn = (d.get("isbn") or [None])[0]
        isbn = str(isbn)[:20] if isbn else None
        exists = db.scalar(select(Book).where(func.lower(Book.title) == title.lower())) or (
            db.scalar(select(Book).where(Book.isbn == isbn)) if isbn else None)
        if exists:
            skipped += 1
            continue
        year = d.get("first_publish_year")
        cover_i, pages = d.get("cover_i"), d.get("number_of_pages_median")
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg?default=false" if isinstance(cover_i, int) and cover_i > 0 else (
            f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false" if isbn else None)
        pages = pages if isinstance(pages, int) and 1 <= pages <= 10000 else None
        try:
            data = BookIn(title=title[:255], isbn=isbn, publication_year=year if isinstance(year, int) and 0 <= year <= 2100 else None,
                          publisher=((d.get("publisher") or [None])[0] or None) and str((d.get("publisher") or [None])[0])[:150],
                          authors=[str(a) for a in authors[:3]], genres=[str(g)[:80] for g in genres],
                          cover_url=cover_url, page_count=pages)
        except ValueError:
            skipped += 1
            continue
        book = Book()
        apply_book_fields(db, book, data)
        db.add(book)
        db.flush()  # make the new row visible to the duplicate checks of the next record
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


# ---------- review moderation ----------
@router.get("/reviews", response_model=list[AdminReviewOut], summary="List reviews for moderation")
def list_reviews(only_with_comment: bool = True, hidden: bool | None = None, skip: int = 0, limit: int = Query(50, le=200),
                 db: Session = Depends(get_db)):
    stmt = select(Review).order_by(Review.updated_at.desc())
    if only_with_comment:
        stmt = stmt.where(Review.comment.is_not(None), Review.comment != "")
    if hidden is not None:
        stmt = stmt.where(Review.is_hidden.is_(hidden))
    rows = db.scalars(stmt.offset(skip).limit(limit))
    return [AdminReviewOut(user_id=r.user_id, user_name=r.user.name, user_email=r.user.email, book_id=r.book_id,
                           book_title=r.book.title, rating=r.rating, comment=r.comment, is_hidden=r.is_hidden,
                           created_at=r.created_at, updated_at=r.updated_at) for r in rows]


@router.patch("/reviews/{user_id}/{book_id}", summary="Hide or unhide a review")
def moderate_review(user_id: int, book_id: int, hidden: bool = True, db: Session = Depends(get_db)):
    review = db.get(Review, (user_id, book_id))
    if not review:
        raise HTTPException(404, "Review not found")
    review.is_hidden = hidden
    db.commit()
    return {"user_id": user_id, "book_id": book_id, "is_hidden": hidden}


@router.delete("/reviews/{user_id}/{book_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a review")
def delete_review(user_id: int, book_id: int, db: Session = Depends(get_db)):
    review = db.get(Review, (user_id, book_id))
    if not review:
        raise HTTPException(404, "Review not found")
    db.delete(review)
    fb = db.get(Feedback, (user_id, book_id))
    if fb and fb.action == "read":
        db.delete(fb)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- system maintenance ----------
@router.get("/stats", response_model=Stats, summary="System statistics")
def stats(db: Session = Depends(get_db)):
    avg = db.scalar(select(func.avg(Review.rating)).where(Review.is_hidden.is_(False)))
    stat = rating_stats(db, list(db.scalars(select(Book.id))))
    top_ids = [b for b, _ in sorted(stat.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[:5]]
    top = [db.get(Book, i) for i in top_ids]
    return Stats(
        users=db.scalar(select(func.count()).select_from(User)), books=db.scalar(select(func.count()).select_from(Book)),
        reviews=db.scalar(select(func.count()).select_from(Review)),
        wishlist_items=db.scalar(select(func.count()).select_from(WishlistItem)),
        average_rating=round(float(avg), 2) if avg else None, top_books=serialize_books(db, top),
    )


@router.get("/users", response_model=list[AdminUserOut], summary="List users (for account management)")
def list_users(q: str | None = None, skip: int = 0, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Review.user_id, func.count()).group_by(Review.user_id)).all())
    stmt = select(User).order_by(User.id)
    if q:
        stmt = stmt.where(User.email.ilike(like_pattern(q), escape="\\") | User.name.ilike(like_pattern(q), escape="\\"))
    return [AdminUserOut(id=u.id, name=u.name, email=u.email, role=u.role, is_active=u.is_active, created_at=u.created_at,
                         reviews_count=counts.get(u.id, 0)) for u in db.scalars(stmt.offset(skip).limit(limit))]


@router.patch("/users/{user_id}/active", summary="Activate / deactivate a user account")
def set_user_active(user_id: int, active: bool, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.role == "admin":
        raise HTTPException(400, "Cannot deactivate an admin")
    user.is_active = active
    db.commit()
    return {"user_id": user_id, "is_active": active}


@router.get("/analytics", response_model=AnalyticsOut, summary="Recommendation analytics: most liked / rejected, acceptance rate")
def analytics(limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)):
    totals = {a: n for a, n in db.execute(select(Feedback.action, func.count()).group_by(Feedback.action))}
    totals = {a: totals.get(a, 0) for a in ("interested", "saved", "read", "not_interested")}
    accepted = totals["interested"] + totals["saved"] + totals["read"]
    decided = accepted + totals["not_interested"]

    def top(actions: tuple[str, ...]) -> list[dict]:
        n = func.sum(case((Feedback.action.in_(actions), 1), else_=0)).label("n")
        rows = db.execute(select(Book.id, Book.title, n).join(Feedback, Feedback.book_id == Book.id)
                          .group_by(Book.id, Book.title).having(n > 0).order_by(n.desc(), Book.title).limit(limit)).all()
        return [{"book_id": r.id, "title": r.title, "count": int(r.n)} for r in rows]

    reasons = {r or "none": n for r, n in db.execute(
        select(Feedback.reason, func.count()).where(Feedback.action == "not_interested").group_by(Feedback.reason))}
    return AnalyticsOut(totals=totals, acceptance_rate=round(accepted / decided, 3) if decided else None,
                        most_liked=top(("interested", "saved")), most_rejected=top(("not_interested",)), reject_reasons=reasons)

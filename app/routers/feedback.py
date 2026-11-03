"""Explicit feedback on books: interested / not_interested / saved / read (+ undo)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Book, Feedback, Review, User, WishlistItem, utcnow
from ..schemas import FeedbackIn, FeedbackItem, FeedbackOut, UndoOut
from ..services import serialize_books
from ..taste import progress_for

router = APIRouter(prefix="/feedback", tags=["Feedback"])


def set_feedback(db: Session, user: User, book_id: int, action: str, reason: str | None = None, rating: int | None = None,
                 sync_wishlist: bool = True) -> Feedback:
    """Upsert the user's single decision for a book and keep the wishlist / rating in sync. Caller commits."""
    fb = db.get(Feedback, (user.id, book_id))
    was_saved = bool(fb and fb.action == "saved")
    if fb:
        fb.action, fb.created_at = action, utcnow()
    else:
        fb = Feedback(user_id=user.id, book_id=book_id, action=action)
        db.add(fb)
    fb.reason = reason if action == "not_interested" else None

    wish = db.get(WishlistItem, (user.id, book_id))
    if not sync_wishlist:
        pass
    elif action == "saved":
        if not wish:
            db.add(WishlistItem(user_id=user.id, book_id=book_id))
    elif wish and (was_saved or action == "not_interested"):
        db.delete(wish)                       # a decision other than "saved" supersedes the old bookmark

    if action == "read" and rating is not None:
        review = db.get(Review, (user.id, book_id))
        if review:
            review.rating = rating
        else:
            db.add(Review(user_id=user.id, book_id=book_id, rating=rating))
    return fb


def clear_feedback(db: Session, user: User, book_id: int) -> tuple[Feedback | None, bool]:
    """Undo a decision. Returns (removed row, rating_kept). Caller commits."""
    fb = db.get(Feedback, (user.id, book_id))
    if not fb:
        return None, False
    kept = False
    if fb.action == "saved":
        wish = db.get(WishlistItem, (user.id, book_id))
        if wish:
            db.delete(wish)
    elif fb.action == "read":
        review = db.get(Review, (user.id, book_id))
        if review:
            if review.comment:
                kept = True                   # never destroy a written review through an undo
            else:
                db.delete(review)
    db.delete(fb)
    return fb, kept


@router.post("", response_model=FeedbackOut, summary="Record a decision about a book (swipe / button)")
def give_feedback(data: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Book, data.book_id):
        raise HTTPException(404, "Book not found")
    fb = set_feedback(db, user, data.book_id, data.action, data.reason, data.rating)
    db.commit()
    review = db.get(Review, (user.id, data.book_id))
    return FeedbackOut(book_id=fb.book_id, action=fb.action, reason=fb.reason, rating=review.rating if review else None,
                       created_at=fb.created_at, taste=progress_for(db, user))


@router.delete("/{book_id}", response_model=UndoOut, summary="Undo my decision about a book")
def undo_feedback(book_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    removed, kept = clear_feedback(db, user, book_id)
    if not removed:
        raise HTTPException(404, "No feedback recorded for this book")
    db.commit()
    return UndoOut(book_id=book_id, removed=removed.action, rating_kept=kept, taste=progress_for(db, user))


@router.get("", response_model=list[FeedbackItem], summary="My decisions, optionally filtered by action")
def list_feedback(action: Literal["interested", "not_interested", "saved", "read"] | None = None,
                  skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(Feedback).where(Feedback.user_id == user.id).order_by(Feedback.created_at.desc(), Feedback.book_id)
    if action:
        stmt = stmt.where(Feedback.action == action)
    rows = list(db.scalars(stmt.offset(skip).limit(limit)))
    books = {b.id: b for b in db.scalars(select(Book).where(Book.id.in_([r.book_id for r in rows])))}
    rows = [r for r in rows if r.book_id in books]
    out = serialize_books(db, [books[r.book_id] for r in rows], user)
    return [FeedbackItem(book=b, action=r.action, reason=r.reason, rating=b.my_rating, created_at=r.created_at)
            for b, r in zip(out, rows)]

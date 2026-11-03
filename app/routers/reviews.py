from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Book, Feedback, Review, User
from ..schemas import MyReviewOut, ReviewIn, ReviewOut
from .feedback import set_feedback

router = APIRouter(tags=["Ratings & Reviews"])


def _out(r: Review) -> ReviewOut:
    return ReviewOut(user_id=r.user_id, user_name=r.user.name, book_id=r.book_id, rating=r.rating,
                     comment=r.comment, created_at=r.created_at, updated_at=r.updated_at)


@router.get("/books/{book_id}/reviews", response_model=list[ReviewOut], summary="Reviews of a book (moderated)")
def book_reviews(book_id: int, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    if not db.get(Book, book_id):
        raise HTTPException(404, "Book not found")
    rows = db.scalars(select(Review).where(Review.book_id == book_id, Review.is_hidden.is_(False))
                      .order_by(Review.updated_at.desc()).offset(skip).limit(limit))
    return [_out(r) for r in rows]


@router.put("/books/{book_id}/review", response_model=ReviewOut, summary="Rate a book / leave or edit a review")
def upsert_review(book_id: int, data: ReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Book, book_id):
        raise HTTPException(404, "Book not found")
    review = db.get(Review, (user.id, book_id))
    if review:
        review.rating, review.comment = data.rating, data.comment
    else:
        review = Review(user_id=user.id, book_id=book_id, rating=data.rating, comment=data.comment)
        db.add(review)
    set_feedback(db, user, book_id, "read", sync_wishlist=False)   # rating a book = "already read it"
    db.commit()
    db.refresh(review)
    return _out(review)


@router.delete("/books/{book_id}/review", status_code=status.HTTP_204_NO_CONTENT, summary="Delete my review")
def delete_review(book_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    review = db.get(Review, (user.id, book_id))
    if not review:
        raise HTTPException(404, "You have not reviewed this book")
    db.delete(review)
    fb = db.get(Feedback, (user.id, book_id))
    if fb and fb.action == "read":
        db.delete(fb)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reviews/mine", response_model=list[MyReviewOut], summary="My reading history (rated books)")
def my_reviews(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Review).where(Review.user_id == user.id).order_by(Review.updated_at.desc()))
    return [MyReviewOut(**_out(r).model_dump(), book_title=r.book.title, is_hidden=r.is_hidden) for r in rows]

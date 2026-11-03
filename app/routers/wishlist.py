from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Book, Feedback, User, WishlistItem
from ..schemas import BookOut
from ..services import serialize_books
from .feedback import set_feedback

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


@router.get("", response_model=list[BookOut], summary="My wishlist")
def my_wishlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    books = db.scalars(select(Book).join(WishlistItem, WishlistItem.book_id == Book.id)
                       .where(WishlistItem.user_id == user.id).order_by(WishlistItem.added_at.desc()))
    return serialize_books(db, list(books), user)


@router.post("/{book_id}", status_code=status.HTTP_201_CREATED, summary="Add a book to my wishlist")
def add_to_wishlist(book_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Book, book_id):
        raise HTTPException(404, "Book not found")
    if db.get(WishlistItem, (user.id, book_id)):
        raise HTTPException(409, "Book already in wishlist")
    fb = db.get(Feedback, (user.id, book_id))
    if fb and fb.action == "read":             # keep an existing "already read" decision
        db.add(WishlistItem(user_id=user.id, book_id=book_id))
    else:
        set_feedback(db, user, book_id, "saved")   # also creates the wishlist row
    db.commit()
    return {"detail": "Added to wishlist", "book_id": book_id}


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a book from my wishlist")
def remove_from_wishlist(book_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(WishlistItem, (user.id, book_id))
    if not item:
        raise HTTPException(404, "Book not in wishlist")
    db.delete(item)
    fb = db.get(Feedback, (user.id, book_id))
    if fb and fb.action == "saved":
        db.delete(fb)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

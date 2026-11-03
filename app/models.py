"""
Relational model (3NF / BCNF) for NextRead.

Strong entities : User, Book, Author, Genre, Publisher
Weak entities   : Review, WishlistItem, Recommendation, Feedback (identified by User + Book)
Junction tables : book_authors, book_genres, user_favorite_genres, user_favorite_authors
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

ROLES = ("reader", "student", "professor", "admin")
FEEDBACK_ACTIONS = ("interested", "not_interested", "saved", "read")
REJECT_REASONS = ("too_long", "not_my_genre", "know_story")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---- many-to-many junction tables (1NF: no multi-valued attributes) -------------------------
book_authors = Table(
    "book_authors", Base.metadata,
    Column("book_id", ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("author_id", ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True),
)
book_genres = Table(
    "book_genres", Base.metadata,
    Column("book_id", ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)
user_favorite_genres = Table(
    "user_favorite_genres", Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)
user_favorite_authors = Table(
    "user_favorite_authors", Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("author_id", ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('reader','student','professor','admin')", name="ck_user_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="reader")
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    # composite attribute "address" stored as its components
    street: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    favorite_moods: Mapped[list | None] = mapped_column(JSON, nullable=True)  # chosen during onboarding
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    favorite_genres: Mapped[list["Genre"]] = relationship(secondary=user_favorite_genres)  # multi-valued
    favorite_authors: Mapped[list["Author"]] = relationship(secondary=user_favorite_authors)
    reviews: Mapped[list["Review"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    wishlist: Mapped[list["WishlistItem"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def age(self) -> int | None:  # derived attribute
        if not self.date_of_birth:
            return None
        t = date.today()
        return t.year - self.date_of_birth.year - ((t.month, t.day) < (self.date_of_birth.month, self.date_of_birth.day))


class Author(Base):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)


class Genre(Base):
    __tablename__ = "genres"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)


class Publisher(Base):  # split out of Book to remove the transitive dependency (3NF)
    __tablename__ = "publishers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    isbn: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publisher_id: Mapped[int | None] = mapped_column(ForeignKey("publishers.id", ondelete="SET NULL"), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mood_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    publisher: Mapped[Publisher | None] = relationship()
    authors: Mapped[list[Author]] = relationship(secondary=book_authors)
    genres: Mapped[list[Genre]] = relationship(secondary=book_genres)
    reviews: Mapped[list["Review"]] = relationship(back_populates="book", cascade="all, delete-orphan")


class Review(Base):
    """Weak entity: identified by (user_id, book_id) -> one review/rating per user per book."""
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)  # set by admin moderation
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="reviews")
    book: Mapped[Book] = relationship(back_populates="reviews")


class WishlistItem(Base):
    """Weak entity: a book saved by a user for later."""
    __tablename__ = "wishlist_items"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="wishlist")
    book: Mapped[Book] = relationship()


class Recommendation(Base):
    """Weak entity: stored output of the recommendation engine for a user."""
    __tablename__ = "recommendations"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    algorithm: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(String(255))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="recommendations")
    book: Mapped[Book] = relationship()


class Feedback(Base):
    """Weak entity: one explicit decision per (user, book): interested | not_interested | saved | read."""
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("action IN ('interested','not_interested','saved','read')", name="ck_feedback_action"),
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), primary_key=True, index=True)
    action: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str | None] = mapped_column(String(20), nullable=True)  # only for not_interested
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship()
    book: Mapped[Book] = relationship()

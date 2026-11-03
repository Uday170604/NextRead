import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .moods import MOODS

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SelfRole = Literal["reader", "student", "professor"]  # "admin" cannot be self-assigned
FeedbackAction = Literal["interested", "not_interested", "saved", "read"]
RejectReason = Literal["too_long", "not_my_genre", "know_story"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- users / auth ----------------
class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=128)
    role: SelfRole = "reader"
    date_of_birth: date | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    favorite_genres: list[str] = []

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("invalid email address")
        return v


class UserUpdate(BaseModel):
    # name / role are optional but, when sent, can never be null (NOT NULL columns)
    name: str | None = Field(default=None, min_length=2, max_length=100)
    role: SelfRole | None = None
    date_of_birth: date | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None


class Preferences(BaseModel):
    favorite_genres: list[str] = []
    favorite_authors: list[str] = []


class UserOut(ORM):
    id: int
    name: str
    email: str
    role: str
    date_of_birth: date | None
    age: int | None
    street: str | None
    city: str | None
    state: str | None
    favorite_genres: list[str] = []
    favorite_authors: list[str] = []
    favorite_moods: list[str] = []
    onboarded: bool = False
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------------- books ----------------
class BookIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    isbn: str | None = None
    description: str | None = None
    publication_year: int | None = Field(default=None, ge=0, le=2100)
    publisher: str | None = None
    authors: list[str] = Field(min_length=1)
    genres: list[str] = Field(min_length=1)
    cover_url: str | None = Field(default=None, max_length=500)
    page_count: int | None = Field(default=None, ge=1, le=10000)
    mood_tags: list[str] | None = None  # None -> derived from genres / keywords / length

    @field_validator("cover_url")
    @classmethod
    def _cover(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if not v:
            return None
        if not re.match(r"^https?://[^\s]+$", v, re.I):
            raise ValueError("cover_url must be an http(s) URL")
        return v

    @field_validator("mood_tags")
    @classmethod
    def _moods(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = list(dict.fromkeys(x.strip().lower() for x in v if x and x.strip()))
        bad = [x for x in cleaned if x not in MOODS]
        if bad:
            raise ValueError(f"unknown mood tag(s): {', '.join(bad)}; allowed: {', '.join(MOODS)}")
        return cleaned

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be blank")
        return v

    @field_validator("authors", "genres")
    @classmethod
    def _names(cls, v: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(x.strip()[:150] for x in v if x and x.strip()))
        if not cleaned:
            raise ValueError("at least one non-blank value is required")
        return cleaned


class BookOut(BaseModel):
    id: int
    title: str
    isbn: str | None
    description: str | None
    publication_year: int | None
    publisher: str | None
    authors: list[str]
    genres: list[str]
    cover_url: str | None = None
    page_count: int | None = None
    mood_tags: list[str] = []
    avg_rating: float | None
    ratings_count: int
    in_wishlist: bool | None = None  # only when the caller is logged in
    my_rating: int | None = None


class BookPage(BaseModel):
    items: list[BookOut]
    total: int
    skip: int
    limit: int
    did_you_mean: str | None = None  # typo suggestion when a text search finds nothing


# ---------------- reviews ----------------
class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    user_id: int
    user_name: str
    book_id: int
    rating: int
    comment: str | None
    created_at: datetime
    updated_at: datetime


class MyReviewOut(ReviewOut):
    book_title: str
    is_hidden: bool


# ---------------- recommendations ----------------
class BreakdownItem(BaseModel):
    key: str
    label: str
    value: float          # 0..1 strength of this signal for the book
    weight: float         # share of the blend this signal received for this user
    contribution: float   # value * weight


class RecommendationOut(BaseModel):
    book: BookOut
    score: float
    match_pct: int = 0
    personalised: bool = False
    algorithm: str
    reason: str
    tag: str = ""         # short chip such as "Hidden gem"
    breakdown: list[BreakdownItem] | None = None
    mood_signals: list[str] | None = None


class RecRow(BaseModel):
    id: str
    title: str
    subtitle: str
    items: list[RecommendationOut]


class TasteProgress(BaseModel):
    learned_pct: int
    signals: int


class DeckOut(BaseModel):
    cards: list[RecommendationOut]
    taste: TasteProgress
    calibrating: bool


class ExplainOut(BaseModel):
    book_id: int
    title: str
    score: float
    match_pct: int
    reason: str
    breakdown: list[BreakdownItem]
    penalties: list[dict]
    mood_matches: list[dict]
    summary: str


class WeeklyOut(BaseModel):
    week_label: str
    name: str
    picks: list[RecommendationOut]
    rated: int
    interested: int
    saved: int
    passed: int
    top_genre: str | None
    taste: TasteProgress


class MoodInfo(BaseModel):
    key: str
    label: str
    emoji: str
    blurb: str


# ---------------- feedback ----------------
class FeedbackIn(BaseModel):
    book_id: int
    action: FeedbackAction
    rating: int | None = Field(default=None, ge=1, le=5, description="optional, only used with action=read")
    reason: RejectReason | None = Field(default=None, description="optional, only used with action=not_interested")


class FeedbackOut(BaseModel):
    book_id: int
    action: str
    reason: str | None
    rating: int | None = None
    created_at: datetime
    taste: TasteProgress


class FeedbackItem(BaseModel):
    book: BookOut
    action: str
    reason: str | None
    rating: int | None
    created_at: datetime


class UndoOut(BaseModel):
    book_id: int
    removed: str
    rating_kept: bool = False
    taste: TasteProgress


# ---------------- profile / taste ----------------
class OnboardingIn(BaseModel):
    favorite_genres: list[str] = []
    favorite_moods: list[str] = []

    @field_validator("favorite_moods")
    @classmethod
    def _moods(cls, v: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(x.strip().lower() for x in v if x and x.strip()))
        bad = [x for x in cleaned if x not in MOODS]
        if bad:
            raise ValueError(f"unknown mood(s): {', '.join(bad)}")
        return cleaned


class TasteOut(BaseModel):
    learned_pct: int
    signals: int
    needs_onboarding: bool
    genres: list[dict]          # {name, score (0..100), count, avg_rating}
    authors: list[dict]         # {name, count, avg_rating}
    moods: list[dict]           # {key, label, emoji, pct}
    avg_rating: float | None
    ratings_count: int
    counts: dict[str, int]
    dna: str


# ---------------- compare / search ----------------
class CompareOut(BaseModel):
    a: BookOut
    b: BookOut
    shared_genres: list[str]
    shared_authors: list[str]
    shared_moods: list[str]
    fit: dict[str, int | None]   # match % per book for the logged-in user (None when anonymous)
    better_fit: Literal["a", "b", "tie"] | None
    why: str


class Suggestion(BaseModel):
    type: Literal["title", "author", "genre"]
    text: str
    book_id: int | None = None


class AnalyticsOut(BaseModel):
    totals: dict[str, int]
    acceptance_rate: float | None
    most_liked: list[dict]
    most_rejected: list[dict]
    reject_reasons: dict[str, int]


class AdminUserOut(ORM):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    reviews_count: int = 0


class AdminReviewOut(MyReviewOut):
    user_email: str


class Stats(BaseModel):
    users: int
    books: int
    reviews: int
    wishlist_items: int
    average_rating: float | None
    top_books: list[BookOut]

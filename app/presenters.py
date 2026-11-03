"""Turn engine objects into API schemas."""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Book, User
from .recommender import COMPONENT_LABELS, Rec
from .schemas import BreakdownItem, RecommendationOut
from .services import serialize_books


def breakdown_of(rec: Rec) -> list[BreakdownItem]:
    return [
        BreakdownItem(key=k, label=COMPONENT_LABELS[k], value=round(v, 3), weight=rec.weights.get(k, 0.0),
                      contribution=round(v * rec.weights.get(k, 0.0), 3))
        for k, v in rec.components.items() if k in COMPONENT_LABELS
    ]


def to_out(db: Session, recs: list[Rec], user: User | None, breakdown: bool = False) -> list[RecommendationOut]:
    books = {b.id: b for b in db.scalars(
        select(Book).where(Book.id.in_([r.book_id for r in recs]))
        .options(selectinload(Book.authors), selectinload(Book.genres), selectinload(Book.publisher)))}
    ordered = [r for r in recs if r.book_id in books]
    out = serialize_books(db, [books[r.book_id] for r in ordered], user)
    return [
        RecommendationOut(book=b, score=r.score, match_pct=r.match_pct, personalised=r.personalised, algorithm=r.algorithm,
                          reason=r.reason, tag=r.tag, breakdown=breakdown_of(r) if breakdown else None,
                          mood_signals=r.mood_signals)
        for b, r in zip(out, ordered)
    ]

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_optional_user
from ..models import Book, Feedback, Recommendation, Review, User
from ..moods import MOODS, parse_mood_keys, score_mood
from ..presenters import breakdown_of, to_out
from ..recommender import MMR_LAMBDA_COLD, Engine
from ..schemas import DeckOut, ExplainOut, RecommendationOut, RecRow, TasteProgress, WeeklyOut
from ..taste import build_taste

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


def _ids(raw: str | None) -> list[int]:
    try:
        return [int(x) for x in (raw or "").split(",") if x.strip()][:500]
    except ValueError:
        raise HTTPException(422, "exclude must be a comma separated list of book ids")


@router.get("", response_model=list[RecommendationOut], summary="Get personalised recommendations")
def get_recommendations(limit: int = Query(10, ge=1, le=50), user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    recs = Engine(db).recommend(user, limit)
    # persist the latest list (Recommendation entity) so it can be audited / reused
    db.execute(delete(Recommendation).where(Recommendation.user_id == user.id))
    db.add_all(Recommendation(user_id=user.id, book_id=r.book_id, score=r.score, algorithm=r.algorithm, reason=r.reason[:255])
               for r in recs)
    db.commit()
    return to_out(db, recs, user)


@router.get("/trending", response_model=list[RecommendationOut], summary="Trending / most popular books (no login needed)")
def trending(limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    return to_out(db, Engine(db).trending(limit), user)


@router.get("/featured", response_model=RecommendationOut, summary="The one big 'Your next read' pick (with score breakdown)")
def featured(exclude: str | None = Query(None, description="comma separated book ids already shown ('Show me another')"),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    recs = Engine(db).recommend(user, 1, exclude=_ids(exclude), explore=False)
    if not recs:
        raise HTTPException(404, "Nothing left to recommend - you have decided on every book in the catalogue")
    return to_out(db, recs, user, breakdown=True)[0]


@router.get("/rows", response_model=list[RecRow], summary="All Netflix-style rows in one call")
def rows(limit: int = Query(12, ge=3, le=24), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    engine = Engine(db)
    out = []
    for row in engine.rows(user, limit):
        out.append(RecRow(id=row["id"], title=row["title"], subtitle=row["subtitle"], items=to_out(db, row["recs"], user)))
    return out


@router.get("/mood", response_model=list[RecommendationOut], summary="Re-rank recommendations for one or two moods")
def mood(moods: str = Query(..., description="one or two comma separated mood keys, e.g. light,quick"),
         limit: int = Query(12, ge=1, le=50), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        keys = parse_mood_keys(moods)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if not 1 <= len(keys) <= 2:
        raise HTTPException(422, "choose one or two moods")
    return to_out(db, Engine(db).mood_recommend(user, keys, limit), user)


@router.get("/deck", response_model=DeckOut, summary="Swipe-deck cards (re-ranks after every piece of feedback)")
def deck(limit: int = Query(10, ge=1, le=30), exclude: str | None = None, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    engine = Engine(db)
    ctx = engine.context(user)
    recs = engine.recommend(user, limit, exclude=_ids(exclude), lam=(0.6 if ctx.has_profile else MMR_LAMBDA_COLD) if ctx.calibrating else None, ctx=ctx)
    return DeckOut(cards=to_out(db, recs, user), taste=TasteProgress(learned_pct=ctx.pct, signals=len(ctx.excluded)),
                   calibrating=ctx.calibrating)


@router.get("/weekly", response_model=WeeklyOut, summary="Weekly 'Your picks' summary card")
def weekly(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    counts = dict(db.execute(select(Feedback.action, func.count()).where(Feedback.user_id == user.id, Feedback.created_at >= since)
                             .group_by(Feedback.action)).all())
    rated = db.scalar(select(func.count()).select_from(Review).where(Review.user_id == user.id, Review.created_at >= since)) or 0
    engine = Engine(db)
    ctx = engine.context(user)
    taste = build_taste(db, user)
    picks = to_out(db, engine.recommend(user, 3, explore=False, ctx=ctx), user)
    return WeeklyOut(week_label=f"Week of {(datetime.now() - timedelta(days=datetime.now().weekday())):%d %b}", name=user.name.split()[0],
                     picks=picks, rated=rated, interested=counts.get("interested", 0), saved=counts.get("saved", 0),
                     passed=counts.get("not_interested", 0), top_genre=taste.genres[0]["name"] if taste.genres else None,
                     taste=TasteProgress(learned_pct=ctx.pct, signals=len(ctx.excluded)))


@router.get("/{book_id}/explain", response_model=ExplainOut, summary="Why this book? Score breakdown for me")
def explain(book_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    engine = Engine(db)
    rec, _ctx = engine.explain(user, book_id)
    bd = breakdown_of(rec)
    top = max(bd, key=lambda b: b.contribution) if bd else None
    text = f"{book.title} {book.description or ''}"
    genres = engine.genres[book_id]
    mood_matches = []
    for m in MOODS.values():
        s = score_mood(m, genres, text, book.page_count, book.mood_tags)
        if s.score >= 0.4:
            mood_matches.append({"key": m.key, "label": m.label, "score": s.score, "signals": s.signals})
    mood_matches.sort(key=lambda x: -x["score"])
    summary = f"{rec.match_pct}% match."
    if top:
        summary += f" Strongest signal: {top.label.lower()} ({round(top.contribution * 100)} pts)."
    if rec.penalties:
        summary += " Held back by: " + ", ".join(rec.penalties) + "."
    return ExplainOut(book_id=book_id, title=book.title, score=rec.score, match_pct=rec.match_pct, reason=rec.reason,
                      breakdown=bd, penalties=[{"label": k, "value": v} for k, v in rec.penalties.items()],
                      mood_matches=mood_matches, summary=summary)

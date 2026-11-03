"""'My Taste' profile: genre / author / mood affinities derived from ratings and explicit feedback."""
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Book, Feedback, Review, User
from .moods import MOODS
from .recommender import taste_progress_pct
from .schemas import TasteOut, TasteProgress


def progress_for(db: Session, user: User) -> TasteProgress:
    """Taste-meter value for a user (distinct books with any decision + a little credit for favourite genres)."""
    seen = set(db.scalars(select(Review.book_id).where(Review.user_id == user.id)))
    seen |= set(db.scalars(select(Feedback.book_id).where(Feedback.user_id == user.id)))
    pct, signals = taste_progress_pct(len(seen), len(user.favorite_genres))
    return TasteProgress(learned_pct=pct, signals=signals)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def build_taste(db: Session, user: User) -> TasteOut:
    opts = (selectinload(Book.genres), selectinload(Book.authors))
    reviews = {r.book_id: r for r in db.scalars(select(Review).where(Review.user_id == user.id))}
    feedback = {f.book_id: f for f in db.scalars(select(Feedback).where(Feedback.user_id == user.id))}
    ids = set(reviews) | set(feedback)
    books = {b.id: b for b in db.scalars(select(Book).where(Book.id.in_(ids)).options(*opts))} if ids else {}

    counts = Counter(f.action for f in feedback.values())
    engagement: dict[int, float] = {}
    for bid in ids:
        r, f = reviews.get(bid), feedback.get(bid)
        if r:
            engagement[bid] = 1.0 if r.rating >= 4 else 0.4 if r.rating == 3 else 0.0
        elif f and f.action == "interested":
            engagement[bid] = 1.0
        elif f and f.action == "saved":
            engagement[bid] = 0.6
        elif f and f.action == "read":
            engagement[bid] = 0.4
        else:
            engagement[bid] = 0.0

    genre_score: Counter = Counter()
    genre_books: dict[str, list[int]] = defaultdict(list)
    genre_ratings: dict[str, list[int]] = defaultdict(list)
    author_books: dict[str, list[int]] = defaultdict(list)
    author_ratings: dict[str, list[int]] = defaultdict(list)
    mood_count: Counter = Counter()
    for bid, w in engagement.items():
        b = books.get(bid)
        if not b or w == 0:
            continue
        for g in b.genres:
            genre_score[g.name] += w
            genre_books[g.name].append(bid)
            if bid in reviews:
                genre_ratings[g.name].append(reviews[bid].rating)
        for a in b.authors:
            author_books[a.name].append(bid)
            if bid in reviews:
                author_ratings[a.name].append(reviews[bid].rating)
        if w >= 0.6:
            mood_count.update(b.mood_tags or [])
    for g in user.favorite_genres:      # declared favourites count a little even before any rating
        genre_score[g.name] += 0.5
    top = genre_score.most_common(8)
    mx = top[0][1] if top else 1
    genres = [{"name": n, "score": round(100 * s / mx), "count": len(genre_books.get(n, [])),
               "avg_rating": round(sum(genre_ratings[n]) / len(genre_ratings[n]), 2) if genre_ratings.get(n) else None}
              for n, s in top]
    authors = []
    for n, bs in author_books.items():
        rs = author_ratings.get(n, [])
        authors.append({"name": n, "count": len(bs), "avg_rating": round(sum(rs) / len(rs), 2) if rs else None})
    authors.sort(key=lambda a: (-a["count"], -(a["avg_rating"] or 0), a["name"]))
    authors = authors[:5]
    tot = sum(mood_count.values())
    moods = [{"key": k, "label": m.label, "emoji": m.emoji, "pct": round(100 * mood_count.get(k, 0) / tot) if tot else 0}
             for k, m in MOODS.items()]
    moods.sort(key=lambda m: -m["pct"])

    given = [r.rating for r in reviews.values()]
    avg = round(sum(given) / len(given), 2) if given else None
    learned = progress_for(db, user)
    needs = user.onboarded_at is None and not ids and not user.favorite_genres

    # --- taste DNA sentence ---
    if not genres:
        dna = "Your taste DNA is still a blank page — swipe a few books and it will start to take shape."
    else:
        top_g = [g["name"] for g in genres[:2]]
        top_m = [m["label"].lower() for m in moods[:2] if m["pct"] >= 15]
        parts = [f"You're a {_join(top_g)} reader"]
        if top_m:
            parts.append(f"who reaches for {_join(top_m)} books")
        if avg is not None:
            parts.append("rates generously" if avg >= 4 else "is a tough critic" if avg < 3 else "keeps a balanced eye")
            parts[-1] += f" ({avg}★ on average)"
        if authors and authors[0]["count"] >= 2:
            parts.append(f"and keeps coming back to {authors[0]['name']}")
        dna = " ".join(parts[:1]) + (", " + ", ".join(parts[1:]) if len(parts) > 1 else "") + "."
    return TasteOut(learned_pct=learned.learned_pct, signals=learned.signals, needs_onboarding=needs, genres=genres,
                    authors=authors, moods=moods, avg_rating=avg, ratings_count=len(given),
                    counts={a: counts.get(a, 0) for a in ("interested", "saved", "read", "not_interested")}, dna=dna)

"""
NextRead hybrid recommendation engine (pure Python, no heavy ML dependency).

Signals blended into one 0..1 score (weights adapt to how much we know about the user):

1. content       - TF-IDF vectors from genre / author / title+description words. A user profile is the
                   weighted sum of the vectors of books they rated, saved or showed interest in.
2. cf            - user-based k-NN collaborative filtering on mean-centred ratings.
3. pop           - Bayesian-average popularity (solves cold start).
4. fav           - share of the book's genres that the user has declared or demonstrated they love.

Explicit feedback (POST /feedback) feeds the engine:
  interested      -> positive content signal            saved -> mild positive (same as wishlist)
  read            -> rating-based when rated, else a tiny positive
  not_interested  -> HARD exclusion + a negative signal on similar books, tuned by the reason
                     (too_long -> length penalty, not_my_genre -> genre penalty, know_story -> exclusion only)

After scoring, results are re-ranked with MMR (maximal marginal relevance) so the top of the list is not
all one genre, and one "exploration" slot is reserved for a genre the user has never tried.
Every recommendation carries a score breakdown and a human-readable reason.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Book, Feedback, Review, User, WishlistItem
from .moods import MOODS, score_mood

STOPWORDS = set("""
the and for with that this from his her their they them are was were has have had not but you your who whom what when
where which while into over under about after before out its our can will would could should one two been being also than
then there here more most some such only other any all each both few very just his she him how why who use used using
book books story tale life world new first man woman young old
""".split())
TOKEN_RE = re.compile(r"[a-z]{3,}")
BOOST = {"g": 2.0, "a": 1.5, "w": 1.0}  # genre > author > words
MMR_LAMBDA = 0.7          # relevance vs diversity trade-off for normal lists
MMR_LAMBDA_COLD = 0.5     # stronger diversity while we are still learning the user's taste
CALIBRATION_SIGNALS = 8   # onboarding target: swipe ~8 books
GEM_MIN_AVG = 3.75        # 'hidden gem' = clearly above-average rating, but fewer ratings than the median book
COMPONENT_LABELS = {
    "content": "Content similarity",
    "cf": "Readers like you",
    "pop": "Popularity",
    "fav": "Your favourite genres",
}
ALGORITHM_OF = {"content": "content-based", "fav": "content-based", "cf": "collaborative", "pop": "popularity"}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def taste_progress_pct(n_books: int, n_fav_genres: int) -> tuple[int, int]:
    """'Taste meter': (percent learned, signal count). 8 swipes ~ 64%, 20 signals ~ 92%."""
    signals = n_books + min(n_fav_genres, 4) * 0.5
    pct = min(99, round(100 * (1 - 0.88 ** signals)))
    return pct, int(signals)


@dataclass
class Rec:
    book_id: int
    score: float
    algorithm: str
    reason: str
    tag: str = ""
    components: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    mood_signals: list[str] | None = None

    @property
    def match_pct(self) -> int:
        return max(1, min(99, round(self.score * 100)))

    @property
    def personalised(self) -> bool:
        if self.algorithm == "exploration":
            return False  # a deliberate stretch pick: the UI shows "New territory" instead of a match %
        return any(k in self.components for k in ("content", "cf", "fav", "mood"))


class Engine:
    """Snapshot of catalogue + ratings + feedback; cheap to build for classroom-sized data."""

    def __init__(self, db: Session):
        self.books: dict[int, Book] = {
            b.id: b for b in db.scalars(select(Book).options(selectinload(Book.authors), selectinload(Book.genres)))
        }
        self.genres = {bid: [g.name for g in b.genres] for bid, b in self.books.items()}
        self.genre_set = {bid: {g.lower() for g in gs} for bid, gs in self.genres.items()}
        self.author_set = {bid: {a.name.lower() for a in b.authors} for bid, b in self.books.items()}
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        self.activity: Counter = Counter()                           # reviews / positive feedback in the last 30 days
        self.ratings: dict[int, dict[int, int]] = defaultdict(dict)  # user -> book -> rating
        self.rated_at: dict[int, dict[int, datetime]] = defaultdict(dict)
        self.book_ratings: dict[int, list[int]] = defaultdict(list)
        for r in db.execute(select(Review.user_id, Review.book_id, Review.rating, Review.created_at)):
            self.ratings[r.user_id][r.book_id] = r.rating
            self.rated_at[r.user_id][r.book_id] = r.created_at
            self.book_ratings[r.book_id].append(r.rating)
            if r.created_at and r.created_at >= cutoff:
                self.activity[r.book_id] += 1
        self.wishlists: dict[int, set[int]] = defaultdict(set)
        for w in db.execute(select(WishlistItem.user_id, WishlistItem.book_id)):
            self.wishlists[w.user_id].add(w.book_id)
        self.fb: dict[int, dict[int, tuple[str, str | None, datetime]]] = defaultdict(dict)
        for f in db.execute(select(Feedback.user_id, Feedback.book_id, Feedback.action, Feedback.reason, Feedback.created_at)):
            self.fb[f.user_id][f.book_id] = (f.action, f.reason, f.created_at)
            if f.action in ("interested", "saved") and f.created_at and f.created_at >= cutoff:
                self.activity[f.book_id] += 1
        self._build_vectors()
        self._build_popularity()

    # ---------- content vectors ----------
    def _raw_features(self, b: Book) -> Counter:
        f: Counter = Counter()
        for g in b.genres:
            f[f"g:{g.name.lower()}"] += 1
        for a in b.authors:
            f[f"a:{a.name.lower()}"] += 1
        for w in TOKEN_RE.findall(f"{b.title} {b.description or ''}".lower()):
            if w not in STOPWORDS:
                f[f"w:{w}"] += 1
        return f

    def _build_vectors(self) -> None:
        raw = {bid: self._raw_features(b) for bid, b in self.books.items()}
        n = max(len(raw), 1)
        df: Counter = Counter()
        for f in raw.values():
            df.update(f.keys())
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        self.vec: dict[int, dict[str, float]] = {
            bid: {t: (1 + math.log(c)) * self.idf[t] * BOOST[t[0]] for t, c in f.items()} for bid, f in raw.items()
        }

    # ---------- popularity ----------
    def _build_popularity(self) -> None:
        all_r = [r for rs in self.book_ratings.values() for r in rs]
        self.global_mean = sum(all_r) / len(all_r) if all_r else 3.5
        self.m = 3  # prior weight (min votes)
        self.pop: dict[int, float] = {}
        for bid in self.books:
            rs = self.book_ratings.get(bid, [])
            v = len(rs)
            avg = sum(rs) / v if v else 0.0
            self.pop[bid] = (v * avg + self.m * self.global_mean) / (v + self.m)

    def avg_rating(self, bid: int) -> tuple[float | None, int]:
        rs = self.book_ratings.get(bid, [])
        return (round(sum(rs) / len(rs), 2) if rs else None, len(rs))

    def title(self, bid: int) -> str:
        return self.books[bid].title

    def similar_books(self, book_id: int, limit: int = 6) -> list[tuple[int, float]]:
        base = self.vec.get(book_id)
        if not base:
            return []
        scored = [(bid, _cosine(base, v)) for bid, v in self.vec.items() if bid != book_id]
        scored = [(b, s) for b, s in scored if s > 0]
        scored.sort(key=lambda x: (-x[1], -self.pop.get(x[0], 0)))
        return scored[:limit]

    # ---------- collaborative ----------
    def _user_means(self) -> dict[int, float]:
        return {u: sum(r.values()) / len(r) for u, r in self.ratings.items() if r}

    def cf_predictions(self, user_id: int, k: int = 25) -> dict[int, tuple[float, int]]:
        mine = self.ratings.get(user_id, {})
        if len(mine) < 2:
            return {}
        means = self._user_means()
        my_mean = means[user_id]
        neighbours: list[tuple[int, float]] = []
        for v, theirs in self.ratings.items():
            if v == user_id:
                continue
            common = set(mine) & set(theirs)
            if len(common) < 3:  # too little overlap -> similarity is noise
                continue
            a = [mine[b] - my_mean for b in common]
            c = [theirs[b] - means[v] for b in common]
            den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in c))
            if den == 0:
                continue
            sim = sum(x * y for x, y in zip(a, c)) / den
            sim *= min(len(common), 10) / 10  # significance weighting
            if sim > 0.1:
                neighbours.append((v, sim))
        neighbours.sort(key=lambda x: -x[1])
        neighbours = neighbours[:k]
        num: dict[int, float] = defaultdict(float)
        den_: dict[int, float] = defaultdict(float)
        cnt: dict[int, int] = defaultdict(int)
        for v, sim in neighbours:
            for bid, r in self.ratings[v].items():
                if bid in mine:
                    continue
                num[bid] += sim * (r - means[v])
                den_[bid] += abs(sim)
                cnt[bid] += 1
        out = {}
        for bid in num:
            pred = max(1.0, min(5.0, my_mean + num[bid] / (den_[bid] + 1.0)))  # +1 damps low-evidence predictions
            out[bid] = (pred, cnt[bid])
        return out

    # ---------- per-user context ----------
    def context(self, user: User) -> "UserContext":
        return UserContext(self, user)

    # ---------- re-ranking ----------
    def _sim(self, a: int, b: int) -> float:
        """Cheap, explainable similarity used for diversity: genre overlap (+ same author)."""
        ga, gb = self.genre_set[a], self.genre_set[b]
        jac = len(ga & gb) / len(ga | gb) if ga | gb else 0.0
        return 0.8 * jac + (0.2 if self.author_set[a] & self.author_set[b] else 0.0)

    def mmr(self, pool: list[Rec], limit: int, lam: float) -> list[Rec]:
        """Maximal marginal relevance: balance a book's score against its similarity to books already chosen."""
        pool = list(pool)
        chosen: list[Rec] = []
        while pool and len(chosen) < limit:
            if not chosen:
                best = pool[0]
            else:
                best = max(pool, key=lambda r: (lam * r.score - (1 - lam) * max(self._sim(r.book_id, c.book_id) for c in chosen), -r.book_id))
            chosen.append(best)
            pool.remove(best)
        return chosen

    # ---------- hybrid recommendations ----------
    def recommend(self, user: User, limit: int = 10, exclude=(), diversify: bool = True, explore: bool = True,
                  lam: float | None = None, ctx: "UserContext | None" = None) -> list[Rec]:
        ctx = ctx or self.context(user)
        skip = set(exclude)
        recs = [ctx.rec(b) for b in ctx.candidates if b not in skip]
        recs.sort(key=lambda r: (-r.score, r.book_id))
        if not diversify:
            return recs[:limit]
        lam = lam if lam is not None else (MMR_LAMBDA if ctx.has_profile else MMR_LAMBDA_COLD)
        chosen = self.mmr(recs[:max(limit * 4, 30)], limit, lam)
        if explore and limit >= 5 and ctx.explored and ctx.has_profile:
            chosen_ids = {r.book_id for r in chosen}
            fresh = [r for r in recs if r.book_id not in chosen_ids and not (self.genre_set[r.book_id] & ctx.explored)
                     and r.components.get("pop", 0) >= 0.55]
            # "adjacent" exploration: well-liked books in an unseen genre that still resemble the user's taste a bit
            fresh.sort(key=lambda r: (-(r.components["pop"] + 0.8 * r.components.get("content", 0) + 0.5 * r.components.get("cf", 0)), r.book_id))
            if fresh:
                best = fresh[0]
                genre = self.genres[best.book_id][0] if self.genres[best.book_id] else "a new genre"
                best.algorithm, best.tag = "exploration", "New territory"
                best.reason = f"New territory: you haven't explored {genre} yet, and readers rate this highly"
                chosen = chosen[:4] + [best] + chosen[4:]
                chosen = chosen[:limit]
        return chosen

    def trending(self, limit: int = 10, exclude=()) -> list[Rec]:
        skip = set(exclude)
        top_act = max(self.activity.values(), default=0) or 1
        def score(b: int) -> float:
            return 0.6 * (self.pop[b] - 1) / 4 + 0.4 * self.activity.get(b, 0) / top_act
        ids = sorted((b for b in self.books if b not in skip), key=lambda b: (-score(b), b))[:limit]
        out = []
        for b in ids:
            n = self.activity.get(b, 0)
            reason = f"{n} reader{'s' if n != 1 else ''} rated or saved it this month" if n else "Highly rated by the community"
            out.append(Rec(b, round(score(b), 4), "popularity", reason, "Trending", {"pop": (self.pop[b] - 1) / 4}))
        return out

    # ---------- rows ----------
    def rows(self, user: User, per_row: int = 12) -> list[dict]:
        ctx = self.context(user)
        rows: list[dict] = []

        def add(rid: str, title: str, subtitle: str, recs: list[Rec], min_items: int = 3) -> None:
            if len(recs) >= min_items:
                rows.append({"id": rid, "title": title, "subtitle": subtitle, "recs": recs[:per_row]})

        add("top-picks", "Top picks for you", "Our hybrid engine's best guesses", self.recommend(user, per_row, ctx=ctx), 1)

        anchor = ctx.best_anchor()
        if anchor is not None:
            aid, _phrase = anchor
            sims = [(b, s) for b, s in self.similar_books(aid, 60) if b in ctx.candidate_set]
            recs = []
            for b, _s in sims[:per_row]:
                shared = [g for g in self.genres[b] if g.lower() in self.genre_set[aid]]
                why = f"Because you liked “{self.title(aid)}”" + (f" — both are {shared[0]}" if shared else "")
                recs.append(ctx.rec(b, reason=why, tag=f"Like {self.title(aid)}"[:30], algorithm="content-based"))
            add("because-liked", f"Because you liked {self.title(aid)}", "Books with a similar feel", recs)

        trend = self.trending(per_row, exclude=ctx.excluded)
        add("trending", "Trending now", "What readers are rating and saving this month",
            [ctx.rec(r.book_id, reason=r.reason, tag="Trending", algorithm="popularity") for r in trend], 1)

        counts = sorted(len(v) for v in self.book_ratings.values() if v)
        median = counts[len(counts) // 2] if counts else 0
        gems = []
        for b in ctx.candidates:
            avg, n = self.avg_rating(b)
            if avg is not None and avg >= GEM_MIN_AVG and 2 <= n <= max(median, 2):
                gems.append((b, avg, n))
        gems.sort(key=lambda x: (-x[1], -ctx.rec(x[0]).score, x[0]))
        add("hidden-gems", "Hidden gems", "Highly rated, but few readers have found them yet",
            [ctx.rec(b, reason=f"Hidden gem: {avg}★ from only {n} readers", tag="Hidden gem", algorithm="popularity") for b, avg, n in gems[:per_row]])

        cf = [(b, p, n) for b, (p, n) in ctx.cf_raw.items() if b in ctx.candidate_set and p >= 3.6]
        cf.sort(key=lambda x: (-x[1], -x[2], x[0]))
        add("readers-like-you", "Readers like you also loved", "Picked by people whose taste overlaps yours",
            [ctx.rec(b, reason=f"Readers with similar taste rated it about {p:.1f}/5", tag="Readers like you", algorithm="collaborative") for b, p, _n in cf[:per_row]])

        if ctx.explored:
            fresh = [b for b in ctx.candidates if not (self.genre_set[b] & ctx.explored)]
            fresh.sort(key=lambda b: (-self.pop[b], b))
            add("new-to-explore", "New to explore", "Genres you haven't tried yet",
                [ctx.rec(b, reason=f"You haven't explored {self.genres[b][0] if self.genres[b] else 'this'} yet", tag="New genre", algorithm="exploration") for b in fresh[:per_row]])

        fav_authors = ctx.favourite_authors()
        if fav_authors:
            hits = [(b, sorted(self.author_set[b] & fav_authors)[0]) for b in ctx.candidates if self.author_set[b] & fav_authors]
            hits.sort(key=lambda x: (-ctx.rec(x[0]).score, x[0]))
            name_of = {a.name.lower(): a.name for b in self.books.values() for a in b.authors}
            add("favourite-authors", "From your favourite authors", "More from writers you keep coming back to",
                [ctx.rec(b, reason=f"More from {name_of.get(a, a.title())}", tag="Author you love", algorithm="content-based") for b, a in hits[:per_row]], 2)
        return rows

    # ---------- mood layer ----------
    def mood_recommend(self, user: User, mood_keys: list[str], limit: int = 12) -> list[Rec]:
        """Transparent re-rank: final = 0.6 * mood score + 0.4 * the normal recommendation score."""
        ctx = self.context(user)
        moods = [MOODS[k] for k in mood_keys]
        out: list[Rec] = []
        for bid in ctx.candidates:
            b = self.books[bid]
            text = f"{b.title} {b.description or ''}"
            scores = [score_mood(m, self.genres[bid], text, b.page_count, b.mood_tags) for m in moods]
            ms = sum(s.score for s in scores) / len(scores)
            if len(scores) > 1 and min(s.score for s in scores) < 0.2:
                continue   # a combined mood must satisfy BOTH moods, not just one
            if ms < 0.2:
                continue
            base = ctx.rec(bid)
            final = round(min(0.99, 0.6 * ms + 0.4 * base.score), 4)
            sig = [f"{m.label}: {'; '.join(s.signals) or 'weak match'}" for m, s in zip(moods, scores)]
            labels = " + ".join(m.label for m in moods)
            out.append(Rec(bid, final, base.algorithm, f"Matches your mood “{labels}” — {sig[0].split(': ', 1)[1] if len(sig) == 1 else 'both moods fit'}",
                           labels, {**base.components, "mood": ms}, dict(base.penalties), base.weights, sig))
        out.sort(key=lambda r: (-r.score, r.book_id))
        return self.mmr(out[:max(limit * 3, 24)], limit, 0.8)

    # ---------- explanation ----------
    def explain(self, user: User, bid: int) -> tuple[Rec, "UserContext"]:
        ctx = self.context(user)
        return ctx.rec(bid), ctx


class UserContext:
    """Everything the engine knows about one user, computed once and reused for every book."""

    def __init__(self, e: Engine, user: User):
        self.e, self.user = e, user
        uid = user.id
        self.rated = e.ratings.get(uid, {})
        self.wish = e.wishlists.get(uid, set())
        self.fb = e.fb.get(uid, {})
        self.excluded = set(self.rated) | set(self.wish) | set(self.fb)   # rejected books never reappear
        self.fav_genres = {g.name.lower() for g in user.favorite_genres}
        self.fav_authors = {a.name.lower() for a in user.favorite_authors}
        self.moods = [m for m in (user.favorite_moods or []) if m in MOODS]
        self.n_signals = len(self.excluded) + len(self.fav_genres) // 2
        self.pct, _ = taste_progress_pct(len(self.excluded), len(self.fav_genres))
        self.calibrating = len(self.excluded) < CALIBRATION_SIGNALS

        # explicit positive anchors (used for reasons and the "because you liked" row)
        self.anchors: list[tuple[int, str, float]] = []   # (book, phrase, weight)
        for bid, r in self.rated.items():
            if r >= 4 and bid in e.books:
                self.anchors.append((bid, f"rated “{e.title(bid)}” {r}★", r / 5))
        for bid, (act, _reason, _t) in self.fb.items():
            if act == "interested" and bid in e.books and bid not in self.rated:
                self.anchors.append((bid, f"were interested in “{e.title(bid)}”", 0.8))
        for bid in self.wish:
            if bid in e.books and bid not in self.rated:
                self.anchors.append((bid, f"saved “{e.title(bid)}”", 0.6))

        # genres the user has demonstrated they like / have already explored
        aff: Counter = Counter()
        self.explored: set[str] = set(self.fav_genres)
        for g in self.fav_genres:
            aff[g] += 1.5
        for bid in self.excluded:
            if bid not in e.books:
                continue
            act = self.fb.get(bid, ("", None, None))[0]
            r = self.rated.get(bid)
            if act == "not_interested":
                continue
            if r is None or r >= 3:
                self.explored |= e.genre_set[bid]
            pos = (r is not None and r >= 4) or act in ("interested", "saved") or bid in self.wish
            if pos:
                for g in e.genre_set[bid]:
                    aff[g] += 1.0 if (r or 0) >= 4 or act == "interested" else 0.5
        self.liked_genres = set(self.fav_genres) | {g for g, _ in aff.most_common(5)}

        # rejections
        self.rejected = [bid for bid, (act, _r, _t) in self.fb.items() if act == "not_interested" and bid in e.books]
        self.rejected_genres: set[str] = set()
        too_long = []
        for bid in self.rejected:
            reason = self.fb[bid][1]
            if reason == "not_my_genre":
                self.rejected_genres |= e.genre_set[bid]
            if reason == "too_long" and e.books[bid].page_count:
                too_long.append(e.books[bid].page_count)
        self.long_threshold = min(too_long) if too_long else None
        # a genre that was rejected but is also explicitly loved stays allowed
        self.rejected_genres -= self.liked_genres

        self.profile = self._build_profile()
        self.has_profile = bool(self.profile) and any(v > 0 for v in self.profile.values())
        self.candidates = [b for b in e.books if b not in self.excluded]
        self.candidate_set = set(self.candidates)
        raw = {b: max(0.0, _cosine(self.profile, e.vec[b])) for b in self.candidates} if self.has_profile else {}
        self._cmax = max(raw.values(), default=0.0)
        self._content_cache: dict[int, float] = {}
        self.cf_raw = e.cf_predictions(uid)
        n_rated = len(self.rated)
        if n_rated >= 5:
            self.w = {"content": 0.35, "cf": 0.40, "pop": 0.12, "fav": 0.13}
        elif n_rated >= 1 or self.has_profile:
            self.w = {"content": 0.45, "cf": 0.17, "pop": 0.20, "fav": 0.18}
        else:
            self.w = {"content": 0.0, "cf": 0.0, "pop": 1.0, "fav": 0.0}

    # ---- profile ----
    def _build_profile(self) -> dict[str, float]:
        e = self.e
        prof: Counter = Counter()

        def add(bid: int, w: float) -> None:
            for t, x in e.vec.get(bid, {}).items():
                prof[t] += w * x

        for bid, r in self.rated.items():
            add(bid, (r - 2.5) / 2.5)           # 5 -> +1.0, 4 -> +0.6, 3 -> +0.2, 2 -> -0.2, 1 -> -0.6
        for bid in self.wish:
            add(bid, 0.5)
        for bid, (act, _reason, _t) in self.fb.items():
            if bid in self.rated or bid in self.wish:
                continue
            if act == "interested":
                add(bid, 0.7)
            elif act == "saved":
                add(bid, 0.5)
            elif act == "read":
                add(bid, 0.15)                  # read but not rated: weakly positive
        for g in self.fav_genres:
            t = f"g:{g}"
            prof[t] += 0.8 * e.idf.get(t, 1.0) * BOOST["g"]
        for a in self.fav_authors:
            t = f"a:{a}"
            prof[t] += 0.8 * e.idf.get(t, 1.0) * BOOST["a"]
        return dict(prof)

    # ---- components ----
    def _content(self, bid: int) -> float:
        if bid not in self._content_cache:
            v = max(0.0, _cosine(self.profile, self.e.vec[bid])) if self.has_profile else 0.0
            self._content_cache[bid] = min(1.0, v / self._cmax) if self._cmax > 0 else 0.0
        return self._content_cache[bid]

    def _fav(self, bid: int) -> float:
        gs = self.e.genre_set[bid]
        return len(gs & self.liked_genres) / len(gs) if gs and self.liked_genres else 0.0

    def components(self, bid: int) -> dict[str, float]:
        comps = {"pop": (self.e.pop[bid] - 1) / 4}
        if self.has_profile:
            comps["content"] = self._content(bid)
        if bid in self.cf_raw:
            p, n = self.cf_raw[bid]
            comps["cf"] = ((p - 1) / 4) * (1.0 if n >= 2 else 0.7)
        if self.liked_genres and self.w["fav"] > 0:
            comps["fav"] = self._fav(bid)
        return comps

    def penalties(self, bid: int) -> dict[str, float]:
        e, pen = self.e, {}
        if self.rejected:
            sim = max((_cosine(e.vec[bid], e.vec[r]) for r in self.rejected), default=0.0)
            if sim >= 0.2:
                pen["similar to books you rejected"] = round(0.4 * sim, 4)
        if self.rejected_genres and e.genre_set[bid] & self.rejected_genres:
            pen["genre you said isn't for you"] = 0.2
        pc = e.books[bid].page_count
        if self.long_threshold and pc and pc >= self.long_threshold:
            pen["longer than books you skipped"] = 0.15
        return pen

    def mood_boost(self, bid: int) -> float:
        if not self.moods:
            return 0.0
        b = self.e.books[bid]
        text = f"{b.title} {b.description or ''}"
        best = max(score_mood(MOODS[m], self.e.genres[bid], text, b.page_count, b.mood_tags).score for m in self.moods)
        return 0.08 * best

    # ---- scoring ----
    def rec(self, bid: int, reason: str | None = None, tag: str | None = None, algorithm: str | None = None) -> Rec:
        comps = self.components(bid)
        tot = sum(self.w[c] for c in comps)
        base = sum(self.w[c] * v for c, v in comps.items()) / tot if tot else 0.0
        pen = self.penalties(bid)
        boost = self.mood_boost(bid)
        score = max(0.0, min(1.0, base - sum(pen.values()) + boost))
        eff_w = {c: round(self.w[c] / tot, 4) for c in comps} if tot else {}
        top = max(comps, key=lambda c: self.w[c] * comps[c])
        rec = Rec(bid, round(score, 4), algorithm or ALGORITHM_OF[top], reason or self._reason(bid, top),
                  tag or self._tag(bid, top), comps, pen, eff_w)
        if boost:
            rec.components["mood_pref"] = boost / 0.08
        return rec

    # ---- explanations ----
    def best_anchor(self) -> tuple[int, str] | None:
        """The user's strongest positive book: highest rating, then most recent."""
        best, best_key = None, None
        for bid, phrase, w in self.anchors:
            when = self.e.rated_at.get(self.user.id, {}).get(bid) or self.fb.get(bid, ("", None, datetime.min))[2] or datetime.min
            key = (w, when)
            if best_key is None or key > best_key:
                best, best_key = (bid, phrase), key
        return best

    def favourite_authors(self) -> set[str]:
        out = set(self.fav_authors)
        for bid, _p, w in self.anchors:
            if w >= 0.8:
                out |= self.e.author_set[bid]
        return out

    def _anchor_for(self, bid: int) -> tuple[int, str] | None:
        best, best_s = None, 0.08
        for abid, phrase, w in self.anchors:
            s = _cosine(self.e.vec[bid], self.e.vec[abid]) * (0.5 + 0.5 * w)
            if s > best_s:
                best, best_s = (abid, phrase), s
        return best

    def _reason(self, bid: int, top: str) -> str:
        e = self.e
        if top in ("content", "fav"):
            anchor = self._anchor_for(bid)
            if anchor:
                abid, phrase = anchor
                shared = [g for g in e.genres[bid] if g.lower() in e.genre_set[abid] or g.lower() in self.liked_genres]
                return f"Because you {phrase}" + (f" and love {shared[0]}" if shared else "")
            shared = [g for g in e.genres[bid] if g.lower() in self.liked_genres]
            if shared:
                return f"Matches your favourite genre: {shared[0]}"
            return f"Similar to {e.genres[bid][0] if e.genres[bid] else 'other'} books you like"
        if top == "cf" and bid in self.cf_raw:
            return f"Readers with similar taste rated it about {self.cf_raw[bid][0]:.1f}/5"
        avg, n = e.avg_rating(bid)
        g = e.genres[bid][0] if e.genres[bid] else None
        if n:
            return f"A crowd favourite{f' in {g}' if g else ''} ({avg}★ from {n} ratings)"
        return "Trending in the catalogue"

    def _tag(self, bid: int, top: str) -> str:
        if top in ("content", "fav"):
            anchor = self._anchor_for(bid)
            if anchor:
                return f"Like {self.e.title(anchor[0])}"[:30]
            return "Your genre"
        return "Readers like you" if top == "cf" else "Crowd favourite"

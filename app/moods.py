"""
Transparent mood / intent scoring layer.

Every mood is described by plain data (genre weights, keywords, a page-count rule and the weight each
signal carries), so a score can always be explained as "genre X + keyword Y + length Z". There is no
learned model here: the same rules are used to derive a book's stored `mood_tags` and to re-rank
recommendations for a chosen mood.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

_TOKEN = re.compile(r"[a-z]+")


def _pages_light(p: int) -> float:
    return 1.0 if p <= 350 else 0.5 if p <= 450 else 0.0


def _pages_quick(p: int) -> float:
    return 1.0 if p <= 220 else 0.7 if p <= 300 else 0.35 if p <= 350 else 0.0


def _pages_epic(p: int) -> float:
    return 1.0 if p >= 800 else 0.8 if p >= 550 else 0.4 if p >= 450 else 0.0


def _pages_comfort(p: int) -> float:
    return 1.0 if p <= 400 else 0.4


def _no_pages(_: int) -> float:
    return 0.0


@dataclass(frozen=True)
class Mood:
    key: str
    label: str
    emoji: str
    blurb: str
    genres: dict[str, float]                 # lower-case genre -> strength 0..1
    keywords: frozenset[str]
    weights: tuple[float, float, float]      # (genre, keyword, pages) - sums to 1
    pages: Callable[[int], float] = field(default=_no_pages)


MOODS: dict[str, Mood] = {m.key: m for m in [
    Mood("light", "Something light", "", "Fun, breezy and easy to sink into",
         {"young adult": 0.8, "romance": 0.7, "fantasy": 0.5, "self-help": 0.3, "classic": 0.2},
         frozenset("adventure friends school magic charming funny wedding hobbit magical journey comedy fun love".split()),
         (0.5, 0.3, 0.2), _pages_light),
    Mood("mind-bending", "Mind-bending", "", "Ideas that rearrange how you see things",
         {"science fiction": 0.9, "philosophy": 0.8, "dystopian": 0.7, "psychology": 0.6, "artificial intelligence": 0.6, "science": 0.4},
         frozenset("reality mind cyberspace hacker consciousness thought truth propaganda artificial intelligence time universe space judgement bias surveillance totalitarian creation gene meme".split()),
         (0.55, 0.45, 0.0)),
    Mood("cry-worthy", "Cry-worthy", "", "Stories that hit you right in the heart",
         {"historical fiction": 0.7, "romance": 0.6, "young adult": 0.4, "biography": 0.4, "fiction": 0.3},
         frozenset("tragedy loss cancer death grief betrayal haunted forbidden love survive survived orphan memoir friend family tragedy camps nazi falls".split()),
         (0.4, 0.6, 0.0)),
    Mood("learn", "Learn something new", "", "Leave smarter than you arrived",
         {"non-fiction": 0.9, "science": 0.9, "history": 0.8, "psychology": 0.8, "business": 0.7, "biography": 0.7,
          "computer science": 0.7, "programming": 0.6, "mathematics": 0.7, "self-help": 0.6, "textbook": 0.5, "philosophy": 0.5},
         frozenset("introduction explains explores examines guide principles framework history practical understand evolution habits decisions".split()),
         (0.8, 0.2, 0.0)),
    Mood("quick", "Quick read", "", "Finish it in a weekend, or less",
         {}, frozenset(), (0.0, 0.0, 1.0), _pages_quick),
    Mood("epic", "Epic & long", "", "Big worlds you can get lost in",
         {"fantasy": 0.8, "science fiction": 0.6, "historical fiction": 0.6, "classic": 0.3},
         frozenset("epic galactic empire houses throne saga decades kingdom war planet dragon wizard universe family".split()),
         (0.3, 0.2, 0.5), _pages_epic),
    Mood("comfort", "Comfort read", "", "Warm, familiar and reassuring",
         {"classic": 0.8, "fantasy": 0.5, "romance": 0.6, "young adult": 0.5, "mystery": 0.5, "fiction": 0.3},
         frozenset("friends school magic home village poirot holmes detective bilbo orphan family manners england".split()),
         (0.6, 0.25, 0.15), _pages_comfort),
    Mood("dark", "Dark & gripping", "", "Tense, twisty and impossible to put down",
         {"thriller": 0.9, "horror": 0.9, "mystery": 0.8, "dystopian": 0.7, "science fiction": 0.2},
         frozenset("murder killed vanishes suspect evil vampire disappearance death surveillance totalitarian fight hacker secret haunting shape-shifting dead".split()),
         (0.6, 0.4, 0.0)),
]}

TAG_THRESHOLD = 0.4


@dataclass
class MoodScore:
    mood: str
    score: float
    signals: list[str]


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def score_mood(mood: Mood, genres: list[str], text: str, page_count: int | None, tags: list[str] | None = None) -> MoodScore:
    """Score one book for one mood (0..1) and say which signals fired."""
    signals: list[str] = []
    gset = [g.lower() for g in genres]
    hits = sorted(((mood.genres[g], g) for g in gset if g in mood.genres), reverse=True)
    g_score = 0.0
    if hits:
        g_score = min(1.0, hits[0][0] + 0.15 * (len(hits) - 1))
        signals.append("genre: " + ", ".join(g for _, g in hits))
    words = _tokens(text)
    kws = sorted(w for w in mood.keywords if w in words)
    k_score = min(1.0, 0.4 * len(kws))
    if kws:
        signals.append("keywords: " + ", ".join(kws[:3]))
    p_score = mood.pages(page_count) if page_count else 0.0
    if p_score and mood.key in ("quick", "epic", "light", "comfort"):
        signals.append(f"length: {page_count} pages")
    wg, wk, wp = mood.weights
    raw = wg * g_score + wk * k_score + wp * p_score
    if tags and mood.key in tags:
        raw = max(raw, 0.6) + 0.2
        signals.append("stored mood tag")
    return MoodScore(mood.key, round(min(1.0, raw), 3), signals)


def derive_mood_tags(genres: list[str], title: str, description: str | None, page_count: int | None, limit: int = 3) -> list[str]:
    """Derive stored mood tags from genres / keywords / length (used where no explicit tags exist)."""
    text = f"{title} {description or ''}"
    scored = [score_mood(m, genres, text, page_count) for m in MOODS.values()]
    scored = [s for s in scored if s.score >= TAG_THRESHOLD]
    scored.sort(key=lambda s: -s.score)
    return [s.mood for s in scored[:limit]]


def parse_mood_keys(raw: str | None) -> list[str]:
    """'light,dark' -> ['light','dark']; raises ValueError on unknown keys."""
    keys = [k.strip().lower() for k in (raw or "").split(",") if k.strip()]
    bad = [k for k in keys if k not in MOODS]
    if bad:
        raise ValueError(f"unknown mood(s): {', '.join(bad)}")
    return list(dict.fromkeys(keys))

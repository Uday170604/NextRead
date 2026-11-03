# NextRead

**What should I read next?** NextRead is a book *recommendation* product — not a library or a reader. It helps someone decide
what to read next and makes that decision feel personal, confident and fun. Book content is never shown; "Where to get it" are links only.

Stack: FastAPI · SQLAlchemy · SQLite (any SQLAlchemy DB) · vanilla-JS single-page app (ES modules, no build step) · JWT auth · 53 pytest tests.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
* Web app: http://127.0.0.1:8000  ·  API docs: http://127.0.0.1:8000/docs
* First start creates `bookrec.db`, seeds 50 books (covers, ISBNs, page counts, mood tags), 7 persona users, 40 synthetic readers and ~600 ratings.

| Account | E-mail | Password |
|---|---|---|
| Admin | admin@bookrec.local | Admin@12345 |
| Demo readers | emma@, john@, sarah@, lucy@, prof.rao@, meera@example.com | Password@123 |
| Brand-new reader (see onboarding) | alex@example.com | Password@123 |

## Features
**Discovery UI**
* **Hero "Your next read"** — realistic CSS-3D hardcover (spine, page edges, gloss + paper texture, idle float, tilt that follows the cursor or the phone gyroscope, dynamic shadow), match-% ring, one-line human reason, genre chips, ❤ Interested / ✕ Not for me / 🔖 Save for later / ✓ Already read it (quick star rating), and **Show me another**.
* **Book Match swipe deck** — swipe right = interested, left = not for me (optionally say why: too long / not my genre / I know the story), up = already read (asks for a rating), down or 🔖 = save. Arrow keys work too. Every decision is sent to the backend and the cards underneath **re-rank live**; the **taste meter** ("Your taste profile: 64% learned") sharpens as you swipe.
* **Mood & intent picker** — Something light, Mind-bending, Cry-worthy, Learn something new, Quick read, Epic & long, Comfort read, Dark & gripping. Pick one or two. The scoring is transparent: `final = 0.6 × mood fit (genre + keywords + length) + 0.4 × your normal match`, and every card lists the signals that fired.
* **Netflix-style rows** (snap-scrolling, lazily hydrated, keyboard navigable): Top picks for you · Because you liked *X* · Trending now · Hidden gems · Readers like you also loved · New to explore · From your favourite authors.
* **Detail panel** (side panel / bottom sheet, cover flies in from the card): description, facts, community rating and reviews, *Why we picked this for you* (breakdown bars), similar books, Where to get it (Open Library, Google Books, WorldCat), rate / review / decide controls.
* **My Taste** — genre radar + bars (with a table view), favourite authors, average rating, mood breakdown, a "taste DNA" sentence, and Interested / Saved / Already read / Not for me lists with **undo**.
* **Compare two books** and a **shareable card** (canvas → PNG download, native share, copy-link to a public picks page).
* **Search** with instant suggestions (title / author / genre, ARIA combobox), "Did you mean…", filters for genre, mood, rating, year and page range.
* **Weekly "Your picks"** summary card, **first-run onboarding** (genres → moods → swipe 8 books), **admin** panel (add books with cover URL / page count / mood tags, moderation, users, **recommendation analytics**).
* Day/night theme (follows the OS by default), `prefers-reduced-motion` support (flat covers, no tilt/float/parallax) plus a manual motion toggle, skeleton loaders, empty / error / offline states, bottom tab bar on phones.

**Recommender** (`app/recommender.py`, `app/moods.py`)
* Hybrid: TF-IDF content + user-based k-NN collaborative filtering + Bayesian popularity + favourite-genre match, with adaptive weights.
* Feedback signals: *interested* = positive, *saved* = mild positive, *read* = rating-based, *not interested* = **hard exclusion** + negative signal on similar books (reason-aware: *too long* → length penalty, *not my genre* → genre penalty).
* **MMR diversity re-ranking** plus one **exploration slot** for a genre the user has never tried.
* Every recommendation has a score breakdown and a human-readable reason; `/explain` shows weights, contributions and penalties.
* **Cold start**: onboarding genres/moods + a deliberately genre-diverse calibration deck for the first ~8 swipes.

## Tests
```bash
python -m pytest -q        # 53 tests: the 24 original API tests + 29 new (feedback, undo, deck, rows, mood, explain, taste, compare, search, migration, recommender behaviour)
```

## Configuration
Environment variables (see `.env.example`): `SECRET_KEY`, `DATABASE_URL`, `SEED_ON_STARTUP`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ACCESS_TOKEN_EXPIRE_MINUTES`.
Before real use: set a long random `SECRET_KEY`, change the admin credentials, set `SEED_ON_STARTUP=false`.

## Upgrading an existing `bookrec.db` (migration notes)
`Base.metadata.create_all()` only creates *missing tables*, so on every start the app also runs `app/migrations.py`:
1. **`migrate()`** inspects the live schema and runs `ALTER TABLE … ADD COLUMN` only for absent columns: `books.cover_url`, `books.page_count`, `books.mood_tags`, `users.favorite_moods`, `users.onboarded_at` (all nullable; the new `feedback` table is created by `create_all`).
2. **`backfill()`** fills new data without overwriting anything: covers / ISBN / page counts for the known seeded titles (only where NULL), derived `mood_tags` (only where NULL), a `read` feedback row for every existing rating and a `saved` row for every wishlist item.

Both steps are idempotent (a second start changes nothing), never drop or rewrite existing data, and are covered by tests that downgrade a database and upgrade it again. The default database file name (`bookrec.db`) and demo logins were kept so existing installs keep working.

## Docker
```bash
docker build -t nextread . && docker run -p 8000:8000 nextread
```

## API (selection — full list at `/docs`)
| Area | Endpoints |
|---|---|
| Auth / profile | `POST /auth/register`, `POST /auth/login`, `GET/PUT /users/me`, `PUT /users/me/preferences`, `POST /users/me/onboarding`, `GET /users/me/taste` |
| Books | `GET /books` (q, genre, author, year, min_rating, pages_min/max, mood, sort), `GET /books/{id}`, `GET /books/{id}/similar`, `GET /books/suggest?q=`, `GET /books/compare?a=&b=`, `GET /moods`, `GET /genres`, `GET /authors` |
| Ratings / wishlist | `PUT/DELETE /books/{id}/review`, `GET /books/{id}/reviews`, `GET /reviews/mine`, `GET/POST/DELETE /wishlist` |
| Feedback | `POST /feedback`, `DELETE /feedback/{book_id}` (undo), `GET /feedback?action=interested\|not_interested\|saved\|read` |
| Recommendations | `GET /recommendations`, `/recommendations/featured`, `/rows`, `/mood?moods=`, `/deck?limit=&exclude=`, `/weekly`, `/trending`, `/{book_id}/explain` |
| Admin | `/admin/books`, `/admin/reviews`, `/admin/users`, `/admin/stats`, `/admin/analytics`, `/admin/import/openlibrary` |

## Project layout
```
app/            main.py, models.py, migrations.py, recommender.py, moods.py, taste.py, presenters.py, routers/…
app/static/     index.html, css/app.css, js/{util,api,theme,cover,actions,rows,detail,deck,home,onboarding,taste,browse,compare,share,auth,admin,main}.js
tests/          test_api.py (original), test_features.py (new)
```

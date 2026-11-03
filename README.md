# 📚 NextRead

[![CI](https://github.com/Uday170604/NextRead/actions/workflows/ci.yml/badge.svg)](https://github.com/Uday170604/NextRead/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-009688)
![License](https://img.shields.io/badge/license-MIT-green)

**"What should I read next?"** NextRead is a personalized book recommendation app. It is not a library or a reader: it helps you decide what to read next and explains *why* each book was picked for you.

<!-- Example: ![Home](docs/screenshots/home.png) -->

---

## ✨ Highlights

- **Hybrid recommender**: TF-IDF content similarity + user-based k-NN collaborative filtering + Bayesian popularity + favourite-genre match, with adaptive weights.
- **Explainable results**: every recommendation has a score breakdown and a human-readable reason.
- **Swipe deck (Book Match)**: swipe right/left/up/down to give feedback; cards re-rank live and a taste meter updates.
- **Mood picker**: "Something light", "Mind-bending", "Cry-worthy" and more, with transparent scoring.
- **Diversity and exploration**: MMR re-ranking plus one exploration slot for a genre you haven't tried.
- **Cold-start handling**: onboarding (genres → moods → swipe 8 books).
- **Netflix-style rows, My Taste dashboard, compare two books, shareable cards, search with suggestions, admin analytics.**
- **Accessible**: dark/light theme, reduced-motion support, ARIA combobox search, keyboard navigation.

## 🧠 How the recommender works

```
User feedback + ratings ─┐
                         ├─► Content score (TF-IDF)         ─┐
Book metadata ───────────┤   Collaborative score (k-NN)      ├─► Weighted blend ─► MMR re-rank ─► Top picks
                         │   Bayesian popularity             │   (adaptive)        + 1 explore slot
Genre / mood prefs ──────┘   Genre match                    ─┘
```

- *Interested* = positive signal, *Saved* = mild positive, *Read* = rating-based.
- *Not for me* = hard exclusion plus a negative signal on similar books (reason-aware: too long → length penalty, not my genre → genre penalty).
- Mood score: `final = 0.6 × mood fit + 0.4 × normal match`.
- `GET /recommendations/{book_id}/explain` shows weights, contributions and penalties.

Code lives in `app/recommender.py` and `app/moods.py`.

## 🛠 Tech stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy, Pydantic |
| Database | SQLite by default (any SQLAlchemy DB works) |
| Auth | JWT |
| Frontend | Vanilla JS single-page app (ES modules, no build step) |
| Testing | pytest (53 tests) |
| DevOps | Docker, GitHub Actions |

## 🚀 Quick start

```bash
git clone https://github.com/Uday170604/NextRead.git
cd NextRead
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then edit values
python -m uvicorn app.main:app --reload
```

- Web app: http://127.0.0.1:8000
- API docs (Swagger): http://127.0.0.1:8000/docs

On first start the app creates the database and seeds 50 books, demo users, 40 synthetic readers and ~600 ratings.

**Demo accounts (local use only):** demo readers use the password `Password@123` (e.g. `emma@example.com`). The admin account is configured through `ADMIN_EMAIL` and `ADMIN_PASSWORD` in your `.env`.

## ⚙️ Configuration

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key (use a long random value) |
| `DATABASE_URL` | Database connection string |
| `SEED_ON_STARTUP` | Seed demo data on first run (`false` in production) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Admin account |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime |

> ⚠️ Before any real deployment: set a strong `SECRET_KEY`, change the admin credentials, and set `SEED_ON_STARTUP=false`.

## 🐳 Docker

```bash
docker build -t nextread .
docker run -p 8000:8000 --env-file .env nextread
```

## ✅ Tests

```bash
python -m pytest -q
```

Covers the API, feedback and undo, swipe deck, rows, moods, explanations, taste profile, compare, search, DB migration and recommender behaviour.

## 🔌 API overview

Full interactive docs are available at `/docs`.

| Area | Endpoints |
|---|---|
| Auth / profile | `POST /auth/register`, `POST /auth/login`, `GET/PUT /users/me`, `GET /users/me/taste` |
| Books | `GET /books`, `GET /books/{id}`, `GET /books/{id}/similar`, `GET /books/suggest`, `GET /books/compare` |
| Reviews / wishlist | `PUT/DELETE /books/{id}/review`, `GET/POST/DELETE /wishlist` |
| Feedback | `POST /feedback`, `DELETE /feedback/{book_id}`, `GET /feedback` |
| Recommendations | `GET /recommendations`, `/rows`, `/mood`, `/deck`, `/weekly`, `/trending`, `/{book_id}/explain` |
| Admin | `/admin/books`, `/admin/reviews`, `/admin/users`, `/admin/stats`, `/admin/analytics` |

## 📁 Project structure

```
app/
  main.py  models.py  migrations.py  recommender.py  moods.py  taste.py  presenters.py
  routers/            API route modules
  static/             index.html, css/, js/ (SPA modules)
tests/                test_api.py, test_features.py
Dockerfile  requirements.txt  .env.example
```

## 🗄 Database migrations

On startup the app creates missing tables and runs `app/migrations.py`, which adds any missing columns and backfills new data. Both steps are idempotent and never drop or overwrite existing data.

## 🗺 Roadmap

- [ ] PostgreSQL + Alembic migrations
- [ ] Rate limiting on auth endpoints
- [ ] Redis caching for recommendation rows
- [ ] Larger real-world dataset via Open Library import
- [ ] Test coverage badge

## 📄 License

Released under the [MIT License](LICENSE).

## 👤 Author

**Uday Garodhara**: [LinkedIn](https://www.linkedin.com/in/uday-garodhara-078223283/) · [GitHub](https://github.com/Uday170604)

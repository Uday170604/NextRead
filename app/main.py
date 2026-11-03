import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, models  # noqa: F401  (models import registers the tables)
from .database import Base, SessionLocal, engine
from .migrations import backfill, migrate
from .routers import admin, auth, books, feedback, recommendations, reviews, users, wishlist
from .seed import seed

STATIC = Path(__file__).parent / "static"


log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if config.SECRET_KEY.startswith("change-me"):
        log.warning("SECRET_KEY is the insecure default - set the SECRET_KEY environment variable before deploying.")
    Base.metadata.create_all(engine)   # creates missing tables (e.g. feedback)
    migrate(engine)                    # adds missing columns to tables from older versions
    with SessionLocal() as db:
        if config.SEED_ON_STARTUP:
            seed(db)
        backfill(db)                   # idempotent: covers/pages/mood tags + feedback rows for old data
    yield


app = FastAPI(
    title="NextRead",
    description=(
        "NextRead helps readers decide what to read next. Hybrid recommender (content + collaborative + popularity) "
        "with explicit feedback, mood re-ranking, diversity and explanations; JWT auth, ratings, wishlist and an admin console."
    ),
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, users.router, books.router, reviews.router, wishlist.router, feedback.router,
          recommendations.router, admin.router):
    app.include_router(r)

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}

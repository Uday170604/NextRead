"""Tests for NextRead v2: feedback, undo, deck, rows, mood, explain, taste, compare, search, migration, recommender behaviour."""
import tempfile

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app import migrations
from app.database import Base, SessionLocal
from app.models import Book, User
from app.recommender import Engine


def book_id(client, title):
    return client.get(f"/books?q={title}").json()["items"][0]["id"]


def fb(client, headers, bid, action, **kw):
    return client.post("/feedback", json={"book_id": bid, "action": action, **kw}, headers=headers)


# ---------------- catalogue fields ----------------
def test_seeded_books_have_cover_pages_and_mood_tags(client):
    items = client.get("/books?limit=100").json()["items"]
    assert len(items) >= 50
    dune = next(b for b in items if b["title"] == "Dune")
    assert dune["page_count"] == 612 and dune["cover_url"].startswith("https://covers.openlibrary.org/")
    assert all(isinstance(b["mood_tags"], list) for b in items)
    assert sum(bool(b["mood_tags"]) for b in items) >= 40     # derived tags exist for nearly every book


def test_mood_list_and_filters(client):
    moods = client.get("/moods").json()
    assert {m["key"] for m in moods} >= {"light", "mind-bending", "quick", "epic", "dark"}
    quick = client.get("/books?mood=quick&limit=100").json()["items"]
    assert quick and all("quick" in b["mood_tags"] for b in quick)
    short = client.get("/books?pages_max=220&limit=100").json()["items"]
    assert short and all(b["page_count"] <= 220 for b in short)
    long_ = client.get("/books?pages_min=800&limit=100").json()["items"]
    assert long_ and all(b["page_count"] >= 800 for b in long_)
    assert client.get("/books?mood=nonsense").status_code == 422


def test_admin_can_set_cover_pages_moods_and_validation(client, admin):
    base = {"title": "Moody Book", "authors": ["M A"], "genres": ["Thriller"]}
    r = client.post("/admin/books", json={**base, "cover_url": "https://example.com/c.jpg", "page_count": 180, "mood_tags": ["quick", "dark"]}, headers=admin)
    assert r.status_code == 201 and r.json()["page_count"] == 180 and r.json()["mood_tags"] == ["quick", "dark"]
    r2 = client.post("/admin/books", json={**base, "title": "Derived Moods"}, headers=admin)
    assert r2.status_code == 201 and "dark" in r2.json()["mood_tags"]           # derived from the Thriller genre
    assert client.post("/admin/books", json={**base, "title": "B1", "cover_url": "javascript:alert(1)"}, headers=admin).status_code == 422
    assert client.post("/admin/books", json={**base, "title": "B2", "mood_tags": ["bogus"]}, headers=admin).status_code == 422
    assert client.post("/admin/books", json={**base, "title": "B3", "page_count": 0}, headers=admin).status_code == 422


# ---------------- feedback ----------------
def test_feedback_requires_auth_and_validates(client, new_user):
    headers, _ = new_user
    assert client.post("/feedback", json={"book_id": 1, "action": "saved"}).status_code == 401
    assert client.get("/feedback").status_code == 401
    assert fb(client, headers, 99999, "saved").status_code == 404
    assert fb(client, headers, 1, "loved").status_code == 422
    assert fb(client, headers, 1, "read", rating=9).status_code == 422
    assert fb(client, headers, 1, "not_interested", reason="boring").status_code == 422
    assert client.delete("/feedback/1", headers=headers).status_code == 404


def test_feedback_lifecycle_list_and_undo(client, new_user):
    headers, _ = new_user
    a, b, c = (book_id(client, t) for t in ("Cosmos", "Dune", "Gone Girl"))
    r = fb(client, headers, a, "interested")
    assert r.status_code == 200 and r.json()["action"] == "interested" and r.json()["taste"]["signals"] == 1
    fb(client, headers, b, "not_interested", reason="too_long")
    fb(client, headers, c, "read", rating=4)
    assert [i["book"]["id"] for i in client.get("/feedback?action=interested", headers=headers).json()] == [a]
    ni = client.get("/feedback?action=not_interested", headers=headers).json()
    assert ni[0]["reason"] == "too_long"
    read = client.get("/feedback?action=read", headers=headers).json()
    assert read[0]["rating"] == 4 and client.get(f"/books/{c}", headers=headers).json()["my_rating"] == 4
    assert len(client.get("/feedback", headers=headers).json()) == 3
    assert client.get("/feedback?action=bogus", headers=headers).status_code == 422
    # a later decision replaces the earlier one (one decision per book)
    fb(client, headers, a, "not_interested")
    assert client.get("/feedback?action=interested", headers=headers).json() == []
    # undo
    u = client.delete(f"/feedback/{b}", headers=headers)
    assert u.status_code == 200 and u.json()["removed"] == "not_interested"
    assert client.delete(f"/feedback/{b}", headers=headers).status_code == 404
    u = client.delete(f"/feedback/{c}", headers=headers)
    assert u.json()["removed"] == "read" and client.get(f"/books/{c}", headers=headers).json()["my_rating"] is None  # rating-only read is undone too


def test_undo_read_keeps_written_review(client, new_user):
    headers, _ = new_user
    bid = book_id(client, "Outliers")
    client.put(f"/books/{bid}/review", json={"rating": 5, "comment": "Great"}, headers=headers)
    assert client.get("/feedback?action=read", headers=headers).json()[0]["book"]["id"] == bid   # rating counts as "already read"
    u = client.delete(f"/feedback/{bid}", headers=headers).json()
    assert u["rating_kept"] is True and client.get(f"/books/{bid}", headers=headers).json()["my_rating"] == 5


def test_saved_feedback_and_wishlist_stay_in_sync(client, new_user):
    headers, _ = new_user
    bid = book_id(client, "Sapiens")
    fb(client, headers, bid, "saved")
    assert [b["id"] for b in client.get("/wishlist", headers=headers).json()] == [bid]
    client.delete(f"/feedback/{bid}", headers=headers)
    assert client.get("/wishlist", headers=headers).json() == []
    client.post(f"/wishlist/{bid}", headers=headers)
    assert client.get("/feedback?action=saved", headers=headers).json()[0]["book"]["id"] == bid
    client.delete(f"/wishlist/{bid}", headers=headers)
    assert client.get("/feedback", headers=headers).json() == []
    fb(client, headers, bid, "saved")
    fb(client, headers, bid, "not_interested")
    assert client.get("/wishlist", headers=headers).json() == []        # a new decision supersedes the bookmark


# ---------------- recommender behaviour ----------------
def all_surfaces(client, headers, limit=50):
    ids = {r["book"]["id"] for r in client.get(f"/recommendations?limit={limit}", headers=headers).json()}
    ids |= {c["book"]["id"] for c in client.get(f"/recommendations/deck?limit=30", headers=headers).json()["cards"]}
    ids |= {i["book"]["id"] for row in client.get("/recommendations/rows", headers=headers).json() for i in row["items"]}
    ids |= {r["book"]["id"] for r in client.get("/recommendations/mood?moods=dark&limit=50", headers=headers).json()}
    f = client.get("/recommendations/featured", headers=headers)
    if f.status_code == 200:
        ids.add(f.json()["book"]["id"])
    return ids


def test_rejected_books_never_reappear(client, new_user):
    headers, _ = new_user
    client.put("/users/me/preferences", json={"favorite_genres": ["Mystery", "Thriller"]}, headers=headers)
    rejected = []
    for _ in range(4):
        top = client.get("/recommendations/featured", headers=headers).json()["book"]["id"]
        fb(client, headers, top, "not_interested")
        rejected.append(top)
    assert len(set(rejected)) == 4                                     # each reject surfaces a new featured book
    assert not set(rejected) & all_surfaces(client, headers)


def test_not_interested_pushes_down_similar_books(client, new_user):
    headers, _ = new_user
    client.put("/users/me/preferences", json={"favorite_genres": ["Mystery"]}, headers=headers)
    base = {r["book"]["title"]: r["score"] for r in client.get("/recommendations?limit=50", headers=headers).json()}
    victim = book_id(client, "Gone Girl")
    fb(client, headers, victim, "not_interested", reason="not_my_genre")
    after = {r["book"]["title"]: r["score"] for r in client.get("/recommendations?limit=50", headers=headers).json()}
    assert "Gone Girl" not in after
    similar = [t for t in ("The Girl with the Dragon Tattoo", "The Da Vinci Code") if t in base and t in after]
    assert similar and all(after[t] < base[t] for t in similar)        # negative signal on similar / same-genre books


def test_too_long_reason_penalises_long_books(client, new_user):
    headers, _ = new_user
    client.put("/users/me/preferences", json={"favorite_genres": ["Fantasy"]}, headers=headers)
    before = {r["book"]["title"]: r["score"] for r in client.get("/recommendations?limit=50", headers=headers).json()}
    fb(client, headers, book_id(client, "The Name of the Wind"), "not_interested", reason="too_long")   # 662 pages
    after = {r["book"]["title"]: r["score"] for r in client.get("/recommendations?limit=50", headers=headers).json()}
    assert "A Game of Thrones" in after and after["A Game of Thrones"] < before["A Game of Thrones"]    # 694 pages
    assert after["The Hobbit"] >= before["The Hobbit"] - 0.2 and "The Hobbit" in after                  # short book not hit by the length penalty


def test_interested_and_saved_are_positive_signals(client, new_user):
    headers, _ = new_user
    for t in ("Dune", "Foundation", "Neuromancer"):
        fb(client, headers, book_id(client, t), "interested")
    recs = client.get("/recommendations?limit=10", headers=headers).json()
    assert sum("Science Fiction" in r["book"]["genres"] for r in recs[:6]) >= 2
    assert any("interested in" in r["reason"] for r in recs)


def test_diversity_mmr_spreads_genres(client, new_user):
    headers, _ = new_user
    client.put("/users/me/preferences", json={"favorite_genres": ["Mystery"]}, headers=headers)
    uid = client.get("/users/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        eng, user = Engine(db), db.get(User, uid)
        plain = eng.recommend(user, 8, diversify=False)
        diverse = eng.recommend(user, 8, diversify=True, explore=False)
        combos = lambda recs: len({frozenset(eng.genre_set[r.book_id]) for r in recs})  # noqa: E731
        assert combos(diverse) >= combos(plain)
        assert {r.book_id for r in diverse} != {r.book_id for r in plain}               # re-ranking actually changed the list
        cold = eng.recommend(db.get(User, uid), 10)
        assert any(r.algorithm == "exploration" for r in cold)                           # one exploration slot for a new genre
        expl = next(r for r in cold if r.algorithm == "exploration")
        assert not (eng.genre_set[expl.book_id] & {"mystery"})


def test_cold_start_onboarding_flow(client, new_user):
    headers, _ = new_user
    t = client.get("/users/me/taste", headers=headers).json()
    assert t["needs_onboarding"] is True and t["learned_pct"] == 0 and t["genres"] == []
    assert client.post("/users/me/onboarding", json={"favorite_moods": ["nope"]}, headers=headers).status_code == 422
    me = client.post("/users/me/onboarding", json={"favorite_genres": ["Fantasy", "Totally Made Up"], "favorite_moods": ["epic", "dark"]}, headers=headers).json()
    assert me["favorite_genres"] == ["Fantasy"] and me["favorite_moods"] == ["epic", "dark"] and me["onboarded"] is True
    t = client.get("/users/me/taste", headers=headers).json()
    assert t["needs_onboarding"] is False and t["learned_pct"] > 0
    d = client.get("/recommendations/deck?limit=8", headers=headers).json()
    assert d["calibrating"] is True and len(d["cards"]) == 8
    assert sum("Fantasy" in c["book"]["genres"] for c in d["cards"]) >= 2          # onboarding genres steer the swipe deck
    seen = set()
    for _ in range(8):                                                               # swipe 8 books
        card = client.get("/recommendations/deck?limit=3", headers=headers).json()["cards"][0]["book"]["id"]
        assert card not in seen
        seen.add(card)
        r = fb(client, headers, card, "interested" if len(seen) % 2 else "not_interested")
    assert r.json()["taste"]["learned_pct"] >= 60                                     # the taste meter sharpens (~64% after 8 swipes)
    assert client.get("/recommendations/deck?limit=3", headers=headers).json()["calibrating"] is False


def test_cold_start_deck_is_genre_diverse(client, new_user):
    headers, _ = new_user
    cards = client.get("/recommendations/deck?limit=8", headers=headers).json()["cards"]
    assert len({c["book"]["genres"][0] for c in cards}) >= 5                          # calibration deck spans many genres


# ---------------- deck / rows / featured / weekly ----------------
def test_deck_reranks_live_after_feedback(client, new_user):
    headers, _ = new_user
    before = client.get("/recommendations/deck?limit=10", headers=headers).json()
    assert before["taste"]["learned_pct"] == 0
    for t in ("Clean Code", "Fluent Python", "Python Crash Course"):
        fb(client, headers, book_id(client, t), "interested")
    after = client.get("/recommendations/deck?limit=10", headers=headers).json()
    assert [c["book"]["id"] for c in after["cards"]] != [c["book"]["id"] for c in before["cards"]]
    assert after["taste"]["learned_pct"] > 0
    assert sum("Computer Science" in c["book"]["genres"] for c in after["cards"][:5]) >= 2
    ex = after["cards"][0]["book"]["id"]
    again = client.get(f"/recommendations/deck?limit=10&exclude={ex}", headers=headers).json()["cards"]
    assert ex not in [c["book"]["id"] for c in again]
    assert client.get("/recommendations/deck?exclude=abc", headers=headers).status_code == 422
    assert client.get("/recommendations/deck").status_code == 401


def test_featured_show_me_another_and_breakdown(client, john):
    f1 = client.get("/recommendations/featured", headers=john).json()
    assert f1["reason"] and 1 <= f1["match_pct"] <= 99
    assert {b["key"] for b in f1["breakdown"]} >= {"content", "pop"}
    f2 = client.get(f"/recommendations/featured?exclude={f1['book']['id']}", headers=john).json()
    assert f2["book"]["id"] != f1["book"]["id"]


def test_rows_for_experienced_and_new_user(client, john, new_user):
    rows = client.get("/recommendations/rows", headers=john).json()
    ids = [r["id"] for r in rows]
    assert ids[0] == "top-picks" and {"trending", "hidden-gems", "readers-like-you", "new-to-explore"} <= set(ids)
    assert any(i.startswith("because-liked") for i in ids)
    seen = {r["book_id"] for r in client.get("/reviews/mine", headers=john).json()}
    for row in rows:
        assert row["title"] and row["items"], row["id"]
        for it in row["items"]:
            assert it["book"]["id"] not in seen and it["reason"] and 1 <= it["match_pct"] <= 99
    gems = next(r for r in rows if r["id"] == "hidden-gems")["items"]
    assert all(g["book"]["avg_rating"] >= 3.75 for g in gems)
    headers, _ = new_user
    new_ids = [r["id"] for r in client.get("/recommendations/rows", headers=headers).json()]
    assert "top-picks" in new_ids and "trending" in new_ids and "readers-like-you" not in new_ids
    assert client.get("/recommendations/rows").status_code == 401


def test_favourite_authors_row(client, new_user):
    headers, _ = new_user
    client.put("/users/me/preferences", json={"favorite_authors": ["Agatha Christie"]}, headers=headers)
    rows = {r["id"]: r for r in client.get("/recommendations/rows", headers=headers).json()}
    assert all("Agatha Christie" in i["book"]["authors"] for i in rows["favourite-authors"]["items"])


def test_weekly_summary(client, new_user):
    headers, _ = new_user
    fb(client, headers, book_id(client, "Dune"), "interested")
    fb(client, headers, book_id(client, "Cosmos"), "not_interested")
    w = client.get("/recommendations/weekly", headers=headers).json()
    assert w["interested"] == 1 and w["passed"] == 1 and len(w["picks"]) == 3 and w["name"] == "Test"


# ---------------- mood layer ----------------
def test_mood_rerank_is_transparent_and_validated(client, john):
    r = client.get("/recommendations/mood?moods=quick&limit=8", headers=john)
    assert r.status_code == 200 and r.json()
    for it in r.json():
        assert it["book"]["page_count"] <= 350 and it["mood_signals"] and "length" in it["mood_signals"][0]
        assert "Quick read" in it["reason"]
    dark = client.get("/recommendations/mood?moods=dark&limit=8", headers=john).json()
    assert any({"Thriller", "Mystery", "Horror"} & set(i["book"]["genres"]) for i in dark[:3])
    both = client.get("/recommendations/mood?moods=quick,dark&limit=8", headers=john).json()
    assert all(i["book"]["page_count"] <= 350 and {"Thriller", "Mystery", "Horror", "Dystopian"} & set(i["book"]["genres"]) for i in both)   # must fit BOTH moods
    assert client.get("/recommendations/mood?moods=bogus", headers=john).status_code == 422
    assert client.get("/recommendations/mood?moods=quick,dark,light", headers=john).status_code == 422
    assert client.get("/recommendations/mood", headers=john).status_code == 422
    assert client.get("/recommendations/mood?moods=quick").status_code == 401


# ---------------- explain / taste / compare ----------------
def test_explain_breakdown(client, john):
    bid = client.get("/recommendations/featured", headers=john).json()["book"]["id"]
    x = client.get(f"/recommendations/{bid}/explain", headers=john).json()
    assert x["book_id"] == bid and x["summary"] and x["reason"]
    keys = {b["key"] for b in x["breakdown"]}
    assert {"content", "pop", "fav"} <= keys
    assert all(0 <= b["value"] <= 1 and abs(b["contribution"] - b["value"] * b["weight"]) < 0.01 for b in x["breakdown"])
    assert abs(sum(b["weight"] for b in x["breakdown"]) - 1) < 0.02
    assert client.get("/recommendations/99999/explain", headers=john).status_code == 404
    assert client.get(f"/recommendations/{bid}/explain").status_code == 401


def test_explain_shows_penalty_for_rejected_similar(client, new_user):
    headers, _ = new_user
    client.put("/users/me/preferences", json={"favorite_genres": ["Mystery"]}, headers=headers)
    fb(client, headers, book_id(client, "Gone Girl"), "not_interested", reason="not_my_genre")
    x = client.get(f"/recommendations/{book_id(client, 'The Da Vinci Code')}/explain", headers=headers).json()
    assert x["penalties"] and "Held back by" in x["summary"]


def test_taste_profile(client, john):
    t = client.get("/users/me/taste", headers=john).json()
    assert t["needs_onboarding"] is False and t["ratings_count"] >= 9 and 1 <= t["avg_rating"] <= 5
    assert t["genres"][0]["score"] == 100 and len(t["genres"]) <= 8
    assert {g["name"] for g in t["genres"]} & {"Science Fiction", "Fantasy"}
    assert t["authors"] and sum(m["pct"] for m in t["moods"]) in range(98, 103)
    assert t["dna"].startswith("You're a") and 0 < t["learned_pct"] <= 99
    assert set(t["counts"]) == {"interested", "saved", "read", "not_interested"}
    assert client.get("/users/me/taste").status_code == 401


def test_compare(client, john):
    a, b = book_id(client, "Dune"), book_id(client, "Foundation")
    r = client.get(f"/books/compare?a={a}&b={b}", headers=john).json()
    assert "Science Fiction" in r["shared_genres"] and r["better_fit"] in ("a", "b", "tie") and r["why"]
    assert r["fit"]["a"] and r["fit"]["b"]
    anon = client.get(f"/books/compare?a={a}&b={b}").json()
    assert anon["fit"] == {"a": None, "b": None} and "Log in" in anon["why"]
    assert client.get(f"/books/compare?a={a}&b={a}").status_code == 422
    assert client.get(f"/books/compare?a={a}&b=99999").status_code == 404


# ---------------- search ----------------
def test_suggestions_and_did_you_mean(client):
    s = client.get("/books/suggest?q=har").json()
    assert {x["type"] for x in s} >= {"title", "author"} and any(x["text"].startswith("Harry Potter") and x["book_id"] for x in s)
    assert any(x["type"] == "genre" for x in client.get("/books/suggest?q=fant").json())
    assert client.get("/books/suggest?q=%25").json() == []
    page = client.get("/books?q=harry poter").json()
    assert page["total"] == 0 and page["did_you_mean"] == "harry potter"
    assert client.get("/books?q=Pride and Prejudise").json()["did_you_mean"].lower().startswith("pride and prejudice")
    assert client.get("/books?q=dune").json()["did_you_mean"] is None


# ---------------- admin analytics ----------------
def test_admin_analytics(client, admin, new_user):
    headers, _ = new_user
    fb(client, headers, book_id(client, "Dracula"), "interested")
    fb(client, headers, book_id(client, "Rich Dad Poor Dad"), "not_interested", reason="know_story")
    a = client.get("/admin/analytics?limit=20", headers=admin).json()
    assert a["totals"]["interested"] >= 1 and a["totals"]["not_interested"] >= 1 and 0 < a["acceptance_rate"] < 1
    assert any(x["title"] == "Rich Dad Poor Dad" for x in a["most_rejected"]) and a["most_liked"]
    assert a["reject_reasons"].get("know_story", 0) >= 1
    assert client.get("/admin/analytics", headers=headers).status_code == 403


# ---------------- migration safety ----------------
def test_migration_upgrades_old_database_without_data_loss():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    eng = create_engine(f"sqlite:///{tmp.name}")
    Base.metadata.create_all(eng)
    with Session(eng) as db:
        from app.seed import seed
        seed(db)
    # simulate a database created by the previous version: no new columns, no feedback table
    with eng.begin() as c:
        c.execute(text("DROP TABLE feedback"))
        for col in ("cover_url", "page_count", "mood_tags"):
            c.execute(text(f"ALTER TABLE books DROP COLUMN {col}"))
        for col in ("favorite_moods", "onboarded_at"):
            c.execute(text(f"ALTER TABLE users DROP COLUMN {col}"))
        users_before = c.execute(text("SELECT COUNT(*) FROM users")).scalar()
        reviews_before = c.execute(text("SELECT COUNT(*) FROM reviews")).scalar()
    assert "cover_url" not in {c["name"] for c in inspect(eng).get_columns("books")}

    Base.metadata.create_all(eng)                      # what the app does first: creates the missing feedback table
    added = migrations.migrate(eng)
    assert sorted(added) == ["books.cover_url", "books.mood_tags", "books.page_count", "users.favorite_moods", "users.onboarded_at"]
    assert migrations.migrate(eng) == []               # idempotent: a second start changes nothing
    with Session(eng) as db:
        counts = migrations.backfill(db)
        assert counts["books_enriched"] >= 45 and counts["mood_tags"] >= 50 and counts["feedback_read"] == reviews_before
        dune = db.scalar(select(Book).where(Book.title == "Dune"))
        assert dune.page_count == 612 and dune.cover_url and dune.mood_tags
        again = migrations.backfill(db)
        assert again == {"books_enriched": 0, "mood_tags": 0, "feedback_read": 0, "feedback_saved": again["feedback_saved"]} and again["feedback_saved"] == 0
        assert db.scalar(text("SELECT COUNT(*) FROM users")) == users_before and db.scalar(text("SELECT COUNT(*) FROM reviews")) == reviews_before
        # an old DB must work with the new engine too
        eng_rec = Engine(db)
        user = db.scalar(select(User).where(User.email == "john@example.com"))
        assert len(eng_rec.recommend(user, 5)) == 5


def test_migration_keeps_custom_values_and_runs_on_fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    eng = create_engine(f"sqlite:///{tmp.name}")
    Base.metadata.create_all(eng)
    assert migrations.migrate(eng) == []               # nothing to add on a brand-new schema
    with Session(eng) as db:
        from app.seed import seed
        seed(db, with_demo_users=False)
        b = db.scalar(select(Book).where(Book.title == "Dune"))
        b.cover_url, b.page_count, b.mood_tags = "https://example.com/mine.jpg", 999, ["light"]
        db.commit()
        migrations.backfill(db)
        db.refresh(b)
        assert (b.cover_url, b.page_count, b.mood_tags) == ("https://example.com/mine.jpg", 999, ["light"])   # never overwrites


def test_homepage_is_nextread_and_static_modules_served(client):
    html = client.get("/").text
    assert "<title>NextRead" in html and "BookNook" not in html and "/static/js/main.js" in html
    for path in ("css/app.css", "js/api.js", "js/deck.js", "js/rows.js", "js/detail.js", "js/taste.js", "js/theme.js"):
        assert client.get(f"/static/{path}").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "NextRead"

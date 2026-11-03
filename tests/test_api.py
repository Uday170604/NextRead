"""End-to-end API tests (each test maps to a use case in the project report)."""
from app.routers import admin as admin_router


# ---------- authentication (UC-01) ----------
def test_register_login_and_profile(client):
    r = client.post("/auth/register", json={"name": "Asha Rao", "email": "Asha@Test.com", "password": "longenough",
                                            "role": "student", "date_of_birth": "2002-04-01", "city": "Rajkot",
                                            "favorite_genres": ["Fantasy", "Mystery"]})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "asha@test.com" and body["age"] >= 23
    assert sorted(body["favorite_genres"]) == ["Fantasy", "Mystery"]
    assert "password" not in body and "password_hash" not in body

    assert client.post("/auth/register", json={"name": "Dup", "email": "asha@test.com", "password": "longenough"}).status_code == 409
    assert client.post("/auth/login", data={"username": "asha@test.com", "password": "wrong"}).status_code == 401
    tok = client.post("/auth/login", data={"username": "asha@test.com", "password": "longenough"}).json()["access_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["name"] == "Asha Rao"


def test_register_validation_and_no_self_admin(client):
    assert client.post("/auth/register", json={"name": "X Y", "email": "not-an-email", "password": "longenough"}).status_code == 422
    assert client.post("/auth/register", json={"name": "X Y", "email": "a@b.co", "password": "short"}).status_code == 422
    assert client.post("/auth/register", json={"name": "X Y", "email": "a@b.co", "password": "longenough", "role": "admin"}).status_code == 422


def test_protected_routes_need_token(client):
    assert client.get("/users/me").status_code == 401
    assert client.get("/recommendations").status_code == 401
    assert client.get("/wishlist").status_code == 401
    assert client.get("/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


# ---------- browse / search / details (UC-02, 03, 06) ----------
def test_browse_search_filter_sort(client):
    page = client.get("/books?limit=5").json()
    assert page["total"] >= 40 and len(page["items"]) == 5
    assert client.get("/books?q=hawking").json()["total"] == 1                      # author search
    assert client.get("/books?q=dragon").json()["total"] >= 1                       # description/title search
    fantasy = client.get("/books?genre=fantasy&limit=100").json()
    assert fantasy["total"] > 3 and all("Fantasy" in b["genres"] for b in fantasy["items"])
    old = client.get("/books?year_to=1900&limit=100").json()["items"]
    assert old and all(b["publication_year"] <= 1900 for b in old)
    top = client.get("/books?sort=rating&limit=3").json()["items"]
    assert top[0]["avg_rating"] >= top[1]["avg_rating"] >= top[2]["avg_rating"]
    assert all(b["avg_rating"] >= 4 for b in client.get("/books?min_rating=4&limit=100").json()["items"])


def test_book_details_and_similar(client):
    book = client.get("/books?q=Dune").json()["items"][0]
    detail = client.get(f"/books/{book['id']}").json()
    assert detail["title"] == "Dune" and detail["authors"] == ["Frank Herbert"] and detail["ratings_count"] > 0
    similar = client.get(f"/books/{book['id']}/similar").json()
    assert 1 <= len(similar) <= 6 and all(b["id"] != book["id"] for b in similar)
    assert client.get("/books/99999").status_code == 404
    assert "Fantasy" in client.get("/genres").json() and "Frank Herbert" in client.get("/authors").json()


# ---------- rate / review (UC-05, 07) ----------
def test_rate_and_review_lifecycle(client, new_user):
    headers, _ = new_user
    book_id = client.get("/books?q=Atomic Habits").json()["items"][0]["id"]
    before = client.get(f"/books/{book_id}").json()
    r = client.put(f"/books/{book_id}/review", json={"rating": 5, "comment": "Life changing"}, headers=headers)
    assert r.status_code == 200 and r.json()["rating"] == 5
    after = client.get(f"/books/{book_id}", headers=headers).json()
    assert after["ratings_count"] == before["ratings_count"] + 1 and after["my_rating"] == 5
    # editing replaces, it does not duplicate (composite key user_id + book_id)
    client.put(f"/books/{book_id}/review", json={"rating": 3}, headers=headers)
    assert client.get(f"/books/{book_id}").json()["ratings_count"] == before["ratings_count"] + 1
    assert client.get("/reviews/mine", headers=headers).json()[0]["book_title"] == "Atomic Habits"
    assert client.put(f"/books/{book_id}/review", json={"rating": 6}, headers=headers).status_code == 422
    assert client.delete(f"/books/{book_id}/review", headers=headers).status_code == 204
    assert client.delete(f"/books/{book_id}/review", headers=headers).status_code == 404


# ---------- wishlist (UC-08) ----------
def test_wishlist(client, new_user):
    headers, _ = new_user
    book_id = client.get("/books?q=Cosmos").json()["items"][0]["id"]
    assert client.post(f"/wishlist/{book_id}", headers=headers).status_code == 201
    assert client.post(f"/wishlist/{book_id}", headers=headers).status_code == 409
    wl = client.get("/wishlist", headers=headers).json()
    assert [b["id"] for b in wl] == [book_id] and wl[0]["in_wishlist"] is True
    assert client.delete(f"/wishlist/{book_id}", headers=headers).status_code == 204
    assert client.get("/wishlist", headers=headers).json() == []
    assert client.post("/wishlist/99999", headers=headers).status_code == 404


# ---------- preferences (UC-09) & recommendations (UC-04) ----------
def test_cold_start_user_gets_popular_books(client, new_user):
    headers, _ = new_user
    recs = client.get("/recommendations?limit=5", headers=headers).json()
    assert len(recs) == 5 and {r["algorithm"] for r in recs} == {"popularity"}
    assert recs[0]["score"] >= recs[-1]["score"]


def test_preferences_steer_recommendations(client, new_user):
    headers, _ = new_user
    r = client.put("/users/me/preferences", json={"favorite_genres": ["Mystery"], "favorite_authors": ["Agatha Christie"]}, headers=headers)
    assert r.status_code == 200 and r.json()["favorite_genres"] == ["Mystery"]
    recs = client.get("/recommendations?limit=5", headers=headers).json()
    assert sum("Mystery" in x["book"]["genres"] for x in recs) >= 3
    assert any(x["algorithm"] == "content-based" for x in recs)


def test_personalised_recs_exclude_seen_books_and_explain(client, john):
    seen = {r["book_id"] for r in client.get("/reviews/mine", headers=john).json()}
    seen |= {b["id"] for b in client.get("/wishlist", headers=john).json()}
    recs = client.get("/recommendations?limit=10", headers=john).json()
    assert len(recs) == 10
    assert not seen & {r["book"]["id"] for r in recs}
    assert all(r["reason"] for r in recs)
    scifi_fantasy = sum(bool({"Science Fiction", "Fantasy"} & set(r["book"]["genres"])) for r in recs[:5])
    assert scifi_fantasy >= 3  # a sci-fi/fantasy fan is mostly recommended sci-fi/fantasy


def test_new_ratings_change_recommendations(client, new_user):
    headers, _ = new_user
    before = [r["book"]["id"] for r in client.get("/recommendations?limit=5", headers=headers).json()]
    for q in ("Clean Code", "Fluent Python", "Python Crash Course"):
        bid = client.get(f"/books?q={q}").json()["items"][0]["id"]
        client.put(f"/books/{bid}/review", json={"rating": 5}, headers=headers)
    after = client.get("/recommendations?limit=5", headers=headers).json()
    assert [r["book"]["id"] for r in after] != before
    assert sum("Computer Science" in r["book"]["genres"] for r in after) >= 3


def test_trending_is_public(client):
    r = client.get("/recommendations/trending?limit=4")
    assert r.status_code == 200 and len(r.json()) == 4


# ---------- admin (UC-10..13) ----------
def test_admin_requires_admin_role(client, john):
    assert client.get("/admin/stats", headers=john).status_code == 403
    assert client.post("/admin/books", json={}, headers=john).status_code == 403
    assert client.get("/admin/stats").status_code == 401


def test_admin_book_crud(client, admin):
    payload = {"title": "Test Driven Development", "isbn": "9780321146533", "description": "Kent Beck on TDD.",
               "publication_year": 2002, "publisher": "Addison-Wesley", "authors": ["Kent Beck"], "genres": ["Computer Science"]}
    r = client.post("/admin/books", json=payload, headers=admin)
    assert r.status_code == 201
    book = r.json()
    assert client.post("/admin/books", json=payload, headers=admin).status_code == 409  # duplicate ISBN
    payload["title"] = "Test-Driven Development: By Example"
    assert client.put(f"/admin/books/{book['id']}", json=payload, headers=admin).json()["title"].startswith("Test-Driven")
    assert client.delete(f"/admin/books/{book['id']}", headers=admin).status_code == 204
    assert client.get(f"/books/{book['id']}").status_code == 404


def test_admin_moderation_hides_review_from_public_and_stats(client, admin, new_user):
    headers, email = new_user
    bid = client.get("/books?q=Gone Girl").json()["items"][0]["id"]
    client.put(f"/books/{bid}/review", json={"rating": 1, "comment": "spam spam spam"}, headers=headers)
    uid = client.get("/users/me", headers=headers).json()["id"]
    assert any(r["user_id"] == uid for r in client.get(f"/books/{bid}/reviews").json())
    queue = client.get("/admin/reviews?hidden=false", headers=admin).json()
    assert any(r["user_email"] == email for r in queue)
    assert client.patch(f"/admin/reviews/{uid}/{bid}?hidden=true", headers=admin).status_code == 200
    assert not any(r["user_id"] == uid for r in client.get(f"/books/{bid}/reviews").json())
    assert client.patch(f"/admin/reviews/{uid}/{bid}?hidden=false", headers=admin).json()["is_hidden"] is False


def test_admin_stats_and_user_deactivation(client, admin, new_user):
    headers, email = new_user
    s = client.get("/admin/stats", headers=admin).json()
    assert s["books"] >= 50 and s["users"] >= 49 and len(s["top_books"]) == 5
    uid = client.get("/users/me", headers=headers).json()["id"]
    assert client.patch(f"/admin/users/{uid}/active?active=false", headers=admin).status_code == 200
    assert client.get("/users/me", headers=headers).status_code == 401           # existing token no longer works
    assert client.post("/auth/login", data={"username": email, "password": "secret123"}).status_code == 401


def test_external_book_import(client, admin, monkeypatch):
    """The Open Library call is mocked so the test needs no network."""
    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"docs": [
            {"title": "Imported Book One", "author_name": ["Ann Author"], "first_publish_year": 2001, "subject": ["Robotics"]},
            {"title": "Dune", "author_name": ["Frank Herbert"]},          # already exists -> skipped
            {"title": "No Author"},                                          # invalid -> skipped
        ]}
    monkeypatch.setattr(admin_router.httpx, "get", lambda *a, **k: FakeResp())
    r = client.post("/admin/import/openlibrary?query=robots", headers=admin)
    assert r.status_code == 200 and r.json() == {"created": 1, "skipped": 2}
    assert client.get("/books?q=Imported Book One").json()["total"] == 1


def test_health_and_homepage(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "NextRead" in client.get("/").text


# ---------- regression tests for bugs found in the QA / architecture review ----------
def test_profile_update_ignores_null_required_fields(client, new_user):
    headers, _ = new_user
    r = client.put("/users/me", json={"name": None, "role": None, "city": "Rajkot"}, headers=headers)
    assert r.status_code == 200 and r.json()["name"] == "Test User" and r.json()["role"] == "reader" and r.json()["city"] == "Rajkot"


def test_users_cannot_create_catalogue_genres_or_authors(client, new_user):
    headers, _ = new_user
    before = len(client.get("/genres").json()), len(client.get("/authors").json())
    r = client.put("/users/me/preferences", json={"favorite_genres": ["Fantasy", "Totally Made Up"],
                                                  "favorite_authors": ["frank herbert", "Nobody Real"]}, headers=headers)
    assert r.json()["favorite_genres"] == ["Fantasy"] and r.json()["favorite_authors"] == ["Frank Herbert"]
    client.post("/auth/register", json={"name": "Gen Test", "email": "gen@test.com", "password": "longenough", "favorite_genres": ["Bogus"]})
    assert (len(client.get("/genres").json()), len(client.get("/authors").json())) == before


def test_search_treats_wildcards_literally(client):
    assert client.get("/books?q=%25").json()["total"] == 0
    assert client.get("/books?q=_").json()["total"] == 0
    assert client.get("/books?q=hawking").json()["total"] == 1


def test_admin_book_validation_rejects_blank_values(client, admin):
    base = {"title": "Valid", "authors": ["A"], "genres": ["G"]}
    assert client.post("/admin/books", json={**base, "authors": [" "]}, headers=admin).status_code == 422
    assert client.post("/admin/books", json={**base, "genres": []}, headers=admin).status_code == 422
    assert client.post("/admin/books", json={**base, "title": "   "}, headers=admin).status_code == 422


def test_import_with_duplicate_isbns_in_one_batch_does_not_crash(client, admin, monkeypatch):
    class Fake:
        def raise_for_status(self): pass
        def json(self): return {"docs": [{"title": "Dup One", "author_name": ["Q"], "isbn": ["9990001112223"]},
                                         {"title": "Dup Two", "author_name": ["Q"], "isbn": ["9990001112223"]},
                                         {"title": "Dup One", "author_name": ["Q"]}]}
    monkeypatch.setattr(admin_router.httpx, "get", lambda *a, **k: Fake())
    r = client.post("/admin/import/openlibrary?query=dups", headers=admin)
    assert r.status_code == 200 and r.json() == {"created": 1, "skipped": 2}


def test_admin_user_list_and_deleting_wishlisted_book(client, admin, new_user):
    headers, email = new_user
    users = client.get("/admin/users?q=" + email, headers=admin).json()
    assert len(users) == 1 and users[0]["email"] == email and users[0]["is_active"] is True
    assert client.get("/admin/users", headers=headers).status_code == 403
    created = client.post("/admin/books", json={"title": "Temp Wish", "authors": ["T"], "genres": ["G"]}, headers=admin).json()
    client.post(f"/wishlist/{created['id']}", headers=headers)
    client.put(f"/books/{created['id']}/review", json={"rating": 4}, headers=headers)
    assert client.delete(f"/admin/books/{created['id']}", headers=admin).status_code == 204
    assert client.get("/wishlist", headers=headers).json() == [] and client.get("/reviews/mine", headers=headers).json() == []

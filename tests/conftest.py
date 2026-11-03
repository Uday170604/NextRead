import os
import tempfile

# Must be set before the app is imported: use a throw-away database for the test session.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SEED_ON_STARTUP"] = "true"
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ["ADMIN_PASSWORD"] = "AdminPass123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # triggers lifespan -> create tables + seed
        yield c


def _login(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin@test.local", "AdminPass123")


@pytest.fixture(scope="session")
def john(client):
    return _login(client, "john@example.com", "Password@123")


@pytest.fixture()
def new_user(client):
    """A freshly registered reader with no history (cold start)."""
    import uuid
    email = f"{uuid.uuid4().hex[:8]}@test.com"
    r = client.post("/auth/register", json={"name": "Test User", "email": email, "password": "secret123"})
    assert r.status_code == 201, r.text
    return _login(client, email, "secret123"), email

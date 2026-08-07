import pytest

from main import app, urls_collection


def _delete_all_urls():
    for doc in urls_collection.stream():
        doc.reference.delete()


@pytest.fixture(autouse=True)
def clear_store():
    # urls_collection is the real Firestore collection shared across the whole app; reset it so tests can't leak state into each other
    _delete_all_urls()
    yield
    _delete_all_urls()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_shorten_creates_short_code(client):
    resp = client.post("/shorten", json={"url": "https://example.com"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["original_url"] == "https://example.com"
    assert len(body["short_code"]) == 6
    assert body["short_url"].endswith(body["short_code"])


def test_shorten_rejects_missing_url(client):
    resp = client.post("/shorten", json={})
    assert resp.status_code == 400


def test_shorten_rejects_non_http_scheme(client):
    resp = client.post("/shorten", json={"url": "ftp://example.com"})
    assert resp.status_code == 400


def test_urls_lists_created_entries(client):
    client.post("/shorten", json={"url": "https://example.com"})
    resp = client.get("/urls")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 1
    assert body[0]["original_url"] == "https://example.com"


def test_redirect_follows_to_original_url(client):
    create = client.post("/shorten", json={"url": "https://example.com"})
    short_code = create.get_json()["short_code"]

    resp = client.get(f"/{short_code}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://example.com"


def test_redirect_missing_code_returns_404(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404


def test_delete_removes_url(client):
    create = client.post("/shorten", json={"url": "https://example.com"})
    short_code = create.get_json()["short_code"]

    resp = client.delete(f"/{short_code}")
    assert resp.status_code == 200

    resp = client.get(f"/{short_code}", follow_redirects=False)
    assert resp.status_code == 404


def test_delete_missing_code_returns_404(client):
    resp = client.delete("/does-not-exist")
    assert resp.status_code == 404

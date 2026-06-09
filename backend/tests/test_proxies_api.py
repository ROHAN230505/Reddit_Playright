"""Proxy CRUD + validation tests. The live `validate_proxy` is stubbed
so tests don't require external network."""

from __future__ import annotations

import pytest

from app.routes import proxies as proxies_route
from app.services import crypto


@pytest.fixture(autouse=True)
def _stub_validate(monkeypatch):
    calls: list[dict] = []

    def fake_validate(*, scheme, host, port, username=None, password=None, timeout=12):
        calls.append({"scheme": scheme, "host": host, "port": port, "username": username, "password": password})
        # Simulate failure for a sentinel host so we can test failure paths.
        if host == "broken.example":
            return False, None, "stubbed: refused connection"
        return True, "203.0.113.42", None

    monkeypatch.setattr(proxies_route, "validate_proxy", fake_validate)
    yield calls


def test_create_proxy_runs_validation_and_persists(client, _stub_validate):
    resp = client.post(
        "/proxies",
        json={
            "label": "p1",
            "scheme": "http",
            "host": "1.2.3.4",
            "port": 8080,
            "username": "u",
            "password": "secret",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["account_count"] == 0
    assert body["last_check_ip"] == "203.0.113.42"
    assert body["has_password"] is True
    # Stub was called once with decrypted password.
    assert _stub_validate[0]["password"] == "secret"


def test_create_proxy_validation_failure_returns_422_but_persists(client):
    resp = client.post(
        "/proxies",
        json={
            "label": "broken",
            "scheme": "http",
            "host": "broken.example",
            "port": 8080,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "stubbed: refused connection" in detail["error"]
    proxy_id = detail["proxy_id"]
    # Row exists in FAILED state for retry.
    show = client.get("/proxies").json()
    [row] = [r for r in show if r["id"] == proxy_id]
    assert row["status"] == "FAILED"


def test_create_proxy_skip_validation(client, _stub_validate):
    resp = client.post(
        "/proxies",
        json={
            "label": "skipped",
            "scheme": "socks5",
            "host": "1.2.3.4",
            "port": 1080,
            "skip_validation": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACTIVE"
    assert resp.json()["last_checked_at"] is None
    # Validation stub never called.
    assert _stub_validate == []


def test_proxy_label_uniqueness(client):
    client.post("/proxies", json={"label": "dup", "host": "1.2.3.4", "port": 80, "skip_validation": True})
    resp = client.post(
        "/proxies", json={"label": "dup", "host": "1.2.3.5", "port": 80, "skip_validation": True}
    )
    assert resp.status_code == 409


def test_proxy_revalidate_endpoint(client):
    p = client.post(
        "/proxies", json={"label": "p", "host": "1.2.3.4", "port": 80, "skip_validation": True}
    ).json()
    resp = client.post(f"/proxies/{p['id']}/validate")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "ip": "203.0.113.42", "error": None}


def test_proxy_password_decrypts_on_revalidate(client):
    """Validate uses the decrypted password from DB on revalidate, not from request."""
    p = client.post(
        "/proxies",
        json={
            "label": "pw",
            "host": "1.2.3.4",
            "port": 80,
            "username": "u",
            "password": "p",
            "skip_validation": True,
        },
    ).json()
    captured: dict = {}

    def capture(*, scheme, host, port, username=None, password=None, timeout=12):
        captured.update(scheme=scheme, host=host, port=port, username=username, password=password)
        return True, "1.1.1.1", None

    import app.routes.proxies as proxies_module
    proxies_module.validate_proxy = capture  # type: ignore[assignment]
    resp = client.post(f"/proxies/{p['id']}/validate")
    assert resp.status_code == 200
    assert captured["password"] == "p"


def test_delete_proxy_blocked_if_account_uses_it(client):
    p = client.post(
        "/proxies", json={"label": "in-use", "host": "1.2.3.4", "port": 80, "skip_validation": True}
    ).json()
    a = client.post(
        "/accounts",
        json={"username": "bot1", "password": "x", "proxy_id": p["id"]},
    )
    assert a.status_code == 200, a.text
    resp = client.delete(f"/proxies/{p['id']}")
    assert resp.status_code == 409
    # Disable the account → still has it as proxy_id, so delete still blocked.
    # Set proxy_id to null first to free up.
    upd = client.patch(f"/accounts/{a.json()['id']}", json={"proxy_id": 0})
    assert upd.status_code == 200
    resp2 = client.delete(f"/proxies/{p['id']}")
    assert resp2.status_code == 200


def test_proxy_account_count_aggregate(client):
    p = client.post(
        "/proxies", json={"label": "shared", "host": "1.2.3.4", "port": 80, "skip_validation": True}
    ).json()
    client.post("/accounts", json={"username": "a1", "password": "x", "proxy_id": p["id"]})
    client.post("/accounts", json={"username": "a2", "password": "x", "proxy_id": p["id"]})
    rows = client.get("/proxies").json()
    [row] = [r for r in rows if r["id"] == p["id"]]
    assert row["account_count"] == 2

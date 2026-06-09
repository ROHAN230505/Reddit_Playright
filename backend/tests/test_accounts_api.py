"""Reddit-account CRUD, heartbeat, and worker-internal secrets endpoint."""

from __future__ import annotations

import pyotp
import pytest

from app.routes import proxies as proxies_route


@pytest.fixture(autouse=True)
def _stub_validate(monkeypatch):
    monkeypatch.setattr(
        proxies_route,
        "validate_proxy",
        lambda **kw: (True, "203.0.113.42", None),
    )


def _create_proxy(client, label="p1", status="ACTIVE"):
    proxy = client.post(
        "/proxies",
        json={"label": label, "host": "1.2.3.4", "port": 80, "skip_validation": True},
    ).json()
    if status != "ACTIVE":
        client.patch(f"/proxies/{proxy['id']}", json={"status": status})
    return proxy


def test_create_account_minimal(client):
    resp = client.post(
        "/accounts", json={"username": "bot1", "password": "p"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["username"] == "bot1"
    assert body["status"] == "NEW"
    assert body["is_enabled"] is True
    assert body["has_totp"] is False
    assert body["proxy_id"] is None
    assert body["user_data_dir"].replace("\\", "/").endswith("/bot1")


def test_create_account_with_totp_normalizes_secret(client):
    secret = "AAAA AAAA AAAA AAAA"  # spaces should be stripped, lowercased uppered
    client.post(
        "/accounts",
        json={"username": "bot2", "password": "p", "totp_secret": secret},
    )
    # Assert via the worker-internal endpoint that the secret was stored normalized.
    secrets = client.get("/accounts/internal/active").json()
    [bot] = [s for s in secrets if s["username"] == "bot2"]
    assert bot["totp_secret"] == "AAAAAAAAAAAAAAAA"
    assert bot["password"] == "p"
    # And that pyotp can use it.
    code = pyotp.TOTP(bot["totp_secret"]).now()
    assert len(code) == 6 and code.isdigit()


def test_create_account_username_unique(client):
    client.post("/accounts", json={"username": "x", "password": "p"})
    resp = client.post("/accounts", json={"username": "x", "password": "p"})
    assert resp.status_code == 409


def test_create_account_with_inactive_proxy_fails(client):
    proxy = _create_proxy(client, label="bad", status="DISABLED")
    resp = client.post(
        "/accounts",
        json={"username": "bot", "password": "p", "proxy_id": proxy["id"]},
    )
    assert resp.status_code == 422


def test_account_heartbeat_updates_state(client):
    a = client.post("/accounts", json={"username": "hb", "password": "p"}).json()
    resp = client.post(
        f"/accounts/{a['id']}/heartbeat",
        json={"last_action": "post_42", "status": "ACTIVE"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["last_action"] == "post_42"
    assert body["last_seen_at"] is not None
    assert body["last_login_at"] is not None  # sets first ACTIVE timestamp


def test_account_heartbeat_failed_records_error(client):
    a = client.post("/accounts", json={"username": "hb2", "password": "p"}).json()
    resp = client.post(
        f"/accounts/{a['id']}/heartbeat",
        json={"last_action": "login", "status": "FAILED", "last_error": "captcha"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["last_error"] == "captcha"


def test_account_update_clears_password_resets_status_to_new(client):
    a = client.post("/accounts", json={"username": "u", "password": "p"}).json()
    # Promote to ACTIVE first.
    client.post(f"/accounts/{a['id']}/heartbeat", json={"last_action": "ok", "status": "ACTIVE"})
    # Update password → status should reset to NEW.
    upd = client.patch(f"/accounts/{a['id']}", json={"password": "newpw"}).json()
    assert upd["status"] == "NEW"
    secrets = client.get("/accounts/internal/active").json()
    [me] = [s for s in secrets if s["username"] == "u"]
    assert me["password"] == "newpw"


def test_account_reverify_resets_status(client):
    a = client.post("/accounts", json={"username": "rv", "password": "p"}).json()
    client.post(f"/accounts/{a['id']}/heartbeat", json={"last_action": "x", "status": "FAILED", "last_error": "boom"})
    upd = client.post(f"/accounts/{a['id']}/reverify").json()
    assert upd["status"] == "NEW"
    assert upd["last_error"] is None


def test_account_delete_soft_disables(client):
    a = client.post("/accounts", json={"username": "del", "password": "p"}).json()
    client.delete(f"/accounts/{a['id']}")
    again = client.get(f"/accounts/{a['id']}").json()
    assert again["is_enabled"] is False
    assert again["status"] == "DISABLED"
    # Internal-active list excludes it.
    listing = client.get("/accounts/internal/active").json()
    assert all(s["username"] != "del" for s in listing)


def test_internal_active_returns_decrypted_secrets_with_proxy(client):
    proxy = _create_proxy(client, label="px")
    client.post(
        "/accounts",
        json={
            "username": "bot",
            "password": "secret-pw",
            "totp_secret": "AAAAAAAAAAAAAAAA",
            "proxy_id": proxy["id"],
        },
    )
    secrets = client.get("/accounts/internal/active").json()
    [bot] = [s for s in secrets if s["username"] == "bot"]
    assert bot["password"] == "secret-pw"
    assert bot["totp_secret"] == "AAAAAAAAAAAAAAAA"
    assert bot["proxy"]["host"] == "1.2.3.4"
    assert bot["proxy"]["scheme"] == "http"


def test_worker_claim_records_account_id(client, make_reply):
    """When a worker passes account_id on /worker/claim, posting_account_id is recorded."""
    a = client.post("/accounts", json={"username": "claimer", "password": "p"}).json()
    reply = make_reply(status="APPROVED")
    resp = client.post(
        "/worker/claim",
        json={"worker_name": "w1", "account_id": a["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["reply_id"] == reply.id
    items = client.get("/replies", params={"status": "POSTING"}).json()
    [item] = items
    assert item["reply_id"] == reply.id
    # posting_account_id isn't in ReplyItem schema; verify via DB.
    from app.db.models import Reply
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        row = db.get(Reply, reply.id)
        assert row.posting_account_id == a["id"]

"""Phase 6 hardening: GLP-default cadence, cooldown bump endpoint, BANNED status."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db.models import RedditAccount
from app.routes import proxies as proxies_route


@pytest.fixture(autouse=True)
def _stub_validate(monkeypatch):
    monkeypatch.setattr(
        proxies_route,
        "validate_proxy",
        lambda **kw: (True, "203.0.113.42", None),
    )


def _create_account(client, username: str, platform: str = "reddit") -> dict:
    body = {"username": username, "password": "p", "platform": platform}
    resp = client.post("/accounts", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_glp_account_gets_conservative_defaults(client, db_session):
    acc = _create_account(client, "glp_user_1", platform="glp")
    row = db_session.get(RedditAccount, acc["id"])
    # GLP defaults (per backend/app/routes/accounts.py create_account):
    assert row.posts_per_hour_limit == 2
    assert row.posts_per_day_limit == 12
    assert row.min_seconds_between_posts == 600
    assert row.max_seconds_between_posts == 1800
    assert row.platform == "glp"


def test_reddit_account_keeps_existing_defaults(client, db_session):
    acc = _create_account(client, "reddit_user_1", platform="reddit")
    row = db_session.get(RedditAccount, acc["id"])
    assert row.posts_per_hour_limit == 4
    assert row.posts_per_day_limit == 30
    assert row.min_seconds_between_posts == 300
    assert row.max_seconds_between_posts == 900
    assert row.platform == "reddit"


def test_bump_cooldown_pushes_next_eligible_at(client, db_session):
    acc = _create_account(client, "cool_1")
    before = datetime.utcnow()
    resp = client.post(f"/accounts/{acc['id']}/cooldown?seconds=120")
    assert resp.status_code == 200, resp.text
    row = db_session.get(RedditAccount, acc["id"])
    assert row.next_eligible_at is not None
    delta = (row.next_eligible_at - before).total_seconds()
    assert 115 <= delta <= 125


def test_bump_cooldown_clamps_excessive_values(client, db_session):
    acc = _create_account(client, "cool_2")
    # 1 day = 86400 — anything beyond clamps to the cap.
    resp = client.post(f"/accounts/{acc['id']}/cooldown?seconds=999999")
    assert resp.status_code == 200
    row = db_session.get(RedditAccount, acc["id"])
    assert row.next_eligible_at is not None
    delta = (row.next_eligible_at - datetime.utcnow()).total_seconds()
    assert delta <= 86401


def test_heartbeat_banned_status_disables_account(client, db_session):
    acc = _create_account(client, "ban_1")
    resp = client.post(
        f"/accounts/{acc['id']}/heartbeat",
        json={"last_action": "banned_42", "status": "BANNED", "last_error": "banned"},
    )
    assert resp.status_code == 200
    row = db_session.get(RedditAccount, acc["id"])
    assert row.is_enabled is False
    assert row.status == "BANNED"


def test_heartbeat_active_does_not_disable(client, db_session):
    acc = _create_account(client, "active_1")
    resp = client.post(
        f"/accounts/{acc['id']}/heartbeat",
        json={"last_action": "login_ok", "status": "ACTIVE"},
    )
    assert resp.status_code == 200
    row = db_session.get(RedditAccount, acc["id"])
    assert row.is_enabled is True
    assert row.status == "ACTIVE"

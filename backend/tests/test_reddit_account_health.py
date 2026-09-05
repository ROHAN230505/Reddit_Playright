"""Public-profile health: session alive ≠ allowed to post."""

from __future__ import annotations

from app.services.reddit_account_health import (
    BANNED,
    HEALTHY,
    NO_COOKIES,
    PROXY_DEAD,
    SESSION_DEAD,
    UNKNOWN,
    HealthResult,
    check_reddit_account,
    refresh_reddit_health,
)


class FakeResp:
    def __init__(self, status_code, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _router(mapping, default=None):
    def http_get(url, **kwargs):
        hits = [(prefix, resp) for prefix, resp in mapping if prefix in url]
        if hits:
            _prefix, resp = max(hits, key=lambda item: len(item[0]))
            if callable(resp):
                return resp(url, **kwargs)
            return resp
        if default is not None:
            return default
        raise AssertionError(f"unexpected url {url}")

    return http_get


def test_banned_profile_beats_live_me_json():
    """The original bug: me.json 200 + cookies still 'ACTIVE' while Reddit banned the user."""
    http_get = _router(
        [
            (
                "/user/destruct_noob/",
                FakeResp(200, text="<html>This account has been banned</html>"),
            ),
            (
                "/api/me.json",
                FakeResp(200, json_data={"kind": "t2", "data": {"name": "destruct_noob"}}),
            ),
        ]
    )
    result = check_reddit_account(
        username="destruct_noob",
        cookie_header={"reddit_session": "still-valid"},
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == BANNED
    assert result.session_alive is True
    assert result.profile_banned is True
    assert "banned" in result.detail.lower()
    assert "session still alive" in result.detail.lower()


def test_healthy_profile_and_session():
    http_get = _router(
        [
            (
                "/user/colblair/about.json",
                FakeResp(200, json_data={"kind": "t2", "data": {"name": "colblair", "is_suspended": False}}),
            ),
            (
                "/user/colblair/",
                FakeResp(200, text="<html><body>overview comments</body></html> reddit"),
            ),
            (
                "/api/me.json",
                FakeResp(200, json_data={"name": "colblair"}),
            ),
        ],
        default=FakeResp(200, text="<html>reddit</html>"),
    )
    result = check_reddit_account(
        username="colblair",
        cookie_header={"reddit_session": "ok"},
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == HEALTHY
    assert result.session_alive is True
    assert result.profile_banned is False


def test_profile_ok_without_cookies_is_not_healthy():
    http_get = _router(
        [
            (
                "/user/zoneyou-th/about.json",
                FakeResp(200, json_data={"kind": "t2", "data": {"name": "zoneyou-th"}}),
            ),
            (
                "/user/zoneyou-th/",
                FakeResp(200, text="<html>reddit profile</html>"),
            ),
        ],
        default=FakeResp(200, json_data={"kind": "t2", "data": {"name": "zoneyou-th"}}),
    )
    result = check_reddit_account(
        username="zoneyou-th",
        cookie_header=None,
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == NO_COOKIES
    assert result.session_alive is False
    assert result.profile_banned is False


def test_profile_ok_but_me_json_403_is_session_dead():
    http_get = _router(
        [
            (
                "/user/Dupernovaa/about.json",
                FakeResp(200, json_data={"kind": "t2", "data": {"name": "Dupernovaa"}}),
            ),
            (
                "/user/Dupernovaa/",
                FakeResp(200, text="<html>reddit profile</html>"),
            ),
            (
                "/api/me.json",
                FakeResp(403, text="forbidden"),
            ),
        ],
        default=FakeResp(200, json_data={"kind": "t2", "data": {"name": "Dupernovaa"}}),
    )
    result = check_reddit_account(
        username="Dupernovaa",
        cookie_header={"reddit_session": "expired"},
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == SESSION_DEAD
    assert result.session_alive is False


def test_me_json_suspended_is_banned_even_if_profile_is_403():
    http_get = _router(
        [
            (
                "/api/me.json",
                FakeResp(
                    200,
                    json_data={
                        "kind": "t2",
                        "data": {"name": "destruct_noob", "is_suspended": True},
                    },
                ),
            ),
            (
                "/user/destruct_noob/",
                FakeResp(403, text="forbidden"),
            ),
        ],
        default=FakeResp(403, text="forbidden"),
    )
    result = check_reddit_account(
        username="destruct_noob",
        cookie_header={"reddit_session": "still-valid"},
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == BANNED
    assert result.session_alive is True
    assert result.profile_banned is True


def test_logged_in_profile_html_detects_ban_after_public_403():
    def http_get(url, **kwargs):
        cookies = kwargs.get("cookies") or {}
        if "/api/me.json" in url:
            return FakeResp(200, json_data={"name": "skylord2355"})
        if cookies.get("reddit_session") and "/user/" in url:
            return FakeResp(200, text="<html>This account has been banned</html>")
        return FakeResp(403, text="forbidden")

    result = check_reddit_account(
        username="skylord2355",
        cookie_header={"reddit_session": "still-valid"},
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == BANNED
    assert result.session_alive is True


def test_public_bot_wall_with_live_session_is_healthy():
    """Reddit 403s logged-out profile fetches from this VPS even when the account is fine.

    Do not leave the operator on UNKNOWN. Still set profile_banned=None so a
    previously sticky BANNED row cannot unban itself off a bot wall.
    """

    def http_get(url, **kwargs):
        cookies = kwargs.get("cookies") or {}
        if "/api/me.json" in url:
            return FakeResp(200, json_data={"name": "Healthy_Concert7779", "is_suspended": False})
        if cookies and "about.json" in url:
            return FakeResp(
                200,
                json_data={
                    "kind": "t2",
                    "data": {"name": "Healthy_Concert7779", "is_suspended": False},
                },
            )
        if cookies:
            return FakeResp(
                200,
                text="<html><title>overview for Healthy_Concert7779</title>reddit</html>",
            )
        return FakeResp(403, text="<html><title>Blocked</title>forbidden</html>")

    result = check_reddit_account(
        username="Healthy_Concert7779",
        cookie_header={"reddit_session": "still-valid"},
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == HEALTHY
    assert result.session_alive is True
    assert result.profile_banned is None
    assert "403" in result.detail or "blocked" in result.detail.lower()


def test_apify_public_about_json_classifies_healthy_when_account_proxy_is_403():
    """Logged-out about.json through Apify residential is the public source of truth."""

    def http_get(url, **kwargs):
        proxies = kwargs.get("proxies") or {}
        proxy = str(proxies.get("https") or proxies.get("http") or "")
        if "/api/me.json" in url:
            return FakeResp(200, json_data={"name": "Healthy_Concert7779", "is_suspended": False})
        if "proxy.apify.com" in proxy and "about.json" in url:
            return FakeResp(
                200,
                json_data={
                    "kind": "t2",
                    "data": {"name": "Healthy_Concert7779", "is_suspended": False},
                },
            )
        return FakeResp(403, text="<html><title>Blocked</title>forbidden</html>")

    result = check_reddit_account(
        username="Healthy_Concert7779",
        cookie_header={"reddit_session": "ok"},
        proxy_url="http://user:pass@disp.oxylabs.io:8001",
        http_get=http_get,
        public_proxy_url="http://groups-RESIDENTIAL:token@proxy.apify.com:8000",
    )
    assert result.health == HEALTHY
    assert result.session_alive is True
    assert result.profile_banned is False


def test_apify_public_about_json_suspended_is_banned():
    def http_get(url, **kwargs):
        proxies = kwargs.get("proxies") or {}
        proxy = str(proxies.get("https") or proxies.get("http") or "")
        if "/api/me.json" in url:
            return FakeResp(200, json_data={"name": "destruct_noob", "is_suspended": False})
        if "proxy.apify.com" in proxy and "about.json" in url:
            return FakeResp(
                200,
                json_data={"kind": "t2", "data": {"name": "destruct_noob", "is_suspended": True}},
            )
        return FakeResp(403, text="<html><title>Blocked</title>forbidden</html>")

    result = check_reddit_account(
        username="destruct_noob",
        cookie_header={"reddit_session": "ok"},
        proxy_url="http://user:pass@disp.oxylabs.io:8001",
        http_get=http_get,
        public_proxy_url="http://groups-RESIDENTIAL:token@proxy.apify.com:8000",
    )
    assert result.health == BANNED
    assert result.profile_banned is True


def test_public_bot_wall_with_dead_session_is_session_dead():
    def http_get(url, **kwargs):
        if "/api/me.json" in url:
            return FakeResp(401, text="unauthorized")
        return FakeResp(403, text="<html><title>Blocked</title>forbidden</html>")

    result = check_reddit_account(
        username="Healthy_Concert7779",
        cookie_header={"reddit_session": "expired"},
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == SESSION_DEAD
    assert result.session_alive is False
    assert result.profile_banned is None


def test_apply_health_keeps_banned_when_session_still_looks_alive():
    from datetime import datetime

    from app.db.models import RedditAccount
    from app.services.reddit_account_health import apply_health_to_account

    account = RedditAccount(
        username="destruct_noob",
        password_enc="x",
        status="BANNED",
        is_enabled=False,
        reddit_health="BANNED",
        created_at=datetime.utcnow(),
    )
    apply_health_to_account(
        account,
        HealthResult(
            health=HEALTHY,
            detail="Public profile ok; me.json 200 as destruct_noob",
            session_alive=True,
            profile_banned=None,
        ),
    )
    assert account.reddit_health == BANNED
    assert account.status == BANNED
    assert account.is_enabled is False


def test_proxy_error_without_fallback_is_proxy_dead():
    import requests

    def http_get(url, **kwargs):
        raise requests.exceptions.ProxyError("407 Proxy Authentication Required")

    result = check_reddit_account(
        username="Tenpiano",
        cookie_header={"reddit_session": "x"},
        proxy_url="http://user:pass@disp.oxylabs.io:8001",
        http_get=http_get,
    )
    assert result.health == PROXY_DEAD


def test_suspended_about_json_is_banned():
    http_get = _router(
        [
            (
                "/user/skylord2355/about.json",
                FakeResp(200, json_data={"kind": "t2", "data": {"name": "skylord2355", "is_suspended": True}}),
            ),
            (
                "/user/skylord2355/",
                FakeResp(200, text="<html>reddit</html>"),
            ),
        ],
        default=FakeResp(200, text="<html>reddit</html>"),
    )
    result = check_reddit_account(
        username="skylord2355",
        cookie_header={"reddit_session": "x"},
        proxy_url=None,
        http_get=http_get,
    )
    assert result.health == BANNED
    assert result.profile_banned is True


def test_health_endpoint_stored_does_not_call_checker(client, monkeypatch):
    called = {"n": 0}

    def boom(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("stored /accounts/health must not hit Reddit")

    monkeypatch.setattr(
        "app.services.reddit_account_health.refresh_reddit_health",
        boom,
    )
    monkeypatch.setattr("app.routes.accounts.rah.refresh_reddit_health", boom)
    client.post("/accounts", json={"username": "stored_only", "password": "p"})
    resp = client.get("/accounts/health")
    assert resp.status_code == 200
    assert called["n"] == 0
    body = resp.json()
    assert "reddit_health" in body["accounts"][0]


def test_live_health_marks_banned_even_when_status_was_active(client, db_session, monkeypatch):
    from app.db.models import RedditAccount

    created = client.post("/accounts", json={"username": "destruct_noob", "password": "p"}).json()
    client.post(
        f"/accounts/{created['id']}/heartbeat",
        json={"last_action": "bootstrap_already_logged_in", "status": "ACTIVE"},
    )

    def fake_check(**kwargs):
        return HealthResult(
            health=BANNED,
            detail="Public profile: this account has been banned; session still alive",
            session_alive=True,
            profile_banned=True,
        )

    monkeypatch.setattr(
        "app.services.reddit_account_health.check_reddit_account",
        fake_check,
    )
    resp = client.get("/accounts/health", params={"live": True})
    assert resp.status_code == 200
    [item] = [a for a in resp.json()["accounts"] if a["username"] == "destruct_noob"]
    assert item["reddit_health"] == "BANNED"
    assert item["status"] == "BANNED"
    assert item["is_enabled"] is False
    assert item["reddit_session_alive"] is True
    assert "banned" in (item["reddit_health_detail"] or "").lower()

    row = db_session.get(RedditAccount, created["id"])
    db_session.refresh(row)
    assert row.status == "BANNED"
    assert row.is_enabled is False


def test_refresh_debounces_recent_checks(db_session, monkeypatch):
    from datetime import datetime, timedelta

    from app.db.models import RedditAccount
    from app.services import crypto

    account = RedditAccount(
        username="debounce_me",
        password_enc=crypto.encrypt("p"),
        status="ACTIVE",
        is_enabled=True,
        platform="reddit",
        reddit_health="HEALTHY",
        reddit_health_checked_at=datetime.utcnow() - timedelta(seconds=5),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)

    called = {"n": 0}

    def fake_check(**kwargs):
        called["n"] += 1
        return HealthResult(
            health=BANNED,
            detail="should not run",
            session_alive=True,
            profile_banned=True,
        )

    monkeypatch.setattr(
        "app.services.reddit_account_health.check_reddit_account",
        fake_check,
    )
    n = refresh_reddit_health(db_session, [account], min_age_seconds=20)
    assert n == 0
    assert called["n"] == 0
    assert account.reddit_health == "HEALTHY"

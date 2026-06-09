"""HTTP client for talking to the backend's /worker endpoints."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """Raised when the backend returns a non-success response."""


class BackendClient:
    def __init__(self, base_url: str, worker_name: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.worker_name = worker_name
        self.timeout = timeout
        self.session = requests.Session()

    def _post(self, path: str, json: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        resp = self.session.post(url, json=json or {}, timeout=self.timeout)
        if not resp.ok:
            raise BackendError(
                f"POST {path} failed: {resp.status_code} {resp.text[:500]}"
            )
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    def list_active_accounts(self, platform: str | None = None) -> list[dict]:
        """Fetch enabled accounts (worker-only endpoint). Optionally filter by
        platform. Used to resolve the slot whose rate limits the backend should
        enforce for this worker."""
        url = f"{self.base_url}/accounts/internal/active"
        resp = self.session.get(url, timeout=self.timeout)
        if not resp.ok:
            raise BackendError(
                f"GET /accounts/internal/active failed: {resp.status_code} {resp.text[:300]}"
            )
        accounts = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else []
        if platform is not None:
            accounts = [a for a in accounts if (a.get("platform") or "reddit").lower() == platform]
        return accounts

    def claim_next(
        self,
        stale_after_seconds: int = 600,
        account_id: int | None = None,
        platform: str | None = None,
    ) -> dict | None:
        body: dict = {
            "worker_name": self.worker_name,
            "stale_after_seconds": stale_after_seconds,
        }
        if account_id is not None:
            body["account_id"] = account_id
        if platform is not None:
            body["platform"] = platform
        payload = self._post("/worker/claim", body)
        if payload is None or payload == "" or payload == "null":
            return None
        if isinstance(payload, dict) and not payload:
            return None
        return payload

    def mark_posted(
        self,
        reply_id: int,
        posted_reddit_comment_id: str | None = None,
        posted_platform_comment_id: str | None = None,
        posted_url: str | None = None,
    ) -> dict:
        return self._post(
            f"/worker/{reply_id}/posted",
            {
                "worker_name": self.worker_name,
                "posted_reddit_comment_id": posted_reddit_comment_id,
                "posted_platform_comment_id": posted_platform_comment_id,
                "posted_url": posted_url,
            },
        )

    def mark_failed(self, reply_id: int, error: str, requeue: bool = True) -> dict:
        return self._post(
            f"/worker/{reply_id}/failed",
            {
                "worker_name": self.worker_name,
                "error": error[:4000],
                "requeue": requeue,
            },
        )

    def heartbeat(
        self,
        account_id: int,
        last_action: str,
        status: str | None = None,
        last_error: str | None = None,
    ) -> dict:
        body: dict = {"last_action": last_action[:255]}
        if status is not None:
            body["status"] = status[:30]
        if last_error is not None:
            body["last_error"] = last_error[:4000]
        return self._post(f"/accounts/{account_id}/heartbeat", body)

    def bump_cooldown(self, account_id: int, seconds: int) -> dict:
        """Push the account's next_eligible_at out by `seconds`."""
        url = f"{self.base_url}/accounts/{account_id}/cooldown?seconds={int(seconds)}"
        resp = self.session.post(url, json={}, timeout=self.timeout)
        if not resp.ok:
            raise BackendError(
                f"POST /accounts/{account_id}/cooldown failed: "
                f"{resp.status_code} {resp.text[:500]}"
            )
        return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

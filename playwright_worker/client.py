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

    def claim_next(self, stale_after_seconds: int = 600) -> dict | None:
        payload = self._post(
            "/worker/claim",
            {
                "worker_name": self.worker_name,
                "stale_after_seconds": stale_after_seconds,
            },
        )
        if payload is None or payload == "" or payload == "null":
            return None
        if isinstance(payload, dict) and not payload:
            return None
        return payload

    def mark_posted(self, reply_id: int, posted_reddit_comment_id: str | None = None) -> dict:
        return self._post(
            f"/worker/{reply_id}/posted",
            {
                "worker_name": self.worker_name,
                "posted_reddit_comment_id": posted_reddit_comment_id,
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

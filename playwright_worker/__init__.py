"""Playwright posting worker for the reddit-reply-draft system.

This package is a thin, production-safe layer that:

1. fetches the next APPROVED reply from the backend (`/worker/claim`),
2. drives a persistent logged-in browser session to post the exact text to
   the exact Reddit target,
3. reports success or failure back to the backend.

The backend remains the source of truth — this worker only acts on what it
is told and never invents drafts or targets.
"""

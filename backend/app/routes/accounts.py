import os
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import Post, Proxy, RedditAccount, Reply, TrackedSubreddit
from app.db.session import get_db
from app.schemas import (
    AutoAssignSubredditsResponse,
    RedditAccountActivity,
    RedditAccountHealthItem,
    RedditAccountHealthResponse,
    RedditAccountCookies,
    RedditAccountCreate,
    RedditAccountHeartbeat,
    RedditAccountItem,
    RedditAccountSecret,
    RedditAccountUpdate,
    SubredditAssignment,
)
from app.services import crypto
from app.services.cookie_parser import (
    deserialize_from_db,
    has_essential_cookie,
    parse_cookies,
    serialize_for_db,
)
from app.services.profile_pool import (
    PROFILE_POOL_SIZE,
    get_profile,
    pick_next_profile_index,
    summarize_profile,
)


def _parse_assigned_subreddits(value: str | None) -> list[str]:
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def _format_assigned_subreddits(values: list[str] | None) -> str | None:
    if not values:
        return None
    return ",".join(s.strip() for s in values if s.strip()) or None


# Sections (GLP) and subreddits (Reddit) use the same CSV-in-Text storage shape.
_parse_assigned_sections = _parse_assigned_subreddits
_format_assigned_sections = _format_assigned_subreddits

router = APIRouter(prefix="/accounts", tags=["accounts"])


USER_DATA_DIR_BASE = os.getenv(
    "USER_DATA_DIR_BASE", "/home/pwuser/.reddit-worker-profile-base"
)


_USERNAME_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _profile_dir(username: str) -> str:
    safe = _USERNAME_SAFE_RE.sub("_", username)
    return os.path.join(USER_DATA_DIR_BASE, safe)


def _normalize_totp(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"\s+", "", raw).upper()
    return cleaned or None


def _serialize(account: RedditAccount, proxy: Proxy | None) -> RedditAccountItem:
    return RedditAccountItem(
        id=account.id,
        username=account.username,
        has_totp=bool(account.totp_secret_enc),
        proxy_id=account.proxy_id,
        proxy_label=proxy.label if proxy else None,
        status=account.status,
        is_enabled=account.is_enabled,
        last_login_at=account.last_login_at,
        last_seen_at=account.last_seen_at,
        last_action=account.last_action,
        last_error=account.last_error,
        user_data_dir=account.user_data_dir,
        has_cookies=bool(account.session_cookies_enc),
        cookies_set_at=account.cookies_set_at,
        profile_index=account.profile_index or 0,
        profile_summary=summarize_profile(account.profile_index or 0),
        posts_per_hour_limit=account.posts_per_hour_limit or 4,
        posts_per_day_limit=account.posts_per_day_limit or 30,
        min_seconds_between_posts=account.min_seconds_between_posts or 300,
        max_seconds_between_posts=account.max_seconds_between_posts or 900,
        next_eligible_at=account.next_eligible_at,
        assigned_subreddits=_parse_assigned_subreddits(account.assigned_subreddits),
        platform=account.platform or "reddit",
        assigned_sections=_parse_assigned_sections(account.assigned_sections),
        created_at=account.created_at,
    )


@router.get("", response_model=list[RedditAccountItem])
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.scalars(
        select(RedditAccount).order_by(RedditAccount.created_at.desc())
    ).all()
    return [_serialize(account, account.proxy) for account in accounts]


@router.get("/health", response_model=RedditAccountHealthResponse)
def accounts_health(db: Session = Depends(get_db)):
    """Batched account + activity payload for dashboard health views."""
    rows = db.scalars(select(RedditAccount).order_by(desc(RedditAccount.created_at))).all()
    activities = _account_activity_payloads(db, list(rows))
    accounts = [_serialize(account, account.proxy) for account in rows]
    return RedditAccountHealthResponse(
        accounts=accounts,
        activity=activities,
        items=[
            RedditAccountHealthItem(account=account_item, activity=activities[account_item.id])
            for account_item in accounts
            if account_item.id in activities
        ],
    )


@router.get("/{account_id}", response_model=RedditAccountItem)
def get_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return _serialize(account, account.proxy)


@router.post("", response_model=RedditAccountItem)
def create_account(payload: RedditAccountCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(RedditAccount).where(RedditAccount.username == payload.username))
    if existing:
        raise HTTPException(status_code=409, detail="Account already exists with that username.")

    if payload.proxy_id is not None:
        proxy = db.get(Proxy, payload.proxy_id)
        if not proxy:
            raise HTTPException(status_code=404, detail="Selected proxy not found.")
        if proxy.status != "ACTIVE":
            raise HTTPException(
                status_code=422,
                detail=f"Proxy is not active (status={proxy.status}). Validate it first.",
            )

    # Round-robin profile assignment unless explicitly specified.
    if payload.profile_index is not None:
        profile_index = payload.profile_index
    else:
        used = [
            row[0]
            for row in db.execute(
                select(RedditAccount.profile_index).where(RedditAccount.is_enabled == True)  # noqa: E712
            ).all()
            if row[0] is not None
        ]
        profile_index = pick_next_profile_index(used)

    # Per-platform conservative defaults. GLP moderation is more aggressive
    # than Reddit's; 4chan is rate-limited by IP and per-board flood control
    # so the cadence is even tighter to stay invisible.
    platform = (payload.platform or "reddit").lower()
    if platform == "glp":
        default_hour = 2
        default_day = 12
        default_min_seconds = 600   # 10 min
        default_max_seconds = 1800  # 30 min
    elif platform == "chan":
        default_hour = 3
        default_day = 20
        default_min_seconds = 300   # 5 min — 4chan flood is ~60s but we stay well clear
        default_max_seconds = 900   # 15 min
    else:
        default_hour = 4
        default_day = 30
        default_min_seconds = 300
        default_max_seconds = 900

    account = RedditAccount(
        username=payload.username,
        password_enc=crypto.encrypt(payload.password),
        totp_secret_enc=(
            crypto.encrypt(_normalize_totp(payload.totp_secret))
            if _normalize_totp(payload.totp_secret)
            else None
        ),
        proxy_id=payload.proxy_id,
        status="NEW",
        is_enabled=True,
        user_data_dir=_profile_dir(payload.username),
        profile_index=profile_index,
        posts_per_hour_limit=payload.posts_per_hour_limit or default_hour,
        posts_per_day_limit=payload.posts_per_day_limit or default_day,
        min_seconds_between_posts=payload.min_seconds_between_posts or default_min_seconds,
        max_seconds_between_posts=payload.max_seconds_between_posts or default_max_seconds,
        platform=platform,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _serialize(account, account.proxy)


@router.patch("/{account_id}", response_model=RedditAccountItem)
def update_account(
    account_id: int, payload: RedditAccountUpdate, db: Session = Depends(get_db)
):
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if payload.password is not None:
        account.password_enc = crypto.encrypt(payload.password)
        account.status = "NEW"
    if payload.totp_secret is not None:
        normalized = _normalize_totp(payload.totp_secret)
        account.totp_secret_enc = crypto.encrypt(normalized) if normalized else None
        account.status = "NEW"
    if payload.proxy_id is not None:
        if payload.proxy_id == 0:
            account.proxy_id = None
        else:
            proxy = db.get(Proxy, payload.proxy_id)
            if not proxy:
                raise HTTPException(status_code=404, detail="Selected proxy not found.")
            account.proxy_id = proxy.id
        account.status = "NEW"
    if payload.is_enabled is not None:
        account.is_enabled = payload.is_enabled
    if payload.status is not None:
        account.status = payload.status
    if payload.profile_index is not None:
        account.profile_index = payload.profile_index
    if payload.posts_per_hour_limit is not None:
        account.posts_per_hour_limit = payload.posts_per_hour_limit
    if payload.posts_per_day_limit is not None:
        account.posts_per_day_limit = payload.posts_per_day_limit
    if payload.min_seconds_between_posts is not None:
        account.min_seconds_between_posts = payload.min_seconds_between_posts
    if payload.max_seconds_between_posts is not None:
        account.max_seconds_between_posts = payload.max_seconds_between_posts
    if payload.assigned_subreddits is not None:
        account.assigned_subreddits = _format_assigned_subreddits(payload.assigned_subreddits)
    if payload.assigned_sections is not None:
        account.assigned_sections = _format_assigned_sections(payload.assigned_sections)

    db.add(account)
    db.commit()
    db.refresh(account)
    return _serialize(account, account.proxy)


@router.post("/auto-assign-subreddits", response_model=AutoAssignSubredditsResponse)
def auto_assign_subreddits(db: Session = Depends(get_db)):
    """Distribute the tracked subreddits across enabled accounts so that the
    sum of recent activity per account is roughly balanced.

    Activity = number of posts created in each subreddit in the last 7 days.
    Algorithm: longest-processing-time-first (LPT) — sort subreddits by
    activity descending, then repeatedly assign the next subreddit to the
    account with the smallest current load. Persists results into
    `reddit_accounts.assigned_subreddits` (CSV)."""
    accounts = list(
        db.scalars(
            select(RedditAccount)
            .where(
                RedditAccount.is_enabled == True,  # noqa: E712
                RedditAccount.platform == "reddit",
            )
            .order_by(RedditAccount.profile_index.asc(), RedditAccount.id.asc())
        ).all()
    )
    if not accounts:
        raise HTTPException(
            status_code=400,
            detail="No enabled Reddit accounts. Add at least one before auto-assigning.",
        )

    tracked = list(
        db.scalars(
            select(TrackedSubreddit).order_by(TrackedSubreddit.name.asc())
        ).all()
    )
    if not tracked:
        return AutoAssignSubredditsResponse(
            assignments=[
                SubredditAssignment(
                    account_id=a.id,
                    username=a.username,
                    profile_index=a.profile_index or 0,
                    subreddits=[],
                    posts_last_7d=0,
                )
                for a in accounts
            ],
            unassigned_subreddits=[],
            total_subreddits=0,
        )

    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    activity_rows = db.execute(
        select(Post.subreddit, func.count(Post.id))
        .where(Post.created_at >= seven_days_ago)
        .group_by(Post.subreddit)
    ).all()
    activity_by_sub: dict[str, int] = {}
    for sub, cnt in activity_rows:
        if sub:
            activity_by_sub[sub.lower()] = int(cnt)

    # Track activity for every tracked subreddit (default 0 if no recent posts).
    sub_activity: list[tuple[str, int]] = [
        (t.name, activity_by_sub.get(t.name.lower(), 0)) for t in tracked
    ]
    # LPT: sort descending by activity, with a stable tiebreaker on name.
    sub_activity.sort(key=lambda x: (-x[1], x[0].lower()))

    # Bins, one per account.
    bins: dict[int, dict] = {
        a.id: {
            "account": a,
            "subreddits": [],
            "load": 0,
        }
        for a in accounts
    }

    # Assign each subreddit to the account with the smallest current load.
    for name, weight in sub_activity:
        chosen_id = min(
            bins.keys(),
            key=lambda aid: (
                bins[aid]["load"],
                len(bins[aid]["subreddits"]),
                bins[aid]["account"].id,
            ),
        )
        bins[chosen_id]["subreddits"].append(name)
        bins[chosen_id]["load"] += weight

    # Persist.
    for aid, payload in bins.items():
        acc: RedditAccount = payload["account"]
        acc.assigned_subreddits = _format_assigned_subreddits(payload["subreddits"])
        db.add(acc)
    db.commit()

    return AutoAssignSubredditsResponse(
        assignments=[
            SubredditAssignment(
                account_id=aid,
                username=payload["account"].username,
                profile_index=payload["account"].profile_index or 0,
                subreddits=payload["subreddits"],
                posts_last_7d=payload["load"],
            )
            for aid, payload in bins.items()
        ],
        unassigned_subreddits=[],
        total_subreddits=len(tracked),
    )


def _account_activity_payloads(
    db: Session,
    accounts: list[RedditAccount],
) -> dict[int, RedditAccountActivity]:
    account_ids = [account.id for account in accounts]
    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)
    if not account_ids:
        return {}

    hourly_rows = db.execute(
        select(Reply.posting_account_id, func.count(Reply.id))
        .where(
            Reply.posting_account_id.in_(account_ids),
            Reply.posted_at != None,  # noqa: E711
            Reply.posted_at >= hour_ago,
        )
        .group_by(Reply.posting_account_id)
    ).all()
    daily_rows = db.execute(
        select(Reply.posting_account_id, func.count(Reply.id))
        .where(
            Reply.posting_account_id.in_(account_ids),
            Reply.posted_at != None,  # noqa: E711
            Reply.posted_at >= day_ago,
        )
        .group_by(Reply.posting_account_id)
    ).all()
    last_posted_rows = db.execute(
        select(Reply.posting_account_id, func.max(Reply.posted_at))
        .where(Reply.posting_account_id.in_(account_ids))
        .group_by(Reply.posting_account_id)
    ).all()

    posts_last_hour = {account_id: int(count) for account_id, count in hourly_rows if account_id is not None}
    posts_last_day = {account_id: int(count) for account_id, count in daily_rows if account_id is not None}
    last_posted_at = {account_id: value for account_id, value in last_posted_rows if account_id is not None}

    recent_rows = db.scalars(
        select(Reply)
        .where(
            Reply.posting_account_id.in_(account_ids),
            Reply.posted_at != None,  # noqa: E711
        )
        .order_by(Reply.posting_account_id, desc(Reply.posted_at))
    ).all()
    recent_by_account: dict[int, list[Reply]] = {account_id: [] for account_id in account_ids}
    for reply in recent_rows:
        if reply.posting_account_id is None:
            continue
        bucket = recent_by_account.setdefault(reply.posting_account_id, [])
        if len(bucket) < 20:
            bucket.append(reply)

    failed_rows = db.scalars(
        select(Reply)
        .where(
            Reply.posting_account_id.in_(account_ids),
            Reply.posting_error != None,  # noqa: E711
        )
        .order_by(Reply.posting_account_id, desc(Reply.posting_claimed_at), desc(Reply.id))
    ).all()
    failed_by_account: dict[int, Reply] = {}
    for reply in failed_rows:
        if reply.posting_account_id is not None and reply.posting_account_id not in failed_by_account:
            failed_by_account[reply.posting_account_id] = reply

    payloads: dict[int, RedditAccountActivity] = {}
    for account in accounts:
        recent = recent_by_account.get(account.id, [])
        recent_posts = [
            {
                "reply_id": r.id,
                "posted_at": r.posted_at.isoformat() if r.posted_at else None,
                "subreddit": r.subreddit,
                "reply_text_preview": (r.reply_text or "")[:140],
                "target_url": r.target_url,
            }
            for r in recent
        ]

        last_failed = failed_by_account.get(account.id)
        last_failed_post = None
        if last_failed:
            last_failed_post = {
                "reply_id": last_failed.id,
                "status": last_failed.status,
                "failed_at": last_failed.posting_claimed_at.isoformat()
                if last_failed.posting_claimed_at
                else None,
                "error": (last_failed.posting_error or "")[:500],
                "target_url": last_failed.target_url,
            }

        next_eligible = account.next_eligible_at
        seconds_until_eligible = 0
        is_in_cooldown = False
        if next_eligible and next_eligible > now:
            seconds_until_eligible = int((next_eligible - now).total_seconds())
            is_in_cooldown = True

        hour_count = posts_last_hour.get(account.id, 0)
        day_count = posts_last_day.get(account.id, 0)
        hour_limit = account.posts_per_hour_limit or 4
        day_limit = account.posts_per_day_limit or 30
        payloads[account.id] = RedditAccountActivity(
            account_id=account.id,
            username=account.username,
            posts_last_hour=hour_count,
            posts_last_day=day_count,
            posts_per_hour_limit=hour_limit,
            posts_per_day_limit=day_limit,
            last_posted_at=last_posted_at.get(account.id),
            next_eligible_at=next_eligible,
            seconds_until_eligible=seconds_until_eligible,
            is_in_cooldown=is_in_cooldown,
            is_at_hourly_limit=hour_count >= hour_limit,
            is_at_daily_limit=day_count >= day_limit,
            recent_posts=recent_posts,
            last_failed_post=last_failed_post,
        )
    return payloads


@router.get("/{account_id}/activity", response_model=RedditAccountActivity)
def account_activity(account_id: int, db: Session = Depends(get_db)):
    """Per-account posting activity stats — feeds older dashboard clients."""
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return _account_activity_payloads(db, [account])[account.id]


@router.post("/{account_id}/reverify", response_model=RedditAccountItem)
def reverify_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.status = "NEW"
    account.last_error = None
    db.add(account)
    db.commit()
    db.refresh(account)
    return _serialize(account, account.proxy)


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.is_enabled = False
    account.status = "DISABLED"
    db.add(account)
    db.commit()
    return {"ok": True, "id": account_id, "status": account.status}


@router.post("/{account_id}/heartbeat", response_model=RedditAccountItem)
def heartbeat(
    account_id: int,
    payload: RedditAccountHeartbeat,
    db: Session = Depends(get_db),
):
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.last_seen_at = datetime.utcnow()
    account.last_action = payload.last_action
    if payload.status:
        account.status = payload.status
        if payload.status == "ACTIVE":
            account.last_login_at = account.last_login_at or datetime.utcnow()
            account.last_error = None
        elif payload.status in ("BANNED", "DISABLED"):
            # Worker signaled the account is dead. Disable it so the claim
            # loop stops handing it work.
            account.is_enabled = False
    if payload.last_error is not None:
        account.last_error = payload.last_error or None
    db.add(account)
    db.commit()
    db.refresh(account)
    return _serialize(account, account.proxy)


@router.post("/{account_id}/cooldown", response_model=RedditAccountItem)
def bump_cooldown(
    account_id: int,
    seconds: int,
    db: Session = Depends(get_db),
):
    """Push `next_eligible_at` out by `seconds` from now. Used by the worker
    when a platform-specific flood-control rejection tells us a precise wait
    time. Clamped to [0, 24h] to prevent accidental DOS of an account."""
    if seconds < 0:
        seconds = 0
    if seconds > 86400:
        seconds = 86400
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.next_eligible_at = datetime.utcnow() + timedelta(seconds=seconds)
    db.add(account)
    db.commit()
    db.refresh(account)
    return _serialize(account, account.proxy)


@router.post("/{account_id}/cookies", response_model=RedditAccountItem)
def upload_cookies(
    account_id: int,
    payload: RedditAccountCookies,
    db: Session = Depends(get_db),
):
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        cookies = parse_cookies(payload.raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not has_essential_cookie(cookies):
        raise HTTPException(
            status_code=422,
            detail=(
                "None of the recognized auth cookies (reddit_session, token_v2, loid) "
                "were found. Make sure you copied the right cookie — `reddit_session` "
                "is the minimum required."
            ),
        )

    account.session_cookies_enc = crypto.encrypt(serialize_for_db(cookies))
    account.cookies_set_at = datetime.utcnow()
    account.status = "NEW"
    account.last_error = None
    db.add(account)
    db.commit()
    db.refresh(account)
    return _serialize(account, account.proxy)


@router.delete("/{account_id}/cookies", response_model=RedditAccountItem)
def clear_cookies(account_id: int, db: Session = Depends(get_db)):
    account = db.get(RedditAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.session_cookies_enc = None
    account.cookies_set_at = None
    db.add(account)
    db.commit()
    db.refresh(account)
    return _serialize(account, account.proxy)


@router.get("/internal/active", response_model=list[RedditAccountSecret])
def list_active_secrets(db: Session = Depends(get_db)):
    """Worker-only: returns DECRYPTED credentials for enabled accounts so the
    Playwright worker can spawn one persistent context per account.

    Intentionally placed under /accounts/internal/active so it's clearly an
    internal endpoint. Protect this with the same dashboard auth in front of
    the API; do not expose it publicly."""
    accounts = db.scalars(
        select(RedditAccount).where(RedditAccount.is_enabled == True)  # noqa: E712
    ).all()
    out: list[RedditAccountSecret] = []
    for account in accounts:
        proxy_payload = None
        if account.proxy is not None and account.proxy.status == "ACTIVE":
            proxy_password = (
                crypto.decrypt(account.proxy.password_enc)
                if account.proxy.password_enc
                else None
            )
            proxy_payload = {
                "id": account.proxy.id,
                "label": account.proxy.label,
                "scheme": account.proxy.scheme,
                "host": account.proxy.host,
                "port": account.proxy.port,
                "username": account.proxy.username,
                "password": proxy_password,
            }
        session_cookies = None
        if account.session_cookies_enc:
            try:
                session_cookies = deserialize_from_db(crypto.decrypt(account.session_cookies_enc))
            except Exception:  # noqa: BLE001
                session_cookies = None
        profile_payload = dict(get_profile(account.profile_index or 0))
        out.append(
            RedditAccountSecret(
                id=account.id,
                username=account.username,
                password=crypto.decrypt(account.password_enc),
                totp_secret=(
                    crypto.decrypt(account.totp_secret_enc)
                    if account.totp_secret_enc
                    else None
                ),
                proxy=proxy_payload,
                user_data_dir=account.user_data_dir or _profile_dir(account.username),
                is_enabled=account.is_enabled,
                status=account.status,
                session_cookies=session_cookies,
                profile=profile_payload,
                platform=account.platform or "reddit",
            )
        )
    return out

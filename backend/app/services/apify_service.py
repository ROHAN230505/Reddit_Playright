import requests

from urllib.parse import quote

from app.config import settings


def residential_proxy_url() -> str | None:
    """Apify residential proxy for logged-out Reddit GETs (health checks).

    Full trudax actor runs are too slow/expensive per account. This is the
    same proxy group the scraper already uses, as a normal HTTP proxy.
    """
    token = (settings.apify_token or "").strip()
    if not token:
        return None
    return f"http://groups-RESIDENTIAL:{quote(token, safe='')}@proxy.apify.com:8000"


def _listing_url(subreddit: str, sort: str) -> str:
    name = subreddit.strip().removeprefix("r/")
    sort_name = (sort or "hot").strip("/") or "hot"
    return f"https://www.reddit.com/r/{name}/{sort_name}/"


def actor_input_for_subreddit(
    subreddit: str,
    limit: int,
    sort: str | None = None,
    time_filter: str | None = None,
) -> dict:
    """Build actor JSON. trudax uses startUrls; prodiger used urls + includeComments."""
    sort_name = sort or settings.scrape_sort
    time_name = time_filter or settings.scrape_time_filter
    listing = _listing_url(subreddit, sort_name)
    actor = (settings.apify_actor_id or "").lower()
    if "trudax" in actor:
        max_comments = max(0, int(settings.max_comments_per_post))
        return {
            "startUrls": [{"url": listing}],
            "skipComments": max_comments <= 0,
            "skipCommunity": True,
            "skipUserPosts": True,
            "maxPostCount": limit,
            "maxComments": max_comments,
            "maxItems": max(limit * (1 + max_comments), limit),
            "sort": sort_name,
            "time": time_name,
            "proxy": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
            },
        }
    return {
        "urls": [{"url": listing}],
        "sort": sort_name,
        "timeFilter": time_name,
        "maxPostsPerSource": limit,
        "includeComments": True,
        "maxCommentsPerPost": settings.max_comments_per_post,
        "commentDepth": settings.comment_depth,
        "outputFormat": "default",
        "maxRequestRetries": settings.max_request_retries,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
        },
    }


def fetch_subreddit(
    subreddit: str,
    limit: int = 50,
    sort: str | None = None,
    time_filter: str | None = None,
) -> dict:
    """Run the configured Apify Reddit actor over one subreddit.

    `sort`/`time_filter` default to the global scrape settings. Karma farming
    overrides them (sort=new) because it wants threads that are still filling
    up, where a fresh reply can actually be seen, rather than the day's
    already-saturated top posts.
    """
    if not settings.apify_token:
        raise ValueError("APIFY_TOKEN is not configured.")

    actor_ref = settings.apify_actor_id.replace("/", "~")
    response = requests.post(
        f"https://api.apify.com/v2/acts/{actor_ref}/runs",
        headers={"Authorization": f"Bearer {settings.apify_token}"},
        json=actor_input_for_subreddit(subreddit, limit, sort, time_filter),
        timeout=180,
    )
    response.raise_for_status()
    run = response.json().get("data", {})
    dataset_id = (
        run.get("namedDatasetIds", {}).get("posts")
        or run.get("defaultDatasetId")
    )
    if not dataset_id:
        return {"items": [], "apify_run_id": run.get("id")}

    headers = {"Authorization": f"Bearer {settings.apify_token}"}
    wait_url = f"https://api.apify.com/v2/actor-runs/{run['id']}"
    wait_data = {}
    # Actor runs often outlive the first 180s wait. A second wait avoids
    # treating an in-flight dataset as an empty successful scrape.
    for _ in range(2):
        wait_response = requests.get(
            wait_url,
            headers=headers,
            params={"waitForFinish": 180},
            timeout=240,
        )
        wait_response.raise_for_status()
        wait_data = wait_response.json().get("data", {}) or {}
        if wait_data.get("status") in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            break

    items_response = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        headers=headers,
        params={"format": "json"},
        timeout=240,
    )
    items_response.raise_for_status()
    payload = items_response.json()
    return {
        "items": payload if isinstance(payload, list) else [],
        "apify_run_id": run.get("id"),
        "apify_status": wait_data.get("status"),
    }

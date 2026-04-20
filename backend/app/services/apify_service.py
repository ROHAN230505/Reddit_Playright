import requests

from app.config import settings


def fetch_subreddit(subreddit: str, limit: int = 50) -> list[dict]:
    if not settings.apify_token:
        raise ValueError("APIFY_TOKEN is not configured.")

    actor_ref = settings.apify_actor_id.replace("/", "~")
    response = requests.post(
        f"https://api.apify.com/v2/acts/{actor_ref}/runs",
        headers={"Authorization": f"Bearer {settings.apify_token}"},
        json={
            "urls": [{"url": f"https://www.reddit.com/r/{subreddit}/"}],
            "sort": settings.scrape_sort,
            "timeFilter": settings.scrape_time_filter,
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
        },
        timeout=180,
    )
    response.raise_for_status()
    run = response.json().get("data", {})
    dataset_id = (
        run.get("namedDatasetIds", {}).get("posts")
        or run.get("defaultDatasetId")
    )
    if not dataset_id:
        return []

    wait_response = requests.get(
        f"https://api.apify.com/v2/actor-runs/{run['id']}",
        headers={"Authorization": f"Bearer {settings.apify_token}"},
        params={"waitForFinish": 180},
        timeout=240,
    )
    wait_response.raise_for_status()

    items_response = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        headers={"Authorization": f"Bearer {settings.apify_token}"},
        params={"format": "json"},
        timeout=240,
    )
    items_response.raise_for_status()
    payload = items_response.json()
    return payload if isinstance(payload, list) else []

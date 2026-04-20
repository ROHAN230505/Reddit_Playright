from apify_client import ApifyClient

from app.config import settings


def fetch_subreddit(subreddit: str, limit: int = 50) -> list[dict]:
    if not settings.apify_token:
        raise ValueError("APIFY_TOKEN is not configured.")

    client = ApifyClient(settings.apify_token)
    run = client.actor("prodiger/reddit-scraper").call(
        run_input={
            "urls": [{"url": f"https://www.reddit.com/r/{subreddit}/"}],
            "maxItems": limit,
        }
    )
    dataset = client.dataset(run["defaultDatasetId"])
    return list(dataset.iterate_items())

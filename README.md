# Reddit AI Reply Intelligence System

## To-Do List From The Spec

1. Manage a persistent tracked-subreddit list from the dashboard.
2. Queue fetch jobs for all tracked subreddits or manual subreddit entries.
3. Scrape Reddit posts and comments via the Apify Reddit actor.
4. Normalize the actor's flat JSON output of `post` and `comment` rows.
5. Filter comments using an LLM for AI relevance only.
6. Generate Reddit-style draft replies with DeepSeek.
7. Insert `sentx.ai` naturally in about 50% of relevant replies.
8. Store posts, comments, replies, and tracked subreddits in the database.
9. Display replies in a Streamlit dashboard with post/comment links.
10. Support copying reply drafts, marking replies done, and managing subreddit tracking.
11. Run the stack with FastAPI, Celery, Redis, PostgreSQL, and Docker.

## Run

1. Copy `.env.example` to `.env` and fill in your API keys.
2. Start the stack with `docker compose up --build`.
3. Open `http://localhost:8501` for the dashboard.
4. Open `http://localhost:8000/docs` for the API docs.

## Apify Actor Notes

The app is wired for the flat JSON output from `prodiger/reddit-scraper`, where rows come back as a stream of `post` and `comment` items.
The default actor ID is configurable with `APIFY_ACTOR_ID`.

# Reddit AI Reply Intelligence System

## To-Do List From The Spec

1. Accept subreddit lists and queue fetch jobs.
2. Scrape Reddit posts and comments via Apify.
3. Normalize comment payloads.
4. Filter comments using an LLM for AI relevance only.
5. Generate Reddit-style draft replies with DeepSeek.
6. Insert `sentx.ai` naturally in about 50% of relevant replies.
7. Store posts, comments, and replies in the database.
8. Display replies in a Streamlit dashboard with post/comment links.
9. Support copying reply drafts and marking replies as done.
10. Run the stack with FastAPI, Celery, Redis, PostgreSQL, and Docker.

## Run

1. Copy `.env.example` to `.env` and fill in your API keys.
2. Start the stack with `docker compose up --build`.
3. Open `http://localhost:8501` for the dashboard.
4. Open `http://localhost:8000/docs` for the API docs.

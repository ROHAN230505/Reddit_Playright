import os


class Settings:
    app_name = "Reddit AI Reply Intelligence System"
    database_url = os.getenv("DATABASE_URL", "sqlite:///./reddit_ai.db")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    apify_token = os.getenv("APIFY_TOKEN", "")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    deepseek_temperature = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.45"))
    deepseek_max_tokens = int(os.getenv("DEEPSEEK_MAX_TOKENS", "90"))
    deepseek_frequency_penalty = float(os.getenv("DEEPSEEK_FREQUENCY_PENALTY", "0.3"))
    reply_promo_ratio = float(os.getenv("REPLY_PROMO_RATIO", "0.10"))
    reply_max_chars = int(os.getenv("REPLY_MAX_CHARS", "280"))
    apify_actor_id = os.getenv("APIFY_ACTOR_ID", "prodiger/reddit-scraper")
    scrape_limit = int(os.getenv("SCRAPE_LIMIT", "15"))
    scrape_sort = os.getenv("SCRAPE_SORT", "hot")
    scrape_time_filter = os.getenv("SCRAPE_TIME_FILTER", "week")
    max_comments_per_post = int(os.getenv("MAX_COMMENTS_PER_POST", "25"))
    comment_depth = int(os.getenv("COMMENT_DEPTH", "3"))
    max_request_retries = int(os.getenv("MAX_REQUEST_RETRIES", "5"))
    # GLP auto-approve: GLP-platform replies skip operator review and go
    # straight to APPROVED so the Playwright worker can claim and post them.
    # Set GLP_AUTO_APPROVE=0 to revert to PENDING (manual review) mode.
    glp_auto_approve = os.getenv("GLP_AUTO_APPROVE", "1").lower() in ("1", "true", "yes", "on")
    # 4chan auto-approve: same idea for chan-platform replies.
    chan_auto_approve = os.getenv("CHAN_AUTO_APPROVE", "1").lower() in ("1", "true", "yes", "on")
    # 4chan reply generation (the every-5-min scrape→classify→draft beat). Set
    # CHAN_SCRAPE_ENABLED=0 to stop generating NEW chan replies. Does not affect
    # posting of already-APPROVED chan replies, nor GLP/Reddit generation.
    chan_scrape_enabled = os.getenv("CHAN_SCRAPE_ENABLED", "1").lower() in ("1", "true", "yes", "on")
    # CSV of GLP topic slugs to scrape (under /topics/). GLP has no dedicated AI
    # forum, so tech/AI lives in Science/Technology. Each thread pulled from a
    # topic page is tagged with that topic slug, so accounts can be restricted
    # to it via assigned_sections. Default keeps us on tech/AI only.
    glp_topics = [
        t.strip().strip("/")
        for t in os.getenv("GLP_TOPICS", "Science/Technology").split(",")
        if t.strip().strip("/")
    ]
    # CSV of 4chan boards to scrape. Default targets /g/ and /biz/.
    chan_boards = [
        b.strip().lower()
        for b in os.getenv("CHAN_BOARDS", "g,biz").split(",")
        if b.strip()
    ]
    # Cap the number of threads per board the LLM drills into per beat tick.
    chan_threads_per_board = int(os.getenv("CHAN_THREADS_PER_BOARD", "10"))
    # Max replies the worker will POST into a single 4chan thread. Posting many
    # replies into one thread reads as spam to 4chan + mods; this spreads our
    # replies across threads. 0 disables the cap.
    chan_max_posts_per_thread = int(os.getenv("CHAN_MAX_POSTS_PER_THREAD", "2"))
    # Egress proxy for 4chan API reads (a.4cdn.org). 4chan rate-limits per IP
    # and can block datacenter ranges, so route reads through a residential/ISP
    # proxy. Set CHAN_PROXY_URL to the provider proxy URL when required.
    # Leave empty to make requests directly (no proxy).
    chan_proxy_url = os.getenv("CHAN_PROXY_URL", "")
    cors_allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        ).split(",")
        if origin.strip()
    ]


settings = Settings()

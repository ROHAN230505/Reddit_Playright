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
    cors_allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:8501,http://127.0.0.1:8501",
        ).split(",")
        if origin.strip()
    ]


settings = Settings()

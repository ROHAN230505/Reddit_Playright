import os


class Settings:
    app_name = "Reddit AI Reply Intelligence System"
    database_url = os.getenv("DATABASE_URL", "sqlite:///./reddit_ai.db")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    apify_token = os.getenv("APIFY_TOKEN", "")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    apify_actor_id = os.getenv("APIFY_ACTOR_ID", "prodiger/reddit-scraper")


settings = Settings()

from fastapi import FastAPI

from app.config import settings
from app.db.session import Base, engine
from app.routes.fetch import router as fetch_router
from app.routes.replies import router as replies_router
from app.routes.tracked_subreddits import router as tracked_subreddits_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)
app.include_router(fetch_router)
app.include_router(replies_router)
app.include_router(tracked_subreddits_router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}

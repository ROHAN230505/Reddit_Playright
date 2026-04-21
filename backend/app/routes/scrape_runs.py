from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ScrapeRun
from app.db.session import get_db
from app.schemas import ScrapeRunListResponse

router = APIRouter(prefix="/scrape-runs", tags=["scrape-runs"])


@router.get("", response_model=ScrapeRunListResponse)
def list_scrape_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    subreddit: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(ScrapeRun)
    if subreddit and subreddit != "All":
        stmt = stmt.where(ScrapeRun.subreddit == subreddit.removeprefix("r/"))
    total_runs = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(ScrapeRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    runs = db.scalars(stmt).all()
    return ScrapeRunListResponse(
        page=page,
        page_size=page_size,
        total_runs=total_runs,
        runs=runs,
    )

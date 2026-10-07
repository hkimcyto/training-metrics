import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api.routes import router
from app.config import get_settings
from app.db.models import Athlete
from app.db.session import SessionLocal
from app.ingest.sync import sync_athlete

log = logging.getLogger("tri")
STATIC = Path(__file__).resolve().parent.parent / "static"


def sync_everyone() -> None:
    """Safety net behind webhooks: catches anything a missed event dropped."""
    settings = get_settings()
    db = SessionLocal()
    try:
        for a in db.scalars(select(Athlete).where(Athlete.refresh_token.is_not(None))).all():
            try:
                sync_athlete(settings, db, a)
            except Exception as e:  # noqa: BLE001
                log.warning("scheduled sync failed for athlete %s: %s", a.id, e)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    scheduler = None
    if settings.strava_enabled:
        scheduler = BackgroundScheduler()
        scheduler.add_job(sync_everyone, "interval", minutes=settings.sync_interval_minutes)
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown()


app = FastAPI(title="Tri Dash API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

# In production the built frontend is served by the API, so one container
# serves everything and cookies stay first-party.
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        f = STATIC / path
        return FileResponse(f if path and f.is_file() else STATIC / "index.html")

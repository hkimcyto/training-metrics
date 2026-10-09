import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
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
from app.ingest.sync import is_sync_active, sync_athlete

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s %(message)s")
log = logging.getLogger("tri")
STATIC = Path(__file__).resolve().parent.parent / "static"


def sync_everyone() -> None:
    """Safety net behind webhooks: catches anything a missed event dropped."""
    settings = get_settings()
    db = SessionLocal()
    try:
        for a in db.scalars(select(Athlete).where(Athlete.refresh_token.is_not(None))).all():
            if is_sync_active(a):
                continue
            try:
                # a first import that never finished (e.g. cut off by a redeploy) restarts in full
                sync_athlete(settings, db, a, full=a.last_synced_at is None)
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
        # first run shortly after boot resumes anything a restart interrupted
        scheduler.add_job(
            sync_everyone,
            "interval",
            minutes=settings.sync_interval_minutes,
            next_run_time=datetime.now(UTC) + timedelta(seconds=20),
        )
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown()


app = FastAPI(title="Training Dash API", version="0.1.0", lifespan=lifespan)
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

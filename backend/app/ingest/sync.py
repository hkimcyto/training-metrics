"""Strava sync: full backfill on first connect, incremental afterwards, and
single-activity updates from webhooks."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Activity, Athlete
from app.ingest.scoring import apply_streams, rescore, resolve_thresholds, sport_of
from app.ingest.strava import StravaClient, Tokens

log = logging.getLogger(__name__)


def client_for(settings: Settings, db: Session, athlete: Athlete) -> StravaClient:
    if not athlete.refresh_token:
        raise ValueError("athlete has not connected Strava")
    c = StravaClient(
        settings,
        Tokens(athlete.access_token or "", athlete.refresh_token, athlete.token_expires_at or 0),
    )

    def persist(t: Tokens) -> None:
        athlete.access_token, athlete.refresh_token, athlete.token_expires_at = (
            t.access_token,
            t.refresh_token,
            t.expires_at,
        )
        db.commit()

    c.on_refresh = persist
    return c


def upsert_summary(db: Session, athlete: Athlete, s: dict[str, Any]) -> Activity:
    ext = str(s["id"])
    act = db.scalar(
        select(Activity).where(
            Activity.athlete_id == athlete.id,
            Activity.source == "strava",
            Activity.external_id == ext,
        )
    )
    if act is None:
        act = Activity(athlete_id=athlete.id, source="strava", external_id=ext)
        db.add(act)
    start = datetime.fromisoformat(s["start_date_local"].replace("Z", ""))
    act.name = s.get("name", "")[:255]
    act.sport_type = s.get("sport_type") or s.get("type", "Workout")
    act.sport = sport_of(act.sport_type).value
    act.start_time = start
    act.day = start.date()
    act.trainer = bool(s.get("trainer"))
    act.moving_s = float(s.get("moving_time") or 0)
    act.elapsed_s = float(s.get("elapsed_time") or 0)
    act.distance_m = float(s.get("distance") or 0)
    act.elev_gain_m = float(s.get("total_elevation_gain") or 0)
    act.avg_speed = s.get("average_speed")
    act.avg_hr = s.get("average_heartrate")
    act.max_hr = s.get("max_heartrate")
    act.avg_watts = s.get("weighted_average_watts") or s.get("average_watts")
    act.device_watts = bool(s.get("device_watts"))
    act.relative_effort = s.get("suffer_score")
    act.polyline = (s.get("map") or {}).get("summary_polyline") or None
    return act


def needs_streams(act: Activity) -> bool:
    return not act.has_streams and act.sport in ("bike", "run") and (act.avg_hr or act.device_watts)


STALE_AFTER = timedelta(minutes=10)


def is_sync_active(athlete: Athlete) -> bool:
    """A sync counts as running if it reported progress recently. A row stuck
    in "running" longer than that was interrupted (e.g. a redeploy)."""
    if athlete.sync_state != "running" or athlete.sync_updated_at is None:
        return False
    updated = athlete.sync_updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return datetime.now(UTC) - updated < STALE_AFTER


def _progress(
    db: Session, athlete: Athlete, state: str, message: str, done: int = 0, total: int = 0
) -> None:
    """Persist sync progress so the UI can show it and a restart can resume."""
    athlete.sync_state, athlete.sync_message = state, message
    athlete.sync_done, athlete.sync_total = done, total
    athlete.sync_updated_at = datetime.now(UTC)
    db.commit()
    log.info("sync athlete=%s %s %s %s/%s", athlete.id, state, message, done, total)


def sync_athlete(
    settings: Settings, db: Session, athlete: Athlete, full: bool = False
) -> dict[str, int]:
    """Pull new activities, fetch streams for the most recent ones that lack
    them, and rescore everything with the current thresholds.

    Progress is committed as it goes, so the dashboard fills in while a long
    first import runs and an interrupted import picks up where it stopped."""
    try:
        return _sync(settings, db, athlete, full)
    except Exception as e:
        db.rollback()
        _progress(db, athlete, "error", f"Sync failed: {e}"[:250])
        log.exception("sync failed for athlete %s", athlete.id)
        raise


def _sync(settings: Settings, db: Session, athlete: Athlete, full: bool) -> dict[str, int]:
    client = client_for(settings, db, athlete)
    after = None
    if not full and athlete.last_synced_at:
        after = int(athlete.last_synced_at.timestamp()) - 3 * 86400  # catch late uploads/edits

    _progress(db, athlete, "running", "Fetching activity list")
    new = 0
    for s in client.activities(after=after):
        upsert_summary(db, athlete, s)
        new += 1
        if new % 100 == 0:
            _progress(db, athlete, "running", "Fetching activity list", new, 0)
    db.flush()
    rescore_all(db, athlete)  # summary-level scores right away, refined after streams
    _progress(db, athlete, "running", "Fetching heart rate and power", 0, 0)

    pending = [
        a
        for a in db.scalars(
            select(Activity)
            .where(Activity.athlete_id == athlete.id, Activity.source == "strava")
            .order_by(Activity.start_time.desc())
            .limit(settings.strava_stream_backfill)
        ).all()
        if needs_streams(a)
    ]
    streamed = 0
    for i, act in enumerate(pending, 1):
        try:
            apply_streams(act, client.streams(act.external_id))
            streamed += 1
        except Exception as e:  # one bad activity shouldn't stop the sync
            log.warning("streams failed for %s: %s", act.external_id, e)
        if i % 10 == 0 or i == len(pending):
            _progress(db, athlete, "running", "Fetching heart rate and power", i, len(pending))

    rescored = rescore_all(db, athlete)
    athlete.last_synced_at = datetime.now(UTC)
    _progress(db, athlete, "idle", f"Synced {new} activities", new, new)
    return {"activities": new, "streams": streamed, "rescored": rescored}


def rescore_all(db: Session, athlete: Athlete) -> int:
    t, _ = resolve_thresholds(db, athlete)
    acts = db.scalars(select(Activity).where(Activity.athlete_id == athlete.id)).all()
    for a in acts:
        rescore(a, t)
    return len(acts)


def handle_webhook_event(settings: Settings, db: Session, event: dict[str, Any]) -> str:
    """Strava sends create/update/delete for activities and deauthorize for
    athletes. Respond fast; the caller runs this in the background."""
    athlete = db.scalar(select(Athlete).where(Athlete.strava_id == event.get("owner_id")))
    if athlete is None:
        return "unknown athlete"
    if (
        event.get("object_type") == "athlete"
        and (event.get("updates") or {}).get("authorized") == "false"
    ):
        athlete.access_token = athlete.refresh_token = None
        db.commit()
        return "deauthorized"
    if event.get("object_type") != "activity":
        return "ignored"
    ext = str(event["object_id"])
    if event.get("aspect_type") == "delete":
        act = db.scalar(
            select(Activity).where(Activity.athlete_id == athlete.id, Activity.external_id == ext)
        )
        if act:
            db.delete(act)
            db.commit()
        return "deleted"
    client = client_for(settings, db, athlete)
    s = client.activity(ext)
    if not s:
        return "missing"
    act = upsert_summary(db, athlete, s)
    if needs_streams(act):
        apply_streams(act, client.streams(ext))
    t, _ = resolve_thresholds(db, athlete)
    rescore(act, t)
    db.commit()
    return "upserted"

from __future__ import annotations

import secrets
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import services
from app.analytics.race import RACE_TYPES
from app.config import Settings, get_settings
from app.db.models import Activity, Athlete, Race
from app.db.session import SessionLocal, get_db
from app.ingest import garmin
from app.ingest.scoring import resolve_thresholds
from app.ingest.strava import StravaClient, StravaError, authorize_url
from app.ingest.sync import handle_webhook_event, is_sync_active, rescore_all, sync_athlete

router = APIRouter(prefix="/api")
RaceTypeIn = Literal[(*RACE_TYPES, "run")]  # type: ignore[valid-type]  # "run" = custom distance
COOKIE = "tri_session"

DbDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _signer(settings: Settings) -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt="session")


def current_athlete(request: Request, db: DbDep, settings: SettingsDep) -> Athlete:
    """The signed-in athlete, or the public demo athlete for visitors."""
    raw = request.cookies.get(COOKIE)
    if raw:
        try:
            athlete = db.get(Athlete, _signer(settings).loads(raw)["aid"])
            if athlete:
                return athlete
        except (BadSignature, KeyError, TypeError):
            pass
    if settings.demo_mode:
        demo = db.scalar(select(Athlete).where(Athlete.is_demo.is_(True)))
        if demo:
            return demo
    raise HTTPException(401, "Connect Strava to continue")


AthleteDep = Annotated[Athlete, Depends(current_athlete)]


def require_owner(athlete: AthleteDep) -> Athlete:
    if athlete.is_demo:
        raise HTTPException(
            403, "The demo athlete is read-only. Connect Strava to use your own data."
        )
    return athlete


OwnerDep = Annotated[Athlete, Depends(require_owner)]


# ------------------------------------------------------------------- meta


@router.get("/health")
def health(db: DbDep) -> dict[str, Any]:
    n = db.scalar(select(func.count(Activity.id)))
    return {"ok": True, "activities": n}


@router.get("/me")
def me(athlete: AthleteDep, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    t, sources = resolve_thresholds(db, athlete)
    return {
        "id": athlete.id,
        "name": athlete.name,
        "is_demo": athlete.is_demo,
        "measurement": athlete.measurement,
        "strava_enabled": settings.strava_enabled,
        "last_synced_at": athlete.last_synced_at.isoformat() if athlete.last_synced_at else None,
        "sync": {
            "state": athlete.sync_state,
            "message": athlete.sync_message,
            "done": athlete.sync_done,
            "total": athlete.sync_total,
        },
        "today": services._today(db, athlete).isoformat(),
        "settings": {
            "weight_kg": athlete.weight_kg,
            "ftp_watts": athlete.ftp_watts,
            "run_threshold_speed": athlete.run_threshold_speed,
            "css_speed": athlete.css_speed,
            "max_hr": athlete.max_hr,
            "rest_hr": athlete.rest_hr,
            "lthr": athlete.lthr,
        },
        "thresholds": {**t.__dict__, "sources": sources},
        "target_race": (r := services.target_race(db, athlete)) and services.race_dict(r),
    }


class SettingsIn(BaseModel):
    weight_kg: float | None = Field(None, gt=30, lt=200)
    ftp_watts: float | None = Field(None, gt=50, lt=600)
    run_threshold_speed: float | None = Field(None, gt=2, lt=7)
    css_speed: float | None = Field(None, gt=0.4, lt=2.5)
    max_hr: float | None = Field(None, gt=120, lt=230)
    rest_hr: float | None = Field(None, gt=25, lt=100)
    lthr: float | None = Field(None, gt=100, lt=220)


@router.patch("/me/settings")
def update_settings(body: SettingsIn, athlete: OwnerDep, db: DbDep) -> dict[str, Any]:
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(athlete, k, v)
    db.commit()
    rescore_all(db, athlete)  # thresholds changed, so every score changes
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------- strava auth


@router.get("/auth/strava/login")
def strava_login(settings: SettingsDep) -> RedirectResponse:
    if not settings.strava_enabled:
        raise HTTPException(503, "Strava is not configured on this server")
    state = secrets.token_urlsafe(16)
    resp = RedirectResponse(authorize_url(settings, state))
    resp.set_cookie(
        "oauth_state",
        state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=settings.api_url.startswith("https"),
    )
    return resp


def _run_sync(athlete_id: int, full: bool) -> None:
    db = SessionLocal()
    try:
        athlete = db.get(Athlete, athlete_id)
        if athlete and not is_sync_active(athlete):
            sync_athlete(get_settings(), db, athlete, full=full)
    except Exception:  # noqa: BLE001 - already recorded on the athlete row
        pass
    finally:
        db.close()


@router.get("/auth/strava/callback")
def strava_callback(
    request: Request,
    background: BackgroundTasks,
    db: DbDep,
    settings: SettingsDep,
    code: str = "",
    state: str = "",
    error: str | None = None,
) -> RedirectResponse:
    if error or not code:
        return RedirectResponse(f"{settings.frontend_url}/?auth=denied")
    if state != request.cookies.get("oauth_state"):
        raise HTTPException(400, "OAuth state mismatch")
    try:
        tokens = StravaClient.exchange_code(settings, code)
    except StravaError as e:
        raise HTTPException(502, str(e)) from e
    profile = tokens.athlete or {}
    athlete = db.scalar(select(Athlete).where(Athlete.strava_id == profile.get("id")))
    if athlete is None:
        athlete = Athlete(strava_id=profile.get("id"), name="")
        db.add(athlete)
    athlete.name = (
        f"{profile.get('firstname', '')} {profile.get('lastname', '')}".strip() or "Athlete"
    )
    athlete.access_token, athlete.refresh_token, athlete.token_expires_at = (
        tokens.access_token,
        tokens.refresh_token,
        tokens.expires_at,
    )
    if profile.get("weight"):
        athlete.weight_kg = float(profile["weight"])
    if profile.get("measurement_preference") == "meters":
        athlete.measurement = "metric"
    db.commit()
    background.add_task(_run_sync, athlete.id, athlete.last_synced_at is None)

    resp = RedirectResponse(f"{settings.frontend_url}/?auth=ok")
    resp.set_cookie(
        COOKIE,
        _signer(settings).dumps({"aid": athlete.id}),
        max_age=60 * 60 * 24 * 60,
        httponly=True,
        samesite="lax",
        secure=settings.api_url.startswith("https"),
    )
    resp.delete_cookie("oauth_state")
    return resp


@router.post("/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.post("/sync")
def sync_now(athlete: OwnerDep, background: BackgroundTasks) -> dict[str, str]:
    if is_sync_active(athlete):
        return {"status": "already running"}
    background.add_task(_run_sync, athlete.id, athlete.last_synced_at is None)
    return {"status": "started"}


# ---------------------------------------------------------------- webhooks


@router.get("/webhooks/strava")
def strava_webhook_verify(
    settings: SettingsDep,
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
) -> dict[str, str]:
    if mode != "subscribe" or token != settings.strava_webhook_verify_token:
        raise HTTPException(403, "bad verify token")
    return {"hub.challenge": challenge}


@router.post("/webhooks/strava")
async def strava_webhook_event(request: Request, background: BackgroundTasks) -> dict[str, bool]:
    event = await request.json()

    def work() -> None:
        db = SessionLocal()
        try:
            handle_webhook_event(get_settings(), db, event)
        finally:
            db.close()

    background.add_task(work)  # Strava wants a 200 within 2 seconds
    return {"ok": True}


# -------------------------------------------------------------- dashboard


@router.get("/dashboard")
def dashboard(
    athlete: AthleteDep, db: DbDep, weeks: int = Query(12, ge=4, le=52)
) -> dict[str, Any]:
    return {"weeks": services.weekly(db, athlete, weeks), "records": services.records(db, athlete)}


@router.get("/pmc")
def pmc(athlete: AthleteDep, db: DbDep, days: int = Query(150, ge=14, le=730)) -> dict[str, Any]:
    return services.pmc_view(db, athlete, days)


@router.get("/training-status")
def training_status(athlete: AthleteDep, db: DbDep) -> dict[str, Any]:
    return services.training_status(db, athlete)


@router.get("/race/prediction")
def race(
    athlete: AthleteDep,
    db: DbDep,
    race_id: int | None = None,
    race: RaceTypeIn | None = None,
    distance_m: float | None = Query(None, gt=100, lt=400_000),
) -> dict[str, Any]:
    if race == "run" and not distance_m:
        raise HTTPException(422, "A custom run needs a distance")
    try:
        return services.race_prediction(db, athlete, race_id, race, distance_m)
    except LookupError as e:
        raise HTTPException(404, "Race not found") from e


# ------------------------------------------------------------------ races


class RaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    day: date
    race_type: RaceTypeIn
    distance_m: float | None = Field(None, gt=100, lt=400_000)
    priority: Literal["A", "B", "C"] = "A"
    climb_m: float | None = Field(None, ge=0, lt=5000)
    temp_c: float = Field(18, gt=-10, lt=45)
    wetsuit: bool = True
    catalog_key: str | None = Field(None, max_length=40)


class RacePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    day: date | None = None
    race_type: RaceTypeIn | None = None
    distance_m: float | None = Field(None, gt=100, lt=400_000)
    priority: Literal["A", "B", "C"] | None = None
    climb_m: float | None = Field(None, ge=0, lt=5000)
    temp_c: float | None = Field(None, gt=-10, lt=45)
    wetsuit: bool | None = None


def _check_distance(r: Race) -> None:
    if r.race_type == "run" and not r.distance_m:
        raise HTTPException(422, "A custom run needs a distance")
    if r.race_type != "run":
        r.distance_m = None  # standard races have fixed distances


def _own_race(db: Session, athlete: Athlete, race_id: int) -> Race:
    r = db.get(Race, race_id)
    if r is None or r.athlete_id != athlete.id:
        raise HTTPException(404, "Race not found")
    return r


@router.get("/races")
def list_races(athlete: AthleteDep, db: DbDep) -> dict[str, Any]:
    return services.races_view(db, athlete)


@router.post("/races", status_code=201)
def add_race(body: RaceIn, athlete: OwnerDep, db: DbDep) -> dict[str, Any]:
    r = Race(athlete_id=athlete.id, **body.model_dump())
    _check_distance(r)
    db.add(r)
    db.commit()
    db.refresh(r)
    return services.race_dict(r)


@router.patch("/races/{race_id}")
def edit_race(race_id: int, body: RacePatch, athlete: OwnerDep, db: DbDep) -> dict[str, Any]:
    r = _own_race(db, athlete, race_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k in ("distance_m", "climb_m"):
            setattr(r, k, v)
    _check_distance(r)
    db.commit()
    return services.race_dict(r)


@router.delete("/races/{race_id}", status_code=204)
def delete_race(race_id: int, athlete: OwnerDep, db: DbDep) -> Response:
    db.delete(_own_race(db, athlete, race_id))
    db.commit()
    return Response(status_code=204)


@router.get("/power-curve")
def power_curve(
    athlete: AthleteDep, db: DbDep, days: int = Query(90, ge=7, le=730)
) -> dict[str, Any]:
    return services.power_curve(db, athlete, days)


@router.get("/efficiency")
def efficiency(
    athlete: AthleteDep, db: DbDep, days: int = Query(120, ge=14, le=730)
) -> dict[str, Any]:
    return services.efficiency_trend(db, athlete, days)


@router.get("/calendar")
def calendar(
    athlete: AthleteDep, db: DbDep, days: int = Query(365, ge=28, le=730)
) -> list[dict[str, Any]]:
    return services.calendar(db, athlete, days)


@router.get("/routes")
def routes(
    athlete: AthleteDep, db: DbDep, days: int = Query(180, ge=7, le=1825)
) -> list[dict[str, Any]]:
    return services.routes(db, athlete, days)


@router.get("/activities")
def list_activities(
    athlete: AthleteDep,
    db: DbDep,
    sport: str | None = None,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    q = select(Activity).where(Activity.athlete_id == athlete.id)
    if sport:
        q = q.where(Activity.sport == sport)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Activity.start_time.desc()).offset(offset).limit(limit)).all()
    return {"total": total, "items": [services.activity_dict(a) for a in rows]}


@router.get("/activities/{activity_id}")
def get_activity(activity_id: int, athlete: AthleteDep, db: DbDep) -> dict[str, Any]:
    a = db.get(Activity, activity_id)
    if a is None or a.athlete_id != athlete.id:
        raise HTTPException(404, "Activity not found")
    return {**services.activity_dict(a), "polyline": a.polyline, "power_curve": a.power_curve}


# ---------------------------------------------------------------- wellness


@router.get("/wellness")
def wellness(athlete: AthleteDep, db: DbDep, days: int = Query(90, ge=7, le=730)) -> dict[str, Any]:
    return services.wellness(db, athlete, days)


@router.post("/wellness/garmin-import")
async def garmin_import(
    athlete: OwnerDep, db: DbDep, file: UploadFile = File(...)
) -> dict[str, Any]:
    data = await file.read()
    if len(data) > 400 * 1024 * 1024:
        raise HTTPException(413, "Upload the wellness folders rather than the full export")
    try:
        if (file.filename or "").lower().endswith(".zip"):
            days, profile = garmin.read_export(data)
        else:
            import json

            days, profile = garmin.parse_records([json.loads(data)]), {}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Couldn't read that file: {e}") from e
    if not days and not profile:
        raise HTTPException(422, "No sleep, HRV or resting-HR data found in that file")
    n = garmin.save(db, athlete, days) if days else 0
    if profile:
        garmin.save_profile(db, athlete, profile)
    rescore_all(db, athlete)  # Garmin thresholds and resting HR change every score
    db.commit()
    return {
        "days_imported": n,
        "first": min(days).isoformat() if days else None,
        "last": max(days).isoformat() if days else None,
        "thresholds_imported": sorted(k for k in profile if k != "race_predictions_as_of"),
    }


@router.post("/wellness/garmin-sync")
def garmin_sync(athlete: OwnerDep, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    if not (settings.garmin_email and settings.garmin_password):
        raise HTTPException(503, "Garmin live sync is not configured on this server")
    n = garmin.live_sync(db, athlete, settings.garmin_email, settings.garmin_password)
    return {"days_imported": n}

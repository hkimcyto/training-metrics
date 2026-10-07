"""End-to-end ingestion against a mocked Strava API: summaries, streams,
token refresh and webhook events, all through the real sync code."""

import time

import httpx
import numpy as np
import pytest
import respx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.db.models import Activity, Athlete, Base
from app.ingest.strava import API, OAUTH, StravaError
from app.ingest.sync import handle_webhook_event, sync_athlete

SETTINGS = Settings(strava_client_id="1", strava_client_secret="s", database_url="sqlite://")

RIDE = {
    "id": 101,
    "name": "Hawk Hill",
    "sport_type": "Ride",
    "start_date_local": "2026-09-20T08:00:00Z",
    "moving_time": 3600,
    "elapsed_time": 3900,
    "distance": 30000.0,
    "total_elevation_gain": 400,
    "average_speed": 8.3,
    "average_heartrate": 140,
    "average_watts": 180,
    "device_watts": True,
    "trainer": False,
    "map": {"summary_polyline": "_p~iF~ps|U_ulLnnqC"},
}
RUN = {
    "id": 102,
    "name": "Easy run",
    "sport_type": "Run",
    "start_date_local": "2026-09-21T07:00:00Z",
    "moving_time": 2700,
    "elapsed_time": 2800,
    "distance": 8000.0,
    "average_speed": 2.96,
    "average_heartrate": 145,
    "map": {},
}


@pytest.fixture
def db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s


@pytest.fixture
def athlete(db):
    a = Athlete(
        name="Test",
        strava_id=7,
        access_token="old",
        refresh_token="r",
        token_expires_at=int(time.time()) - 10,
        ftp_watts=200,
    )
    db.add(a)
    db.commit()
    return a


def ride_streams():
    n = 3600
    return {
        "watts": {"data": list(np.full(n, 180.0))},
        "heartrate": {"data": list(np.linspace(135, 145, n))},
        "time": {"data": list(range(n))},
    }


@respx.mock
def test_full_sync_refreshes_token_scores_and_streams(db, athlete):
    refresh = respx.post(f"{OAUTH}/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "new",
                "refresh_token": "r2",
                "expires_at": int(time.time()) + 3600,
            },
        )
    )
    respx.get(f"{API}/athlete/activities").mock(return_value=httpx.Response(200, json=[RIDE, RUN]))
    respx.get(f"{API}/activities/101/streams").mock(
        return_value=httpx.Response(200, json=ride_streams())
    )
    respx.get(f"{API}/activities/102/streams").mock(return_value=httpx.Response(200, json={}))

    out = sync_athlete(SETTINGS, db, athlete, full=True)

    assert refresh.called and athlete.access_token == "new" and athlete.refresh_token == "r2"
    assert out["activities"] == 2
    ride = db.scalar(select(Activity).where(Activity.external_id == "101"))
    assert ride.sport == "bike" and ride.tss_method == "power"
    assert ride.np_watts == pytest.approx(180, rel=0.01)
    assert ride.tss == pytest.approx(81, rel=0.02)  # 1 h at IF 0.9
    assert ride.decoupling_pct is not None and ride.decoupling_pct > 0  # HR drifted up
    assert ride.power_curve["300"] == pytest.approx(180, rel=0.01)
    run = db.scalar(select(Activity).where(Activity.external_id == "102"))
    assert run.sport == "run" and run.tss_method == "pace"


@respx.mock
def test_sync_is_idempotent(db, athlete):
    athlete.token_expires_at = int(time.time()) + 3600
    respx.get(f"{API}/athlete/activities").mock(return_value=httpx.Response(200, json=[RUN]))
    respx.get(url__regex=r".*/streams").mock(return_value=httpx.Response(200, json={}))
    sync_athlete(SETTINGS, db, athlete, full=True)
    sync_athlete(SETTINGS, db, athlete, full=True)
    assert len(db.scalars(select(Activity)).all()) == 1


@respx.mock
def test_rate_limit_is_retried(db, athlete, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    athlete.token_expires_at = int(time.time()) + 3600
    route = respx.get(f"{API}/athlete/activities").mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json=[RUN])]
    )
    respx.get(url__regex=r".*/streams").mock(return_value=httpx.Response(200, json={}))
    assert sync_athlete(SETTINGS, db, athlete, full=True)["activities"] == 1
    assert route.call_count == 2


@respx.mock
def test_webhook_create_and_delete(db, athlete):
    athlete.token_expires_at = int(time.time()) + 3600
    respx.get(f"{API}/activities/102").mock(return_value=httpx.Response(200, json=RUN))
    respx.get(url__regex=r".*/streams").mock(return_value=httpx.Response(200, json={}))
    ev = {"object_type": "activity", "object_id": 102, "aspect_type": "create", "owner_id": 7}
    assert handle_webhook_event(SETTINGS, db, ev) == "upserted"
    assert db.scalar(select(Activity).where(Activity.external_id == "102")) is not None
    assert handle_webhook_event(SETTINGS, db, {**ev, "aspect_type": "delete"}) == "deleted"
    assert db.scalar(select(Activity).where(Activity.external_id == "102")) is None


def test_webhook_deauthorize_clears_tokens(db, athlete):
    ev = {
        "object_type": "athlete",
        "object_id": 7,
        "aspect_type": "update",
        "owner_id": 7,
        "updates": {"authorized": "false"},
    }
    assert handle_webhook_event(SETTINGS, db, ev) == "deauthorized"
    assert athlete.refresh_token is None


@respx.mock
def test_sync_records_progress_and_errors(db, athlete):
    from datetime import UTC, datetime, timedelta

    from app.ingest.sync import is_sync_active

    athlete.token_expires_at = int(time.time()) + 3600
    respx.get(f"{API}/athlete/activities").mock(return_value=httpx.Response(200, json=[RUN]))
    respx.get(url__regex=r".*/streams").mock(return_value=httpx.Response(200, json={}))
    sync_athlete(SETTINGS, db, athlete, full=True)
    assert athlete.sync_state == "idle" and athlete.last_synced_at is not None

    respx.get(f"{API}/athlete/activities").mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(StravaError):
        sync_athlete(SETTINGS, db, athlete)
    assert athlete.sync_state == "error" and "500" in athlete.sync_message

    athlete.sync_state, athlete.sync_updated_at = "running", datetime.now(UTC)
    assert is_sync_active(athlete)
    athlete.sync_updated_at = datetime.now(UTC) - timedelta(minutes=30)
    assert not is_sync_active(athlete)  # interrupted by a restart, safe to resume

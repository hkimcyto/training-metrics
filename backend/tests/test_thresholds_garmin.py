from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.analytics.thresholds import run_threshold_from_vo2max
from app.db.models import Athlete, Base, WellnessDay
from app.ingest.garmin import parse_profile
from app.ingest.scoring import resolve_thresholds


def test_vo2max_threshold_is_plausible_and_monotonic():
    # Daniels' tables put threshold pace for VO2 max 60 near 3:40/km
    assert run_threshold_from_vo2max(60) == pytest.approx(1000 / 220, rel=0.03)
    assert run_threshold_from_vo2max(45) < run_threshold_from_vo2max(60)


def test_parses_garmin_profile_files():
    files = [
        ("x/139_powerZones.json", [
            {"sport": "CROSS_COUNTRY_SKIING", "functionalThresholdPower": 128.0},
            {"sport": "CYCLING", "functionalThresholdPower": 214.0},
        ]),
        ("x/139_heartRateZones.json", {
            "lactateThresholdHeartRateUsed": 175, "maxHeartRateUsed": 200,
        }),
        ("x/139_bioMetrics_latest.json", {
            "lactateThresholdSpeed": 0.4027, "lactateThresholdHeartRate": 179,
        }),
        ("x/RunRacePredictions_1.json", [
            {"timestamp": "2026-10-07T15:11:51.0", "raceTime5K": 1166, "raceTimeMarathon": 11565},
            {"timestamp": "2026-09-01T10:00:00.0", "raceTime5K": 1300, "raceTimeMarathon": 13000},
        ]),
    ]  # fmt: skip
    p = parse_profile(files)
    assert p["run_threshold_speed"] == pytest.approx(4.027)  # stored in tens of m/s
    assert p["lthr"] == 179  # the latest biometrics win over zone settings
    assert p["ftp_watts"] == 214  # cycling, not skiing
    assert p["max_hr"] == 200
    assert p["race_predictions"] == {"5k": 1166, "marathon": 11565}
    assert p["race_predictions_as_of"] == "2026-10-07"


@pytest.fixture
def db(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as s:
        yield s


def _athlete(db, **kw):
    a = Athlete(name="T", **kw)
    db.add(a)
    db.commit()
    return a


def test_thresholds_prefer_athlete_then_garmin(db):
    garmin = {"run_threshold_speed": 4.03, "ftp_watts": 214, "lthr": 179, "max_hr": 200}
    a = _athlete(db, garmin_profile=garmin)
    t, src = resolve_thresholds(db, a)
    assert (t.run_threshold_speed, t.ftp_watts, t.lthr, t.max_hr) == (4.03, 214, 179, 200)
    assert src["run"] == "Garmin lactate threshold" and src["ftp"] == "Garmin FTP"

    a.run_threshold_speed, a.ftp_watts = 4.5, 250
    t, src = resolve_thresholds(db, a)
    assert (t.run_threshold_speed, t.ftp_watts) == (4.5, 250)
    assert src["run"] == src["ftp"] == "set by athlete"


def test_thresholds_fall_back_to_vo2max_then_training(db):
    a = _athlete(db)
    db.add(WellnessDay(athlete_id=a.id, day=date.today(), vo2max=55, rest_hr=48))
    db.commit()
    t, src = resolve_thresholds(db, a)
    assert src["run"] == "Garmin VO2 max 55"
    assert t.run_threshold_speed == pytest.approx(run_threshold_from_vo2max(55))
    assert t.rest_hr == 48  # from Garmin wellness

    b = _athlete(db)  # no Garmin data at all
    t, src = resolve_thresholds(db, b)
    assert src["run"] == "default" and src["ftp"] == "default"

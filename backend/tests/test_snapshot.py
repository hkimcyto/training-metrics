import gzip
import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import demo
from app.analytics.load import TssMethod
from app.db.models import Activity, Base
from app.ingest.scoring import resolve_thresholds


def _write_snapshot(path):
    acts = []
    for i in range(12):
        day = f"2026-09-{i + 10:02d}T07:00:00"
        acts.append(
            {
                "id": f"r{i}",
                "name": "Run",
                "sport_type": "Run",
                "start_local": day,
                "trainer": False,
                "moving_s": 3600,
                "elapsed_s": 3700,
                "distance_m": 10500,
                "elev_gain_m": 50,
                "avg_speed": 2.9,
                "relative_effort": 60,
                "avg_hr": 145,
                "polyline": None,
            }
        )
        acts.append(
            {
                "id": f"b{i}",
                "name": "Ride",
                "sport_type": "Ride",
                "start_local": day.replace("07", "16"),
                "trainer": False,
                "moving_s": 7200,
                "elapsed_s": 7500,
                "distance_m": 60000,
                "elev_gain_m": 300,
                "avg_speed": 8.3,
                "relative_effort": 120,
                "avg_hr": 140 if i < 8 else None,
                "polyline": None,
            }
        )
    meta = {
        "name": "Test",
        "race_name": "IRONMAN California",
        "race_date": "2026-10-18",
        "ftp_watts": 210,
    }
    with gzip.open(path, "wt") as f:
        json.dump({"athlete": meta, "activities": acts}, f)


def test_snapshot_loads_and_calibrates_relative_effort(tmp_path, monkeypatch):
    snap = tmp_path / "athlete.json.gz"
    _write_snapshot(snap)
    eng = create_engine(f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setattr(demo, "engine", eng)
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng)() as db:
        a = demo.build_from_snapshot(db, snap)
        assert a.is_demo and a.race_name == "IRONMAN California" and a.ftp_watts == 210
        t, sources = resolve_thresholds(db, a)
        assert "calibrated" in sources["re_scale"]
        no_hr = db.scalar(select(Activity).where(Activity.external_id == "b10"))
        with_hr = db.scalar(select(Activity).where(Activity.external_id == "b2"))
        assert no_hr.tss_method == TssMethod.RELATIVE_EFFORT
        assert with_hr.tss_method == TssMethod.HEART_RATE
        # same ride, scored two ways, should land close after calibration
        assert abs(no_hr.tss - with_hr.tss) / with_hr.tss < 0.25

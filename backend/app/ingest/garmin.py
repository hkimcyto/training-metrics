"""Garmin wellness ingestion.

Garmin has no public API for individuals, so there are two routes:

1. The official account export (a ZIP of JSON files). Field names vary
   between export versions, so the parser looks for each metric under any of
   its known names instead of assuming one schema.
2. An optional live sync through the unofficial ``garminconnect`` library,
   for people who accept its trade-offs (it signs in as the user).
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Athlete, WellnessDay

log = logging.getLogger(__name__)

FIELDS: dict[str, tuple[str, ...]] = {
    "sleep_score": ("overallScore", "sleepScore", "overall_score"),
    "hrv_ms": ("lastNightAvg", "weeklyAvg", "hrvValue", "avgOvernightHrv"),
    "rest_hr": ("restingHeartRate", "currentDayRestingHeartRate", "restingHeartRateValue"),
    "body_battery_high": ("bodyBatteryHighestValue", "maxBodyBattery"),
    "body_battery_low": ("bodyBatteryLowestValue", "minBodyBattery"),
    "stress_avg": ("averageStressLevel", "avgStressLevel"),
}
SLEEP_PARTS = ("deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds")
DATE_KEYS = ("calendarDate", "sleepStartDate", "date")


def _walk(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _first_number(d: dict[str, Any], keys: Iterable[str]) -> float | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict):  # e.g. {"overall": {"value": 82}}
            v = v.get("value")
        if isinstance(v, int | float) and v > 0:
            return float(v)
    return None


def _day(rec: dict[str, Any]) -> date | None:
    for k in DATE_KEYS:
        v = rec.get(k)
        if isinstance(v, str) and len(v) >= 10:
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                continue
        if isinstance(v, dict) and isinstance(v.get("date"), str):
            return date.fromisoformat(v["date"][:10])
    return None


def _body_battery(rec: dict[str, Any]) -> dict[str, float]:
    """UDS files hold body battery as a list of typed stats."""
    out: dict[str, float] = {}
    bb = rec.get("bodyBattery")
    if isinstance(bb, dict):
        for s in bb.get("bodyBatteryStatList", []):
            t, v = s.get("bodyBatteryStatType"), s.get("statsValue")
            if t == "HIGHEST" and v is not None:
                out["body_battery_high"] = float(v)
            elif t == "LOWEST" and v is not None:
                out["body_battery_low"] = float(v)
    stress = rec.get("allDayStress")
    if isinstance(stress, dict):
        for agg in stress.get("aggregatorList", []):
            if agg.get("type") == "TOTAL" and agg.get("averageStressLevel"):
                out["stress_avg"] = float(agg["averageStressLevel"])
    return out


def _health_status(rec: dict[str, Any]) -> dict[str, float]:
    """healthStatusData files hold overnight HRV as a list of typed metrics."""
    out: dict[str, float] = {}
    metrics = rec.get("metrics")
    if isinstance(metrics, list):
        for m in metrics:
            if not isinstance(m, dict) or m.get("type") != "HRV":
                continue
            v = m.get("value")
            if isinstance(v, int | float) and v > 0:
                out["hrv_ms"] = float(v)
    return out


def parse_records(records: Iterable[Any]) -> dict[date, dict[str, float]]:
    days: dict[date, dict[str, float]] = defaultdict(dict)
    for rec in _walk(list(records)):
        d = _day(rec)
        if d is None:
            continue
        row = days[d]
        # metrics often sit in nested objects (e.g. sleepScores.overall.value)
        # that carry no date of their own, so search those too
        scopes = [rec] + [s for s in _walk(list(rec.values())) if _day(s) in (None, d)]
        for field, keys in FIELDS.items():
            if field in row:
                continue
            for scope in scopes:
                v = _first_number(scope, keys)
                if v is None and field == "sleep_score" and "overall" in scope:
                    v = _first_number(scope, ("overall",))
                if v is not None:
                    row[field] = v
                    break
        parts = [rec.get(k) for k in SLEEP_PARTS]
        if "sleep_s" not in row and any(isinstance(p, int | float) for p in parts):
            row["sleep_s"] = float(sum(p for p in parts if isinstance(p, int | float)))
        for k, v in (_body_battery(rec) | _health_status(rec)).items():
            row.setdefault(k, v)
    return {d: r for d, r in days.items() if r}


def parse_export(zip_bytes: bytes) -> dict[date, dict[str, float]]:
    """Read every wellness-looking JSON file in a Garmin export ZIP."""
    wanted = ("sleepdata", "udsfile", "healthstatus", "hrv", "wellness")
    records: list[Any] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            low = name.lower()
            if low.endswith(".json") and any(w in low for w in wanted):
                try:
                    records.append(json.loads(zf.read(name)))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    log.warning("skipping unreadable %s", name)
    return parse_records(records)


def save(
    db: Session, athlete: Athlete, days: dict[date, dict[str, float]], source: str = "garmin"
) -> int:
    existing = {
        w.day: w
        for w in db.scalars(select(WellnessDay).where(WellnessDay.athlete_id == athlete.id)).all()
    }
    for d, vals in days.items():
        row = existing.get(d) or WellnessDay(athlete_id=athlete.id, day=d)
        row.source = source
        for k, v in vals.items():
            setattr(row, k, v)
        db.add(row)
    db.commit()
    return len(days)


def live_sync(db: Session, athlete: Athlete, email: str, password: str, days: int = 14) -> int:
    """Optional: pull recent days through the unofficial garminconnect client."""
    try:
        from garminconnect import Garmin  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("install with: pip install '.[garmin]'") from e
    api = Garmin(email, password)
    api.login()
    records: list[Any] = []
    today = date.today()
    for i in range(days):
        ds = (today - timedelta(days=i)).isoformat()
        for call in (api.get_sleep_data, api.get_hrv_data, api.get_stats):
            try:
                r = call(ds)
                if isinstance(r, dict):
                    r.setdefault("calendarDate", ds)
                records.append(r)
            except Exception as e:  # noqa: BLE001
                log.info("garmin %s %s: %s", call.__name__, ds, e)
    return save(db, athlete, parse_records(records), source="garmin-live")

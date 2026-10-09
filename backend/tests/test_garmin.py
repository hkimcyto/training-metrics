import io
import json
import zipfile
from datetime import date

from app.ingest.garmin import parse_export, parse_records

SLEEP = [
    {
        "calendarDate": "2026-09-30",
        "deepSleepSeconds": 5400,
        "lightSleepSeconds": 14400,
        "remSleepSeconds": 6300,
        "sleepScores": {"overall": {"value": 84}},
    }
]
UDS = [
    {
        "calendarDate": "2026-09-30",
        "restingHeartRate": 46,
        "bodyBattery": {
            "bodyBatteryStatList": [
                {"bodyBatteryStatType": "HIGHEST", "statsValue": 91},
                {"bodyBatteryStatType": "LOWEST", "statsValue": 14},
            ]
        },
        "allDayStress": {"aggregatorList": [{"type": "TOTAL", "averageStressLevel": 24}]},
    }
]
HRV = {"hrvSummaries": [{"calendarDate": "2026-09-30", "lastNightAvg": 68, "weeklyAvg": 63}]}


def test_parses_nested_and_flat_shapes():
    d = parse_records([SLEEP, UDS, HRV])[date(2026, 9, 30)]
    assert d["sleep_s"] == 26100
    assert d["sleep_score"] == 84
    assert d["rest_hr"] == 46
    assert d["hrv_ms"] == 68  # last night, not the weekly average
    assert d["body_battery_high"] == 91 and d["body_battery_low"] == 14
    assert d["stress_avg"] == 24


def test_parses_hrv_from_health_status_metrics():
    health = [
        {
            "calendarDate": "2026-10-07",
            "metrics": [
                {"type": "HRV", "value": 70.0, "status": "IN_RANGE"},
                {"type": "HR", "value": 52.0, "status": "IN_RANGE"},
                {"type": "SKIN_TEMP_C", "status": "UNKNOWN"},
            ],
        }
    ]
    d = parse_records([health])[date(2026, 10, 7)]
    assert d["hrv_ms"] == 70
    assert "rest_hr" not in d  # overnight HR is not resting HR


def test_reads_export_zip_and_skips_activity_files():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("DI_CONNECT/DI-Connect-Wellness/2026_sleepData.json", json.dumps(SLEEP))
        z.writestr("DI_CONNECT/DI-Connect-Aggregator/UDSFile_2026.json", json.dumps(UDS))
        z.writestr(
            "DI_CONNECT/DI-Connect-Fitness/user_summarizedActivities.json",
            json.dumps([{"calendarDate": "2026-09-30", "restingHeartRate": 99}]),
        )
    days = parse_export(buf.getvalue())
    assert days[date(2026, 9, 30)]["rest_hr"] == 46

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


def test_parses_garmin_training_metrics_keeping_the_best_record_per_day():
    status = [
        {
            "calendarDate": "2026-10-07",
            "timestamp": "2026-10-07T15:11:51.0",
            "trainingStatus": "PEAKING",
            "fitnessLevelTrend": "INCREASING",
        },
        {
            "calendarDate": "2026-10-07",
            "timestamp": "2026-10-07T09:00:00.0",
            "trainingStatus": "PRODUCTIVE",
            "fitnessLevelTrend": "INCREASING",
        },
    ]
    load = [
        {
            "calendarDate": 1791331200000,
            "timestamp": 1791385911000,
            "acwrStatus": "LOW",
            "dailyTrainingLoadAcute": 714,
            "dailyTrainingLoadChronic": 1108,
        },
    ]
    vo2 = [
        {
            "calendarDate": "2026-10-07",
            "updateTimestamp": "2026-10-07T21:01:28.0",
            "sport": "CYCLING",
            "vo2MaxValue": 58.0,
        },
        {
            "calendarDate": "2026-10-07",
            "updateTimestamp": "2026-10-07T08:00:00.0",
            "sport": "RUNNING",
            "vo2MaxValue": 60.0,
        },
    ]
    readiness = [
        {
            "calendarDate": "2026-10-07",
            "timestamp": "2026-10-07T15:11:51.0",
            "inputContext": "AFTER_WAKEUP_RESET",
            "score": 41,
        },
        {
            "calendarDate": "2026-10-07",
            "timestamp": "2026-10-07T20:00:00.0",
            "inputContext": "AFTER_POST_EXERCISE_RESET",
            "score": 20,
        },
    ]
    d = parse_records([status, load, vo2, readiness])[date(2026, 10, 7)]
    assert d["training_status"] == "PEAKING" and d["fitness_trend"] == "INCREASING"
    assert (d["acute_load"], d["chronic_load"], d["load_status"]) == (714, 1108, "LOW")
    assert d["vo2max"] == 60.0  # running preferred over a later cycling value
    assert d["readiness"] == 41  # the morning reading, not the post-workout one


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

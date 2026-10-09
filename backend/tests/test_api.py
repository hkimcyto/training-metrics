import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/me",
        "/api/dashboard",
        "/api/pmc",
        "/api/race/prediction",
        "/api/training-status",
        "/api/power-curve",
        "/api/efficiency",
        "/api/calendar",
        "/api/routes",
        "/api/activities",
        "/api/wellness",
    ],
)
def test_public_endpoints_serve_demo(client, path):
    assert client.get(path).status_code == 200


def test_demo_is_read_only(client):
    assert client.patch("/api/me/settings", json={"ftp_watts": 300}).status_code == 403
    assert client.post("/api/sync").status_code == 403


def test_forecast_reaches_race_day(client):
    body = client.get("/api/pmc").json()
    fc = body["forecast"]
    assert fc["days"][-1]["day"] == fc["race_date"]
    assert fc["race_day"]["tsb"] > body["series"][-1]["tsb"]  # the taper freshens the athlete


def test_prediction_legs_add_up(client):
    legs = client.get("/api/race/prediction").json()["legs"]
    parts = sum(legs[k]["p50"] for k in ("swim", "t1", "bike", "t2", "run"))
    assert parts == pytest.approx(legs["total"]["p50"], rel=0.03)


def test_prediction_for_any_race_type(client):
    body = client.get("/api/race/prediction", params={"race": "5k"}).json()
    assert body["race_type"] == "5k" and not body["is_target"]
    assert set(body["legs"]) == {"total", "run"}
    assert client.get("/api/race/prediction", params={"race": "ultra"}).status_code == 422


def test_me_lists_race_types(client):
    keys = [r["key"] for r in client.get("/api/me").json()["race_types"]]
    assert "marathon" in keys and "olympic_tri" in keys


def test_training_status_is_estimated_without_garmin_metrics(client):
    body = client.get("/api/training-status").json()
    assert body["source"] == "estimated"
    assert body["status"] in {"PEAKING", "PRODUCTIVE", "MAINTAINING", "RECOVERY", "STRAINED"}
    assert len(body["timeline"]) == 85


def test_efficiency_points_carry_workout_details(client):
    pts = client.get("/api/efficiency").json()["points"]
    assert pts
    for k in ("id", "name", "distance_m", "moving_s", "avg_hr", "ef", "decoupling", "polyline"):
        assert k in pts[0]


def test_activity_404_for_other_ids(client):
    assert client.get("/api/activities/999999").status_code == 404


def test_webhook_verification(client):
    ok = client.get(
        "/api/webhooks/strava",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "tri-dash-verify",
            "hub.challenge": "abc",
        },
    )
    assert ok.json() == {"hub.challenge": "abc"}
    bad = client.get(
        "/api/webhooks/strava",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "abc"},
    )
    assert bad.status_code == 403

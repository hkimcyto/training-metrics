import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/me",
        "/api/dashboard",
        "/api/pmc",
        "/api/race/prediction",
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

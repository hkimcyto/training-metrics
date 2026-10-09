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
        "/api/races",
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
    assert body["race_type"] == "5k" and not body["is_target"] and body["race"] is None
    assert set(body["legs"]) == {"total", "run"}
    assert client.get("/api/race/prediction", params={"race": "ultra"}).status_code == 422


def test_forecast_without_garmin_has_no_garmin_prediction(client):
    body = client.get("/api/race/prediction", params={"race": "marathon"}).json()
    assert body["garmin_prediction"] is None
    assert body["inputs"]["sources"]["run"] != "Garmin lactate threshold"


def test_races_list_types_catalog_and_target(client):
    body = client.get("/api/races").json()
    keys = [r["key"] for r in body["race_types"]]
    assert "marathon" in keys and "olympic_tri" in keys
    assert any(c["name"] == "Boston Marathon" for c in body["catalog"])
    assert body["target_id"] == body["races"][0]["id"]
    assert client.get("/api/me").json()["target_race"]["name"] == "Fall IRONMAN (demo)"


def test_forecast_defaults_to_the_target_race(client):
    body = client.get("/api/race/prediction").json()
    assert body["is_target"] and body["race"]["name"] == "Fall IRONMAN (demo)"
    assert body["course"]["bike_climb_m"] == 1200


def test_forecast_for_a_custom_distance_run(client):
    body = client.get("/api/race/prediction", params={"race": "run", "distance_m": 15000})
    assert body.status_code == 200 and body.json()["course"]["label"] == "15 km run"
    assert client.get("/api/race/prediction", params={"race": "run"}).status_code == 422
    assert client.get("/api/race/prediction", params={"race_id": 999999}).status_code == 404


def test_demo_cannot_add_races(client):
    race = {"name": "X", "day": "2027-04-20", "race_type": "marathon"}
    assert client.post("/api/races", json=race).status_code == 403


@pytest.fixture
def owner(client):
    """The client signed in as a fresh, non-demo athlete."""
    from app.api.routes import COOKIE, _signer
    from app.config import get_settings
    from app.db.models import Athlete
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        a = Athlete(name="Owner")
        db.add(a)
        db.commit()
        aid = a.id
    client.cookies.set(COOKIE, _signer(get_settings()).dumps({"aid": aid}))
    yield client
    client.cookies.clear()


def test_owner_manages_a_race_calendar(owner):
    assert owner.get("/api/me").json()["target_race"] is None
    boston = owner.post(
        "/api/races",
        json={"name": "Boston", "day": "2099-04-20", "race_type": "marathon", "priority": "A"},
    ).json()
    tune_up = owner.post(
        "/api/races",
        json={"name": "Tune-up 15K", "day": "2099-03-01", "race_type": "run",
              "distance_m": 15000, "priority": "B"},
    ).json()  # fmt: skip
    # the A race is the target even though the B race comes first
    assert owner.get("/api/races").json()["target_id"] == boston["id"]
    fc = owner.get("/api/race/prediction", params={"race_id": tune_up["id"]}).json()
    assert fc["course"]["run_m"] == 15000 and not fc["is_target"]

    owner.patch(f"/api/races/{tune_up['id']}", json={"priority": "A"})
    assert owner.get("/api/races").json()["target_id"] == tune_up["id"]
    bad = owner.patch(f"/api/races/{tune_up['id']}", json={"distance_m": None})
    assert bad.status_code == 422  # a custom run must keep its distance

    assert owner.delete(f"/api/races/{tune_up['id']}").status_code == 204
    assert [r["name"] for r in owner.get("/api/races").json()["races"]] == ["Boston"]


def test_owner_cannot_touch_someone_elses_race(owner):
    from sqlalchemy import select

    from app.db.models import Athlete, Race
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        demo = db.scalar(select(Athlete).where(Athlete.is_demo.is_(True)))
        other = db.scalar(select(Race.id).where(Race.athlete_id == demo.id))
    assert owner.patch(f"/api/races/{other}", json={"name": "mine"}).status_code == 404
    assert owner.delete(f"/api/races/{other}").status_code == 404
    assert owner.get("/api/race/prediction", params={"race_id": other}).status_code == 404


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

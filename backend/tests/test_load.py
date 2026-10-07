import numpy as np
import pytest

from app.analytics.load import (
    Sport,
    Thresholds,
    TssMethod,
    WorkoutSummary,
    grade_adjusted_speed,
    hr_tss,
    normalized_power,
    power_tss,
    run_tss,
    score,
    swim_tss,
)

T = Thresholds(
    ftp_watts=200, run_threshold_speed=4.0, css_speed=1.0, lthr=165, max_hr=190, rest_hr=50
)


def test_one_hour_at_ftp_is_100():
    assert power_tss(3600, 200, 200).tss == pytest.approx(100)


def test_np_of_steady_ride_equals_average():
    assert normalized_power(np.full(3600, 180.0)) == pytest.approx(180)


def test_np_exceeds_average_for_intervals():
    w = np.tile(np.r_[np.full(60, 300.0), np.full(60, 100.0)], 30)
    assert normalized_power(w) > w.mean() * 1.1


def test_run_hour_at_threshold_is_100():
    assert run_tss(3600, 4.0, 4.0).tss == pytest.approx(100)


def test_swim_uses_cubed_intensity():
    easy, hard = swim_tss(3600, 3600 * 0.9, 1.0), swim_tss(3600, 3600 * 1.1, 1.0)
    assert hard.tss / easy.tss == pytest.approx((1.1 / 0.9) ** 3)


def test_hr_tss_hour_at_lthr_is_100():
    assert hr_tss(3600, 165, T).tss == pytest.approx(100)


def test_uphill_running_counts_as_faster():
    flat = grade_adjusted_speed(np.array([3.0]), np.array([0.0]))[0]
    up = grade_adjusted_speed(np.array([3.0]), np.array([8.0]))[0]
    assert flat == pytest.approx(3.0)
    assert up > 3.5


@pytest.mark.parametrize(
    "workout,method",
    [
        (WorkoutSummary(Sport.BIKE, 3600, avg_watts=150, device_watts=True), TssMethod.POWER),
        (WorkoutSummary(Sport.BIKE, 3600, avg_hr=130), TssMethod.HEART_RATE),
        (WorkoutSummary(Sport.RUN, 3600, distance_m=10_000), TssMethod.PACE),
        (WorkoutSummary(Sport.SWIM, 3000, distance_m=2500), TssMethod.SWIM_PACE),
        (WorkoutSummary(Sport.STRENGTH, 3600), TssMethod.DURATION),
    ],
)
def test_score_picks_best_available_method(workout, method):
    assert score(workout, T).method is method

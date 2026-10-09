from app.analytics.status import classify


def test_building_fitness_is_productive():
    assert classify(ctl_change_28d=8, ctl=80, tsb=-10, acwr=1.1, hrv_low_nights=0) == "PRODUCTIVE"


def test_flat_fitness_is_maintaining():
    assert classify(ctl_change_28d=1, ctl=80, tsb=-5, acwr=1.0, hrv_low_nights=0) == "MAINTAINING"


def test_taper_after_a_build_is_peaking():
    assert classify(ctl_change_28d=6, ctl=90, tsb=12, acwr=0.75, hrv_low_nights=0) == "PEAKING"


def test_suppressed_hrv_or_deep_fatigue_is_strained():
    assert classify(ctl_change_28d=8, ctl=80, tsb=-10, acwr=1.1, hrv_low_nights=3) == "STRAINED"
    assert classify(ctl_change_28d=8, ctl=80, tsb=-35, acwr=1.4, hrv_low_nights=0) == "STRAINED"


def test_backing_off_is_recovery_then_detraining():
    assert classify(ctl_change_28d=-2, ctl=80, tsb=10, acwr=0.75, hrv_low_nights=0) == "RECOVERY"
    assert classify(ctl_change_28d=-12, ctl=70, tsb=20, acwr=0.6, hrv_low_nights=0) == "DETRAINING"


def test_no_training_has_no_status():
    assert classify(ctl_change_28d=0, ctl=2, tsb=0, acwr=None, hrv_low_nights=0) == "NO_STATUS"

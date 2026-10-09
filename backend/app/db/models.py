from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(primary_key=True)
    strava_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String(120))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    measurement: Mapped[str] = mapped_column(String(10), default="imperial")

    access_token: Mapped[str | None] = mapped_column(String(255))
    refresh_token: Mapped[str | None] = mapped_column(String(255))
    token_expires_at: Mapped[int | None] = mapped_column(Integer)

    weight_kg: Mapped[float] = mapped_column(Float, default=75.0)
    sex: Mapped[str] = mapped_column(String(1), default="M")
    ftp_watts: Mapped[float | None] = mapped_column(Float)
    run_threshold_speed: Mapped[float | None] = mapped_column(Float)
    css_speed: Mapped[float | None] = mapped_column(Float)
    lthr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    rest_hr: Mapped[float | None] = mapped_column(Float)

    # thresholds and race predictions read from a Garmin export
    garmin_profile: Mapped[dict | None] = mapped_column(JSON)

    race_name: Mapped[str | None] = mapped_column(String(120))
    race_date: Mapped[date | None] = mapped_column(Date)
    race_type: Mapped[str] = mapped_column(String(16), default="ironman", server_default="ironman")
    race_climb_m: Mapped[float] = mapped_column(Float, default=1500)
    race_wetsuit: Mapped[bool] = mapped_column(Boolean, default=True)
    race_temp_c: Mapped[float] = mapped_column(Float, default=22)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_state: Mapped[str] = mapped_column(String(16), default="idle", server_default="idle")
    sync_message: Mapped[str | None] = mapped_column(String(255))
    sync_done: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sync_total: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sync_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    activities: Mapped[list[Activity]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("athlete_id", "source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(64))

    name: Mapped[str] = mapped_column(String(255))
    sport: Mapped[str] = mapped_column(String(16), index=True)
    sport_type: Mapped[str] = mapped_column(String(40))
    start_time: Mapped[datetime] = mapped_column(DateTime)
    day: Mapped[date] = mapped_column(Date, index=True)
    trainer: Mapped[bool] = mapped_column(Boolean, default=False)

    moving_s: Mapped[float] = mapped_column(Float)
    elapsed_s: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[float] = mapped_column(Float, default=0)
    elev_gain_m: Mapped[float] = mapped_column(Float, default=0)
    avg_speed: Mapped[float | None] = mapped_column(Float)
    graded_speed: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    avg_watts: Mapped[float | None] = mapped_column(Float)
    np_watts: Mapped[float | None] = mapped_column(Float)
    device_watts: Mapped[bool] = mapped_column(Boolean, default=False)
    relative_effort: Mapped[float | None] = mapped_column(Float)

    tss: Mapped[float] = mapped_column(Float, default=0)
    tss_method: Mapped[str] = mapped_column(String(16), default="duration")
    intensity: Mapped[float | None] = mapped_column(Float)
    ef: Mapped[float | None] = mapped_column(Float)
    decoupling_pct: Mapped[float | None] = mapped_column(Float)
    power_curve: Mapped[dict | None] = mapped_column(JSON)
    polyline: Mapped[str | None] = mapped_column(Text)
    has_streams: Mapped[bool] = mapped_column(Boolean, default=False)

    athlete: Mapped[Athlete] = relationship(back_populates="activities")


class WellnessDay(Base):
    __tablename__ = "wellness_days"
    __table_args__ = (UniqueConstraint("athlete_id", "day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(
        ForeignKey("athletes.id", ondelete="CASCADE"), index=True
    )
    day: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(16), default="garmin")
    sleep_s: Mapped[float | None] = mapped_column(Float)
    sleep_score: Mapped[float | None] = mapped_column(Float)
    hrv_ms: Mapped[float | None] = mapped_column(Float)
    rest_hr: Mapped[float | None] = mapped_column(Float)
    body_battery_high: Mapped[float | None] = mapped_column(Float)
    body_battery_low: Mapped[float | None] = mapped_column(Float)
    stress_avg: Mapped[float | None] = mapped_column(Float)
    # Garmin's own training metrics, when the export includes them
    training_status: Mapped[str | None] = mapped_column(String(24))
    fitness_trend: Mapped[str | None] = mapped_column(String(16))
    vo2max: Mapped[float | None] = mapped_column(Float)
    acute_load: Mapped[float | None] = mapped_column(Float)
    chronic_load: Mapped[float | None] = mapped_column(Float)
    load_status: Mapped[str | None] = mapped_column(String(16))
    readiness: Mapped[float | None] = mapped_column(Float)

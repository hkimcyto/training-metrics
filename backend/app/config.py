from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tri.db"
    secret_key: str = "dev-only-change-me"
    frontend_url: str = "http://localhost:5173"
    api_url: str = "http://localhost:8000"

    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_webhook_verify_token: str = "tri-dash-verify"
    # how many recent activities get full streams (Strava allows 1,000 requests a day)
    strava_stream_backfill: int = 150

    garmin_email: str = ""
    garmin_password: str = ""

    demo_mode: bool = True
    sync_interval_minutes: int = 60

    @property
    def strava_redirect_uri(self) -> str:
        return f"{self.api_url}/api/auth/strava/callback"

    @property
    def strava_enabled(self) -> bool:
        return bool(self.strava_client_id and self.strava_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()

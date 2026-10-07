"""Strava API client: OAuth, activity listing, streams and webhooks.

Strava allows 200 requests per 15 minutes and 2,000 a day per app (100/1,000
for read endpoints). The client reads the rate-limit headers and backs off on
429 instead of failing the whole sync.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings

API = "https://www.strava.com/api/v3"
OAUTH = "https://www.strava.com/oauth"
STREAM_KEYS = [
    "time",
    "watts",
    "heartrate",
    "velocity_smooth",
    "grade_smooth",
    "distance",
    "moving",
]


class StravaError(RuntimeError):
    pass


@dataclass
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: int
    athlete: dict[str, Any] | None = None


def authorize_url(settings: Settings, state: str) -> str:
    q = {
        "client_id": settings.strava_client_id,
        "redirect_uri": settings.strava_redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read,activity:read_all,profile:read_all",
        "state": state,
    }
    return f"{OAUTH}/authorize?{urlencode(q)}"


class StravaClient:
    def __init__(self, settings: Settings, tokens: Tokens, http: httpx.Client | None = None):
        self.settings = settings
        self.tokens = tokens
        self.http = http or httpx.Client(timeout=30)
        self.on_refresh: Any = None  # callback(Tokens) so the caller can persist new tokens

    # ------------------------------------------------------------------ oauth
    @staticmethod
    def exchange_code(settings: Settings, code: str, http: httpx.Client | None = None) -> Tokens:
        http = http or httpx.Client(timeout=30)
        r = http.post(
            f"{OAUTH}/token",
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        if r.status_code != 200:
            raise StravaError(f"token exchange failed: {r.status_code} {r.text}")
        j = r.json()
        return Tokens(j["access_token"], j["refresh_token"], j["expires_at"], j.get("athlete"))

    def _refresh_if_needed(self) -> None:
        if self.tokens.expires_at - 300 > time.time():
            return
        r = self.http.post(
            f"{OAUTH}/token",
            data={
                "client_id": self.settings.strava_client_id,
                "client_secret": self.settings.strava_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.tokens.refresh_token,
            },
        )
        if r.status_code != 200:
            raise StravaError(f"token refresh failed: {r.status_code}")
        j = r.json()
        self.tokens = Tokens(j["access_token"], j["refresh_token"], j["expires_at"])
        if self.on_refresh:
            self.on_refresh(self.tokens)

    # --------------------------------------------------------------- requests
    def _get(self, path: str, params: dict[str, Any] | None = None, retries: int = 3) -> Any:
        self._refresh_if_needed()
        for attempt in range(retries + 1):
            r = self.http.get(
                f"{API}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self.tokens.access_token}"},
            )
            if r.status_code == 429 and attempt < retries:
                # wait for the next 15-minute window boundary, capped for interactive use
                time.sleep(min(60 * (attempt + 1), 180))
                continue
            if r.status_code == 404:
                return None
            if r.status_code >= 400:
                raise StravaError(f"GET {path} -> {r.status_code}: {r.text[:200]}")
            return r.json()
        raise StravaError(f"rate limited on {path}")

    def athlete(self) -> dict[str, Any]:
        return self._get("/athlete")

    def zones(self) -> dict[str, Any] | None:
        return self._get("/athlete/zones")

    def activities(self, after: int | None = None, per_page: int = 100) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            params: dict[str, Any] = {"page": page, "per_page": per_page}
            if after:
                params["after"] = after
            batch = self._get("/athlete/activities", params) or []
            yield from batch
            if len(batch) < per_page:
                return
            page += 1

    def activity(self, activity_id: int | str) -> dict[str, Any] | None:
        return self._get(f"/activities/{activity_id}")

    def streams(self, activity_id: int | str) -> dict[str, list[Any]]:
        data = self._get(
            f"/activities/{activity_id}/streams",
            {"keys": ",".join(STREAM_KEYS), "key_by_type": "true"},
        )
        if not data:
            return {}
        return {k: v.get("data", []) for k, v in data.items()}

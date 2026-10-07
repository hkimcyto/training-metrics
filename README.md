# Tri Dash

**Ironman training analytics.** Tri Dash pulls workouts from Strava and recovery data from Garmin. It scores every session on one training-stress scale and fits a fitness-fatigue model to the athlete's own data. From that model it searches for the best taper, then simulates race day thousands of times to predict a finish time with a realistic range.

![Training load and taper](docs/screenshots/load-light.png)

| | |
|---|---|
| ![Overview](docs/screenshots/overview-light.png) | ![Race forecast](docs/screenshots/race-light.png) |
| ![Performance](docs/screenshots/performance-dark.png) | ![Recovery](docs/screenshots/wellness-dark.png) |

## What it does

| Area | Details |
|---|---|
| **Ingestion** | Strava OAuth, full-history backfill, incremental sync and real-time webhooks (create, update, delete, deauthorize). Token refresh and rate-limit backoff are handled. Garmin wellness comes from the official account export (ZIP), with an optional live sync. |
| **Training stress** | Each workout is scored by the most accurate method its data allows: power TSS from Normalized Power, rTSS from grade-adjusted pace (Minetti cost-of-running model), sTSS from swim pace (cubed intensity), hrTSS from Banister TRIMP, or duration as a fallback. |
| **Fitness, fatigue, form** | Exponentially weighted 42/7-day load, ramp rate and acute:chronic workload ratio. |
| **Personal response model** | A Banister impulse-response model fitted to the athlete's aerobic-efficiency markers by regularised non-linear least squares. With a short history it falls back to population constants. |
| **Taper optimiser** | A grid search over taper length and depth, with each candidate scored by the fitted model's predicted race-day performance. |
| **Race prediction** | A Monte Carlo simulation of 6,000 races. The swim comes from Critical Swim Speed. The bike comes from a physics energy balance (aero drag, rolling resistance, climbing, drivetrain loss). The run comes from threshold pace scaled by a durability factor and heat. Output is the P10/P50/P90 range for each leg. |
| **Performance** | Mean-maximal power curve with a Critical Power / W′ fit, Efficiency Factor trends and aerobic decoupling. |
| **Routes** | A layered map of every outdoor ride and run, decoded from Strava polylines. |
| **Recovery** | HRV against a rolling 60-day baseline, resting HR, sleep, Body Battery, and the correlation between yesterday's load and this morning's HRV. |

## Architecture

```mermaid
flowchart LR
  subgraph Sources
    S[Strava API]
    G[Garmin export ZIP / garminconnect]
  end
  subgraph API["FastAPI service"]
    I[ingest/: OAuth, sync, webhooks, Garmin parser]
    A[analytics/: pure NumPy/SciPy models]
    SV[services.py: read models]
    R[api/routes.py]
  end
  DB[(Postgres)]
  W[React + TypeScript SPA]

  S -- OAuth + REST --> I
  S -- webhook events --> R
  G --> I
  I --> DB
  DB --> SV
  A --> SV
  SV --> R
  R -- JSON --> W
```

* **`backend/app/analytics/`** holds pure functions with no I/O. Each model is unit-tested against known values: Coggan's 1 h at FTP = 100 TSS, Google's polyline example, and parameter recovery from synthetic data for the Banister and Critical Power fits.
* **`backend/app/ingest/`** talks to Strava and Garmin. These tests run the real sync code against a mocked Strava API (`respx`), covering token refresh, 429 retries, idempotent upserts and webhook events.
* **`backend/app/services.py`** builds every view the UI needs from stored activities, so the HTTP layer stays thin.
* **`frontend/`** is a React 19 app with TanStack Query, Recharts and Leaflet. In production FastAPI serves the built app, so one container serves everything and the session cookie stays first-party.

## The models, briefly

**Training Stress Score.** `TSS = hours × IF² × 100`, where IF is intensity relative to threshold. Normalized Power (30 s rolling mean, 4th-power average) weights surges the way the body feels them. Swimming uses IF³ because drag rises with the square of speed.

**Banister model.** Performance is modelled as `p(t) = p₀ + k₁·Σ w(s)e^{−(t−s)/τ₁} − k₂·Σ w(s)e^{−(t−s)/τ₂}`. The kernel sums are computed recursively in O(n). The fit uses a soft-L1 loss and a prior pulling parameters toward (k₁, k₂, τ₁, τ₂) = (1, 2, 42, 7), and it is rejected if fatigue would outlast fitness (τ₂ ≥ τ₁).

**Bike leg.** The bike time T is solved with Brent's method from
`P·η·T = (½ρ·CdA·v³ + Crr·m·g·v)·T + m·g·H·(1 − r)`, where `v = D/T`.
CdA, Crr and race-day intensity are drawn from distributions in each simulation.

**Critical Power.** Work against time is linear (`W = CP·t + W′`), so CP and W′ come from ordinary least squares on the 2–20 minute bests.

## Running it

```bash
cp .env.example .env            # add Strava API credentials to use real data
make install                    # Python venv (uv) + npm install
make demo                       # seed the demo athlete
make api                        # FastAPI on :8000
make web                        # Vite on :5173, proxying /api
```

Or run it with Docker and Postgres:

```bash
docker compose up --build       # http://localhost:8000
```

To use your own Strava data, create an API app at <https://www.strava.com/settings/api>, set its callback domain to your host, and put the client ID and secret in `.env`. To receive webhooks, register a subscription pointing at `https://<host>/api/webhooks/strava`.

## Tests and CI

```bash
make test    # pytest (52 tests, ~85% coverage) + vitest
make lint    # ruff, tsc, oxlint, prettier
```

GitHub Actions runs linting, type checks and both test suites. It also applies the Alembic migrations to a real Postgres service container and builds the Docker image.

## Deploying

`render.yaml` defines the web service and a Postgres database for Render Blueprints. Any Docker host works: run the image with `DATABASE_URL`, `SECRET_KEY` and the Strava settings. On start, the container runs migrations and seeds the demo athlete if one doesn't exist.

## Data and privacy

The public site serves a synthetic demo athlete. Its data is generated by `app/demo.py` from a hidden Banister model, so the fitting code has a real signal to recover. Connected athletes only ever see their own data, and the demo athlete is read-only. Strava tokens are stored server-side and cleared when the athlete revokes access.

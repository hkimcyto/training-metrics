"""Turn raw Strava API exports into the public demo snapshot.

Input:  a directory of /athlete/activities pages (JSON), plus optional
        per-activity detail files (average HR/power and power curves) and
        down-sampled heart-rate/speed streams.
Output: backend/app/fixtures/athlete.json.gz

Privacy: route polylines are trimmed by 500 m at each end so start and finish
points (usually home) are never published, and virtual-ride "routes" (Zwift
world coordinates) are dropped.

    python tools/build_snapshot.py RAW_DIR --name "First L." --since 2026-01-06
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.analytics.polyline import decode, encode  # noqa: E402

KEEP = {
    "Run",
    "TrailRun",
    "Ride",
    "VirtualRide",
    "GravelRide",
    "Swim",
    "OpenWaterSwim",
    "WeightTraining",
    "Workout",
}
TRIM_M = 500.0


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6_371_000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def trim(encoded: str) -> str | None:
    pts = decode(encoded)
    if len(pts) < 4:
        return None
    start, end = pts[0], pts[-1]
    kept = [p for p in pts if haversine(p, start) > TRIM_M and haversine(p, end) > TRIM_M]
    return encode(kept) if len(kept) >= 4 else None


def load_pages(raw: Path) -> list[dict]:
    acts: dict[str, dict] = {}
    for f in sorted(raw.glob("p*.json")):
        d = json.loads(f.read_text())
        if isinstance(d, list):
            d = json.loads(d[0]["text"])
        for a in d["activities"]:
            acts[a["id"]] = a
    return list(acts.values())


def stream_metrics(s: dict) -> dict:
    """EF and decoupling from a down-sampled HR + speed stream. Samples where
    the athlete was stopped (speed under 2 m/s) are ignored."""
    pairs = [
        (h, v)
        for h, v in zip(s["hr"][1:], s["x"][1:], strict=False)
        if h and v and v > 2.0 and h > 90
    ]
    if len(pairs) < 10:
        return {}
    hr = sum(h for h, _ in pairs) / len(pairs)
    sp = sum(v for _, v in pairs) / len(pairs)
    half = len(pairs) // 2

    def ef(ps: list[tuple[float, float]]) -> float:
        return (sum(v for _, v in ps) / len(ps)) / (sum(h for h, _ in ps) / len(ps))

    e1, e2 = ef(pairs[:half]), ef(pairs[half:])
    return {"hr": hr, "ef": sp * 60 / hr, "decoupling": (e1 - e2) / e1 * 100}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--since", default="2000-01-01")
    ap.add_argument("--meta", type=Path, help="JSON file with athlete settings (race, weight, FTP)")
    ap.add_argument("--trust-trainer-power", action="store_true")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "backend/app/fixtures/athlete.json.gz",
    )
    args = ap.parse_args()

    out = []
    for a in sorted(load_pages(args.raw), key=lambda x: x["start_local"]):
        if a["sport_type"] not in KEEP or a["start_local"] < args.since:
            continue
        s = a["summary"]
        row = {
            "id": a["id"],
            "name": a["name"],
            "sport_type": a["sport_type"],
            "start_local": a["start_local"],
            "trainer": bool(a.get("is_trainer")) or a["sport_type"] == "VirtualRide",
            "moving_s": s["moving_time"],
            "elapsed_s": s["elapsed_time"],
            "distance_m": s["distance"],
            "elev_gain_m": s.get("elevation_gain") or 0,
            "avg_speed": s.get("avg_speed") or None,
            "relative_effort": s.get("relative_effort"),
            "polyline": None,
        }
        if a.get("reduced_polyline") and a["sport_type"] != "VirtualRide":
            row["polyline"] = trim(a["reduced_polyline"])
        perf = args.raw / "perf" / f"{a['id']}.json"
        if perf.exists():
            p = json.loads(perf.read_text())
            if p.get("hr") and p["hr"] > 60:
                row["avg_hr"] = p["hr"]
            if p.get("dw") and p.get("w"):
                # Trainer power is kept for the power curve and efficiency trend,
                # but not used for TSS when --trust-trainer-power is off: smart
                # trainers often read differently from outdoor power.
                row["avg_watts"], row["device_watts"] = p["w"], args.trust_trainer_power
                row["power_curve"] = {str(k): float(v) for k, v in p.get("curve", {}).items()}
        st = args.raw / "streams" / f"{a['id']}.json"
        if st.exists():
            m = stream_metrics(json.loads(st.read_text()))
            if m:
                row.setdefault("avg_hr", m["hr"])
                row["ef"], row["decoupling_pct"] = m["ef"], m["decoupling"]
        out.append(row)

    meta = {"name": args.name, **(json.loads(args.meta.read_text()) if args.meta else {})}
    payload = {"athlete": meta, "activities": out}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt") as f:
        json.dump(payload, f, separators=(",", ":"))
    routes = sum(1 for r in out if r["polyline"])
    print(f"wrote {len(out)} activities ({routes} with routes) to {args.out}")


if __name__ == "__main__":
    main()

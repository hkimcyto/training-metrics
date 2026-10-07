"""Google encoded-polyline decoding (the format Strava uses for route maps),
plus a coarse grid that turns many routes into a heatmap."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable


def decode(encoded: str, precision: int = 5) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    index = lat = lng = 0
    factor = 10**precision
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lng += deltas[1]
        coords.append((lat / factor, lng / factor))
    return coords


def encode(coords: Iterable[tuple[float, float]], precision: int = 5) -> str:
    factor = 10**precision
    out: list[str] = []
    prev_lat = prev_lng = 0
    for lat, lng in coords:
        ilat, ilng = round(lat * factor), round(lng * factor)
        for d in (ilat - prev_lat, ilng - prev_lng):
            v = ~(d << 1) if d < 0 else d << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev_lat, prev_lng = ilat, ilng
    return "".join(out)


def heat_grid(
    routes: Iterable[list[tuple[float, float]]], cell_deg: float = 0.0015
) -> list[tuple[float, float, int]]:
    """Count how many distinct routes pass through each ~150 m cell."""
    counts: Counter[tuple[int, int]] = Counter()
    for route in routes:
        cells = {(int(lat / cell_deg), int(lng / cell_deg)) for lat, lng in route}
        counts.update(cells)
    return [((i + 0.5) * cell_deg, (j + 0.5) * cell_deg, c) for (i, j), c in counts.items()]

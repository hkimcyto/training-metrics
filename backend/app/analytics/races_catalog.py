# ruff: noqa: E501  (a data table reads best one race per line)
"""Well-known races to start from when adding one to the calendar.

Course details stay roughly the same year to year, so they live here; race
dates move, so the athlete enters the date. Climbing and temperature are
rounded typical values, meant to be edited when the athlete knows better.
`climb_m` is bike-course climbing and only matters for triathlons.
"""

from __future__ import annotations

from typing import Any

_ROWS = [
    # key, name, type, location, month, temp °C, bike climbing m, wetsuit legal
    ("boston", "Boston Marathon", "marathon", "Boston, MA", "April", 12),
    ("nyc", "New York City Marathon", "marathon", "New York, NY", "November", 12),
    ("chicago", "Chicago Marathon", "marathon", "Chicago, IL", "October", 14),
    ("berlin", "Berlin Marathon", "marathon", "Berlin, Germany", "September", 15),
    ("london", "London Marathon", "marathon", "London, UK", "April", 13),
    ("tokyo", "Tokyo Marathon", "marathon", "Tokyo, Japan", "March", 10),
    ("cim", "California International Marathon", "marathon", "Sacramento, CA", "December", 8),
    ("la", "Los Angeles Marathon", "marathon", "Los Angeles, CA", "March", 17),
    ("nyc_half", "NYC Half", "half_marathon", "New York, NY", "March", 8),
    ("brooklyn_half", "Brooklyn Half", "half_marathon", "Brooklyn, NY", "May", 16),
    ("sf_half", "San Francisco Half Marathon", "half_marathon", "San Francisco, CA", "July", 14),
    ("im_california", "IRONMAN California", "ironman", "Sacramento, CA", "October", 25, 500, True),
    ("im_kona", "IRONMAN World Championship (Kona)", "ironman", "Kailua-Kona, HI", "October", 30, 1700, False),
    ("im_arizona", "IRONMAN Arizona", "ironman", "Tempe, AZ", "November", 22, 600, True),
    ("roth", "Challenge Roth", "ironman", "Roth, Germany", "July", 25, 1400, True),
    ("oceanside", "IRONMAN 70.3 Oceanside", "half_ironman", "Oceanside, CA", "April", 18, 900, True),
    ("santa_cruz", "IRONMAN 70.3 Santa Cruz", "half_ironman", "Santa Cruz, CA", "September", 18, 700, True),
    ("nyc_tri", "New York City Triathlon", "olympic_tri", "New York, NY", "July", 27, 300, True),
]  # fmt: skip

CATALOG: list[dict[str, Any]] = [
    {
        "key": row[0],
        "name": row[1],
        "race_type": row[2],
        "location": row[3],
        "month": row[4],
        "temp_c": row[5],
        "climb_m": row[6] if len(row) > 6 else None,
        "wetsuit": row[7] if len(row) > 7 else True,
    }
    for row in _ROWS
]

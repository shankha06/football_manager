"""Shared utility functions."""
from __future__ import annotations

import random
from typing import Sequence


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def weighted_random_choice(items: Sequence, weights: Sequence[float]):
    """Pick one item using the given probability weights."""
    return random.choices(items, weights=weights, k=1)[0]


def round_robin_schedule(teams: list[int]) -> list[list[tuple[int, int]]]:
    """Generate a full home-and-away round-robin schedule.

    Returns a list of matchdays, each containing (home, away) tuples.
    Uses the standard circle method.
    """
    n = len(teams)
    if n % 2 == 1:
        teams = teams + [-1]  # bye placeholder
        n += 1

    half = n // 2
    schedule_first_half: list[list[tuple[int, int]]] = []
    rotation = list(teams)

    for _ in range(n - 1):
        matchday: list[tuple[int, int]] = []
        for i in range(half):
            home = rotation[i]
            away = rotation[n - 1 - i]
            if home == -1 or away == -1:
                continue
            matchday.append((home, away))
        schedule_first_half.append(matchday)
        # rotate: fix first element, rotate the rest
        rotation = [rotation[0]] + [rotation[-1]] + rotation[1:-1]

    # Second half: reverse home/away
    schedule_second_half = [
        [(away, home) for home, away in md] for md in schedule_first_half
    ]

    return schedule_first_half + schedule_second_half


def avg_attributes(player, attrs: list[str]) -> float:
    """Return the average of the given attribute names on a player object."""
    total = sum(getattr(player, a, 50) for a in attrs)
    return total / max(len(attrs), 1)


def zone_distance(z1: tuple[int, int], z2: tuple[int, int]) -> float:
    """Manhattan distance between two pitch zones (col, row)."""
    return abs(z1[0] - z2[0]) + abs(z1[1] - z2[1])


def format_currency(amount_millions: float) -> str:
    """Pretty-print a monetary amount in millions."""
    if amount_millions >= 1.0:
        return f"€{amount_millions:.1f}M"
    return f"€{amount_millions * 1000:.0f}K"


def format_wage(weekly: float) -> str:
    """Pretty-print weekly wage."""
    if weekly >= 1.0:
        return f"€{weekly:.0f}K/w"
    return f"€{weekly * 1000:.0f}/w"


def ordinal(n: int) -> str:
    """Convert integer to ordinal string (1 -> '1st', 2 -> '2nd', etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

"""Pure functions for football fixture input, expected value, and shortlist ranking."""
from __future__ import annotations

from datetime import date, datetime
from itertools import combinations
from math import prod
import re


def parse_matches(text: str, fallback_date: str = "") -> list[dict]:
    """One game per line: Home - Away | YYYY-MM-DD [HH:MM].

    Supports Persian dashes and English vs, skips duplicate lines and comments.
    A date must be supplied per-line or through fallback_date.
    """
    matches = []
    seen = set()
    sep = re.compile(r"\s+(?:vs\.?|v\.?|[-–—−]|مقابل)\s+", re.IGNORECASE)
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        teams = sep.split(parts[0], maxsplit=1)
        if len(teams) != 2 or not all(teams):
            raise ValueError(f"Line {line_number}: invalid team format. Example: Barcelona - Inter")
        home, away = teams
        if home.casefold() == away.casefold():
            raise ValueError(f"Line {line_number}: home and away teams must be different.")
        fixture_date = parts[1] if len(parts) >= 2 and parts[1] else fallback_date
        if not fixture_date:
            raise ValueError(f"Line {line_number}: match date is missing.")
        try:
            # First ten chars must be an ISO date.
            date.fromisoformat(fixture_date[:10])
            if len(fixture_date) > 10:
                datetime.strptime(fixture_date, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise ValueError(f"Line {line_number}: use YYYY-MM-DD or YYYY-MM-DD HH:MM.") from exc
        key = (home.casefold(), away.casefold(), fixture_date)
        if key not in seen:
            seen.add(key)
            matches.append({"home": home, "away": away, "kickoff": fixture_date})
    if len(matches) > 40:
        raise ValueError("Maximum 40 matches per input to control API expenses.")
    return matches


def capped_score(scores: dict | None) -> int:
    if not isinstance(scores, dict):
        return 0
    keys = ("form", "home_away", "availability", "tactics", "data_quality")
    total = 0
    for key in keys:
        try:
            value = int(scores.get(key, 0))
        except (ValueError, TypeError):
            value = 0
        total += max(0, min(5, value))
    return total


def expected_value(decimal_odds: float, probability_pct: float) -> float | None:
    """Return expected net return per unit for BINARY markets (no push/half win)."""
    try:
        odd, p = float(decimal_odds), float(probability_pct)
    except (TypeError, ValueError):
        return None
    if odd <= 1 or not 0 <= p <= 100:
        return None
    return (p / 100) * odd - 1


def shortlist(rows: list[dict], *, min_odd: float = 1.65,
              max_odd: float = 1.95, min_score: int = 20,
              min_ev: float = 0.03, max_count: int = 8) -> list[dict]:
    qualified = []
    for row in rows:
        if not row.get("verified", False):
            continue
        if not row.get("market") or row.get("market_type", "binary") != "binary":
            continue
        try:
            odds = float(row.get("odds") or 0)
            probability = float(row.get("probability_pct") or 0)
            score = int(row.get("score", 0))
        except (ValueError, TypeError):
            continue
        ev = expected_value(odds, probability)
        if ev is None:
            continue
        if min_odd <= odds <= max_odd and score >= min_score and ev >= min_ev:
            qualified.append({**row, "ev": ev})
    return sorted(qualified, key=lambda r: (r["ev"], r["score"]), reverse=True)[:max_count]


def combos_in_range(rows: list[dict], min_total: float = 2, max_total: float = 3,
                    max_legs: int = 3) -> list[dict]:
    """Optional candidates only; independence/correlation must be reviewed manually."""
    combo_rows = []
    for size in range(2, min(max_legs, len(rows)) + 1):
        for combo in combinations(rows, size):
            total = prod(float(row["odds"]) for row in combo)
            if min_total <= total <= max_total:
                combo_rows.append({"games": [row["game"] for row in combo],
                                   "markets": [row["market"] for row in combo],
                                   "odds": round(total, 2),
                                   "legs": size})
    return sorted(combo_rows, key=lambda r: (r["legs"], r["odds"]))


def flatten_row(row: dict) -> dict:
    """Export-friendly record; no secrets included."""
    return {key: row.get(key) for key in (
        "game", "kickoff", "verified", "status", "competition", "market",
        "market_type", "odds", "probability_pct", "score", "ev", "rationale",
        "risks", "sources"
    )}


def parse_vertical_schedule(text: str, fallback_date: str) -> list[dict]:
    """Accept the copied three-line format: home / HH:MM / away.

    Common non-fixture section headings are skipped, but malformed lines are rejected
    rather than silently mis-pairing teams.
    """
    headings = {
        "اروپا", "لیگ قهرمانان", "لیگ قهرمانان اروپا", "امشب", "فردا",
        "فرداشب", "صبح", "uefa champions league", "champions league",
    }
    lines = [x.strip() for x in text.splitlines() if x.strip() and not x.strip().startswith("#")]
    lines = [line for line in lines if line.casefold() not in headings]
    if not lines or len(lines) % 3 != 0:
        raise ValueError("For three-line input, each match needs: home team, kickoff time, away team.")
    clock_pattern = re.compile(r"^(?:[01]?\d|2[0-3]):[0-5]\d$")
    out = []
    for i in range(0, len(lines), 3):
        home, clock, away = lines[i:i+3]
        if not clock_pattern.fullmatch(clock):
            raise ValueError(f"Invalid kickoff time for match {i // 3 + 1}: {clock}")
        if not home or not away or home.casefold() == away.casefold():
            raise ValueError("Invalid team name(s) in one of the fixtures.")
        out.append(f"{home} - {away} | {fallback_date} {clock}")
    return parse_matches("\n".join(out), fallback_date=fallback_date)


def parse_schedule(text: str, fallback_date: str = "") -> list[dict]:
    """Handle both one-line fixtures and copied 3-line schedules."""
    if not text.strip():
        return []
    try:
        return parse_matches(text, fallback_date)
    except ValueError as normal_error:
        if not fallback_date:
            raise normal_error
        try:
            return parse_vertical_schedule(text, fallback_date)
        except ValueError:
            raise normal_error


def risk_tier(row: dict) -> str | None:
    """Relative UI risk label: low/medium/high; none if not priceable.

    Research quality + *uncalibrated* win probabilities are NOT a reliable
    forecast, and 'low' must never be described as a safe or certain bet.
    Requires quoted odds and a probability to avoid invented classification.
    """
    try:
        odds = float(row.get("odds"))
        probability = float(row.get("probability_pct"))
        score = int(row.get("score", 0))
    except (TypeError, ValueError):
        return None
    ev = expected_value(odds, probability)
    if ev is None:
        return None
    if not row.get("verified", False) or row.get("market_type") != "binary":
        return "high"
    if probability >= 65 and score >= 22 and ev >= 0.05:
        return "low"
    if probability >= 57 and score >= 19 and ev >= 0:
        return "medium"
    return "high"

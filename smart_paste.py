"""Smart Paste: conservative, offline normalization of copied football fixtures.

No network/AI calls, no invented opponents, and no timezone conversion. Users must
review and approve extracted fixtures before chargeable AI research runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from html import unescape
import re
import unicodedata

MAX_CHARACTERS = 60000
MAX_LINES = 1100
MAX_FIXTURES = 40

MATCH_SEPARATOR = re.compile(r"\s+(?:vs\.?|versus|v\.?|[-–—−]|مقابل)\s+", re.I)
STATUS = re.compile(r"(?:app\.football\.|scores_fixtures|are_scheduled|view_fixture|postponed|half[- ]?time|full[- ]?time|^scheduled$)", re.I)
JUNK = re.compile(r"^(?:\.|[-•|]+|[—–]|\d{1,2}\.\d{1,2}pm\s+Kick-off.*)$", re.I)
DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}(?:\s+(?:[01]\d|2[0-3]):[0-5]\d)?$")
TIME_ONLY = re.compile(r"^(?:(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)|(?P<h12>0?[1-9]|1[0-2])[:.](?P<m12>[0-5]\d)\s*(?P<ampm>am|pm))$", re.I)
KICKOFF_TRAILER = re.compile(r"\s+(?:kick[- ]?off(?:\s+at)?|starts?(?:\s+at)?|ko(?:\s+at)?)\s*[:]?\s*"
                             r"(?P<time>(?:[01]?\d|2[0-3]):[0-5]\d|(?:0?[1-9]|1[0-2])[:.][0-5]\d\s*(?:am|pm))\s*$", re.I)
ROUND_HEADING = re.compile(r"^(?:round\s+\d+|matchday\s+\d+|fixtures?|results?|tomorrow|today|tonight|"
                           r"uefa(?:\s+champions\s+league)?|champions\s+league|"
                           r"europa\s+league|football|scores|اروپا|لیگ قهرمانان|لیگ قهرمانان اروپا|امشب|فردا|فرداشب|صبح)$", re.I)


@dataclass
class SmartPasteResult:
    fixtures: list[dict] = field(default_factory=list)
    mode: str = "empty"
    warnings: list[str] = field(default_factory=list)
    ignored: int = 0
    unpaired: list[str] = field(default_factory=list)


def normalize_line(line: str) -> str:
    normalized = unicodedata.normalize("NFKC", unescape(line)).replace("\u200b", "").replace("\u200c", "")
    normalized = re.sub(r"^[\s\u2022•*]+", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_date(value: str) -> str:
    if not DATE_TIME.fullmatch(value):
        raise ValueError("Use YYYY-MM-DD or YYYY-MM-DD HH:MM for the match date/time.")
    try:
        if len(value) == 10:
            return date.fromisoformat(value).isoformat()
        return datetime.strptime(value, "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ValueError("Invalid match date/time. Check day, month and clock.") from exc


def clock_24h(value: str) -> str | None:
    m = TIME_ONLY.fullmatch(value.strip())
    if not m:
        return None
    if m.group("h24"):
        return f"{int(m.group('h24')):02d}:{m.group('m24')}"
    hour = int(m.group("h12")) % 12 + (12 if m.group("ampm").lower() == "pm" else 0)
    return f"{hour:02d}:{m.group('m12')}"


def is_noise(line: str) -> bool:
    return bool(not line or STATUS.search(line) or JUNK.fullmatch(line)
                or ROUND_HEADING.fullmatch(line) or TIME_ONLY.fullmatch(line)
                or DATE_TIME.fullmatch(line))


def validate_team(name: str) -> bool:
    return (bool(name) and 2 <= len(name) <= 110 and not is_noise(name)
            and not re.fullmatch(r"\d+", name))


def add_fixture(result: SmartPasteResult, home: str, away: str, when: str, source: str,
                seen: set[tuple[str, str, str]], *, confidence: str = "HIGH") -> None:
    home, away = normalize_line(home), normalize_line(away)
    if not validate_team(home) or not validate_team(away) or home.casefold() == away.casefold():
        return
    if not DATE_TIME.fullmatch(when):
        raise ValueError(f"Invalid kickoff for {home} vs {away}: {when}")
    when = normalize_date(when)
    key = (home.casefold(), away.casefold(), when[:10])
    if key not in seen:
        seen.add(key)
        result.fixtures.append({"home": home, "away": away, "kickoff": when,
                                "source": source, "confidence": confidence})


def _fixture_line(line: str, fallback_date: str, keep_times: bool) -> tuple[str, str, str] | None:
    """Find a fixture in a single line, including BBC 'Kick-off at ...' summaries."""
    fields = [p.strip() for p in line.split("|")]
    left = fields[0]
    match_date = fallback_date
    if len(fields) >= 2 and DATE_TIME.fullmatch(fields[1]):
        match_date = normalize_date(fields[1])
    pieces = MATCH_SEPARATOR.split(left, maxsplit=1)
    if len(pieces) != 2:
        return None
    home, away = (p.strip() for p in pieces)
    suffix = KICKOFF_TRAILER.search(away)
    if suffix:
        if keep_times and len(match_date) == 10:
            t = clock_24h(suffix.group("time"))
            if t:
                match_date += " " + t
        away = away[:suffix.start()].strip()
    if not validate_team(home) or not validate_team(away):
        return None
    return home, away, match_date


def smart_parse(text: str, fallback_date: str, *, keep_times: bool = False) -> SmartPasteResult:
    """Parse match lines, BBC blocks, vertical home/time/away, or plain team pairs.

    keep_times only interprets pasted clocks in the SOURCE timezone, which must
    match the site's selected timezone; default False deliberately discards them.
    """
    fallback_date = normalize_date(fallback_date[:10])
    if not text.strip():
        return SmartPasteResult()
    if len(text) > MAX_CHARACTERS:
        raise ValueError("Paste is too long. Please split it into smaller groups.")
    raw_lines = [normalize_line(raw) for raw in text.splitlines()]
    lines = [line for line in raw_lines if line]
    if len(lines) > MAX_LINES:
        raise ValueError("Too many text lines. Please split the list into smaller groups.")
    result = SmartPasteResult()
    seen: set[tuple[str, str, str]] = set()
    inline = []
    for line in lines:
        parsed = _fixture_line(line, fallback_date, keep_times)
        if parsed is not None:
            inline.append(parsed)
    if inline:
        result.mode = "fixture lines / copied website summaries"
        for home, away, when in inline:
            add_fixture(result, home, away, when, "Explicit fixture", seen)
        result.ignored = max(0, len(lines) - len(inline))
    else:
        # Fallback for fixture providers that show home/home/status/away/away.
        for index, line in enumerate(lines):
            if not re.search(r"are_scheduled", line, re.I):
                continue
            before = next((x for x in reversed(lines[max(0, index-3):index]) if validate_team(x)), None)
            after = next((x for x in lines[index+1:index+5] if validate_team(x)), None)
            if before and after:
                add_fixture(result, before, after, fallback_date, "Website schedule block", seen,
                            confidence="REVIEW")
        if result.fixtures:
            result.mode = "website schedule blocks"
        else:
            # Three lines: home / kick-off time / away; trailing headings excluded.
            candidates = [line for line in lines if not is_noise(line)]
            found_vertical = []
            used: set[int] = set()
            for j in range(len(lines) - 2):
                if j in used or j+1 in used or j+2 in used:
                    continue
                if validate_team(lines[j]) and clock_24h(lines[j+1]) and validate_team(lines[j+2]):
                    when = (fallback_date + " " + clock_24h(lines[j+1])) if keep_times else fallback_date
                    found_vertical.append((lines[j], lines[j+2], when))
                    used.update((j, j+1, j+2))
            if found_vertical:
                result.mode = "three-line fixture blocks"
                for home, away, when in found_vertical:
                    add_fixture(result, home, away, when, "Home / clock / away", seen, confidence="REVIEW")
                result.ignored = max(0, len(lines) - 3*len(found_vertical))
            else:
                # Only team names: consecutive pairs. Adjacent duplicates are collapsed.
                deduped = []
                for line in candidates:
                    if not deduped or line.casefold() != deduped[-1].casefold():
                        deduped.append(line)
                result.mode = "team names (paired in pasted order)"
                for i in range(0, len(deduped) - 1, 2):
                    add_fixture(result, deduped[i], deduped[i+1], fallback_date,
                                "Inferred team pair — confirm opponent", seen, confidence="REVIEW")
                if len(deduped) % 2:
                    result.unpaired = deduped[-1:]
                if deduped:
                    result.warnings.append("Team names were paired in the order pasted. Confirm every opponent and home/away team.")
                result.ignored = max(0, len(lines) - len(deduped))
    if len(result.fixtures) > MAX_FIXTURES:
        raise ValueError(f"Too many fixtures ({len(result.fixtures)}). Maximum {MAX_FIXTURES} per paste.")
    if not result.fixtures:
        result.warnings.append("No clear fixture pairing was found. Enter 'Home - Away' or paste both teams per match.")
    if result.unpaired:
        result.warnings.append("Unpaired team name(s): " + ", ".join(result.unpaired[:8]))
    if result.fixtures and not keep_times and len(result.fixtures) > 0:
        result.warnings.append("Kickoff time was not imported. The default date was used when needed; add or check times in the preview if relevant.")
    if result.fixtures and keep_times:
        result.warnings.append("Imported times are NOT timezone-converted. Confirm they match the Kickoff timezone selection.")
    return result


def validated_preview(rows: list[dict], *, max_fixtures: int = 18) -> list[dict]:
    """Validate user-edited table before paid API requests. No silent row fixing."""
    result: list[dict] = []
    seen = set()
    for idx, record in enumerate(rows, 1):
        home = normalize_line(str(record.get("home") or ""))
        away = normalize_line(str(record.get("away") or ""))
        kickoff = str(record.get("kickoff") or "").strip()
        if not validate_team(home) or not validate_team(away) or home.casefold() == away.casefold():
            raise ValueError(f"Row {idx}: enter two different valid team names.")
        try:
            kickoff = normalize_date(kickoff)
        except ValueError as exc:
            raise ValueError(f"Row {idx}: {exc}") from exc
        # Prevent duplicated fixture spending twice, even if one row has an optional time.
        key = (home.casefold(), away.casefold(), kickoff[:10])
        if key in seen:
            raise ValueError(f"Row {idx}: duplicated fixture. Remove or correct this row.")
        seen.add(key)
        result.append({"home": home, "away": away, "kickoff": kickoff})
    if len(result) > max_fixtures:
        raise ValueError(f"Maximum {max_fixtures} matches per analysis run.")
    return result

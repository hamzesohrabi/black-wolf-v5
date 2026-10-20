"""Live evidence-based analysis via OpenAI Responses API + web_search.

IMPORTANT: This is not a live odds feed or a calibrated probabilities model.
The only accepted prices are user-supplied bookmaker quotes in the UI.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from engine import capped_score


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fixture_status": {"type": "string", "enum": ["confirmed", "uncertain", "finished"]},
        "competition": {"type": "string"},
        "fixture_evidence": {"type": "string"},
        "recent_evidence": {"type": "string"},
        "team_news": {"type": "string"},
        "market": {"type": "string"},
        "market_type": {"type": "string", "enum": ["binary", "none"]},
        "probability_pct": {"type": ["number", "null"]},
        "rationale": {"type": "string"},
        "risks": {"type": "string"},
        "scores": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "form": {"type": "integer"},
                "home_away": {"type": "integer"},
                "availability": {"type": "integer"},
                "tactics": {"type": "integer"},
                "data_quality": {"type": "integer"},
            },
            "required": ["form", "home_away", "availability", "tactics", "data_quality"],
        },
    },
    "required": ["fixture_status", "competition", "fixture_evidence",
                 "recent_evidence", "team_news", "market", "market_type",
                 "probability_pct", "rationale", "risks", "scores"],
}

SYSTEM_PROMPT = """You are a cautious football match research assistant.
Always use web search to verify the EXACT upcoming fixture, local kickoff date, opponent pair, tournament and recent evidence.
If the fixture cannot be verified using an authoritative competition/club fixture source, set fixture_status=uncertain.
If already played, set finished. Never mix two separate fixtures or dates. No betting recommendation for uncertain or finished fixtures.
For confirmed fixtures, find recent form, home/away, injuries and tactics, prioritize official/credible sources, explain stale/missing news.
Suggest ONE precisely described BINARY pre-match market (90 minutes only), e.g. 1X2 home/draw/away, double chance, total over/under N.5, team goals over/under N.5, BTTS yes/no, half-goal handicap. Only choose binary markets without pushes/refunds/half-wins.
Odds, prices and bookmakers are never provided by you: no made-up odds or claims of real-time availability.
Optional probability_pct is a ROUGH, UNCALIBRATED estimate, not a guarantee; set null when evidence is insufficient. Never set it based on desired odds.
Use five 0-5 rubric scores: form, home_away, availability, tactics, data_quality. Score conservatively; missing evidence lowers data_quality.
Answer only as strict JSON with all required properties; prose fields and market in Persian. Do not fabricate scores, injuries, statistics, or citations.
"""


def valid_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and bool(parts.netloc)
    except (TypeError, ValueError):
        return False


def extract_cited_urls(response) -> list[str]:
    """Only URLs returned by the search tool or official API citation annotations."""
    result = []
    try:
        output = response.model_dump().get("output", [])
    except Exception:
        return result
    for part in output:
        if part.get("type") == "web_search_call":
            for item in (part.get("action") or {}).get("sources", []) or []:
                url = item.get("url", "") if isinstance(item, dict) else ""
                if valid_url(url) and url not in result:
                    result.append(url)
        if part.get("type") == "message":
            for content in part.get("content", []):
                for annotation in content.get("annotations", []) or []:
                    if annotation.get("type") == "url_citation":
                        url = annotation.get("url", "")
                        if valid_url(url) and url not in result:
                            result.append(url)
    return result[:10]


def analyze_fixture(client, model: str, match: dict, as_of: str, input_timezone: str = "Europe/Berlin") -> dict:
    text = (f"Reference current date/time: {as_of}.\n"
            f"User-supplied event: {match['home']} vs {match['away']} "
            f"at {match['kickoff']} (user input timezone: {input_timezone}; time optional).\n"
            "Independently verify this exact schedule with web search, then research pre-match facts. "
            "If the date does not match official evidence mark uncertain. "
            "Do not invent bookmaker odds. Provide no tips for ended/unconfirmed games.")
    response = client.responses.create(
        model=model,
        tools=[{"type": "web_search", "search_context_size": "medium"}],
        tool_choice="required",
        include=["web_search_call.action.sources"],
        input=[{"role": "system", "content": SYSTEM_PROMPT},
               {"role": "user", "content": text}],
        text={"format": {"type": "json_schema", "name": "football_analysis_v1",
                         "strict": True, "schema": SCHEMA}},
    )
    if not response.output_text:
        raise RuntimeError("مدل خروجی تحلیلی ارائه نکرد؛ نتیجه‌ای ثبت نشد.")
    data = json.loads(response.output_text)
    urls = extract_cited_urls(response)
    confirmed = data.get("fixture_status") == "confirmed" and bool(urls)
    prob = data.get("probability_pct")
    if not isinstance(prob, (int, float)) or not 0 < prob < 100:
        prob = None
    market = data.get("market", "") if confirmed else ""
    if data.get("market_type") != "binary":
        market = ""
    return {
        "game": f"{match['home']} – {match['away']}",
        "kickoff": match["kickoff"],
        "verified": confirmed,
        "status": data.get("fixture_status", "uncertain"),
        "competition": data.get("competition", ""),
        "market": market,
        "market_type": "binary" if market else "none",
        "probability_pct": prob if market else None,
        "odds": None,
        "score": capped_score(data.get("scores")),
        "ev": None,
        "rationale": data.get("rationale", ""),
        "risks": data.get("risks", ""),
        "fixture_evidence": data.get("fixture_evidence", ""),
        "recent_evidence": data.get("recent_evidence", ""),
        "team_news": data.get("team_news", ""),
        "scores": data.get("scores", {}),
        "sources": urls,
    }

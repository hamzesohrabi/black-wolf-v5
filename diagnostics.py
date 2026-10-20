"""Sanitized, actionable OpenAI error reporting for the BLACK WOLF dashboard.

Never display server credentials, raw server exceptions, or request payloads.
"""
from __future__ import annotations


def _error_code(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        nested = body.get("error")
        if isinstance(nested, dict):
            body = nested
        candidate = body.get("code")
        if isinstance(candidate, str):
            return candidate.lower()
    candidate = getattr(exc, "code", None)
    return candidate.lower() if isinstance(candidate, str) else ""


def describe_ai_failure(exc: Exception, model: str) -> str:
    """Return user-safe guidance. Detail is intentionally limited; do not leak keys."""
    status = getattr(exc, "status_code", None)
    code = _error_code(exc)
    error_class = type(exc).__name__
    if status == 401:
        return "HTTP 401 · API authentication failed. Confirm OPENAI_API_KEY in Streamlit Secrets is complete, valid and belongs to your OpenAI API project."
    if status == 403:
        return "HTTP 403 · Request denied. Check project permissions, supported region and model/tool access."
    if status == 404:
        return f"HTTP 404 · Model or API endpoint not found or not accessible. Check OPENAI_MODEL ({model}) and the project's model access."
    if status == 429:
        if code in {"insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached"}:
            return "HTTP 429 · API billing/credit exhausted. Check OpenAI Platform billing, available API credits and spending limits. ChatGPT subscriptions do not pay for API calls."
        return "HTTP 429 · Rate limit or billing restriction. Check OpenAI Platform Usage/Billing and project limits; do not repeatedly retry."
    if status == 400:
        return f"HTTP 400 · API request rejected. Check supported model ({model}), web search, structured-output settings and the Streamlit server logs."
    if status and status >= 500:
        return f"HTTP {status} · OpenAI service error. Retry later; check the provider status if it persists."
    if error_class in ("APITimeoutError", "TimeoutError"):
        return "AI request timed out. Try a single fixture and check Streamlit logs/network; the model may be slow when using web search."
    if error_class in ("APIConnectionError", "ConnectError", "ConnectionError"):
        return "Could not connect to OpenAI API. Check the server network and Streamlit logs."
    if error_class == "JSONDecodeError":
        return "The model returned invalid JSON. Check the structured-output handling in ai_analysis.py."
    if isinstance(exc, RuntimeError) and str(exc).startswith("The model returned no analysis output"):
        return "Model returned no usable analysis. Check web-search access and response configuration in the Streamlit logs."
    return f"AI request failed ({error_class}). Check Streamlit logs; no fixture was verified by this request."

"""BLACK WOLF — responsive, English-language Streamlit football research dashboard.

Deployment: Streamlit Community Cloud, main file streamlit_app.py.
No live bookmaker odds, betting execution, or guaranteed results.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
import io
import json
import os
import logging
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from ai_analysis import analyze_fixture
from diagnostics import describe_ai_failure
from engine import combos_in_range, expected_value, flatten_row, shortlist, risk_tier
from smart_paste import smart_parse, validated_preview

logger = logging.getLogger("black_wolf")

st.set_page_config(
    page_title="BLACK WOLF | Football Intelligence",
    page_icon="◼",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"About": "BLACK WOLF — Evidence-led football match research. No guaranteed predictions."},
)

STYLE = """
<style>
/* Space Grotesk: same typeface as the supplied font; fetched from Google Fonts at runtime.
   No font binary is embedded or stored in this public repository. */
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300..700&display=swap');
:root {color-scheme: light;--bw-black:#0a0a0a;--bw-ink:#171717;--bw-muted:#686868;--bw-line:#dedede;--bw-soft:#f5f5f5;--bw-paper:#fff;
--bw-low:#148447;--bw-low-bg:#e7f5ed;--bw-medium:#bf6905;--bw-medium-bg:#fff0d7;--bw-high:#c72a2a;--bw-high-bg:#fce8e8;}
html,body,.stApp,[data-testid="stAppViewContainer"] {background:var(--bw-paper)!important;color:var(--bw-ink)!important;direction:ltr!important;}
html,body,.stApp, .stMarkdown, p,h1,h2,h3,h4,h5,label,input,textarea,button,select, [data-testid="stMetricValue"], [data-testid="stWidgetLabel"] {
 font-family:'Space Grotesk',Arial,sans-serif!important;
}
[data-testid="stHeader"] {background:rgba(255,255,255,.96)!important;border-bottom:1px solid #ededed;}
[data-testid="stDecoration"] {display:none;}
[data-testid="stToolbar"], [data-testid="stToolbar"] * {color:#111!important;}
.block-container {max-width:1150px;padding-top:1.1rem;padding-bottom:3.2rem;}
.stMarkdown,.stText,.stCaption,label,h1,h2,h3,p {text-align:left;}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li {line-height:1.55;}
[data-testid="stMarkdownContainer"] h1,[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3,
[data-testid="stWidgetLabel"] p {color:#111!important;}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p,small {color:#666!important;}
[data-testid="stWidgetLabel"] {color:#151515!important;font-weight:650!important;}
[data-testid="stSidebar"] {background:#fafafa!important;border-right:1px solid var(--bw-line);}
[data-testid="stSidebar"] *,[data-testid="stSidebar"] p {color:#161616!important;}
[data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,[data-testid="stDateInput"] input,
[data-testid="stSelectbox"] [data-baseweb="select"]>div {
 background:#fff!important;color:#141414!important;border:1px solid #cacaca!important;
 border-radius:12px!important;box-shadow:none!important;}
[data-testid="stTextArea"] textarea::placeholder,[data-testid="stTextInput"] input::placeholder {color:#929292!important;opacity:1;}
[data-testid="stSelectbox"] [data-baseweb="select"] * {color:#111!important;}
[data-baseweb="popover"] {color:#141414!important;}
[data-testid="stFileUploader"] {background:#fff;border-radius:12px;}
[data-testid="stFileUploader"] section {background:#fcfcfc!important;border:1px dashed #a0a0a0!important;border-radius:12px!important;}
[data-testid="stFileUploader"] section *,[data-testid="stFileUploader"] small {color:#484848!important;}
[data-testid="stExpander"] {background:#fff;border:1px solid #dcdcdc!important;border-radius:15px!important;box-shadow:none!important;overflow:hidden;}
[data-testid="stExpander"] summary,[data-testid="stExpander"] summary * {color:#171717!important;font-weight:650!important;}
[data-testid="stMetric"] {background:#fff;border:1px solid #dcdcdc;border-radius:13px;padding:.8rem 1rem;}
[data-testid="stMetricLabel"] p {color:#777!important;}
[data-testid="stMetricValue"] {color:#0c0c0c!important;}
[data-testid="stAlert"] {background:#f6f6f6!important;color:#151515!important;border:1px solid #d8d8d8!important;border-radius:12px;}
[data-testid="stAlert"] p,[data-testid="stAlert"] * {color:#191919!important;}
[data-testid="stDataFrame"] {border:1px solid #d8d8d8;border-radius:12px;overflow:hidden;}
button[kind="primary"],[data-testid="stFormSubmitButton"] button[kind="primary"] {
 background:#090909!important;color:#fff!important;border:1px solid #090909!important;
 border-radius:11px!important;min-height:2.9rem;font-weight:700!important;box-shadow:none!important;}
button[kind="primary"]:hover {background:#383838!important;border-color:#383838!important;}
button[kind="secondary"],[data-testid="stDownloadButton"] button {
 border-radius:11px!important;border:1px solid #aaa!important;color:#111!important;background:#fff!important;font-weight:650!important;}
button[kind="secondary"]:hover,[data-testid="stDownloadButton"] button:hover {border-color:#111!important;background:#f4f4f4!important;}
button:focus-visible,input:focus-visible,textarea:focus-visible {outline:2px solid #111!important;outline-offset:2px;}
[data-testid="stCheckbox"] label span,[data-testid="stCheckbox"] label p {color:#181818!important;}
[data-testid="stProgress"] div[role="progressbar"]>div {background:#0a0a0a!important;}
hr {border-color:#dedede!important;}
/* Monochrome brand and layout */
.bw-hero {position:relative;overflow:hidden;background:#070707;color:#fff!important;padding:34px 38px 35px;
 border-radius:21px;margin-bottom:17px;isolation:isolate;}
.bw-hero:before {content:"";position:absolute;width:400px;height:400px;border:1px solid #343434;border-radius:50%;
 right:-150px;top:-150px;pointer-events:none;}
.bw-hero:after {content:"";position:absolute;width:300px;height:300px;border:1px solid #252525;border-radius:50%;
 right:-105px;top:-103px;pointer-events:none;}
.bw-brand {display:flex;gap:13px;align-items:center;margin-bottom:29px;position:relative;z-index:1;}
.bw-mark {height:46px;width:46px;display:flex;align-items:center;justify-content:center;border:1px solid #717171;
 border-radius:11px;background:#161616;}
.bw-wordmark {font-size:17px;color:#fff;font-weight:700;letter-spacing:.14em;line-height:1.1;}
.bw-brand-sub {font-size:10px;color:#b7b7b7;font-weight:600;letter-spacing:.18em;margin-top:4px;}
.bw-kicker {color:#bdbdbd;font-size:10px;letter-spacing:.19em;font-weight:700;margin-bottom:10px;}
.bw-hero h1 {position:relative;z-index:1;color:#fff!important;font-size:clamp(1.85rem,4vw,3.05rem)!important;
 max-width:750px;letter-spacing:-.055em;line-height:1.12;font-weight:700;margin:0 0 13px!important;}
.bw-hero p {position:relative;z-index:1;color:#c7c7c7!important;max-width:680px;font-size:13px;line-height:1.6;margin:0;}
.bw-pill {position:relative;z-index:1;display:inline-block;margin-top:19px;border:1px solid #666;
 padding:7px 12px;border-radius:7px;color:#f3f3f3;font-size:10px;font-weight:600;letter-spacing:.05em;}
.bw-kpi-row {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:3px 0 26px;}
.bw-kpi {padding:18px;border-radius:14px;background:#fff;border:1px solid #e0e0e0;}
.bw-kpi-top {font-size:10px;letter-spacing:.12em;color:#747474;font-weight:700;}
.bw-kpi-number {font-size:29px;color:#101010;font-weight:700;line-height:1.2;margin-top:4px;}
.bw-kpi-note {font-size:12px;color:#777;margin-top:3px;}
.bw-section {margin:25px 0 14px;}
.bw-eyebrow {font-size:10px;letter-spacing:.16em;color:#606060;font-weight:700;}
.bw-section h2 {font-size:25px;line-height:1.25;letter-spacing:-.045em;color:#0d0d0d!important;margin:5px 0 6px;font-weight:700;}
.bw-section p {font-size:13px;color:#777;margin:0;line-height:1.6;}
.bw-divider {border-top:1px solid #e1e1e1;margin:27px 0 15px;}
.bw-micro {font-size:12px;color:#666;line-height:1.6;}
.bw-login {margin:5rem auto 1.5rem;max-width:650px;}
.bw-footer {font-size:11px;color:#777;line-height:1.6;padding-top:20px;text-align:center;}
/* The ONLY color accents are the three evidence-based risk levels. */
.bw-risk-legend {display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0 16px;}
.bw-risk-badge {display:inline-flex;align-items:center;justify-content:center;padding:5px 10px;border-radius:7px;
 font-size:10px;font-weight:700;letter-spacing:.055em;white-space:nowrap;border:1px solid currentColor;}
.bw-risk-low {color:var(--bw-low)!important;background:var(--bw-low-bg)!important;}
.bw-risk-medium {color:var(--bw-medium)!important;background:var(--bw-medium-bg)!important;}
.bw-risk-high {color:var(--bw-high)!important;background:var(--bw-high-bg)!important;}
.bw-odds {font-size:22px;font-weight:700;letter-spacing:-.04em;}
.bw-odds.bw-risk-low,.bw-odds.bw-risk-medium,.bw-odds.bw-risk-high {background:none!important;}
.bw-legend-note {font-size:11px;color:#777;line-height:1.5;}
.bw-value-result {display:flex;align-items:center;gap:11px;flex-wrap:wrap;background:#fafafa;
 border:1px solid #dedede;border-radius:12px;padding:12px 14px;margin:9px 0 4px;}
.bw-value-number {color:#111;font-size:13px;font-weight:600;}
.bw-market-list {display:grid;gap:10px;margin:8px 0 13px;}
.bw-market-card {display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1.2fr) auto;align-items:center;
 gap:16px;background:#fff;border:1px solid #dedede;border-radius:14px;padding:15px 18px;}
.bw-card-overline {color:#777;font-size:10px;font-weight:700;letter-spacing:.09em;}
.bw-card-title {color:#111;font-size:15px;font-weight:700;line-height:1.3;margin:4px 0;overflow-wrap:anywhere;}
.bw-card-sub {color:#686868;font-size:12px;line-height:1.4;overflow-wrap:anywhere;}
.bw-card-right {text-align:right;min-width:115px;}
.bw-card-right .bw-risk-badge {margin-top:5px;}
@media(max-width:760px){
 .block-container {padding:.45rem .8rem 2.5rem;}
 .bw-hero {padding:25px 23px 27px;border-radius:17px;}
 .bw-brand {margin-bottom:23px;}
 .bw-hero h1 {font-size:1.96rem!important;}
 .bw-hero p {font-size:12px;}
 .bw-kpi-row {gap:7px;}
 .bw-kpi {padding:12px 10px;border-radius:11px;}
 .bw-kpi-top {font-size:9px;letter-spacing:.025em;}
 .bw-kpi-number {font-size:22px;}
 .bw-kpi-note {font-size:10px;}
 .bw-section h2 {font-size:22px;}
 .bw-login {margin-top:1.2rem;}
 .bw-market-card {grid-template-columns:minmax(0,1fr) auto;gap:9px;padding:13px;}
 .bw-market-card .bw-market-middle {grid-column:1/-1;grid-row:2;}
 .bw-card-right {grid-column:2;grid-row:1;min-width:84px;}
 .bw-odds {font-size:20px;}
 [data-testid="stMetric"] {padding:.65rem;}
}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)

WOLF_SVG = """<svg width="27" height="27" viewBox="0 0 100 100" fill="none" aria-hidden="true">
<path d="M13 11L36 23L50 19L64 23L87 11L83 57L68 80L50 91L32 80L17 57L13 11Z" stroke="#FFFFFF" stroke-width="6" stroke-linejoin="round"/>
<path d="M26 48L43 56L34 59M74 48L57 56L66 59" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M41 73L50 79L59 73" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round"/></svg>"""


def risk_markup(tier: str) -> str:
    """Present only an estimated, relative risk grade (never a 'safe bet')."""
    labels = {"low": "LOWER RISK", "medium": "MEDIUM RISK", "high": "HIGHER RISK"}
    if tier not in labels:
        return '<span class="bw-legend-note">NOT RATED</span>'
    return f'<span class="bw-risk-badge bw-risk-{tier}">{labels[tier]}</span>'


def odds_markup(odds: float, tier: str) -> str:
    klass = f" bw-risk-{tier}" if tier in ("low", "medium", "high") else ""
    return f'<span class="bw-odds{klass}">{float(odds):.2f}</span>'


def candidate_cards(rows: list[dict]) -> str:
    cards = []
    for rank, row in enumerate(rows, 1):
        tier = risk_tier(row)
        cards.append(f"""<div class="bw-market-card">
          <div><div class="bw-card-overline">CANDIDATE {rank:02d}</div>
            <div class="bw-card-title">{escape(str(row.get('game','')))}</div>
            <div class="bw-card-sub">Research score {int(row.get('score',0))}/25</div></div>
          <div class="bw-market-middle"><div class="bw-card-overline">MARKET</div>
            <div class="bw-card-title">{escape(str(row.get('market','')))}</div>
            <div class="bw-card-sub">Est. EV: {float(row.get('ev',0))*100:+.1f}%</div></div>
          <div class="bw-card-right">{odds_markup(row['odds'],tier)}<div>{risk_markup(tier)}</div></div>
        </div>""")
    return '<div class="bw-market-list">'+''.join(cards)+'</div>'


def risk_legend() -> str:
    return ('<div class="bw-risk-legend">'
            +risk_markup('low')+risk_markup('medium')+risk_markup('high')
            +'<span class="bw-legend-note">Relative research heuristic, not a guarantee of winning.</span></div>')


def secret(name: str, default: str = "") -> str:
    """Read secure server configuration without exposing secrets in the app."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, OSError, KeyError):
        return default


def hero(*, login: bool = False) -> None:
    heading = "Football intelligence.<br>Without the noise." if not login else "Welcome to <br>BLACK WOLF."
    subtitle = (
        "Verify fixtures, research the latest team news, compare real odds, and surface value candidates — in one clear dashboard."
        if not login else "Private access to your AI football research workspace."
    )
    st.markdown(f"""
    <div class="bw-hero">
      <div class="bw-brand">
        <div class="bw-mark">{WOLF_SVG}</div>
        <div><div class="bw-wordmark">BLACK WOLF</div><div class="bw-brand-sub">FOOTBALL INTELLIGENCE</div></div>
      </div>
      <div class="bw-kicker">FOOTBALL RESEARCH · BLACK & WHITE EDITION</div>
      <h1>{heading}</h1>
      <p>{subtitle}</p>
      <span class="bw-pill">18 MATCHES &nbsp;→&nbsp; 8 CANDIDATES &nbsp;→&nbsp; UP TO 3 PRIORITIES</span>
    </div>
    """, unsafe_allow_html=True)


def section(number: str, title: str, description: str) -> None:
    st.markdown(f"""<div class="bw-section"><div class="bw-eyebrow">{escape(number)} / BLACK WOLF</div>
    <h2>{escape(title)}</h2><p>{escape(description)}</p></div>""", unsafe_allow_html=True)


def login_gate() -> bool:
    password = secret("APP_PASSWORD")
    if not password or password in ("a-unique-long-password", "YOUR_PASSWORD", "YOUR_PRIVATE_PASSWORD"):
        hero(login=True)
        st.error("The administrator must configure APP_PASSWORD in Streamlit Secrets before the app can be used.")
        return False
    if st.session_state.get("logged_in", False):
        return True
    hero(login=True)
    col, _ = st.columns([1.25, 1])
    with col:
        section("SECURE ACCESS", "Sign in", "Enter the private password configured for this dashboard.")
        with st.form("login_form"):
            entered = st.text_input("Dashboard password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign in to BLACK WOLF", use_container_width=True, type="primary")
        if submitted:
            if compare_digest(entered.encode("utf-8"), password.encode("utf-8")):
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
    st.markdown('<div class="bw-footer">PRIVATE DASHBOARD &nbsp;•&nbsp; SERVER-SIDE API KEY &nbsp;•&nbsp; NO AUTOMATIC BETS</div>', unsafe_allow_html=True)
    return False


if not login_gate():
    st.stop()

key = secret("OPENAI_API_KEY")
model = secret("OPENAI_MODEL", "gpt-5-mini").strip()
now = datetime.now(ZoneInfo("Europe/Berlin"))

with st.sidebar:
    st.markdown("### Research controls")
    st.caption("Tune the shortlist. These are decision rules, not a guarantee of profitability.")
    price_low, price_high = st.slider(
        "Target decimal-odds range", min_value=1.2, max_value=4.0,
        value=(1.65, 1.95), step=0.05,
    )
    min_score = st.slider("Minimum research score / 25", 0, 25, value=20)
    min_ev_pct = st.slider("Minimum estimated EV (%)", 0, 25, value=3, step=1)
    st.divider()
    st.caption(f"Model from server settings: {model or 'Not configured'}")
    st.caption("Pricing and availability depend on your own API account.")
    if st.button("Sign out", use_container_width=True):
        for item in list(st.session_state.keys()):
            del st.session_state[item]
        st.rerun()

hero()
st.markdown("""
<div class="bw-kpi-row">
  <div class="bw-kpi"><div class="bw-kpi-top">MATCH SLATE</div><div class="bw-kpi-number">Up to 18</div><div class="bw-kpi-note">Per research run</div></div>
  <div class="bw-kpi"><div class="bw-kpi-top">SHORTLIST</div><div class="bw-kpi-number">Top 8</div><div class="bw-kpi-note">Only qualified picks</div></div>
  <div class="bw-kpi"><div class="bw-kpi-top">RESEARCH MODE</div><div class="bw-kpi-number">AI + Web</div><div class="bw-kpi-note">Cited source links</div></div>
</div>
""", unsafe_allow_html=True)

section("01", "Smart Paste your fixtures", "Paste raw website text, a match list, or team names. BLACK WOLF separates fixtures, removes duplicates and lets you review everything before AI research.")
with st.expander("What can Smart Paste read?", expanded=False):
    st.code("Arsenal - Bayern\nInter vs Porto\nBarcelona\nLiverpool", language="text")
    st.caption("Also accepts BBC-style repeated team names, fixture status labels, and 'Kick-off at 5:45pm' summaries. When only team names are supplied, consecutive pairs are provisional and must be reviewed.")
    st.warning("Pasted fixtures are not verified by Smart Paste. AI research later checks each match against available sources.")

field_a, field_b = st.columns([1, 1], gap="medium")
with field_a:
    match_day = st.date_input("Default match date", value=now.date(), help="Used when the copied text does not contain a valid ISO date.")
with field_b:
    timezone = st.selectbox(
        "Kickoff timezone", ["Europe/Berlin", "Asia/Tehran", "UTC"],
        index=0, format_func=lambda x: {"Europe/Berlin": "Berlin (CET/CEST)", "Asia/Tehran": "Tehran", "UTC": "UTC"}[x],
    )
input_text = st.text_area(
    "Smart Paste — copied fixtures or team names", height=210, key="smart_input_text",
    placeholder="Paste copied football schedules here...\n\nFenerbahce\nFenerbahce\napp.football.scores_fixtures.are_scheduled\nSlavia Prague\nSlavia Prague\n5.45pm\nFenerbahce vs Slavia Prague Kick-off at 5:45pm",
    help="Paste original text. No need to clean website labels or repeat names yourself.",
)
keep_times = st.checkbox(
    "Import clock times from pasted text (only if they match the timezone above)", value=False,
    help="Default OFF. BBC and other websites may show times in a different timezone. Times are NEVER converted automatically.",
)
csv_file = st.file_uploader("Or upload CSV (home, away, optional kickoff)", type=["csv"])

sig_material = (str(match_day) + "|" + timezone + "|" + str(keep_times) + "|" + input_text).encode("utf-8")
if csv_file is not None:
    sig_material += b"|csv|" + csv_file.getvalue()
input_signature = sha256(sig_material).hexdigest()

if st.button("1  ·  Prepare & clean fixtures", type="primary", use_container_width=True):
    try:
        if csv_file is not None:
            df = pd.read_csv(io.BytesIO(csv_file.getvalue()), dtype=str).fillna("")
            df.columns = [c.strip().lower() for c in df.columns]
            if not {"home", "away"}.issubset(df.columns):
                raise ValueError("CSV must include home and away columns. The kickoff column is optional.")
            proposed = [{
                "home": str(row["home"]).strip(), "away": str(row["away"]).strip(),
                "kickoff": str(row.get("kickoff") or match_day.isoformat()).strip(),
                "source": "CSV upload", "confidence": "REVIEW",
            } for _, row in df.iterrows()]
            validated_preview(proposed, max_fixtures=18)
            notes = ["CSV uploaded. Check every fixture before analysis."]
            mode = "CSV upload"
        else:
            parsed = smart_parse(input_text, match_day.isoformat(), keep_times=keep_times)
            proposed = parsed.fixtures
            notes = parsed.warnings
            mode = parsed.mode
            if len(proposed) > 18:
                raise ValueError(f"Found {len(proposed)} fixtures. Limit to 18 per research run (delete the rest and prepare again).")
        if not proposed:
            st.warning("No fixtures found. Try 'Team A - Team B' on each line, or paste a website fixture list.")
            st.session_state.pop("bw_preview", None)
        else:
            st.session_state.bw_preview = proposed
            st.session_state.bw_preview_notes = notes
            st.session_state.bw_preview_mode = mode
            st.session_state.bw_preview_signature = input_signature
            st.session_state.bw_preview_version = st.session_state.get("bw_preview_version", 0) + 1
            st.success(f"Prepared {len(proposed)} distinct fixture(s). Review and confirm them below.")
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as err:
        st.error(f"Smart Paste could not prepare this input: {err}")

is_current_preview = bool(st.session_state.get("bw_preview")) and st.session_state.get("bw_preview_signature") == input_signature
review_confirmed = False
edited_preview = None
if is_current_preview:
    st.markdown("#### 2 · Review the extracted fixtures")
    st.caption(f"Detected format: {st.session_state.get('bw_preview_mode', 'unknown')}. Tap any cell to edit team names or dates; remove incorrect rows. AI has NOT been called yet.")
    for note in st.session_state.get("bw_preview_notes", []):
        st.info(note)
    table = pd.DataFrame(st.session_state.bw_preview, columns=["home", "away", "kickoff", "source", "confidence"])
    edited_preview = st.data_editor(
        table, hide_index=True, use_container_width=True, num_rows="dynamic",
        disabled=["source", "confidence"], key=f"bw_review_{st.session_state.bw_preview_version}",
        column_config={
            "home": st.column_config.TextColumn("Home team", required=True, width="medium"),
            "away": st.column_config.TextColumn("Away team", required=True, width="medium"),
            "kickoff": st.column_config.TextColumn("Date / kickoff", required=True, help="YYYY-MM-DD or YYYY-MM-DD HH:MM"),
            "source": st.column_config.TextColumn("Parsed from"),
            "confidence": st.column_config.TextColumn("Pair quality"),
        },
    )
    review_confirmed = st.checkbox(
        "I checked the team pairings, home/away order and dates. Continue to AI verification.",
        key=f"bw_confirm_{st.session_state.bw_preview_version}",
    )
    st.caption("High confidence means the text clearly named both teams; it does NOT confirm that the real-world match exists.")
elif st.session_state.get("bw_preview"):
    st.warning("The input or date/time settings changed. Click 'Prepare & clean fixtures' again to refresh your preview.")

def current_matches() -> list[dict]:
    if edited_preview is None:
        raise ValueError("Prepare the fixture list and confirm the preview first.")
    return validated_preview(edited_preview.to_dict(orient="records"), max_fixtures=18)

st.caption("Research makes one AI web-search request per fixture. API usage may incur charges.")
acknowledge = st.checkbox("I understand that AI research requests may incur API charges.")
usage_count = st.session_state.get("used_calls", 0)
if not key:
    st.warning("OPENAI_API_KEY is missing from Streamlit Secrets. Ask the administrator to configure it.")
run_disabled = not bool(key) or not acknowledge or usage_count >= 36 or not is_current_preview or not review_confirmed
if st.button("3  ·  Verify & analyze with AI  →", type="primary", use_container_width=True, disabled=run_disabled):
    try:
        matches = current_matches()
        if not matches:
            st.warning("Enter at least one match.")
        elif len(matches) > 18:
            st.error("Maximum 18 matches per run. Split longer lists into separate runs.")
        elif len(matches) + usage_count > 36:
            st.error("This session would exceed the 36-request safety cap. Select fewer matches.")
        else:
            from openai import OpenAI

            client = OpenAI(api_key=key, timeout=90.0, max_retries=1)
            progress = st.progress(0, text="Starting research…")
            output = []
            for i, match in enumerate(matches):
                progress.progress(i / len(matches), text=f"Researching {i+1}/{len(matches)}: {match['home']} vs {match['away']}")
                st.session_state.used_calls = st.session_state.get("used_calls", 0) + 1
                try:
                    output.append(analyze_fixture(
                        client, model, match, datetime.now(ZoneInfo("Europe/Berlin")).isoformat(timespec="minutes"),
                        input_timezone=timezone,
                    ))
                except Exception as exc:
                    # Stop the batch after a failed API request to avoid more paid calls
                    # while credentials, credit or configuration may be broken.
                    message = describe_ai_failure(exc, model)
                    logger.error("AI research failed: type=%s status=%s on fixture %s. No raw credentials logged.",
                                 type(exc).__name__, getattr(exc, "status_code", "n/a"), i + 1)
                    output.append({
                        "game": f"{match['home']} – {match['away']}",
                        "kickoff": match["kickoff"], "verified": False, "status": "error",
                        "competition": "", "market": "", "market_type": "none",
                        "score": 0, "probability_pct": None, "odds": None,
                        "rationale": "", "recent_evidence": "", "team_news": "",
                        "fixture_evidence": "", "risks": message,
                        "sources": [],
                    })
                    for unattempted in matches[i + 1:]:
                        output.append({
                            "game": f"{unattempted['home']} – {unattempted['away']}",
                            "kickoff": unattempted["kickoff"], "verified": False,
                            "status": "skipped", "competition": "", "market": "",
                            "market_type": "none", "score": 0,
                            "probability_pct": None, "odds": None,
                            "rationale": "", "recent_evidence": "", "team_news": "",
                            "fixture_evidence": "",
                            "risks": "Skipped because an earlier AI request failed; fix the error before rerunning.",
                            "sources": [],
                        })
                    break
            progress.progress(1.0, text="Research stopped due to API error" if any(r["status"] == "error" for r in output) else "Research completed")
            st.session_state.analysis = output
            st.session_state.analysis_timezone = timezone
            st.session_state.analysis_label = f"{len(output)} fixtures • {datetime.now(ZoneInfo('Europe/Berlin')).strftime('%d %b %Y, %H:%M')}"
            st.session_state.run_id = st.session_state.get("run_id", 0) + 1
            if any(r["status"] == "error" for r in output):
                first_error = next(r for r in output if r["status"] == "error")
                st.error(first_error["risks"])
                st.caption("Research stopped after the first failure to avoid repeated API requests. Resolve the issue, then rerun.")
            else:
                st.success(f"Research completed for {len(output)} matches. Check the evidence below.")
    except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as err:
        st.error(f"Unable to analyze fixture list: {err}")

if "analysis" not in st.session_state:
    st.markdown("""<div class="bw-footer">BLACK WOLF · EVIDENCE OVER HYPE · NO AUTOMATED WAGER PLACEMENT<br>
AI probabilities are uncalibrated estimates. Always verify team news and prices before any decision.</div>""", unsafe_allow_html=True)
    st.stop()

st.markdown('<div class="bw-divider"></div>', unsafe_allow_html=True)
section("02", "AI research & market prices", "Review match verification and cited evidence, then enter actual bookmaker odds for the exact recommended market.")
st.caption(f"Last completed research: {st.session_state.get('analysis_label', 'Current session')} · Timezone: {st.session_state.get('analysis_timezone', timezone)}")
st.markdown(risk_legend(), unsafe_allow_html=True)

verified_count = sum(bool(r.get("verified")) for r in st.session_state.analysis)
review_col_a, review_col_b, review_col_c = st.columns(3, gap="small")
with review_col_a:
    st.metric("Matches analyzed", len(st.session_state.analysis))
with review_col_b:
    st.metric("Fixtures verified", verified_count)
with review_col_c:
    st.metric("Needs verification", len(st.session_state.analysis) - verified_count)

scored = []
for i, record in enumerate(st.session_state.analysis):
    is_verified = bool(record.get("verified"))
    score = int(record.get("score", 0))
    status = record.get("status")
    label = "VERIFIED" if is_verified else "API ERROR" if status == "error" else "NOT ANALYZED" if status == "skipped" else "UNVERIFIED"
    with st.expander(f"{i+1:02d}   {record['game']}     ·     {label}     ·     {score}/25", expanded=i == 0):
        if status == "error":
            st.error(record.get("risks", "AI request failed."))
        elif status == "skipped":
            st.info("Not analyzed: earlier AI request failed. No additional API charge was attempted for this fixture.")
        elif not is_verified:
            st.warning("Fixture not verified with cited sources. No market is eligible for the shortlist.")
        top_a, top_b = st.columns([1.4, 1])
        with top_a:
            st.markdown("**Fixture & competition**")
            st.write(record.get("competition") or "Not confirmed")
            st.caption(f"Submitted kickoff: {record.get('kickoff') or 'Not provided'}")
        with top_b:
            st.markdown("**Research score**")
            st.progress(max(0, min(25, score)) / 25)
            st.caption(f"{score} / 25 · heuristic research-quality filter")
        st.markdown("**Fixture verification**")
        st.write(record.get("fixture_evidence") or "Insufficient scheduling evidence.")
        research_a, research_b = st.columns(2, gap="large")
        with research_a:
            st.markdown("**Recent form**")
            st.write(record.get("recent_evidence") or "No reliable recent evidence found.")
            st.markdown("**Squad availability**")
            st.write(record.get("team_news") or "No reliable team news confirmed.")
        with research_b:
            st.markdown("**Suggested market**")
            st.write(record.get("market") or "No qualified market")
            st.markdown("**Why this market**")
            st.write(record.get("rationale") or "Insufficient information.")
            st.markdown("**Main risks**")
            st.write(record.get("risks") or "Unknown risks.")
        sources = record.get("sources") or []
        if sources:
            st.markdown("**Research sources**")
            for j, source in enumerate(sources[:5], 1):
                st.markdown(f"{j}. [Open reference]({source})")
        else:
            st.caption("No attributable source links were returned.")

        priced, probability = None, None
        if is_verified and record.get("market"):
            st.markdown("**Market valuation**")
            odds_col, prob_col = st.columns(2, gap="medium")
            with odds_col:
                priced = st.number_input(
                    "Actual decimal odds", min_value=1.01, max_value=50.0, step=0.01,
                    value=None, format="%.2f", placeholder="e.g. 1.82",
                    key=f"price_{st.session_state.run_id}_{i}",
                    help="Use current odds from your bookmaker for this exact market.",
                )
            with prob_col:
                suggestion = record.get("probability_pct")
                probability = st.number_input(
                    "Estimated win probability (%)", min_value=1.0, max_value=99.0,
                    step=0.5, value=float(suggestion) if suggestion is not None else None,
                    key=f"prob_{st.session_state.run_id}_{i}",
                    help="AI estimate is rough and uncalibrated. Adjust only with evidence.",
                )
            if priced is not None and probability is not None:
                ev = expected_value(priced, probability)
                if ev is not None:
                    tier = risk_tier({**record, "odds": priced, "probability_pct": probability})
                    st.markdown(
                        f'<div class="bw-value-result">{odds_markup(priced, tier)}{risk_markup(tier)}'
                        f'<span class="bw-value-number">Implied probability: {100/priced:.1f}% &nbsp;·&nbsp; '
                        f'Estimated EV: {ev*100:+.1f}%</span></div>',
                        unsafe_allow_html=True,
                    )
                    st.caption("Relative risk indicators use uncalibrated estimates; a green label never means guaranteed or safe.")
    scored_record = {**record, "odds": priced, "probability_pct": probability}
    scored_record["ev"] = expected_value(priced, probability)
    scored.append(scored_record)

st.markdown('<div class="bw-divider"></div>', unsafe_allow_html=True)
section("03", "Shortlist & decisions", "Only verified binary markets with entered odds and enough estimated value can reach your shortlist.")
selected = shortlist(
    scored, min_odd=price_low, max_odd=price_high,
    min_score=min_score, min_ev=min_ev_pct / 100, max_count=8,
)
if selected:
    st.markdown(f"**{len(selected)} candidate(s)** passed your filters. Even lower-risk labels can lose.")
    rank_df = pd.DataFrame([{
        "Rank": i+1,
        "Fixture": row["game"],
        "Market": row["market"],
        "Odds": round(float(row["odds"]), 2),
        "Score": int(row["score"]),
        "Est. EV (%)": round(float(row["ev"]) * 100, 1),
    } for i, row in enumerate(selected)])
    st.markdown(candidate_cards(selected), unsafe_allow_html=True)
    with st.expander("View shortlist as a data table"):
        st.dataframe(rank_df, hide_index=True, use_container_width=True)
    st.markdown("#### Highest-ranked singles (up to 3)")
    for index, row in enumerate(selected[:3], 1):
        st.markdown(
            f"**{index}. {escape(str(row['game']))}** — {escape(str(row['market']))} · "
            f"{odds_markup(row['odds'], risk_tier(row))} &nbsp; {risk_markup(risk_tier(row))}",
            unsafe_allow_html=True,
        )
    combos = combos_in_range(selected, min_total=2, max_total=3, max_legs=3)
    if combos:
        combo = combos[0]
        st.markdown(f"**Optional combination (decimal {combo['odds']:.2f}):**")
        st.write("  +  ".join(combo["games"]))
        st.caption("Combinations multiply risk. Independence/correlation and combined probability are not verified.")
else:
    st.info("No picks passed the current filters. 'No selection' is a valid and often appropriate result.")

st.markdown('<div class="bw-divider"></div>', unsafe_allow_html=True)
section("04", "Export your analysis", "Save research and decisions in a structured format for tracking and review.")
report = {
    "created_at": datetime.now(ZoneInfo("Europe/Berlin")).isoformat(),
    "timezone": st.session_state.get("analysis_timezone", timezone),
    "model": model,
    "method": "verified binary markets only; actual user-supplied odds; uncalibrated AI estimates",
    "games": [flatten_row(r) for r in scored],
    "selected": [flatten_row(r) for r in selected],
}
json_data = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
csv_rows = [{**flatten_row(row), "sources": " ; ".join(row.get("sources") or [])} for row in scored]
export_left, export_right = st.columns(2)
with export_left:
    st.download_button("↓ Download JSON report", data=json_data,
                       file_name="black_wolf_analysis.json", mime="application/json", use_container_width=True)
with export_right:
    st.download_button("↓ Download CSV report", data=pd.DataFrame(csv_rows).to_csv(index=False).encode("utf-8-sig"),
                       file_name="black_wolf_analysis.csv", mime="text/csv", use_container_width=True)
st.markdown("""<div class="bw-footer">BLACK WOLF · RESEARCH FIRST. RISK ALWAYS. <br>
No live odds feed. No automatic bet placement. AI estimates are not statistically calibrated and cannot guarantee outcomes.</div>""", unsafe_allow_html=True)

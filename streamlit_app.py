"""Football Strategy | deploy on Streamlit Community Cloud.

All API calls occur server-side using an administrator-owned secret.
There is no live bookmaker feed, no automatic wager placement, and no guarantee.
"""
from __future__ import annotations

from datetime import datetime
from hmac import compare_digest
import io
import json
import os
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from ai_analysis import analyze_fixture
from engine import combos_in_range, expected_value, flatten_row, parse_schedule, shortlist


st.set_page_config(
    page_title="Football Strategy AI | تحلیل فوتبال",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""<style>
html, body, [data-testid="stApp"] { direction: rtl; }
.stApp { background: radial-gradient(ellipse at top, #142940, #0b1726 60%); }
.block-container { max-width: 1020px; padding-top: 1.25rem; padding-bottom: 3rem; }
.stMarkdown, .stText, .stCaption, label, h1, h2, h3 { text-align: right; }
[data-testid="stMetricValue"], [data-testid="stMetricDelta"], input[type="number"] { direction: ltr; text-align: left; }
[data-testid="stSidebar"] { direction: rtl; }
@media (max-width: 640px) {
    .block-container { padding: 0.75rem 0.8rem 3rem; }
    h1 { font-size: 1.6rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.35rem; }
}
</style>""", unsafe_allow_html=True)


def secret(name: str, default: str = "") -> str:
    """Read secure server config; never expose value in the UI or exports."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, OSError, KeyError):
        return default


def login_gate() -> bool:
    password = secret("APP_PASSWORD")
    if not password or password == "a-unique-long-password":
        st.error("مدیر سایت هنوز APP_PASSWORD را در تنظیمات امن سرور ثبت نکرده است.")
        return False
    if st.session_state.get("logged_in", False):
        return True
    st.title("⚽ ورود به تحلیل‌گر فوتبال")
    st.caption("دسترسی به تحلیل آنلاین خصوصی است تا هزینه API توسط افراد ناشناس مصرف نشود.")
    with st.form("login_form"):
        entered = st.text_input("رمز ورود سایت", type="password")
        submitted = st.form_submit_button("ورود", use_container_width=True, type="primary")
    if submitted:
        if compare_digest(entered.encode("utf-8"), password.encode("utf-8")):
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("رمز ورود نادرست است.")
    return False


if not login_gate():
    st.stop()

key = secret("OPENAI_API_KEY")
model = secret("OPENAI_MODEL", "gpt-5-mini").strip()
now = datetime.now(ZoneInfo("Europe/Berlin"))

with st.sidebar:
    st.markdown("### تنظیمات استراتژی")
    price_low, price_high = st.slider(
        "بازه ضریب موردنظر", min_value=1.2, max_value=4.0,
        value=(1.65, 1.95), step=0.05,
    )
    min_score = st.slider("حداقل امتیاز تحلیل (از ۲۵)", 0, 25, value=20)
    min_ev_pct = st.slider("حداقل EV تخمینی", 0, 25, value=3, step=1, format="%d%%")
    st.caption("این آستانه‌ها قراردادی هستند و اثبات‌کننده سودآوری نیستند.")
    if st.button("خروج از حساب", use_container_width=True):
        for item in list(st.session_state.keys()):
            del st.session_state[item]
        st.rerun()

st.title("⚽ Football Strategy AI")
st.caption("تحلیل آنلاین مسابقات با منابع به‌روز · استراتژی ۱۸ ← ۸ ← ۳ · مناسب موبایل")
st.info("AI ممکن است اشتباه کند. برنامه برای ضریب ۱.۸۰ بازار را تحریف نمی‌کند؛ ابتدا شواهد بررسی می‌شود و سپس شما ضریب واقعی را وارد می‌کنید.")

s1, s2, s3 = st.columns(3)
with s1:
    st.metric("بازی در هر نوبت", "۱۸ حداکثر")
with s2:
    st.metric("فهرست نهایی", "۸ حداکثر")
with s3:
    st.metric("مدل تحلیل", "AI + Web")

st.subheader("۱. لیست بازی‌ها")
with st.expander("فرمت‌های قابل قبول", expanded=False):
    st.code("آرسنال - بایرن | 2026-11-05 21:00\nاینتر - پورتو | 2026-11-05 23:00", language="text")
    st.write("یا از سایت مسابقات کپی کن و برای هر بازی نام میزبان، ساعت و نام مهمان را در سه خط جدا قرار بده. عنوان «لیگ قهرمانان» نادیده گرفته می‌شود.")
    st.caption("نام‌ها و زمان‌های داخل نمونه صرفاً آموزشی‌اند و وجود آن مسابقات تأیید نشده است.")

match_day = st.date_input("تاریخ پیش‌فرض برای بازی‌هایی که تاریخ ندارند", value=now.date(),
                          help="برای هر شب، تاریخ موردنظر را جداگانه مشخص کن.")
timezone = st.selectbox("منطقه زمانی ساعت‌های ورودی", ["Europe/Berlin", "Asia/Tehran", "UTC"], index=0,
                        format_func=lambda x: {"Europe/Berlin": "اروپا/برلین", "Asia/Tehran": "ایران/تهران", "UTC": "UTC"}[x])
input_text = st.text_area("بازی‌ها را اینجا بچسبان", height=170,
                          placeholder="کومو - منچستر یونایتد\nلیل - گالاتاسرای\n...",
                          help="در فرم یک‌خطی، برای جدا کردن نام تیم‌ها از « - » استفاده کن.")
csv_file = st.file_uploader("یا CSV با ستون‌های home, away, kickoff", type=["csv"])


def current_matches() -> list[dict]:
    if csv_file is not None:
        data = csv_file.getvalue().decode("utf-8-sig")
        df = pd.read_csv(io.StringIO(data)).fillna("")
        if not {"home", "away"}.issubset(df.columns):
            raise ValueError("CSV باید دو ستون home و away داشته باشد؛ kickoff اختیاری است.")
        text = "\n".join(
            f"{str(row['home']).strip()} - {str(row['away']).strip()} | "
            f"{str(row.get('kickoff') or match_day.isoformat()).strip()}"
            for _, row in df.iterrows()
        )
        return parse_schedule(text, fallback_date=match_day.isoformat())
    return parse_schedule(input_text, fallback_date=match_day.isoformat())

st.caption("در هر بازی یک درخواست پژوهش آنلاین اجرا می‌شود که ممکن است هزینه API داشته باشد.")
acknowledge = st.checkbox("هزینه درخواست‌های هوش مصنوعی را می‌دانم و تأیید می‌کنم.")
usage_count = st.session_state.get("used_calls", 0)
st.caption(f"درخواست‌های انجام‌شده در این نشست: {usage_count} از سقف ۳۶")
can_analyze = bool(key) and acknowledge and usage_count < 36
if not key:
    st.error("مدیر سایت هنوز OPENAI_API_KEY را در بخش Secrets تنظیم نکرده است.")

if st.button("🔎 شروع تحلیل هوش مصنوعی", type="primary", use_container_width=True, disabled=not can_analyze):
    try:
        matches = current_matches()
        if not matches:
            st.warning("حداقل یک مسابقه وارد کن.")
        elif len(matches) > 18:
            st.error("در هر بار حداکثر ۱۸ مسابقه مجاز است؛ فهرست را به چند نوبت تقسیم کن.")
        elif len(matches) + usage_count > 36:
            st.error("سقف درخواست‌های این نشست تمام می‌شود؛ یک نوبت کوچک‌تر انتخاب کن.")
        else:
            from openai import OpenAI

            client = OpenAI(api_key=key, timeout=90.0, max_retries=1)
            progress = st.progress(0, text="آماده‌سازی")
            output = []
            for i, match in enumerate(matches):
                progress.progress(i / len(matches), text=f"{i+1}/{len(matches)} — {match['home']} / {match['away']}")
                st.session_state.used_calls = st.session_state.get("used_calls", 0) + 1
                try:
                    output.append(analyze_fixture(
                        client, model, match, now.isoformat(timespec="minutes"),
                        input_timezone=timezone,
                    ))
                except Exception:
                    output.append({
                        "game": f"{match['home']} – {match['away']}",
                        "kickoff": match["kickoff"], "verified": False, "status": "error",
                        "competition": "", "market": "", "market_type": "none",
                        "score": 0, "probability_pct": None, "odds": None,
                        "rationale": "", "recent_evidence": "", "team_news": "",
                        "fixture_evidence": "", "risks": "خطا در درخواست آنلاین؛ این مسابقه به فهرست نهایی وارد نشد.",
                        "sources": [],
                    })
            progress.progress(1.0, text="تحلیل کامل شد")
            st.session_state.analysis = output
            st.session_state.analysis_timezone = timezone
            st.session_state.run_id = st.session_state.get("run_id", 0) + 1
            st.success(f"{len(output)} بازی بررسی شد. جزئیات و لینک منابع را پایین ببین.")
    except (ValueError, UnicodeDecodeError) as err:
        st.error(f"اشکال در لیست ورودی: {err}")

if "analysis" not in st.session_state:
    st.caption("بعد از تحلیل، برای هر مسابقه یک توضیح فارسی و لینک منبع می‌بینی و می‌توانی ضریب واقعی بازار را وارد کنی.")
    st.stop()

st.divider()
st.subheader("۲. گزارش AI و ورود ضرایب واقعی")
st.caption("بازارهای پیشنهادی فقط دوحالته هستند؛ شرط‌های دارای برگشت پول یا نیم‌برد به مدل EV ساده وارد نمی‌شوند.")
scored = []
for i, row in enumerate(st.session_state.analysis):
    status = "تأیید اولیه" if row.get("verified") else "تأییدنشده"
    score = row.get("score", 0)
    with st.expander(f"{i+1}. {row['game']} | {status} | {score}/۲۵", expanded=i == 0):
        st.write(f"**تاریخ/زمان ورودی:** {row.get('kickoff','—')} ({st.session_state.get('analysis_timezone', timezone)})")
        st.write(f"**رقابت:** {row.get('competition') or 'تأیید نشده'}")
        st.write(f"**وضعیت برنامه:** {row.get('fixture_evidence') or 'شواهد کافی در دسترس نیست'}")
        st.write(f"**فرم اخیر:** {row.get('recent_evidence') or 'نامشخص'}")
        st.write(f"**ترکیب و غایبان:** {row.get('team_news') or 'نامشخص'}")
        st.write(f"**بازار پیشنهادی:** {row.get('market') or 'فعلاً هیچ‌کدام'}")
        st.write(f"**منطق:** {row.get('rationale') or 'اطلاعات کافی پیدا نشد'}")
        st.write(f"**ریسک:** {row.get('risks') or 'نامشخص'}")
        sources = row.get("sources") or []
        if sources:
            st.markdown("**منابع پژوهش:**")
            for j, source in enumerate(sources[:5], 1):
                st.markdown(f"[{j}. مشاهده منبع]({source})")
        else:
            st.warning("منبع قابل ارائه پیدا نشد؛ این مسابقه قابل انتخاب نیست.")
        if not row.get("verified") or not row.get("market"):
            st.warning("برای این بازی پیشنهاد قابل اتکا ثبت نشد. ضریب وارد نکن.")
            priced = None
            probability = None
        else:
            left, right = st.columns(2)
            with left:
                priced = st.number_input("ضریب واقعی همین بازار", min_value=1.01, max_value=50.0,
                                         step=0.01, value=None, format="%.2f",
                                         key=f"price_{st.session_state.run_id}_{i}")
            with right:
                suggestion = row.get("probability_pct")
                probability = st.number_input("احتمال تخمینی (%)", min_value=1.0,
                                               max_value=99.0, step=0.5,
                                               value=float(suggestion) if suggestion is not None else None,
                                               key=f"prob_{st.session_state.run_id}_{i}")
            if priced and probability:
                ev = expected_value(priced, probability)
                if ev is not None:
                    st.caption(f"احتمال ضمنی: {100/priced:.1f}٪ | EV محاسبه‌شده: {ev*100:+.1f}٪ — وابسته به دقت احتمال تخمینی")
    record = {**row, "odds": priced, "probability_pct": probability}
    record["ev"] = expected_value(priced, probability)
    scored.append(record)

st.divider()
st.subheader("۳. رتبه‌بندی استراتژی")
selected = shortlist(scored, min_odd=price_low, max_odd=price_high,
                     min_score=min_score, min_ev=min_ev_pct / 100,
                     max_count=8)
if selected:
    st.success(f"{len(selected)} گزینه از معیارها عبور کردند؛ این به معنی تضمین برد نیست.")
    rank_df = pd.DataFrame([{
        "ردیف": i + 1,
        "مسابقه": r["game"], "بازار": r["market"],
        "ضریب": round(float(r["odds"]), 2),
        "امتیاز": int(r["score"]),
        "EV تخمینی (%)": round(float(r["ev"]) * 100, 1),
    } for i, r in enumerate(selected)])
    st.dataframe(rank_df, hide_index=True, use_container_width=True)
    st.markdown("**حداکثر ۳ گزینه اول برای بررسی تکی:**")
    for row in selected[:3]:
        st.write(f"• {row['game']}: {row['market']} — ضریب {row['odds']:.2f}")
    combos = combos_in_range(selected, min_total=2, max_total=3, max_legs=3)
    if combos:
        combo = combos[0]
        st.write(f"**میکس اختیاری:** {' + '.join(combo['games'])} | ضریب کل {combo['odds']:.2f}")
        st.caption("احتمال میکس بررسی نشده و ممکن است بین بازارها همبستگی وجود داشته باشد؛ میکس الزامی نیست.")
else:
    st.warning("هیچ بازی‌ای با ضریب واردشده و آستانه‌های فعلی معیارها را پاس نکرد. «بدون انتخاب» کاملاً مجاز است.")

st.subheader("۴. دریافت خروجی")
report = {
    "created_at": now.isoformat(), "timezone": st.session_state.get("analysis_timezone", timezone), "model": model,
    "method": "binary markets only; user prices; AI probability is uncalibrated",
    "games": [flatten_row(r) for r in scored],
    "selected": [flatten_row(r) for r in selected],
}
st.download_button("دانلود گزارش JSON", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
                   file_name="football_strategy_ai_report.json", mime="application/json",
                   use_container_width=True)
csv_rows = [{**flatten_row(r), "sources": " ; ".join(r.get("sources") or [])} for r in scored]
st.download_button("دانلود گزارش CSV", pd.DataFrame(csv_rows).to_csv(index=False).encode("utf-8-sig"),
                   file_name="football_strategy_ai_report.csv", mime="text/csv",
                   use_container_width=True)
st.caption("این برنامه داده‌های لحظه‌ای ضرایب را دریافت نمی‌کند و هیچ شرطی را به‌صورت خودکار ثبت نمی‌کند. مبلغ قابل‌از‌دست‌دادن را محدود نگه دار.")

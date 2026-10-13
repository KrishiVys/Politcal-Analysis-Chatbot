#!/usr/bin/env python3
"""
Campen Political Analysis Chatbot -- local web UI for updatedcode.py
=======================================================================

A chat-style interface for the same agent you use from the command line.
It calls updatedcode.py's gather_report() directly, so the analysis logic
(Brave-primary/X-backup, GDELT + Google News fallback, politician and party
briefings, relevance filtering, etc.) is identical to the CLI.
This file only adds the interface on top.

SETUP
    pip install streamlit
    (plus what updatedcode.py needs: requests, beautifulsoup4, sarvamai,
    and optionally reportlab for PDF export)
    API keys: a .env file in this folder, or environment variables.

RUN
    streamlit run app.py
    (if that command isn't found:  python -m streamlit run app.py)
    Opens at http://localhost:8501 and runs entirely on your own machine.

NOTES
    Single-user and local. Each new search runs the full pipeline and uses
    the same API quota as a CLI run, except when an identical search from
    the last 30 minutes is reused (see "Reuse recent results").
"""

import os
import re
import glob
import html
import time
import contextlib
import hmac
from datetime import datetime, timedelta

import streamlit as st

import updatedcode as uc

st.set_page_config(page_title="Campen Political Analysis Chatbot", page_icon="🏛️", layout="wide")


def _load_secrets_into_env() -> None:
    """When deployed (e.g. Streamlit Community Cloud), API keys are entered as
    Streamlit "Secrets" rather than a .env file. Copy the simple top-level
    ones into the environment, where the rest of the code looks for them.
    Anything already set in the environment (or .env) wins. Locally, with no
    secrets file, this does nothing."""
    try:
        items = dict(st.secrets)
    except Exception:
        return
    for key, value in items.items():
        if isinstance(value, (str, int, float)) and str(value).strip() and key not in os.environ:
            os.environ[key] = str(value)


_load_secrets_into_env()

# Optional password screen. Once the app is online, anyone with the link could
# otherwise run searches on YOUR API keys. Set APP_PASSWORD (in Secrets or .env)
# to require it; leave it unset for local use.
_app_password = os.environ.get("APP_PASSWORD", "")
if _app_password and not st.session_state.get("auth_ok"):
    st.markdown("### 🔒 Campen Political Analysis Chatbot")
    entered = st.text_input("Password", type="password", key="app_password_input")
    if entered:
        if hmac.compare_digest(entered.encode("utf-8"), _app_password.encode("utf-8")):
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

# app.py and updatedcode.py must be from the same version. If an older
# updatedcode.py is in the folder (or an old copy is still loaded in a running
# app), stop with clear instructions instead of failing mid-search.
if (not hasattr(uc, "resolve_subject") or not hasattr(uc, "build_top_stories") or not hasattr(uc, "gather_daily_wrap")
        or not hasattr(uc, "resolve_wrap_party")):
    st.error(
        "**Version mismatch:** this app.py is newer than the updatedcode.py it found at:\n\n"
        f"`{getattr(uc, '__file__', 'unknown location')}`\n\n"
        "To fix it:\n"
        "1. Download the latest **updatedcode.py** and save it over the old one in that same folder.\n"
        "2. Stop the app: click the terminal running it and press **Ctrl+C**.\n"
        "3. Start it again: `python -m streamlit run app.py`"
    )
    st.stop()

EXAMPLE_POLITICIANS = ["Narendra Modi", "KCR", "Rahul Gandhi", "Mamata Banerjee"]
EXAMPLE_PARTIES = ["BJP", "Congress", "BRS", "TDP"]
REPORT_TYPES = {"Auto-detect": "auto", "Politician": "politician", "Political party": "party"}
CACHE_TTL_MINUTES = 30
NO_DATA_TEXT = getattr(uc, "EMPTY_SECTION_TEXT", "Nothing reported in this period.")

# Source presets. Each source key maps to a gather_report() "no_*" flag.
SOURCE_INFO = {
    "reddit": ("Reddit", "Free. Public discussion threads."),
    "youtube": ("YouTube", "Free (needs a YouTube key for search). Videos plus configured official channels."),
    "telegram": ("Telegram", "Free. Needs channels listed in politician_handles.json, otherwise skipped."),
    "ads": ("Facebook/Instagram ads", "Free via Meta's Ad Library. Paid political ads only, not organic posts."),
    "social_news": ("News about their social posts", "Free. News stories about something they posted."),
    "brave": ("Brave search (primary social)", "Paid. Searches X/Instagram/Facebook/YouTube for public posts."),
    "x": ("X / Twitter API (backup)", "Paid per post. Only called when Brave finds too few X results."),
}
PRESETS = {
    "All sources (recommended)": set(SOURCE_INFO),
    "Free sources only": {"reddit", "youtube", "telegram", "ads", "social_news"},
    "News only": set(),
}

# Progress messages printed by gather_report(), in pipeline order, mapped to
# plain-language step names for the progress bar.
PROGRESS_STEPS = [
    ("Gathering data on", "Starting"),
    ("News headlines...", "Searching news"),
    ("Reddit...", "Checking Reddit"),
    ("YouTube search (API)...", "Searching YouTube"),
    ("YouTube channel feeds (RSS)...", "Reading official YouTube channels"),
    ("Telegram channels...", "Reading Telegram channels"),
    ("Facebook/Instagram ads (Meta)...", "Checking the Meta ad library"),
    ("News about their social posts...", "Finding news about their posts"),
    ("Search-indexed posts (Brave)", "Searching social media via Brave"),
    ("X / Twitter (API)", "Checking the X backup"),
    ("Asking Sarvam AI", "Writing the summary"),
    ("Using a template summary", "Writing the summary"),
]

CUSTOM_CSS = """
<style>
.campen-header {
    padding: 1.25rem 1.5rem; border-radius: 12px; margin-bottom: 1rem;
    background: linear-gradient(135deg, #0f2746 0%, #1a3a63 55%, #6b1f2a 100%);
    color: #f5f5f5;
}
.campen-header h1 { margin: 0; font-size: 1.6rem; color: #ffffff; }
.campen-header p { margin: 0.3rem 0 0 0; color: #d7dde6; font-size: 0.92rem; }
.badge-row { margin: 0 0 0.6rem 0; }
.badge {
    display: inline-block; padding: 0.2rem 0.65rem; margin: 0 0.35rem 0.3rem 0;
    border-radius: 999px; font-size: 0.8rem; border: 1px solid rgba(128,128,128,0.35);
    background: rgba(128,128,128,0.06);
}
.topline-box {
    border-left: 4px solid #6b1f2a; background: rgba(107,31,42,0.07);
    padding: 0.75rem 1rem; border-radius: 6px; margin: 0.4rem 0 0.8rem 0;
}
.topline-box b { color: #9c2c3c; }
.category-card {
    border: 1px solid rgba(128,128,128,0.25); border-radius: 8px;
    padding: 0.7rem 0.9rem; margin-bottom: 0.6rem; background: rgba(128,128,128,0.03);
}
.category-card .cat-label { font-weight: 600; font-size: 0.88rem; opacity: 0.85; margin-bottom: 0.2rem; }
.category-card .cat-empty { font-style: italic; opacity: 0.55; }
.source-pill {
    display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px;
    font-size: 0.78rem; margin: 0.1rem 0.25rem 0.1rem 0; border: 1px solid rgba(128,128,128,0.3);
}
.source-pill.good { background: rgba(34,139,34,0.12); border-color: rgba(34,139,34,0.4); }
.source-pill.bad { background: rgba(128,128,128,0.08); }
.watch-box {
    border-left: 4px solid #1a5fb4; background: rgba(26,95,180,0.07);
    padding: 0.75rem 1rem; border-radius: 6px; margin: 0.4rem 0 0.8rem 0;
}
.watch-box b { color: #1a5fb4; }
.category-card.tone { border-color: rgba(156,44,60,0.45); }
.category-card.timeline { border-color: rgba(26,95,180,0.45); }
.category-card ul, .watch-box ul, .topline-box ul { margin: 0.2rem 0 0 1.1rem; padding: 0; }
</style>
"""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def is_good_status(value: str) -> bool:
    m = re.match(r"\d+", value.strip())
    return value in ("written", "found") or bool(m and int(m.group(0)) > 0)


def social_item_count(data: dict) -> int:
    return (len(data["x_posts"]) + len(data["youtube"]) + len(data["telegram"]) + len(data["reddit"])
            + sum(len(v) for v in data["indexed"].values()))


def window_text(result: dict) -> str:
    if result["start_date"] or result["end_date"]:
        return uc._range_text(result["start_date"], result["end_date"])
    return "Recent (last month)"


def categories_of(result: dict) -> list:
    """The report's own structure (politician or party)."""
    return result["narrative"].get("_categories") or uc.SUMMARY_CATEGORIES


def category_html(text: str, empty_text: str = NO_DATA_TEXT) -> str:
    """Escaped HTML for one category: a single flowing paragraph, matching
    the report's paragraph format (no bullet points)."""
    text = (text or "").strip()
    if not text:
        return f'<span class="cat-empty">{html.escape(empty_text)}</span>'
    return html.escape(text)


def summary_as_text(result: dict) -> str:
    narrative = result["narrative"]
    lines = [f"{result['name']} — {window_text(result)}", ""]
    topline = narrative.get(uc.TOPLINE_KEY, "").strip()
    lines += [f"{uc.TOPLINE_LABEL}: {topline or 'No single development stood out in the available coverage.'}", ""]
    for key, label, _ in categories_of(result):
        text = narrative.get(key, "").strip()
        lines += [label, text if text else NO_DATA_TEXT, ""]
    return "\n".join(lines).strip()


def matches(query: str, *fields) -> bool:
    if not query:
        return True
    q = query.lower()
    return any(q in (f or "").lower() for f in fields)


def set_progress(placeholder, fraction: float, text: str) -> None:
    try:
        placeholder.progress(fraction, text=text)
    except TypeError:  # older Streamlit versions without the text= argument
        placeholder.progress(fraction)


class ProgressLog:
    """Captures gather_report()'s print() output. Turns recognized progress
    messages into a plain-language progress bar, and keeps the full raw text
    for the "Technical log" expander."""

    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.buffer = ""
        self.fraction = 0.0
        set_progress(placeholder, 0.0, "Starting...")

    def write(self, text):
        self.buffer += text
        for i, (marker, friendly) in enumerate(PROGRESS_STEPS):
            if marker in text:
                self.fraction = max(self.fraction, min(0.95, (i + 1) / len(PROGRESS_STEPS)))
                set_progress(self.placeholder, self.fraction, f"{friendly}...")

    def flush(self):
        pass

    def getvalue(self):
        return self.buffer


# --------------------------------------------------------------------------
# Report rendering
# --------------------------------------------------------------------------

def render_badges(result: dict) -> None:
    kind = "🏳️ Political party" if result.get("subject_type") == "party" else "🧑‍💼 Politician"
    badges = [f"📌 {html.escape(result['name'])}", kind, f"🗓️ {html.escape(window_text(result))}"]
    query = result.get("_query", "")
    if query and query.lower() != result["name"].lower():
        badges.append(f"🔤 searched as “{html.escape(query)}”")
    if result.get("_generated_at"):
        badges.append(f"🕒 {result['_generated_at'].strftime('%d %b %Y, %H:%M')}")
    st.markdown('<div class="badge-row">' + "".join(f'<span class="badge">{b}</span>' for b in badges) + "</div>",
                unsafe_allow_html=True)


def render_summary_tab(result: dict) -> None:
    narrative, wiki, name = result["narrative"], result["wiki"], result["name"]
    if narrative.get("note"):
        st.warning(narrative["note"])
    for key, label, _ in categories_of(result):
        extra = {uc.TIMELINE_KEY: " timeline", uc.TONE_KEY: " tone"}.get(key, "")
        st.markdown(f'<div class="category-card{extra}"><div class="cat-label">{html.escape(label)}</div>'
                    f'{category_html(narrative.get(key, ""))}</div>', unsafe_allow_html=True)

    with st.expander("📋 Copy summary as plain text"):
        st.caption("Use the copy icon in the top-right corner of the box.")
        st.code(summary_as_text(result), language=None)

    with st.expander("Basic Details (Wikipedia)"):
        if not wiki.get("found"):
            st.info(f"Multiple people match '{name}' on Wikipedia. Try a more specific name."
                    if wiki.get("disambiguation") else "No Wikipedia page found for this name.")
        else:
            if wiki.get("description"):
                st.markdown(f"**{wiki['description']}**")
            if wiki.get("extract"):
                st.write(wiki["extract"])
            if wiki.get("page_url"):
                st.markdown(f"[Full Wikipedia page]({wiki['page_url']})")


def render_timeline_tab(data: dict) -> None:
    import pandas as pd  # installed with Streamlit

    day_index = uc.build_day_index(data)
    st.markdown("**Activity per day** (all sources combined)")
    if not day_index:
        st.info("No dated items to chart. Pick a Daily, Weekly, or Custom time window to see activity over time.")
    else:
        days = [d.split(" ")[0] for d, _ in day_index]
        st.bar_chart(pd.DataFrame({"Items": [c for _, c in day_index]}, index=days))
        busiest = max(day_index, key=lambda x: x[1])
        st.caption(f"Busiest day: {busiest[0]} with {busiest[1]} item(s).")

    st.markdown("**Items per source**")
    counts = {
        "News": len(data["headlines"]), "X (API)": len(data["x_posts"]), "YouTube": len(data["youtube"]),
        "Telegram": len(data["telegram"]), "Reddit": len(data["reddit"]), "Political ads": len(data["meta_ads"]),
        "News about posts": len(data["social_news"]),
    }
    for label, items in data["indexed"].items():
        counts[f"{label} (Brave)"] = len(items)
    counts = {k: v for k, v in counts.items() if v}
    if not counts:
        st.info("No items were found from any source.")
    else:
        st.bar_chart(pd.DataFrame({"Items": list(counts.values())}, index=list(counts.keys())))


def render_headlines_tab(result: dict, key_prefix: str) -> None:
    data, start_date, end_date = result["data"], result["start_date"], result["end_date"]
    query = st.text_input("Filter headlines", key=f"{key_prefix}_hl_filter",
                          placeholder="Type a word to filter, e.g. rally")
    headlines = [h for h in data["headlines"] if matches(query, h.get("headline"), h.get("source"))]
    if query:
        st.caption(f"Showing {len(headlines)} of {len(data['headlines'])} headlines.")
    if not headlines:
        st.write("No headlines match." if query else "No headlines found for this window.")
        return
    if start_date or end_date:
        for day_label, day_items in uc.group_headlines_by_day(headlines):
            st.markdown(f"**{day_label}**")
            for h in day_items:
                line = f"- [{h['headline']}]({h['url']})" if h.get("url") else f"- {h['headline']}"
                st.markdown(line + (f"  \n  *{h['source']}*" if h.get("source") else ""))
    else:
        for i, h in enumerate(headlines, 1):
            line = f"{i}. [{h['headline']}]({h['url']})" if h.get("url") else f"{i}. {h['headline']}"
            meta = " | ".join(filter(None, [h.get("source", ""), h.get("date", "")]))
            st.markdown(line + (f"  \n   *{meta}*" if meta else ""))


def render_social_tab(result: dict, key_prefix: str) -> None:
    data, status = result["data"], result["status"]
    query = st.text_input("Filter social & public items", key=f"{key_prefix}_soc_filter",
                          placeholder="Type a word to filter across all sections")
    for sec in uc.build_sections(data):
        items = [it for it in sec["items"] if matches(query, it["title"], it["body"], it["meta"])]
        if query and not items:
            continue  # hide sections with no matches while filtering
        label = f"{sec['title'].title()} ({len(items)})"
        with st.expander(label, expanded=bool(query)):
            if not items:
                st.write(uc._empty_note(sec, status))
            for i, it in enumerate(items, 1):
                st.markdown(f"{i}. [{it['title']}]({it['url']})" if it["url"] else f"{i}. {it['title']}")
                if it["body"]:
                    st.caption(it["body"])
                if it["meta"]:
                    st.caption(it["meta"])




def render_sources_tab(status: dict) -> None:
    pills = []
    for label, val in status.items():
        good = is_good_status(val)
        pills.append(f'<span class="source-pill {"good" if good else "bad"}">{"✅" if good else "⬜"} '
                     f"{html.escape(label)}: {html.escape(val)}</span>")
    st.markdown(" ".join(pills), unsafe_allow_html=True)
    st.caption("⬜ means the source was skipped, found nothing, or failed. The text explains which.")


def render_stories_tab(result: dict) -> None:
    stories = result.get("stories") or []
    if not stories:
        st.info("No news stories to group in this window.")
        return
    st.caption(uc.glance_text(result.get("glance") or uc.build_glance(result["data"], stories)))
    st.caption("The same story from several outlets is shown once, ranked by how many separate outlets carried it. "
               "Widely carried stories are usually the most significant; a single-outlet story is reported, not "
               "necessarily established.")
    for i, story in enumerate(stories, 1):
        n = len(story["outlets"])
        badge = "🟢" if n >= 3 else ("🟡" if n == 2 else "⚪")
        line = f"{i}. [{story['headline']}]({story['url']})" if story.get("url") else f"{i}. {story['headline']}"
        st.markdown(f"{line}  \n   {badge} *{uc.story_meta(story)}*")


def _card():
    """A bordered box for a highlighted section (plain container on older Streamlit)."""
    try:
        return st.container(border=True)
    except TypeError:
        return st.container()


def render_wrap(wrap: dict, key_prefix: str) -> None:
    n = wrap["narrative"]
    st.markdown(f"### 🗞️ {uc.wrap_title(wrap)}")
    notes = []
    if wrap["used_template"]:
        notes.append("Sarvam AI wasn't available, so each point is the story's own headline.")
    if any(pt["top"] for nn in n["states"].values() for pts in nn["points"].values() for pt in pts):
        notes.append(uc.WRAP_TOP_LEGEND)
    notes.append("Each point appears once; the outlet names beside it link to the articles.")
    st.caption(" ".join(notes))
    tabs = st.tabs([s_["label"] for s_ in wrap["states"]] + ["🔎 Sources Checked"])
    for tab, state in zip(tabs, wrap["states"]):
        with tab:
            sn = uc.wrap_state_narrative(wrap, state)
            st.caption(uc.glance_text(state["glance"]))
            if not state["stories"]:
                who = f"{state['party']} " if state.get("party") else ""
                st.info(f"No {who}news found for {state['label']} in this period.")
                continue
            starred, other = uc.wrap_sections_for_display(state, sn)
            for key, label, icon, pts in starred:
                with _card():
                    st.markdown(f"#### {icon} {label}" + (f"  ·  {len(pts)} point{'s' if len(pts) != 1 else ''}"
                                                          if pts else ""))
                    if not pts:
                        st.caption(uc.WRAP_EMPTY_HIGHLIGHT)
                    lines = []
                    for group, gpts in uc.wrap_point_groups(pts, key):
                        if group:
                            lines.append(f"- **{group}**")
                        lines += [("    - " if group else "- ") + uc.point_markdown(pt) for pt in gpts]
                    if lines:
                        st.markdown("\n".join(lines))
            if other:
                with st.expander("📰 Other news", expanded=True):
                    lines = []
                    for key, label, pts in other:
                        lines.append(f"- **{label}**")
                        lines += ["    - " + uc.point_markdown(pt) for pt in pts]
                    st.markdown("\n".join(lines))
    with tabs[-1]:
        render_sources_tab(wrap["status"])
    if n.get("what_to_watch"):
        st.markdown('<div class="watch-box"><b>👀 What to Watch</b><ul>'
                    + "".join(f"<li>{html.escape(w)}</li>" for w in n["what_to_watch"]) + "</ul></div>",
                    unsafe_allow_html=True)
    render_wrap_downloads(wrap, key_prefix)


def render_wrap_downloads(wrap: dict, key_prefix: str) -> None:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Prepare Markdown", key=f"{key_prefix}_wmd_btn"):
            path = uc.save_wrap_markdown(wrap)
            with open(path, "rb") as f:
                st.session_state[f"{key_prefix}_wmd"] = (os.path.basename(path), f.read())
        if f"{key_prefix}_wmd" in st.session_state:
            fname, content = st.session_state[f"{key_prefix}_wmd"]
            st.download_button("Download .md", content, file_name=fname, mime="text/markdown", key=f"{key_prefix}_wmd_dl")
    with col2:
        if uc.SimpleDocTemplate is None:
            st.caption("PDF export needs: pip install reportlab")
        else:
            if st.button("📑 Prepare PDF", key=f"{key_prefix}_wpdf_btn"):
                path = uc.save_wrap_pdf(wrap)
                with open(path, "rb") as f:
                    st.session_state[f"{key_prefix}_wpdf"] = (os.path.basename(path), f.read())
            if f"{key_prefix}_wpdf" in st.session_state:
                fname, content = st.session_state[f"{key_prefix}_wpdf"]
                st.download_button("Download .pdf", content, file_name=fname, mime="application/pdf",
                                   key=f"{key_prefix}_wpdf_dl")


def render_report(result: dict, key_prefix: str) -> None:
    data, narrative, status = result["data"], result["narrative"], result["status"]
    render_badges(result)

    glance = result.get("glance") or {}
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Headlines", len(data["headlines"]))
    m2.metric("Multi-outlet stories", glance.get("multi_outlet", 0),
              help="Distinct stories carried by more than one outlet -- usually the period's most significant.")
    m3.metric("Social / Public Items", social_item_count(data))
    m4.metric("Political Ads", len(data["meta_ads"]))
    m5.metric("Sources With Data", f"{sum(1 for v in status.values() if is_good_status(v))}/{len(status)}")

    topline = narrative.get(uc.TOPLINE_KEY, "").strip()
    glance_left, glance_right = st.columns([3, 2])
    glance_left.markdown(f'<div class="topline-box"><b>{html.escape(uc.TOPLINE_LABEL)}</b><br>'
                         f'{html.escape(topline) if topline else "<i>No single development stood out in the available coverage.</i>"}</div>',
                         unsafe_allow_html=True)
    glance_right.markdown(f'<div class="watch-box"><b>👀 What to Watch</b><br>'
                          f'{category_html(narrative.get("upcoming", ""), "Nothing scheduled in the available data.")}</div>',
                          unsafe_allow_html=True)

    tabs = st.tabs(["📋 Summary", f"⭐ Top Stories ({len(result.get('stories') or [])})", "📈 Timeline",
                    f"📰 Headlines ({len(data['headlines'])})", "📣 Social & Public", "🔎 Sources Checked"])
    with tabs[0]:
        render_summary_tab(result)
    with tabs[1]:
        render_stories_tab(result)
    with tabs[2]:
        render_timeline_tab(data)
    with tabs[3]:
        render_headlines_tab(result, key_prefix)
    with tabs[4]:
        render_social_tab(result, key_prefix)
    with tabs[5]:
        render_sources_tab(status)


def render_downloads(result: dict, key_prefix: str) -> None:
    col1, col2 = st.columns(2)
    args = (result["name"], result["wiki"], result["data"], result["narrative"],
            result["start_date"], result["end_date"], result["status"], result["used_template"],
            result.get("stories"))
    with col1:
        if st.button("📄 Prepare Markdown", key=f"{key_prefix}_md_btn"):
            path = uc.save_markdown(*args)
            with open(path, "rb") as f:
                st.session_state[f"{key_prefix}_md"] = (os.path.basename(path), f.read())
        if f"{key_prefix}_md" in st.session_state:
            fname, content = st.session_state[f"{key_prefix}_md"]
            st.download_button("Download .md", content, file_name=fname, mime="text/markdown", key=f"{key_prefix}_md_dl")
    with col2:
        if uc.SimpleDocTemplate is None:
            st.caption("PDF export needs: pip install reportlab")
        else:
            if st.button("📑 Prepare PDF", key=f"{key_prefix}_pdf_btn"):
                path = uc.save_pdf(*args)
                with open(path, "rb") as f:
                    st.session_state[f"{key_prefix}_pdf"] = (os.path.basename(path), f.read())
            if f"{key_prefix}_pdf" in st.session_state:
                fname, content = st.session_state[f"{key_prefix}_pdf"]
                st.download_button("Download .pdf", content, file_name=fname, mime="application/pdf", key=f"{key_prefix}_pdf_dl")


def render_empty_notice(result: dict) -> None:
    st.info(f"No data was found for '{result['name']}' in this window. Things to try: check the spelling, "
            "use a more specific name, widen the time window, or enable more sources in the sidebar.")


def render_assistant_message(msg: dict, key_prefix: str) -> None:
    """Shared by the live turn and history replay, so widget keys match on reruns
    (that is what makes buttons like "Run fresh" and the downloads work)."""
    if msg.get("kind") == "wrap":
        wrap = msg["wrap"]
        if msg.get("from_cache"):
            c1, c2 = st.columns([4, 1])
            c1.info(f"♻️ Reused a wrap-up from {msg.get('cache_age_min', 0)} minute(s) ago, so no new API calls were made.")
            if c2.button("🔄 Run fresh", key=f"{key_prefix}_fresh"):
                st.session_state.force_fresh = True
                st.session_state.trigger_prompt = wrap.get("_query") or "daily wrap"
                st.session_state.trigger_wrap_range = (wrap["start_day"], wrap["end_day"])
                st.session_state.trigger_wrap_party = (wrap.get("party") or {}).get("name", "")
                st.rerun()
        render_wrap(wrap, key_prefix)
        return
    result = msg["result"]
    if msg.get("from_cache"):
        c1, c2 = st.columns([4, 1])
        c1.info(f"♻️ Reused a result from {msg.get('cache_age_min', 0)} minute(s) ago, so no new API calls were made.")
        if c2.button("🔄 Run fresh", key=f"{key_prefix}_fresh"):
            st.session_state.force_fresh = True
            st.session_state.trigger_prompt = result.get("_query") or result["name"]
            st.rerun()
    if msg.get("is_empty"):
        render_empty_notice(result)
        return
    render_report(result, key_prefix)
    render_downloads(result, key_prefix)


# --------------------------------------------------------------------------
# Header + sidebar
# --------------------------------------------------------------------------

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
st.markdown(
    '<div class="campen-header"><h1>🏛️ Campen Political Analysis Chatbot</h1>'
    '<p>Daily and weekly briefings on Indian politicians (e.g. "KCR") and political parties (e.g. "BJP"), '
    "plus a daily news wrap-up for Andhra Pradesh and Telangana. Runs locally, using the sources you choose "
    "in the sidebar.</p></div>",
    unsafe_allow_html=True,
)

for key, default in [("messages", []), ("trigger_prompt", None), ("result_cache", {}),
                     ("recent_queries", []), ("force_fresh", False), ("trigger_wrap_range", None),
                     ("trigger_wrap_party", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

WRAP_CHOICES = {"Andhra Pradesh & Telangana": "both", "Andhra Pradesh": "andhra pradesh", "Telangana": "telangana"}
WRAP_PARTY_CHOICES = ["All news", "BRS", "Congress", "BJP", "TDP", "YSRCP", "Jana Sena", "AIMIM", "CPI", "CPI(M)",
                      "Other party…"]

with st.sidebar:
    st.header("⚙️ Settings")

    st.subheader("🗞️ News wrap-up")
    wrap_label = st.selectbox("States", list(WRAP_CHOICES), key="opt_wrap_states",
                              help="A general round-up of the news -- not about any one politician. Government & "
                                   "cabinet decisions, policy & legislation, ministries & departments, and court "
                                   "rulings are highlighted first, then the rest of the news.")
    wrap_focus = st.selectbox("Focus", WRAP_PARTY_CHOICES, key="opt_wrap_party",
                              help="All news, or a wrap-up about one party in these states: news naming the party or "
                                   "its leaders (and, for the party leading a state's government, that government's "
                                   "decisions), with party politics highlighted first.")
    wrap_party = ""
    if wrap_focus == "Other party…":
        wrap_party = st.text_input("Party name", key="opt_wrap_party_other", placeholder="e.g. AAP").strip()
    elif wrap_focus != "All news":
        wrap_party = wrap_focus
    today_ist = uc.ist_today()
    wrap_period = st.radio("Period", ["Single day", "Date range"], horizontal=True, key="opt_wrap_period")
    if wrap_period == "Single day":
        wrap_start = wrap_end = st.date_input("Day", value=today_ist, max_value=today_ist, key="opt_wrap_day")
    else:
        c1, c2 = st.columns(2)
        wrap_start = c1.date_input("From", value=today_ist - timedelta(days=6), max_value=today_ist,
                                   key="opt_wrap_from")
        wrap_end = c2.date_input("To", value=today_ist, max_value=today_ist, key="opt_wrap_to")
    wrap_range_error = None
    try:
        wrap_days = uc.validate_wrap_range(wrap_start, wrap_end)
        if wrap_days > 1:
            st.caption(f"{wrap_days} days -- the summary covers the whole period, not just the latest day.")
    except ValueError as e:
        wrap_range_error = str(e)
        st.error(wrap_range_error)
    if st.button("🗞️ Generate wrap-up", use_container_width=True, key="wrap_btn", disabled=bool(wrap_range_error)):
        who = f"{wrap_party} " if wrap_party else ""
        st.session_state.trigger_prompt = (f"{who}Daily wrap-up: {wrap_label}" if wrap_start == wrap_end else
                                           f"{who}News wrap-up: {wrap_label}, {uc.wrap_period_text(wrap_start, wrap_end)}")
        st.session_state.trigger_wrap_range = (wrap_start, wrap_end)
        st.session_state.trigger_wrap_party = wrap_party
        st.rerun()
    st.caption("Or type in the chat box: \"daily wrap\", \"daily wrap telangana\", \"yesterday's AP roundup\", "
               "\"weekly wrap\", \"wrap-up last 5 days\" -- or for a party: \"BRS wrap\", \"TDP weekly wrap-up\".")

    st.divider()
    st.subheader("📋 Politician / party report")

    report_type = st.radio("Report type", list(REPORT_TYPES),
                           help="Auto-detect recognizes major Indian parties (BJP, Congress, BRS, TDP, AAP, TMC, DMK...). "
                                "Pick 'Political party' for a party that isn't recognized automatically.")
    subject_mode = REPORT_TYPES[report_type]

    window = st.radio(
        "Time window", ["Recent (no date filter)", "Daily (last 1 day)", "Weekly (last 7 days)", "Custom range"],
        help="Recent uses roughly the last month of news. Daily, Weekly, and Custom also limit social sources to that window.",
    )
    custom_start = custom_end = None
    date_error = None
    if window == "Custom range":
        c1, c2 = st.columns(2)
        custom_start = c1.date_input("From", value=datetime.now().date() - timedelta(days=7))
        custom_end = c2.date_input("To", value=datetime.now().date())
        if custom_start and custom_end and custom_start > custom_end:
            date_error = "'From' must be on or before 'To'."
            st.error(date_error)

    st.divider()
    preset = st.radio("Sources", list(PRESETS) + ["Custom"],
                      help="Presets pick sources for you. Choose Custom to switch individual sources on or off.")
    if preset == "Custom":
        enabled = {key for key, (label, tip) in SOURCE_INFO.items() if st.checkbox(label, value=True, help=tip)}
    else:
        enabled = set(PRESETS[preset])
        st.caption("Included: " + (", ".join(SOURCE_INFO[k][0] for k in SOURCE_INFO if k in enabled)
                                   if enabled else "news headlines and basic details only"))

    x_always = False
    brave_platforms = list(uc.PLATFORMS)
    if "brave" in enabled or "x" in enabled:
        with st.expander("Advanced social options"):
            if "brave" in enabled:
                brave_platforms = st.multiselect("Brave: platforms to search", list(uc.PLATFORMS),
                                                 default=list(uc.PLATFORMS), format_func=lambda k: uc.PLATFORMS[k][0])
            if "x" in enabled:
                x_always = st.checkbox("Always call the X API", value=False,
                                       help="Skips the cost-saving backup logic and calls the X API on every search.")

    headlines_limit = st.slider("Max headlines (Recent window only)", 5, 30, 10,
                                help="Date-range searches always fetch as many headlines as exist.")
    use_cache = st.checkbox(f"Reuse results from the last {CACHE_TTL_MINUTES} minutes", value=True,
                            help="Repeating the exact same search shows the earlier result instead of spending API quota again.")

    if st.session_state.recent_queries:
        st.divider()
        st.subheader("🕘 Recent searches")
        for i, q in enumerate(st.session_state.recent_queries):
            if st.button(q, key=f"recent_q_{i}", use_container_width=True):
                st.session_state.trigger_prompt = q
                st.rerun()

    st.divider()
    sarvam_key = os.environ.get("SARVAM_API_KEY")
    key_help = {
        "SARVAM_API_KEY": ("written summary", "https://dashboard.sarvam.ai"),
        "BRAVE_API_KEY": ("Brave search", "https://brave.com/search/api"),
        "X_BEARER_TOKEN": ("X backup", "https://developer.x.com"),
        "YOUTUBE_API_KEY": ("YouTube search", "https://console.cloud.google.com"),
        "META_ACCESS_TOKEN": ("Meta ads", "https://developers.facebook.com"),
    }
    keys_set = sum(1 for var in key_help if os.environ.get(var))
    with st.expander(f"🔑 Setup check ({keys_set}/{len(key_help)} keys set)", expanded=keys_set == 0):
        for var, (what, url) in key_help.items():
            if os.environ.get(var):
                st.markdown(f"✅ {var} — {what}")
            else:
                st.markdown(f"⬜ {var} — {what}  \n&nbsp;&nbsp;&nbsp;[Get a key →]({url})", unsafe_allow_html=True)
        st.markdown(f"{'✅' if uc.SimpleDocTemplate else '⬜'} reportlab — PDF export"
                    + ("" if uc.SimpleDocTemplate else "  \n&nbsp;&nbsp;&nbsp;Run: `pip install reportlab`"),
                    unsafe_allow_html=True)
        cfg = uc.load_config(uc.CONFIG_PATH)
        st.markdown(f"✅ {uc.CONFIG_PATH} — {len(cfg)} politician(s) configured" if cfg
                    else f"⬜ {uc.CONFIG_PATH} — not found (Telegram and YouTube channel feeds need it)")

    saved = sorted(glob.glob(os.path.join("reports", "*.*")), key=os.path.getmtime, reverse=True)[:8]
    with st.expander(f"📁 Saved reports ({len(saved)})"):
        if not saved:
            st.caption("Markdown and PDF files you prepare will show up here.")
        for path in saved:
            fname = os.path.basename(path)
            with open(path, "rb") as f:
                st.download_button(fname, f.read(), file_name=fname, key=f"saved_{fname}")

    st.divider()
    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# --------------------------------------------------------------------------
# Chat area
# --------------------------------------------------------------------------

with st.expander("ℹ️ How this works"):
    st.markdown(
        "1. Type a **politician** (like \"KCR\") or a **political party** (like \"BJP\", \"Congress\") below, "
        "or click an example. Known parties are detected automatically; use **Report type** in the sidebar to override.\n"
        "2. Pick a **time window** and a **source preset** in the sidebar.\n"
        "3. The bot gathers news and social data, then writes a briefing: a top line, a dated timeline of key "
        "developments, the main areas of activity, media & public sentiment, and what to watch next. "
        "Politicians and parties each get their own set of sections.\n"
        "4. Use the tabs to see the top stories (the same story from several outlets grouped together, most "
        "widely carried first), the timeline, headlines, and social posts, and download the report as Markdown or PDF.\n"
        "5. For a **news wrap-up of Andhra Pradesh and/or Telangana** -- one day or a date range of up to 31 days -- "
        "use the wrap-up section at the top of the sidebar, or type \"daily wrap\" / \"weekly wrap\" in the chat box. "
        "Set **Focus** to a party (or type e.g. \"BRS wrap\") for a wrap-up about that party in these states.\n\n"
        "Paid sources (Sarvam, Brave, X) use real API quota on every new search. "
        "Use the **Free sources only** preset to avoid that, apart from the Sarvam summary."
    )

client = uc.SarvamAI(api_subscription_key=sarvam_key) if (uc.SarvamAI and sarvam_key) else None


def run_wrap_turn(query: str, choice: str, start_day, end_day, key_prefix: str, party: str = "") -> None:
    """One chat turn for the news wrap-up (one day or a date range): reuse a
    recent identical one if allowed, otherwise gather it, show it, and add it
    to the history."""
    try:
        uc.validate_wrap_range(start_day, end_day)
        uc.resolve_wrap_party(party)
    except ValueError as e:
        text = f"Can't build that wrap-up: {e}"
        st.error(text)
        st.session_state.messages.append({"role": "assistant", "content": text, "error": True})
        return
    cache_key = ("wrap", choice, str(start_day), str(end_day), (party or "").lower())
    force_fresh = st.session_state.force_fresh
    st.session_state.force_fresh = False
    cached = st.session_state.result_cache.get(cache_key)
    cache_age = (time.time() - cached[0]) / 60 if cached else None
    if use_cache and not force_fresh and cached and cache_age < CACHE_TTL_MINUTES:
        msg = {"role": "assistant", "kind": "wrap", "wrap": cached[1], "from_cache": True,
               "cache_age_min": int(cache_age)}
        render_assistant_message(msg, key_prefix)
        st.session_state.messages.append(msg)
        return
    placeholder = st.empty()
    log = ProgressLog(placeholder)
    try:
        with contextlib.redirect_stdout(log):
            wrap = uc.gather_daily_wrap(choice, start_day, client, end_day=end_day, fresh=force_fresh, party=party)
        placeholder.empty()
        wrap["_query"] = query
        with st.expander("🛠️ Technical log"):
            st.code(log.getvalue() or "(no output)")
        msg = {"role": "assistant", "kind": "wrap", "wrap": wrap}
        render_assistant_message(msg, key_prefix)
        st.session_state.result_cache[cache_key] = (time.time(), wrap, False)
        st.session_state.messages.append(msg)
        if hasattr(st, "toast"):
            st.toast("News wrap-up ready", icon="🗞️")
    except Exception as e:
        placeholder.empty()
        text = f"Something went wrong building the wrap-up: {e}"
        with st.expander("🛠️ Technical log"):
            st.code(log.getvalue() or "(no output)")
        st.error(text)
        st.session_state.messages.append({"role": "assistant", "content": text, "error": True})

if not st.session_state.messages:
    st.markdown("##### Try an example:")
    for row_label, examples in [("Politicians", EXAMPLE_POLITICIANS), ("Parties", EXAMPLE_PARTIES),
                                ("News wrap-up", ["Daily wrap-up: Andhra Pradesh & Telangana",
                                                  "Daily wrap-up: Telangana", "Daily wrap-up: Andhra Pradesh",
                                                  "Weekly wrap-up: Andhra Pradesh & Telangana"]),
                                ("Party wrap-up", ["BRS news wrap-up: Telangana", "Congress news wrap-up: Telangana",
                                                   "TDP news wrap-up: Andhra Pradesh",
                                                   "YSRCP weekly wrap-up: Andhra Pradesh"])]:
        st.caption(row_label)
        cols = st.columns(len(examples))
        for col, example_name in zip(cols, examples):
            if col.button(example_name, key=f"example_{example_name}", use_container_width=True):
                st.session_state.trigger_prompt = example_name
                st.rerun()

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🏛️"):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        elif msg.get("error"):
            st.error(msg["content"])
        else:
            render_assistant_message(msg, key_prefix=f"msg{i}")

prompt = st.chat_input("Enter a politician or a party (e.g. 'KCR', 'BJP'), or 'daily wrap'...")
if not prompt and st.session_state.trigger_prompt:
    prompt = st.session_state.trigger_prompt
    st.session_state.trigger_prompt = None
prompt = prompt.strip() if prompt else prompt

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    recent = [q for q in st.session_state.recent_queries if q.lower() != prompt.lower()]
    st.session_state.recent_queries = ([prompt] + recent)[:5]
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)

    key_prefix = f"msg{len(st.session_state.messages)}"  # index this reply will have in history
    wrap_choice = uc.detect_wrap_request(prompt, default=WRAP_CHOICES[wrap_label])
    with st.chat_message("assistant", avatar="🏛️"):
        if wrap_choice:
            # Dates: an explicit range from a button/"Run fresh" first, then a period typed in words
            # ("weekly", "last 5 days", "yesterday"), then whatever is set in the sidebar.
            rng = st.session_state.trigger_wrap_range
            st.session_state.trigger_wrap_range = None
            rng = rng or uc.detect_wrap_range(prompt) or (wrap_start, wrap_end)
            # Party: from a button/"Run fresh" first, then one named in the message, then the sidebar's Focus.
            party = st.session_state.trigger_wrap_party
            st.session_state.trigger_wrap_party = None
            if party is None:
                party = uc.detect_wrap_party(prompt) or wrap_party
            run_wrap_turn(prompt, wrap_choice, rng[0], rng[1], key_prefix, party)
        elif date_error:
            text = f"Please fix the date range in the sidebar first: {date_error}"
            st.error(text)
            st.session_state.messages.append({"role": "assistant", "content": text, "error": True})
        else:

            start_date = end_date = None
            if window == "Daily (last 1 day)":
                start_date = uc.utc_now() - timedelta(days=1)
            elif window == "Weekly (last 7 days)":
                start_date = uc.utc_now() - timedelta(days=7)
            elif window == "Custom range" and custom_start and custom_end:
                start_date = datetime.combine(custom_start, datetime.min.time())
                end_date = datetime.combine(custom_end, datetime.min.time())

            # Cache key uses the window *choice*, not computed timestamps, so a
            # repeat "Weekly" search a few minutes later still counts as the same.
            cache_key = (prompt.lower(), subject_mode, window, str(custom_start), str(custom_end), headlines_limit,
                         tuple(sorted(enabled)), tuple(brave_platforms), x_always)
            force_fresh = st.session_state.force_fresh
            st.session_state.force_fresh = False
            cached = st.session_state.result_cache.get(cache_key)
            cache_age = (time.time() - cached[0]) / 60 if cached else None

            if use_cache and not force_fresh and cached and cache_age < CACHE_TTL_MINUTES:
                msg = {"role": "assistant", "result": cached[1], "from_cache": True,
                       "cache_age_min": int(cache_age), "is_empty": cached[2]}
                render_assistant_message(msg, key_prefix)
                st.session_state.messages.append(msg)
            else:
                progress_placeholder = st.empty()
                log = ProgressLog(progress_placeholder)
                try:
                    with contextlib.redirect_stdout(log):
                        result = uc.gather_report(
                            prompt, start_date, end_date,
                            platforms_csv=",".join(brave_platforms) if brave_platforms else "x",
                            headlines_limit=headlines_limit,
                            no_reddit="reddit" not in enabled, no_x="x" not in enabled, x_always=x_always,
                            no_youtube="youtube" not in enabled, no_ads="ads" not in enabled,
                            no_telegram="telegram" not in enabled, no_brave="brave" not in enabled,
                            no_social_news="social_news" not in enabled,
                            subject_type=subject_mode,
                            client=client,
                        )
                    progress_placeholder.empty()
                    result["_query"] = prompt
                    result["_generated_at"] = datetime.now()
                    is_empty = (not result["data"]["headlines"] and social_item_count(result["data"]) == 0
                                and not result["narrative"].get(uc.TOPLINE_KEY, "").strip())
                    with st.expander("🛠️ Technical log"):
                        st.code(log.getvalue() or "(no output)")
                    msg = {"role": "assistant", "result": result, "is_empty": is_empty}
                    render_assistant_message(msg, key_prefix)
                    st.session_state.result_cache[cache_key] = (time.time(), result, is_empty)
                    st.session_state.messages.append(msg)
                    if not is_empty and hasattr(st, "toast"):
                        st.toast(f"Report ready for {result['name']}", icon="✅")
                except Exception as e:
                    progress_placeholder.empty()
                    text = f"Something went wrong: {e}"
                    with st.expander("🛠️ Technical log"):
                        st.code(log.getvalue() or "(no output)")
                    st.error(text)
                    st.session_state.messages.append({"role": "assistant", "content": text, "error": True})

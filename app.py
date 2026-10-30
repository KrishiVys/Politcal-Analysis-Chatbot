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
import io
import re
import glob
import html
import time
import contextlib
import hmac
from datetime import datetime, timedelta

import streamlit as st

import updatedcode as uc
import streamlit.components.v1 as components
try:
    import site_data as sd          # constituency & region news (needs site_data.py + ap_tg_data.json here)
except Exception as _sd_error:      # the rest of the app still works without them
    sd = None

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
        or not hasattr(uc, "gather_daily_carousel")):
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


def render_carousel(c: dict, key_prefix: str) -> None:
    st.markdown(f"### 🎠 {uc.carousel_title(c)}")
    st.warning(f"**{c['notice']}**")
    if c["used_template"]:
        st.caption("Sarvam AI wasn't available: stories were chosen by coverage and all writing is left to the editor.")
    st.caption(f"Generated {c['generated']}")
    tabs = st.tabs(["🎠 Slides", "📝 Post copy", "♿ Alt text", "🗂️ Source log", "✍️ Review & final slides",
                    "🔎 Sources checked"])
    with tabs[0]:
        for sl in c["slides"]:
            n_items = len(sl["cards"]) + len(sl["briefs"])
            flags = sum(len(card["flags"]) for card in sl["cards"])
            label = (f"Slide {sl['n']} — {sl['title']}" + (f"  ·  {n_items} stor{'y' if n_items == 1 else 'ies'}" if n_items else "")
                     + (f"  ·  ⚠️ {flags} flag{'s' if flags != 1 else ''}" if flags else ""))
            with st.expander(label, expanded=sl["n"] in (1, 2)):
                st.markdown("\n".join(uc.carousel_slide_markdown(c, sl)) or "_(empty)_")
        if c["notes"]:
            with st.expander("Selection notes (choices the code corrected)"):
                st.markdown("\n".join(f"- {n}" for n in c["notes"]))
    with tabs[1]:
        p = c["post"]
        st.markdown("**Opening hook**")
        st.code(p["hook"], language=None)
        st.markdown("**Caption**")
        st.code(p["caption"] or "(editor to write)", language=None)
        st.markdown("**Hashtags**")
        st.code(" ".join(p["hashtags"]), language=None)
        for f in c["post_flags"]:
            st.caption(f"⚠️ {f}")
    with tabs[2]:
        st.markdown("\n".join(f"- **Slide {n}:** {a}" for n, a in c["alt_text"].items()))
    with tabs[3]:
        import pandas as pd
        st.dataframe(pd.DataFrame([{
            "ID": e["id"], "Headline": e["headline"], "Category": e["category"], "Outlets": e["outlets"],
            "Established": e["established"], "First published": e["published"], "Outcome": e["outcome"],
            "Main source": e["sources"][0]["url"] if e["sources"] else ""} for e in c["source_log"]]),
            use_container_width=True, hide_index=True)
    with tabs[4]:
        render_editorial_review(c, key_prefix)
    with tabs[5]:
        render_sources_tab(c["status"])
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Prepare Markdown (draft)", key=f"{key_prefix}_cmd_btn"):
            path = uc.save_carousel_markdown(c)
            with open(path, "rb") as f:
                st.session_state[f"{key_prefix}_cmd"] = (os.path.basename(path), f.read())
        if f"{key_prefix}_cmd" in st.session_state:
            fname, content = st.session_state[f"{key_prefix}_cmd"]
            st.download_button("Download .md", content, file_name=fname, mime="text/markdown", key=f"{key_prefix}_cmd_dl")
    with col2:
        if uc.SimpleDocTemplate is None:
            st.caption("PDF export needs: pip install reportlab")
        else:
            if st.button("📑 Prepare PDF (draft)", key=f"{key_prefix}_cpdf_btn"):
                path = uc.save_carousel_pdf(c)
                with open(path, "rb") as f:
                    st.session_state[f"{key_prefix}_cpdf"] = (os.path.basename(path), f.read())
            if f"{key_prefix}_cpdf" in st.session_state:
                fname, content = st.session_state[f"{key_prefix}_cpdf"]
                st.download_button("Download .pdf", content, file_name=fname, mime="application/pdf",
                                   key=f"{key_prefix}_cpdf_dl")


STATUS_CHOICES = ["", "developing", "allegation", "disputed"]


def _review_apply(edit: dict, images: dict, kp: str) -> list:
    """Copy the saved review form into the review state. Returns problems with uploaded images."""
    ss, problems = st.session_state, []
    edit["cover"]["hook"] = ss.get(f"{kp}_rv_hook", edit["cover"]["hook"])
    for s in edit["stories"]:
        p = f"{kp}_rv_{s['id']}"
        s["include"] = bool(ss.get(p + "_inc", s["include"]))
        s["chip"] = ss.get(p + "_chip", s["chip"]).strip()
        s["status"] = ss.get(p + "_status", s["status"])
        if s["section"] == "state":
            s["state"] = ss.get(p + "_state", s["state"])
        s["headline"] = ss.get(p + "_head", s["headline"]).strip()
        s["summary"] = ss.get(p + "_sum", s["summary"]).strip()
        if s["section"] == "top":
            s["bullets"] = [b.strip() for b in ss.get(p + "_bul", "\n".join(s["bullets"])).split("\n") if b.strip()]
        s["image_caption"] = ss.get(p + "_cap", s["image_caption"]).strip()
        s["image_credit"] = ss.get(p + "_credit", s["image_credit"]).strip()
        up = ss.get(p + "_img")
        if up is not None:
            data = up.getvalue()
            try:
                from PIL import Image
                Image.open(io.BytesIO(data)).verify()
                images[s["id"]] = data
            except Exception:
                problems.append(f"The image for “{s['headline'][:50]}” couldn't be read -- use PNG, JPG or WebP.")
        elif ss.get(p + "_noimg"):
            images.pop(s["id"], None)
    for b in edit["briefs"]:
        p = f"{kp}_rv_{b['id']}"
        b["include"] = bool(ss.get(p + "_inc", b["include"]))
        b["text"] = ss.get(p + "_txt", b["text"]).strip()
    t = edit["takeaway"]
    t["headline"] = ss.get(f"{kp}_rv_tk_head", t["headline"]).strip()
    t["detail"] = ss.get(f"{kp}_rv_tk_detail", t["detail"]).strip()
    t["follow"] = ss.get(f"{kp}_rv_tk_follow", t["follow"]).strip()
    edit["sources_url"] = ss.get(f"{kp}_rv_url", edit["sources_url"]).strip()
    for i, item in enumerate(uc.CAROUSEL_CHECKLIST):
        edit["checklist"][item] = bool(ss.get(f"{kp}_rv_chk_{i}", edit["checklist"][item]))
    edit["approver"] = ss.get(f"{kp}_rv_approver", edit["approver"]).strip()
    for k in (f"{kp}_deck_en", f"{kp}_deck_te"):      # anything built before this change is out of date
        ss.pop(k, None)
    return problems


def _review_apply_telugu(edit: dict, kp: str) -> None:
    ss = st.session_state
    for s in edit["stories"]:
        if not s["include"]:
            continue
        p = f"{kp}_te_{s['id']}"
        for field in ("headline", "summary", "image_caption"):
            if p + "_" + field in ss:
                s["te"][field] = ss[p + "_" + field].strip()
        if p + "_bullets" in ss:
            s["te"]["bullets"] = [b.strip() for b in ss[p + "_bullets"].split("\n") if b.strip()]
    for b in edit["briefs"]:
        if b["include"] and f"{kp}_te_{b['id']}" in ss:
            b["te"]["text"] = ss[f"{kp}_te_{b['id']}"].strip()
    if f"{kp}_te_hook" in ss:
        edit["cover"]["te"]["hook"] = ss[f"{kp}_te_hook"].strip()
    for field in ("headline", "detail", "follow"):
        if f"{kp}_te_tk_{field}" in ss:
            edit["takeaway"]["te"][field] = ss[f"{kp}_te_tk_{field}"].strip()
    ss.pop(f"{kp}_deck_te", None)


def render_editorial_review(c: dict, kp: str) -> None:
    """Editorial review of the draft, then the FINAL slides (PowerPoint, CamPen template) once approved."""
    ek, ik = f"{kp}_edit", f"{kp}_imgs"
    if ek not in st.session_state:
        st.session_state[ek] = uc.carousel_edit_state(c)
        st.session_state[ik] = {}
    edit, images = st.session_state[ek], st.session_state[ik]
    if uc.Presentation is None:
        st.warning("Building the final slides needs python-pptx:  pip install python-pptx")
    st.caption("Check and edit every story, add licensed images with their credits, complete the checklist and "
               "approve. Only an approved review is built into the final slides, in the CamPen template.")

    with st.form(f"{kp}_review_form"):
        st.markdown("#### Slide 1 — Cover")
        st.text_area("Cover line (hook)", edit["cover"]["hook"], key=f"{kp}_rv_hook", height=70)
        for sec, title, mx in uc.DECK_SECTIONS:
            group = [s for s in edit["stories"] if s["section"] == sec]
            if not group:
                continue
            st.markdown(f"#### {title.replace('--', '—')}  ·  up to {mx}")
            for s in group:
                p = f"{kp}_rv_{s['id']}"
                with st.expander(("✅ " if s["include"] else "⬜ ") + (s["headline"] or s["id"])[:90],
                                 expanded=(sec == "top")):
                    st.checkbox("Include on the slide", s["include"], key=p + "_inc")
                    c1, c2 = st.columns(2)
                    c1.text_input("Label chip", s["chip"], key=p + "_chip")
                    c2.selectbox("Status tag", STATUS_CHOICES, index=STATUS_CHOICES.index(s["status"] or ""),
                                 format_func=lambda v: v.title() if v else "None", key=p + "_status")
                    if sec == "state":
                        states = ["Telangana", "Andhra Pradesh"]
                        st.selectbox("State", states, index=states.index(s["state"]) if s["state"] in states else 0,
                                     key=p + "_state")
                    st.text_input("Headline", s["headline"], key=p + "_head")
                    st.text_area(f"Summary ({len(s['summary'].split())} words)", s["summary"], key=p + "_sum", height=110)
                    if sec == "top":
                        st.text_area("Key facts (one per line)", "\n".join(s["bullets"]), key=p + "_bul", height=90)
                    st.file_uploader("Image (optional -- only one you are licensed to use)",
                                     type=["png", "jpg", "jpeg", "webp"], key=p + "_img")
                    if s["id"] in images:
                        st.checkbox("Remove the current image", False, key=p + "_noimg")
                    c3, c4 = st.columns(2)
                    c3.text_input("Image caption", s["image_caption"], key=p + "_cap")
                    c4.text_input("Image credit (required with an image)", s["image_credit"], key=p + "_credit")
                    st.caption(s["verification"])
                    for f in s["flags"]:
                        st.caption(f"⚠️ {f}")
                    if s["links"]:
                        st.caption("Sources: " + " · ".join(f"[{l['name']}]({l['url']})" for l in s["links"][:5]))
        if edit["briefs"]:
            st.markdown(f"#### Slide 8 — In brief  ·  up to {uc.DECK_MAX_BRIEFS}")
            for b in edit["briefs"]:
                p = f"{kp}_rv_{b['id']}"
                c1, c2 = st.columns([1, 9])
                c1.checkbox("Use", b["include"], key=p + "_inc")
                c2.text_input("Brief", b["text"], key=p + "_txt", label_visibility="collapsed")
        st.markdown("#### Slide 9 — Today's takeaway")
        t = edit["takeaway"]
        st.text_input("Takeaway headline", t["headline"], key=f"{kp}_rv_tk_head")
        st.text_area("Takeaway detail (e.g. what led the news in the Telugu states)", t["detail"], key=f"{kp}_rv_tk_detail",
                     height=70)
        st.text_input("Follow line", t["follow"], key=f"{kp}_rv_tk_follow")
        st.markdown("#### Slide 10 — Sources")
        st.text_input("Sources page link (becomes the QR code)", edit["sources_url"], key=f"{kp}_rv_url",
                      help="Download the sources page below, host it (e.g. on your website or Google Drive) and "
                           "paste its link here. Without a link, slide 9 lists the outlets instead.")
        st.markdown("#### Editorial checklist")
        for i, item in enumerate(uc.CAROUSEL_CHECKLIST):
            st.checkbox(item, edit["checklist"][item], key=f"{kp}_rv_chk_{i}")
        st.text_input("Approving editor", edit["approver"], key=f"{kp}_rv_approver")
        saved = st.form_submit_button("💾 Save review")
    if saved:
        for msg in _review_apply(edit, images, kp):
            st.error(msg)
        st.success("Review saved.")

    errors, warnings = uc.review_problems(edit, images)
    if errors:
        st.error("**Before approval:**\n" + "\n".join(f"- {e}" for e in errors))
    if warnings:
        with st.expander(f"⚠️ {len(warnings)} thing(s) to check"):
            st.markdown("\n".join(f"- {w}" for w in warnings))
    st.download_button("⬇️ Sources page (HTML) to host for the QR code", uc.carousel_sources_html(edit),
                       file_name=f"CamPen_DailyWrap_{edit['day']}_sources.html", mime="text/html",
                       key=f"{kp}_srcpage")

    st.markdown("#### Final slides")
    if st.button("✅ Approve & build the final slides (English)", key=f"{kp}_build_en",
                 disabled=bool(errors) or uc.Presentation is None):
        try:
            final = uc.finalize_carousel(edit, images)
            st.session_state[f"{kp}_deck_en"] = (f"CamPen_DailyWrap_{edit['day']}_EN.pptx",
                                                 uc.build_carousel_pptx(final, images, "en"), final["approved_at"])
        except Exception as e:
            st.error(f"Couldn't build the slides: {e}")
    if f"{kp}_deck_en" in st.session_state:
        fname, data, when = st.session_state[f"{kp}_deck_en"]
        st.success(f"Approved by {edit['approver']} at {when}.")
        st.download_button("⬇️ Download the final slides (PowerPoint)", data, file_name=fname, key=f"{kp}_dl_en",
                           mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")

    st.markdown("#### Telugu slides")
    if client is None:
        st.caption("Translating to Telugu needs a Sarvam API key.")
    st.caption("Translate the review to get the Telugu slides and the Telugu sources page.")
    if st.button("🔤 Translate the review to Telugu (Sarvam)", key=f"{kp}_translate", disabled=client is None):
        with st.spinner("Translating..."):
            problems = uc.translate_carousel(edit, client)
        st.session_state.pop(f"{kp}_deck_te", None)
        if problems:
            st.warning("Some text couldn't be translated and was left in English -- fix it below:\n"
                       + "\n".join(f"- {p}" for p in problems[:10]))
    has_te = any(s["te"] for s in edit["stories"] if s["include"]) or edit["cover"]["te"]
    if has_te:
        with st.form(f"{kp}_te_form"):
            st.caption("Check and edit the Telugu text before building the Telugu slides.")
            st.text_area("Cover line", edit["cover"]["te"].get("hook", ""), key=f"{kp}_te_hook", height=70)
            for s in [s for s in edit["stories"] if s["include"]]:
                p = f"{kp}_te_{s['id']}"
                with st.expander(s["headline"][:90]):
                    st.text_input("శీర్షిక (headline)", s["te"].get("headline", ""), key=p + "_headline")
                    st.text_area("సారాంశం (summary)", s["te"].get("summary", ""), key=p + "_summary", height=110)
                    if s["section"] == "top":
                        st.text_area("ముఖ్యాంశాలు (key facts, one per line)", "\n".join(s["te"].get("bullets", [])),
                                     key=p + "_bullets", height=90)
                    if s.get("image_caption"):
                        st.text_input("Image caption", s["te"].get("image_caption", ""), key=p + "_image_caption")
            for b in [b for b in edit["briefs"] if b["include"]]:
                st.text_input(f"Brief: {b['text'][:60]}", b["te"].get("text", ""), key=f"{kp}_te_{b['id']}")
            t = edit["takeaway"]
            st.text_input("Takeaway headline", t["te"].get("headline", ""), key=f"{kp}_te_tk_headline")
            st.text_area("Takeaway detail", t["te"].get("detail", ""), key=f"{kp}_te_tk_detail", height=70)
            st.text_input("Follow line", t["te"].get("follow", ""), key=f"{kp}_te_tk_follow")
            te_saved = st.form_submit_button("💾 Save Telugu text")
        if te_saved:
            _review_apply_telugu(edit, kp)
            st.success("Telugu text saved.")
        missing = uc.telugu_missing(edit)
        if missing:
            st.warning("Not translated yet:\n" + "\n".join(f"- {m}" for m in missing[:10]))
        st.download_button("⬇️ Sources page in Telugu (HTML) to host for the QR code",
                           uc.carousel_sources_html(edit, "te") if not missing else "",
                           file_name=f"CamPen_DailyWrap_{edit['day']}_sources_TE.html", mime="text/html",
                           key=f"{kp}_srcpage_te", disabled=bool(missing),
                           help="Available once every headline and brief is translated.")
        if st.button("✅ Approve & build the final slides (Telugu)", key=f"{kp}_build_te",
                     disabled=bool(errors) or bool(missing) or uc.Presentation is None):
            try:
                final = uc.finalize_carousel(edit, images)
                st.session_state[f"{kp}_deck_te"] = (f"CamPen_DailyWrap_{edit['day']}_TE.pptx",
                                                     uc.build_carousel_pptx(final, images, "te"), final["approved_at"])
            except Exception as e:
                st.error(f"Couldn't build the Telugu slides: {e}")
        if f"{kp}_deck_te" in st.session_state:
            fname, data, when = st.session_state[f"{kp}_deck_te"]
            st.download_button("⬇️ Download the final Telugu slides (PowerPoint)", data, file_name=fname,
                               key=f"{kp}_dl_te",
                               mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")


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


REG_PERIODS = ["Today", "Yesterday", "Last 7 days"]
REG_CSS = """<style>
.rp-card{background:#fff;border:1px solid #e5e9f0;border-radius:14px;padding:14px 18px;margin:0 0 12px;}
.rp-card h3{font-size:16px;font-weight:700;margin:2px 0 8px;color:#0f172a}
.rp-title{font-size:21px;font-weight:800;margin:0 0 8px;color:#0f172a}
.rp-facts{display:flex;flex-wrap:wrap;gap:7px}.rp-fact{background:#f1f5f9;border-radius:9px;padding:5px 9px;font-size:13px;color:#0f172a}
.rp-fact b{color:#475569;font-weight:600;margin-right:4px}
.rp-item{padding:9px 0;border-top:1px solid #eef1f5}.rp-item:first-of-type{border-top:none}
.rp-txt{font-size:15px;line-height:1.5;color:#0f172a}
.rp-meta{margin-top:5px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12.5px}
.rp-badge{background:#eef2ff;color:#3730a3;border-radius:999px;padding:2px 9px;font-weight:600}
.rp-badge.d{background:#ecfdf5;color:#065f46}.rp-badge.t{background:#fff7ed;color:#9a3412}
.rp-src{color:#64748b}.rp-src a{color:#1d4ed8;text-decoration:none;font-weight:500}
</style>"""


def reg_period_dates(period: str):
    today = uc.ist_today()
    if period == "Yesterday":
        return today - timedelta(days=1), today - timedelta(days=1)
    if period == "Last 7 days":
        return today - timedelta(days=6), today
    return today, today


def _rp_item(it: dict, show_places: bool = True) -> str:
    e = html.escape
    badges = []
    if show_places:
        for a in it["acs"][:4]:
            badges.append(f'<span class="rp-badge">📍 {e(a["name"])} · AC {a["ac_no"]}</span>')
        named = {d for a in it["acs"] for d in sd.AC_BY_KEY[(a["state"], a["ac_no"])]["districts"]}
        for _s, dn in it["districts"]:
            if dn not in named and len(badges) < 6:
                badges.append(f'<span class="rp-badge d">{e(dn)} district</span>')
    if it.get("tag"):
        badges.append(f'<span class="rp-badge t">{e(it["tag"])}</span>')
    if it.get("when"):
        badges.append(f'<span class="rp-src">{e(it["when"])}</span>')
    links = " · ".join(f'<a href="{e(l["url"])}" target="_blank" rel="noopener">{e(l["name"])}</a>' for l in it["links"][:5])
    src = f'<span class="rp-src">Sources: {links}</span>' if links else ""
    return f'<div class="rp-item"><div class="rp-txt">{e(it["text"])}</div><div class="rp-meta">{"".join(badges)}{src}</div></div>'


def _reg_pick(key: str, period: str) -> None:
    label = dict(sd.search_options()).get(key, key)
    st.session_state.trigger_regional = (key, period)
    st.session_state.trigger_prompt = f"Political news: {label.split(' ', 1)[-1]} ({period})"


def render_regional(msg: dict, key_prefix: str) -> None:
    """Political news for a constituency, Lok Sabha seat, district, region, party or leader -- with constituency
    numbers, a by-topic / by-place view and the map."""
    e = html.escape
    st.markdown(REG_CSS, unsafe_allow_html=True)
    r, result, period = sd.resolve(msg["key"]), msg["result"], msg["period"]
    facts = "".join(f'<span class="rp-fact"><b>{e(k)}</b>{e(v)}</span>' for k, v in r["info"].items())
    st.markdown(f'<div class="rp-card"><div class="rp-title">🗳️ {e(r["title"])}</div><div class="rp-facts">{facts}</div></div>',
                unsafe_allow_html=True)
    segs = ([x for x in sd.ACS if x["state"] == r["ac"]["state"] and x["lok_sabha"] == r["ac"]["lok_sabha"] and x is not r["ac"]]
            if r["kind"] == "ac" else r.get("segments") or [])
    if segs:
        st.caption("Other Assembly segments of the same Lok Sabha seat:" if r["kind"] == "ac" else "Assembly constituencies:")
        for i in range(0, len(segs), 6):
            cols = st.columns(6)
            for col, x in zip(cols, segs[i:i + 6]):
                col.button(f"{x['name']} · {x['ac_no']}", key=f"{key_prefix}_seg_{x['state'][:2]}{x['ac_no']}",
                           on_click=_reg_pick, args=(f"ac:{sd.STATE_SHORT[x['state']]}:{x['ac_no']}", period),
                           use_container_width=True)
    items = sd.items_of(result)
    left, right = st.columns([1.5, 1])
    with right:
        components.html(sd.map_html(result, r["highlight"], height=400), height=410)
    with left:
        if not items:
            st.info(f"No political news found for {r['title']} ({result['period']}). Try 'Last 7 days', or a nearby "
                    "district or region.")
            return
        view = st.radio("View", ["By topic", "By place"], horizontal=True, key=f"{key_prefix}_rview",
                        label_visibility="collapsed")
        st.caption(f"{len(items)} points · {result['period']} · gathered {result['fetched']}"
                   + ("" if result["used_ai"] else " · headlines shown (Sarvam summaries unavailable)"))
        if view == "By topic":
            for st_ in result["states"]:
                for sec in st_["sections"]:
                    st.markdown(f'<div class="rp-card"><h3>{sec["icon"]} {e(sec["label"])} <span class="rp-src">· '
                                f'{len(sec["items"])}</span></h3>' + "".join(_rp_item(it) for it in sec["items"]) + "</div>",
                                unsafe_allow_html=True)
                if st_["watch"]:
                    st.markdown('<div class="rp-card"><h3>👀 What to watch</h3>' + "".join(
                        f'<div class="rp-item"><div class="rp-txt">{e(w)}</div></div>' for w in st_["watch"]) + "</div>",
                        unsafe_allow_html=True)
        else:
            for (st_name, dn), its in sd.by_district(result):
                if dn:
                    seats = sorted({(a["ac_no"], a["name"]) for it in its for a in it["acs"]
                                    if dn in sd.AC_BY_KEY[(a["state"], a["ac_no"])]["districts"]})
                    sub = (" · " + ", ".join(f"{e(n)} (AC {no})" for no, n in seats)) if seats else ""
                    title = f"📍 {e(dn)} district <span class='rp-src'>· {e(st_name)}{sub}</span>"
                else:
                    title = f"🏛️ State-wide · {e(st_name)}"
                st.markdown(f'<div class="rp-card"><h3>{title}</h3>' + "".join(_rp_item(it, bool(dn)) for it in its)
                            + "</div>", unsafe_allow_html=True)


def render_assistant_message(msg: dict, key_prefix: str) -> None:
    """Shared by the live turn and history replay, so widget keys match on reruns
    (that is what makes buttons like "Run fresh" and the downloads work)."""
    if msg.get("kind") == "regional":
        if sd is None:
            st.warning("Constituency & region news needs site_data.py and ap_tg_data.json next to app.py.")
        else:
            render_regional(msg, key_prefix)
        return
    if msg.get("kind") == "carousel":
        c = msg["carousel"]
        if msg.get("from_cache"):
            c1, c2 = st.columns([4, 1])
            c1.info(f"♻️ Reused a carousel from {msg.get('cache_age_min', 0)} minute(s) ago, so no new API calls were made.")
            if c2.button("🔄 Run fresh", key=f"{key_prefix}_fresh"):
                st.session_state.force_fresh = True
                st.session_state.trigger_prompt = c.get("_query") or "carousel"
                st.session_state.trigger_carousel = (c["day"], c.get("_states", "both"))
                st.rerun()
        render_carousel(c, key_prefix)
        return
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
                     ("trigger_wrap_party", None), ("trigger_carousel", None), ("trigger_regional", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

WRAP_CHOICES = {"Andhra Pradesh & Telangana": "both", "Andhra Pradesh": "andhra pradesh", "Telangana": "telangana"}
CAROUSEL_STATE_CHOICES = {"Andhra Pradesh & Telangana": "both", "Andhra Pradesh": "ap", "Telangana": "telangana",
                          "None (national only)": "none"}
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
    st.subheader("🗳️ Constituency & region news")
    if sd is None:
        st.caption("Add site_data.py and ap_tg_data.json next to app.py to turn this on.")
        reg_period = "Today"
    else:
        _reg_options = sd.search_options()
        _reg_labels = dict(_reg_options)
        reg_key = st.selectbox("Search", [k for k, _ in _reg_options], index=None, key="opt_reg_q",
                               format_func=lambda k: _reg_labels.get(k, k),
                               placeholder="Constituency (name or no.), district, region, party, leader…")
        reg_period = st.radio("Period", REG_PERIODS, horizontal=True, key="opt_reg_period")
        if st.button("🗳️ Show political news", use_container_width=True, key="regional_btn", disabled=not reg_key):
            _reg_pick(reg_key, reg_period)
            st.rerun()
        st.caption("Political news only -- parties, leaders, elected representatives, elections -- tagged with "
                   "constituency numbers and shown on a map. Or type e.g. \"Kuppam news\", \"AC 175 AP\", "
                   "\"Rayalaseema this week\", \"Warangal district\".")

    st.divider()
    st.subheader("🎠 Daily news carousel (draft)")
    car_states_label = st.selectbox("State slide", list(CAROUSEL_STATE_CHOICES), key="opt_car_states",
                                    help="Which states feed 'national and state developments'. The carousel also "
                                         "covers national politics, world affairs, business, tech/science, health, "
                                         "environment and sports.")
    car_day = st.date_input("Day", value=uc.ist_today(), max_value=uc.ist_today(), key="opt_car_day")
    if st.button("🎠 Generate draft carousel", use_container_width=True, key="carousel_btn"):
        st.session_state.trigger_prompt = f"Daily news carousel, {car_day:%d %b %Y}"
        st.session_state.trigger_carousel = (car_day, CAROUSEL_STATE_CHOICES[car_states_label])
        st.rerun()
    st.caption("A ten-slide DRAFT for editorial review, with separate National, AP/Telangana and Sports slides and the "
               "AP/Telangana angle in every section -- nothing is published or treated as verified. "
               "Or type \"carousel\" in the chat box.")

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
        "Set **Focus** to a party (or type e.g. \"BRS wrap\") for a wrap-up about that party in these states.\n"
        "6. For a ten-slide **daily news carousel** (a DRAFT for editorial review, with sources, verification "
        "statuses, caption, hashtags and alt text), use the carousel section in the sidebar or type \"carousel\".\n\n"
        "Paid sources (Sarvam, Brave, X) use real API quota on every new search. "
        "Use the **Free sources only** preset to avoid that, apart from the Sarvam summary."
    )

client = uc.SarvamAI(api_subscription_key=sarvam_key) if (uc.SarvamAI and sarvam_key) else None


def run_carousel_turn(query: str, day, states: str, key_prefix: str) -> None:
    """One chat turn for the DRAFT daily news carousel."""
    cache_key = ("carousel", str(day), states)
    force_fresh = st.session_state.force_fresh
    st.session_state.force_fresh = False
    cached = st.session_state.result_cache.get(cache_key)
    cache_age = (time.time() - cached[0]) / 60 if cached else None
    if use_cache and not force_fresh and cached and cache_age < CACHE_TTL_MINUTES:
        msg = {"role": "assistant", "kind": "carousel", "carousel": cached[1], "from_cache": True,
               "cache_age_min": int(cache_age)}
        render_assistant_message(msg, key_prefix)
        st.session_state.messages.append(msg)
        return
    placeholder = st.empty()
    log = ProgressLog(placeholder)
    try:
        with contextlib.redirect_stdout(log):
            c = uc.gather_daily_carousel(day, states, client)
        placeholder.empty()
        c["_query"], c["_states"] = query, states
        with st.expander("🛠️ Technical log"):
            st.code(log.getvalue() or "(no output)")
        msg = {"role": "assistant", "kind": "carousel", "carousel": c}
        render_assistant_message(msg, key_prefix)
        st.session_state.result_cache[cache_key] = (time.time(), c, False)
        st.session_state.messages.append(msg)
        if hasattr(st, "toast"):
            st.toast("Draft carousel ready for editorial review", icon="🎠")
    except Exception as e:
        placeholder.empty()
        text = f"Something went wrong building the carousel: {e}"
        with st.expander("🛠️ Technical log"):
            st.code(log.getvalue() or "(no output)")
        st.error(text)
        st.session_state.messages.append({"role": "assistant", "content": text, "error": True})


def run_regional_turn(query: str, key: str, period: str, key_prefix: str) -> None:
    """One chat turn: political news for a constituency / Lok Sabha seat / district / region / party / leader."""
    start, end = reg_period_dates(period)
    cache_key = ("regional", key, str(start), str(end))
    force_fresh = st.session_state.force_fresh
    st.session_state.force_fresh = False
    cached = st.session_state.result_cache.get(cache_key)
    cache_age = (time.time() - cached[0]) / 60 if cached else None
    if use_cache and not force_fresh and cached and cache_age < CACHE_TTL_MINUTES:
        msg = {"role": "assistant", "kind": "regional", "key": key, "period": period, "result": cached[1]}
        render_assistant_message(msg, key_prefix)
        st.session_state.messages.append(msg)
        return
    placeholder = st.empty()
    log = ProgressLog(placeholder)
    try:
        r = sd.resolve(key)
        with contextlib.redirect_stdout(log):
            w = uc.gather_daily_wrap(r["states"], start, client, end_day=end, party=r["subject"], fresh=force_fresh)
        placeholder.empty()
        result = sd.simplify_wrap(w)
        result["fetched"] = f"{uc.utc_now() + uc.IST_OFFSET:%d %b %Y, %I:%M %p} IST"
        with st.expander("🛠️ Technical log"):
            st.code(log.getvalue() or "(no output)")
        msg = {"role": "assistant", "kind": "regional", "key": key, "period": period, "result": result}
        render_assistant_message(msg, key_prefix)
        st.session_state.result_cache[cache_key] = (time.time(), result, False)
        st.session_state.messages.append(msg)
    except Exception as e:
        placeholder.empty()
        text = f"Something went wrong gathering the political news: {e}"
        with st.expander("🛠️ Technical log"):
            st.code(log.getvalue() or "(no output)")
        st.error(text)
        st.session_state.messages.append({"role": "assistant", "content": text, "error": True})


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
                                ("Daily carousel (draft)", ["Daily news carousel"]),
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
        elif msg.get("note"):
            st.info(msg["content"])
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
        reg = st.session_state.trigger_regional
        st.session_state.trigger_regional = None
        if reg is None and sd is not None and not st.session_state.trigger_carousel \
                and not st.session_state.trigger_wrap_range and not uc.detect_carousel_request(prompt):
            found = sd.detect_regional(prompt)       # a constituency, Lok Sabha seat, district or region named
            if isinstance(found, tuple):
                reg = found
            elif found:
                reg = (found, sd.detect_period(prompt) or reg_period)
        if reg and reg[0] == "ask-state":
            text = (f"Constituency number {reg[1]} exists in both Andhra Pradesh and Telangana -- which one? "
                    f"Try \"AC {reg[1]} AP\" or \"AC {reg[1]} Telangana\".")
            st.info(text)
            st.session_state.messages.append({"role": "assistant", "content": text, "note": True})
        elif reg:
            run_regional_turn(prompt, reg[0], reg[1], key_prefix)
        elif st.session_state.trigger_carousel or uc.detect_carousel_request(prompt):
            car = st.session_state.trigger_carousel or (car_day, CAROUSEL_STATE_CHOICES[car_states_label])
            st.session_state.trigger_carousel = None
            run_carousel_turn(prompt, car[0], car[1], key_prefix)
        elif wrap_choice:
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

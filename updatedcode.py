#!/usr/bin/env python3
"""
Indian Politician & Party Intelligence Agent  (all-in-one)
=============================================================

Give it a politician (or a nickname like "KCR") OR a political party (like
"BJP", "Congress", "BRS", "TDP") and a time window (--daily, --weekly, or
--from-date/--to-date). Known parties are detected automatically; use
--type party (or --party) for one that isn't in the built-in list. It
gathers everything it can reach legitimately, then writes one briefing:

  BASIC DETAILS ......... Wikipedia
  NEWS HEADLINES ........ GDELT (real date-range search), Google News RSS fallback
  SUMMARY ............... written by Sarvam AI (Indian LLM) from the data below;
                          falls back to a template summary if Sarvam is unavailable.
                          Politicians: top line, dated timeline, actions, statements,
                          controversies, ground work, maneuvering, sentiment, what to watch.
                          Parties: top line, dated timeline, leadership, policy &
                          governance, elections, alliances & rivals, controversies,
                          sentiment, what to watch.
  SOCIAL / PUBLIC ....... PRIMARY: Brave Search API -- search-indexed public posts on
                          X / Instagram / Facebook / YouTube.
                          BACKUP for X: the paid X API, used only if Brave finds
                          fewer than X_BACKUP_THRESHOLD (3) X results.
                          Also: YouTube (API search + official channel feeds),
                          Telegram public channels, Reddit, Facebook/Instagram
                          political ads (Meta Ad Library), and news stories about
                          their social posts
  SOURCES CHECKED ....... what ran, what was skipped and why

Every optional source is skipped gracefully if its key isn't set.

--------------------------------------------------------------------------
SETUP
--------------------------------------------------------------------------
    pip install requests beautifulsoup4 sarvamai
    pip install reportlab          # optional, only needed for --pdf

Environment variables (all optional except that without SARVAM_API_KEY you
get a template summary instead of a written narrative):

    SARVAM_API_KEY     dashboard.sarvam.ai (free credits on signup)
    X_BEARER_TOKEN     developer.x.com (paid, pay-per-use; last 7 days only;
                       BACKUP to Brave -- only called when Brave finds few X results)
    YOUTUBE_API_KEY    console.cloud.google.com, enable "YouTube Data API v3"
                       (free, ~100 searches/day)
    META_ACCESS_TOKEN  developers.facebook.com (Ad Library; needs identity
                       confirmation; political/issue ADS only)
    BRAVE_API_KEY      brave.com/search/api (check current free allowance)

  Windows PowerShell:   $env:SARVAM_API_KEY="..."
  macOS / Linux:        export SARVAM_API_KEY="..."

  RECOMMENDED -- set them once instead of every session: create a file
  named .env in this same folder (see .env.example) with lines like
      SARVAM_API_KEY=sk_...
  then:  pip install python-dotenv
  The script loads it automatically. Keys typed directly in your shell
  still override it, so this never conflicts with a one-off change.
  IMPORTANT: never commit or share this file -- it contains your real keys.

Optional file politician_handles.json (same folder) -- lists each
politician's OFFICIAL YouTube channel IDs and PUBLIC Telegram channels, plus
extra nicknames. I can't guess channel IDs reliably, so you fill them in:

    {
      "K. Chandrashekar Rao": {
        "aliases": ["KCR"],
        "youtube_channel_ids": ["UCxxxxxxxxxxxxxxxxxxxxxx"],
        "telegram_channels": ["channelname"]
      },
      "Bharatiya Janata Party": {
        "type": "party",
        "youtube_channel_ids": ["UCxxxxxxxxxxxxxxxxxxxxxx"],
        "telegram_channels": ["channelname"]
      }
    }

Parties use the same format plus "type": "party". Major parties are
recognized without any entry here; add one only to list a party's official
channels, or to add a party that isn't built in (optionally with
"search_terms": ["ABC", "Full Party Name"]).

--------------------------------------------------------------------------
USAGE
--------------------------------------------------------------------------
    python updatedcode.py --test                    # check your setup
    python updatedcode.py "Narendra Modi"
    python updatedcode.py "KCR" --weekly --save
    python updatedcode.py "Rahul Gandhi" --daily
    python updatedcode.py "KCR" --from-date 2026-09-01 --to-date 2026-09-20
    python updatedcode.py "BJP" --weekly --pdf          # party report (auto-detected)
    python updatedcode.py "Congress" --daily
    python updatedcode.py "Some New Party" --party --weekly

    Daily news wrap-up for Andhra Pradesh and Telangana (not about any one politician):
    python updatedcode.py --wrap                          # both states, today (India time)
    python updatedcode.py --wrap telangana --save
    python updatedcode.py --wrap ap --date 2026-10-09 --pdf
    python updatedcode.py --wrap --from-date 2026-10-01 --to-date 2026-10-07 --save   # a date range (max 31 days)
    python updatedcode.py --wrap telangana --wrap-party BRS               # one party's news in AP/Telangana
    python updatedcode.py --carousel --save --pdf                         # DRAFT 10-slide daily news carousel
    (In interactive mode, typing "daily wrap", "today's news telangana",
     "AP roundup", "weekly wrap" or "telangana wrap last 5 days" does the same.)

Flags:
    --save  --pdf  --headlines N  --model NAME  --config FILE
    --type auto|politician|party   --party (shortcut for --type party)
    --from-date/--to-date YYYY-MM-DD   --daily   --weekly
    --platforms x,instagram,facebook,youtube   (which platforms Brave searches)
    --no-reddit --no-x --no-youtube --no-ads --no-telegram --no-brave --no-social-news
    --x-always   also call the X API even when Brave already found enough X results
    --wrap [both|ap|telangana]   news wrap-up instead of a report
        --date YYYY-MM-DD for one day, or --from-date/--to-date for a range of days (max 31)

Every report includes TOP STORIES: the period's coverage grouped so that the
same story from several outlets counts once, ranked by how many separate
outlets carried it -- the AI summary uses this to judge what mattered most.

Note: this tool no longer includes any fact-checking. For checking a video,
a claim, or published fact-checks, use the separate video_factcheck.py /
video_factcheck_app.py tools instead -- they're intentionally independent
of this one.

--------------------------------------------------------------------------
HONEST LIMITATIONS
--------------------------------------------------------------------------
* Instagram/Facebook: no API at any price exposes organic posts (Meta closed
  that in 2018). You get political ADS (Ad Library) plus whatever public
  posts a search index happens to hold. This tool does not scrape those
  platforms or bypass their logins/bot protection.
* X via Brave: a PARTIAL sample of what a search index holds (X restricts crawlers).
  X via the API backup: complete but only the last 7 days; older windows get no API posts.
* Search-indexed results are a PARTIAL sample -- X/Instagram/Facebook restrict
  crawlers, so expect gaps (YouTube is indexed well).
* Sarvam writes only from the data handed to it and cannot verify anything
  else. Always check the linked sources for anything important.
* Sarvam renames/deprecates models now and then; if you see a "deprecated"
  error, check docs.sarvam.ai and pass the current name with --model.
"""

from __future__ import annotations

import os
import re
import math
import sys
import json
import base64
import hashlib
import time
import threading
import argparse
import textwrap
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, quote
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run:  pip install requests beautifulsoup4 sarvamai")

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # Telegram source is skipped if this is missing

try:
    from sarvamai import SarvamAI
except ImportError:
    SarvamAI = None  # falls back to a template summary

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
except ImportError:
    SimpleDocTemplate = None  # --pdf is skipped with a clear message if reportlab isn't installed

# Load API keys from a .env file in this folder, if present, so you don't have
# to re-type $env:/export commands every session. See .env.example for the
# format. Silently does nothing if python-dotenv isn't installed or there's
# no .env file -- keys set directly in the shell still work either way, and
# take priority over anything in .env (override=False keeps it that way).
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PoliticianInfoAgent/1.0; personal research tool)"}
DEFAULT_MODEL = "sarvam-105b"
CONFIG_PATH = "politician_handles.json"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# The paid X API is only a BACKUP to Brave. It runs when Brave finds fewer than
# this many X results (or Brave isn't configured). Raise it to lean on the API
# more, lower it to save money, or pass --x-always to always call it.
X_BACKUP_THRESHOLD = 3

PLATFORMS = {
    "x": ("X / Twitter", ["x.com", "twitter.com"]),
    "instagram": ("Instagram", ["instagram.com"]),
    "facebook": ("Facebook", ["facebook.com"]),
    "youtube": ("YouTube", ["youtube.com"]),
}

_YT_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


class SourceSkipped(Exception):
    """Raised when a source can't run for a normal, explainable reason."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_iso_date(value):
    """Parse an ISO-8601 date/time string to a naive-UTC datetime, or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def mentions_any(text: str, names: list) -> bool:
    """True if any of the given name variants appears in `text` (case-insensitive).

    Used to drop results from loosely-matched sources (Reddit, Brave search)
    that don't actually mention the politician. Not applied to GDELT/Google
    News, since those already search for the exact quoted name and re-checking
    the title alone would wrongly drop real articles that mention the person
    only in the body text.
    """
    if not text:
        return False
    t = text.lower()
    for n in names:
        if n and re.search(r"(?<![a-z0-9])" + re.escape(n.lower()) + r"(?![a-z0-9])", t):
            return True
    return False


def filter_relevant(items: list, names: list, text_fn) -> "tuple[list, int]":
    """Keep only items where text_fn(item) mentions one of `names`.

    Returns (kept_items, number_dropped) so callers can report what happened.
    """
    kept = [it for it in items if mentions_any(text_fn(it), names)]
    return kept, len(items) - len(kept)


# --------------------------------------------------------------------------
# Nickname / initials resolution (e.g. "KCR" -> "K. Chandrashekar Rao")
# --------------------------------------------------------------------------
# Curated and not exhaustive. Add entries freely (keys are lowercase). Only
# add names that are genuinely unambiguous. You can also add aliases per
# politician in politician_handles.json.
POLITICIAN_ALIASES = {
    "kcr": "K. Chandrashekar Rao",
    "ktr": "K. T. Rama Rao",
    "ysr": "Y. S. Rajasekhara Reddy",
    "raga": "Rahul Gandhi",
    "didi": "Mamata Banerjee",
    "dks": "D. K. Shivakumar",
    "stalin": "M. K. Stalin",
    "jagan": "Y. S. Jagan Mohan Reddy",
    "chandrababu": "N. Chandrababu Naidu",
    "fadnavis": "Devendra Fadnavis",
    "kejriwal": "Arvind Kejriwal",
    "owaisi": "Asaduddin Owaisi",
    "akhilesh": "Akhilesh Yadav",
    "tejashwi": "Tejashwi Yadav",
    "lalu": "Lalu Prasad Yadav",
    "nitish": "Nitish Kumar",
    "vijayan": "Pinarayi Vijayan",
    "kharge": "Mallikarjun Kharge",
    "sonia": "Sonia Gandhi",
    "modi": "Narendra Modi",
    "uddhav": "Uddhav Thackeray",
    "shinde": "Eknath Shinde",
    "mamata": "Mamata Banerjee",
    "yogi": "Yogi Adityanath",
}


def resolve_politician_name(raw_name: str) -> "tuple[str, bool]":
    key = raw_name.strip().lower()
    if key in POLITICIAN_ALIASES:
        return POLITICIAN_ALIASES[key], True
    return raw_name.strip(), False


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: couldn't read {path} ({e}). Continuing without it.")
        return {}


def resolve_identity(raw: str, config_path: str) -> "tuple[str, list, dict, bool]":
    """Return (canonical_name, all_search_names, config_entry, was_recognized)."""
    raw = raw.strip()
    canonical, was_alias = resolve_politician_name(raw)
    entry, recognized = {}, was_alias
    wanted = {raw.lower(), canonical.lower()}
    for key, e in load_config(config_path).items():
        names = [key.lower()] + [a.lower() for a in e.get("aliases", [])]
        if wanted & set(names):
            entry, canonical, recognized = e, key, (recognized or key.lower() != raw.lower())
            break

    names = [canonical] + list(entry.get("aliases", []))
    if raw.lower() != canonical.lower():
        names.append(raw)
    seen, unique = set(), []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            unique.append(n)
    return canonical, unique, entry, recognized


# --------------------------------------------------------------------------
# Political parties: recognition and search terms
# --------------------------------------------------------------------------
# canonical name -> (aliases a user might type, search terms). The FIRST search
# term is the "primary" one, used for sources that take a single keyword
# (Reddit, YouTube, X, Meta Ad Library). All terms are OR'd together for news.
# Deliberately left out of search terms: short forms that are ambiguous on
# their own (e.g. "Congress" alone matches the US Congress, "CPI" matches the
# Consumer Price Index, "SP" is too short for GDELT). They still work as
# things you can TYPE to select the party.
POLITICAL_PARTIES = {
    "Bharatiya Janata Party": (["BJP"], ["BJP", "Bharatiya Janata Party"]),
    "Indian National Congress": (["Congress", "INC", "Congress party", "Congress Party"],
                                 ["Congress party", "Indian National Congress"]),
    "Bharat Rashtra Samithi": (["BRS", "TRS", "Telangana Rashtra Samithi"], ["BRS", "Bharat Rashtra Samithi"]),
    "Telugu Desam Party": (["TDP", "Telugu Desam"], ["TDP", "Telugu Desam"]),
    "YSR Congress Party": (["YSRCP", "YSRC", "YSR Congress"], ["YSRCP", "YSR Congress"]),
    "Jana Sena Party": (["Jana Sena", "Janasena", "JSP"], ["Jana Sena", "Janasena"]),
    "Aam Aadmi Party": (["AAP"], ["Aam Aadmi Party", "AAP"]),
    "All India Trinamool Congress": (["TMC", "AITC", "Trinamool", "Trinamool Congress"], ["Trinamool", "TMC"]),
    "Dravida Munnetra Kazhagam": (["DMK"], ["DMK", "Dravida Munnetra Kazhagam"]),
    "All India Anna Dravida Munnetra Kazhagam": (["AIADMK", "ADMK"], ["AIADMK"]),
    "Samajwadi Party": (["SP", "Samajwadi"], ["Samajwadi Party"]),
    "Bahujan Samaj Party": (["BSP"], ["BSP", "Bahujan Samaj Party"]),
    "Nationalist Congress Party": (["NCP"], ["NCP", "Nationalist Congress Party"]),
    "Shiv Sena": (["Shinde Sena"], ["Shiv Sena"]),
    "Shiv Sena (UBT)": (["Shiv Sena UBT", "Sena UBT", "UBT"], ["Shiv Sena UBT", "Sena UBT"]),
    "Communist Party of India (Marxist)": (["CPI(M)", "CPIM", "CPM"], ["CPI(M)", "CPIM"]),
    "Communist Party of India": (["CPI"], ["Communist Party of India"]),
    "Janata Dal (United)": (["JDU", "JD(U)"], ["JD(U)", "JDU"]),
    "Janata Dal (Secular)": (["JDS", "JD(S)"], ["JD(S)", "JDS"]),
    "Rashtriya Janata Dal": (["RJD"], ["RJD", "Rashtriya Janata Dal"]),
    "All India Majlis-e-Ittehadul Muslimeen": (["AIMIM", "MIM"], ["AIMIM"]),
    "Biju Janata Dal": (["BJD"], ["BJD", "Biju Janata Dal"]),
    "Shiromani Akali Dal": (["SAD", "Akali Dal"], ["Akali Dal", "Shiromani Akali Dal"]),
    "Jharkhand Mukti Morcha": (["JMM"], ["JMM", "Jharkhand Mukti Morcha"]),
    "Indian Union Muslim League": (["IUML"], ["IUML", "Indian Union Muslim League"]),
}

_PARTY_LOOKUP = {}
for _canon, (_aliases, _terms) in POLITICAL_PARTIES.items():
    for _n in [_canon] + _aliases:
        _PARTY_LOOKUP[_n.lower()] = _canon


def _unique(names: list) -> list:
    seen, out = set(), []
    for n in names:
        if n and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def build_news_query(terms: list, india_only: bool = False) -> str:
    """Build a quoted (OR'd, if several) search query from terms, e.g.
    ("BJP" OR "Bharatiya Janata Party"). Terms under 3 characters are left out
    because GDELT rejects them. india_only adds GDELT's sourcecountry:IN
    filter, which keeps e.g. US "Congress" stories out of party searches.
    """
    usable = [t for t in terms if len(re.sub(r"\W", "", t)) >= 3] or terms[:1]
    query = f'"{usable[0]}"' if len(usable) == 1 else "(" + " OR ".join(f'"{t}"' for t in usable) + ")"
    return query + (" sourcecountry:IN" if india_only else "")


def _phrase(name: str) -> str:
    """Quote a plain name for search. A query already built by
    build_news_query() (starting with a quote or parenthesis) is used as-is."""
    return name if name[:1] in ('"', "(") else f'"{name}"'


def resolve_subject(raw: str, config_path: str, subject_type: str = "auto") -> dict:
    """Work out whether `raw` is a politician or a political party, and how to
    search for it. subject_type: "auto" (detect), "politician", or "party".

    Returns a dict: type, name (canonical), search_names (for relevance checks
    and Brave), entry (politician_handles.json entry, if any), recognized,
    primary_term (single keyword sources), news_terms (OR'd for news).
    """
    raw = raw.strip()
    key = raw.lower()
    config = load_config(config_path)

    config_party = None
    for k, e in config.items():
        names = [k.lower()] + [a.lower() for a in e.get("aliases", [])]
        if key in names and e.get("type") == "party":
            config_party = (k, e)
            break
    known_party = _PARTY_LOOKUP.get(key)
    is_party = subject_type == "party" or (subject_type == "auto" and (config_party or known_party))

    if not is_party:
        name, search_names, entry, recognized = resolve_identity(raw, config_path)
        return {"type": "politician", "name": name, "search_names": search_names, "entry": entry,
                "recognized": recognized, "primary_term": name, "news_terms": [name]}

    if config_party:
        name, entry = config_party
        aliases, terms = POLITICAL_PARTIES.get(name, ([], [name]))
        terms = entry.get("search_terms") or terms
    elif known_party:
        name, entry = known_party, {}
        for k, e in config.items():  # channels may be listed under the full party name
            if k.lower() == name.lower():
                entry = e
        aliases, terms = POLITICAL_PARTIES[name]
        terms = entry.get("search_terms") or terms
    else:  # forced party mode for a party not in the list
        name, entry, terms = raw, {}, [raw]

    return {"type": "party", "name": name, "search_names": _unique([name] + list(terms)), "entry": entry,
            "recognized": name.lower() != key, "primary_term": terms[0], "news_terms": list(terms)}


# --------------------------------------------------------------------------
# Data sources (pulled in unchanged from the individually tested scripts)
# --------------------------------------------------------------------------

def find_wikipedia_title(name: str) -> "str | None":
    url = "https://en.wikipedia.org/w/api.php"
    params = {"action": "query", "list": "search", "srsearch": name, "format": "json", "srlimit": 1}
    resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    results = resp.json().get("query", {}).get("search", [])
    return results[0]["title"] if results else None


def get_wikipedia_summary(name: str) -> dict:
    title = find_wikipedia_title(name)
    if not title:
        return {"found": False}

    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        return {"found": False}

    data = resp.json()
    if data.get("type") == "disambiguation":
        return {"found": False, "disambiguation": True, "title": title}

    return {
        "found": True,
        "title": data.get("title", title),
        "description": data.get("description", ""),
        "extract": data.get("extract", ""),
        "page_url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
    }


def get_gdelt_news(
    name: str,
    max_records: int = 40,
    start_date: "datetime | None" = None,
    end_date: "datetime | None" = None,
) -> list[dict]:
    """Fetch news articles from GDELT's free DOC 2.0 API.

    GDELT is used (instead of/alongside Google News RSS) specifically
    because it supports real startdatetime/enddatetime filtering, which
    is what makes daily/weekly/date-range reports actually accurate.
    """
    params = {
        "query": _phrase(name),
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(min(max_records, 250)),
        "sort": "datedesc",
    }
    if start_date:
        params["startdatetime"] = start_date.strftime("%Y%m%d%H%M%S")
    if end_date:
        params["enddatetime"] = (end_date + timedelta(days=1)).strftime("%Y%m%d%H%M%S")
    if not start_date and not end_date:
        params["timespan"] = "1M"  # default: last month, when no explicit window given

    # GDELT asks for roughly 1 request per 5 seconds; retry once with backoff
    # on 429s, then let the caller fall back to Google News RSS.
    import time
    resp = None
    for attempt in range(2):
        resp = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, headers=HEADERS, timeout=20)
        if resp.status_code != 429:
            break
        wait = 4 * (attempt + 1)
        print(f"  (GDELT rate-limited, retrying in {wait}s...)")
        time.sleep(wait)
    resp.raise_for_status()

    try:
        data = resp.json()
    except ValueError:
        # GDELT occasionally returns an empty body or HTML error page.
        return []

    articles = data.get("articles", [])
    results = []
    for a in articles:
        seendate = a.get("seendate", "")
        date_parsed = None
        try:
            date_parsed = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ")
        except ValueError:
            pass
        results.append({
            "headline": a.get("title", "(no title)"),
            "source": a.get("domain", ""),
            "date": date_parsed.strftime("%a, %d %b %Y") if date_parsed else seendate,
            "date_parsed": date_parsed,
            "url": a.get("url", ""),
        })
    return results


def get_google_news_fallback(
    name: str,
    max_records: int = 40,
    start_date: "datetime | None" = None,
    end_date: "datetime | None" = None,
) -> list[dict]:
    """Fallback headline source if GDELT is unavailable/rate-limited.

    Google News RSS doesn't support true server-side date filtering, so
    results are filtered client-side against the requested window.
    """
    from email.utils import parsedate_to_datetime

    query = requests.utils.quote(_phrase(name))
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.content)
    items = root.findall(".//item")

    results = []
    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")
        date_el = item.find("pubDate")
        source_el = item.find("source")

        raw_title = title_el.text if title_el is not None else "(no title)"
        source_name = source_el.text if source_el is not None else ""
        headline_text = raw_title
        if source_name and raw_title.endswith(f" - {source_name}"):
            headline_text = raw_title[: -(len(source_name) + 3)]

        date_parsed = None
        if date_el is not None and date_el.text:
            try:
                date_parsed = parsedate_to_datetime(date_el.text).replace(tzinfo=None)
            except (TypeError, ValueError):
                pass

        if start_date and date_parsed and date_parsed < start_date:
            continue
        if end_date and date_parsed and date_parsed > end_date + timedelta(days=1):
            continue

        results.append({
            "headline": headline_text.strip(),
            "source": source_name.strip(),
            "date": date_parsed.strftime("%a, %d %b %Y") if date_parsed else (date_el.text if date_el is not None else ""),
            "date_parsed": date_parsed,
            "url": link_el.text if link_el is not None else "",
        })
        if len(results) >= max_records:
            break

    return results


def get_reddit_mentions(
    name: str,
    max_results: int = 10,
    start_date: "datetime | None" = None,
    end_date: "datetime | None" = None,
) -> list[dict]:
    """Fetch public Reddit posts mentioning the politician (free, no API key)."""
    query = requests.utils.quote(f'"{name}"')
    url = f"https://www.reddit.com/search.json?q={query}&sort=new&limit=50"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    results = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        created = post.get("created_utc")
        post_dt = datetime.fromtimestamp(created, timezone.utc).replace(tzinfo=None) if created else None

        if start_date and post_dt and post_dt < start_date:
            continue
        if end_date and post_dt and post_dt > end_date + timedelta(days=1):
            continue

        results.append({
            "title": post.get("title", "(no title)"),
            "subreddit": post.get("subreddit_name_prefixed", ""),
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "date_parsed": post_dt,
            "date": post_dt.strftime("%a, %d %b %Y") if post_dt else "",
            "url": f"https://www.reddit.com{post.get('permalink', '')}" if post.get("permalink") else "",
        })
        if len(results) >= max_results:
            break

    results.sort(key=lambda r: r["num_comments"], reverse=True)
    return results


def get_youtube_videos(
    name: str,
    api_key: str,
    max_results: int = 10,
    start_date: "datetime | None" = None,
    end_date: "datetime | None" = None,
) -> list[dict]:
    """Fetch recent YouTube videos mentioning the politician.

    Free (YouTube Data API v3 has no paid tier -- it's quota-based: 10,000
    free units/day, and a single search costs 100 units, so roughly 100
    searches/day free). Supports real date-range filtering.
    """
    params = {
        "key": api_key,
        "q": name,
        "part": "snippet",
        "type": "video",
        "order": "date",
        "maxResults": max(1, min(max_results, 50)),
        "relevanceLanguage": "en",
    }
    if start_date:
        params["publishedAfter"] = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    if end_date:
        params["publishedBefore"] = (end_date + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    resp = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=15)
    if resp.status_code == 403:
        raise ValueError("YouTube API returned 403 -- likely daily quota exceeded (10,000 units/day, resets at midnight Pacific) or an invalid key.")
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        published = snippet.get("publishedAt", "")
        try:
            pub_dt = datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pub_dt = None

        video_id = item.get("id", {}).get("videoId", "")
        results.append({
            "title": snippet.get("title", "(no title)"),
            "channel": snippet.get("channelTitle", ""),
            "date_parsed": pub_dt,
            "date": pub_dt.strftime("%a, %d %b %Y") if pub_dt else published,
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        })
    return results


def get_meta_ads(
    name: str,
    access_token: str,
    max_results: int = 10,
    start_date: "datetime | None" = None,
    end_date: "datetime | None" = None,
) -> list[dict]:
    """Fetch political/issue ads about the politician from Meta's Ad Library.

    HONEST LIMITATION: Meta does not offer a general search API for organic
    Facebook/Instagram posts (that was shut down platform-wide in 2018 for
    privacy reasons -- no amount of payment reopens it). The Ad Library API
    is the one real, official, relevant thing Meta does offer for a
    politician specifically: it covers political and issue ads (worldwide,
    kept for 7 years) run BY or ABOUT them across Facebook, Instagram,
    Messenger, and Audience Network. It's free, but requires you to
    complete Meta's identity confirmation process for political ad data
    access on your developer account first.
    """
    url = "https://graph.facebook.com/v20.0/ads_archive"
    params = {
        "access_token": access_token,
        "search_terms": name,
        "ad_type": "POLITICAL_AND_ISSUE_ADS",
        "ad_reached_countries": json.dumps(["IN"]),
        "ad_active_status": "ALL",
        "fields": "page_name,ad_creative_bodies,ad_delivery_start_time,ad_delivery_stop_time,ad_snapshot_url,publisher_platforms",
        "limit": max(1, min(max_results, 50)),
    }
    if start_date:
        params["ad_delivery_date_min"] = start_date.strftime("%Y-%m-%d")
    if end_date:
        params["ad_delivery_date_max"] = end_date.strftime("%Y-%m-%d")

    resp = requests.get(url, params=params, timeout=15)
    if resp.status_code in (400, 401, 403):
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        raise ValueError(
            f"Meta Ad Library API rejected the request ({resp.status_code}): {detail}. "
            "Check META_ACCESS_TOKEN is valid and has completed identity confirmation "
            "for political ads access."
        )
    resp.raise_for_status()
    data = resp.json()

    results = []
    for ad in data.get("data", []):
        bodies = ad.get("ad_creative_bodies", [])
        results.append({
            "page_name": ad.get("page_name", ""),
            "text": bodies[0] if bodies else "",
            "start_date": ad.get("ad_delivery_start_time", ""),
            "platforms": ", ".join(ad.get("publisher_platforms", [])),
            "url": ad.get("ad_snapshot_url", ""),
        })
    return results


def group_headlines_by_day(headlines: list[dict]) -> list[tuple]:
    groups: dict = {}
    undated = []
    for h in headlines:
        dt = h.get("date_parsed")
        if dt:
            key = dt.strftime("%A, %b %d, %Y")
            groups.setdefault(key, []).append(h)
        else:
            undated.append(h)

    ordered = sorted(groups.items(), key=lambda item: item[1][0]["date_parsed"], reverse=True)
    if undated:
        ordered.append(("Undated", undated))
    return ordered


def _filter_by_date(items: list[dict], start_date, end_date) -> list[dict]:
    out = []
    for it in items:
        dt = it.get("date_parsed")
        if dt is not None:
            if start_date and dt < start_date:
                continue
            if end_date and dt >= end_date + timedelta(days=1):
                continue
        out.append(it)
    out.sort(key=lambda i: i.get("date_parsed") or datetime.min, reverse=True)
    return out


def parse_youtube_feed(xml_bytes: bytes) -> list[dict]:
    """Parse a YouTube channel Atom feed into a list of video dicts."""
    root = ElementTree.fromstring(xml_bytes)
    channel_title = (root.findtext("atom:title", default="", namespaces=_YT_NS) or "").strip()

    videos = []
    for entry in root.findall("atom:entry", _YT_NS):
        published = entry.findtext("atom:published", default="", namespaces=_YT_NS)
        try:
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pub_dt = None

        link_el = entry.find("atom:link", _YT_NS)
        views = None
        stats = entry.find("media:group/media:community/media:statistics", _YT_NS)
        if stats is not None and stats.get("views"):
            try:
                views = int(stats.get("views"))
            except ValueError:
                pass

        videos.append({
            "title": (entry.findtext("atom:title", default="(no title)", namespaces=_YT_NS) or "").strip(),
            "channel": channel_title,
            "date_parsed": pub_dt,
            "date": pub_dt.strftime("%a, %d %b %Y") if pub_dt else published,
            "views": views,
            "url": link_el.get("href") if link_el is not None else "",
        })
    return videos


def get_youtube_channel_uploads(channel_id: str, start_date=None, end_date=None) -> list[dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    if resp.status_code == 404:
        raise ValueError(f"YouTube channel ID '{channel_id}' not found -- double-check it starts with 'UC'.")
    resp.raise_for_status()

    videos = parse_youtube_feed(resp.content)
    return _filter_by_date(videos, start_date, end_date)


def parse_telegram_html(html: str, channel: str) -> list[dict]:
    """Parse one page of a Telegram public channel preview into post dicts."""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for wrap in soup.select("div.tgme_widget_message_wrap"):
        msg = wrap.select_one("div.tgme_widget_message")
        if msg is None:
            continue

        text_el = wrap.select_one("div.tgme_widget_message_text")
        text = text_el.get_text(" ", strip=True) if text_el else ""

        date_link = wrap.select_one("a.tgme_widget_message_date")
        time_el = date_link.select_one("time") if date_link else None
        post_dt = None
        if time_el is not None and time_el.get("datetime"):
            try:
                post_dt = datetime.fromisoformat(time_el["datetime"]).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                pass

        views_el = wrap.select_one("span.tgme_widget_message_views")
        post_id = None
        data_post = msg.get("data-post", "")  # e.g. "channelname/1234"
        if "/" in data_post:
            try:
                post_id = int(data_post.rsplit("/", 1)[1])
            except ValueError:
                pass

        # Skip media-only posts with no caption -- nothing useful to summarize.
        if not text:
            continue

        posts.append({
            "text": text,
            "channel": channel,
            "post_id": post_id,
            "date_parsed": post_dt,
            "date": post_dt.strftime("%a, %d %b %Y") if post_dt else "",
            "views": views_el.get_text(strip=True) if views_el else "",
            "url": date_link["href"] if date_link and date_link.get("href") else f"https://t.me/{data_post}",
        })
    return posts


def get_telegram_channel_posts(channel: str, start_date=None, end_date=None, max_pages: int = 5) -> list[dict]:
    """Fetch recent posts from a PUBLIC Telegram channel, paging backwards.

    Stops once it reaches posts older than start_date, or after max_pages.
    Waits between page requests so it stays polite.
    """
    channel = channel.strip().lstrip("@")
    all_posts: list[dict] = []
    before = None

    for page in range(max_pages):
        url = f"https://t.me/s/{channel}"
        if before:
            url += f"?before={before}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            raise ValueError(f"Telegram channel '{channel}' not found or not public.")
        resp.raise_for_status()

        page_posts = parse_telegram_html(resp.text, channel)
        if not page_posts:
            break
        all_posts.extend(page_posts)

        dated = [p["date_parsed"] for p in page_posts if p["date_parsed"]]
        ids = [p["post_id"] for p in page_posts if p["post_id"]]
        if not ids:
            break
        if start_date and dated and min(dated) < start_date:
            break  # already paged back far enough
        before = min(ids)
        time.sleep(1.0)

    return _filter_by_date(all_posts, start_date, end_date)


def get_social_news_coverage(name: str, max_results: int = 20, start_date=None, end_date=None) -> list[dict]:
    """Find news stories about what the politician posted/said on social media.

    This catches posts that MADE NEWS on X, Instagram, Facebook, etc. It does
    not (and can't) list everything they posted.
    """
    query = f'{_phrase(name)} (tweet OR "posted on X" OR Instagram OR Facebook post OR "social media post")'
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    root = ElementTree.fromstring(resp.content)
    results = []
    for item in root.findall(".//item"):
        raw_title = (item.findtext("title") or "(no title)").strip()
        source = (item.findtext("source") or "").strip()
        headline = raw_title[: -(len(source) + 3)] if source and raw_title.endswith(f" - {source}") else raw_title

        pub_dt = None
        pub_text = item.findtext("pubDate")
        if pub_text:
            try:
                pub_dt = parsedate_to_datetime(pub_text).astimezone(timezone.utc).replace(tzinfo=None)
            except (TypeError, ValueError):
                pass

        results.append({
            "headline": headline,
            "source": source,
            "date_parsed": pub_dt,
            "date": pub_dt.strftime("%a, %d %b %Y") if pub_dt else (pub_text or ""),
            "url": item.findtext("link") or "",
        })

    return _filter_by_date(results, start_date, end_date)[:max_results]


def build_query(names: list[str], domains: list[str]) -> str:
    """e.g.  (site:x.com OR site:twitter.com) ("Full Name" OR "KCR")"""
    site_part = " OR ".join(f"site:{d}" for d in domains)
    name_part = " OR ".join(f'"{n}"' for n in names)
    query = f"({site_part}) ({name_part})"
    return query[:390]


def parse_page_age(value: str) -> "datetime | None":
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:26] if "." in value else value, fmt)
        except ValueError:
            continue
    return None


def brave_search(query: str, api_key: str, start_date=None, end_date=None, count: int = 20) -> list[dict]:
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    params = {"q": query, "count": min(count, 20), "country": "IN", "search_lang": "en"}
    if start_date and end_date:
        params["freshness"] = f"{start_date.strftime('%Y-%m-%d')}to{end_date.strftime('%Y-%m-%d')}"

    def _get(p):
        last_exc = None
        for attempt in range(3):
            try:
                r = requests.get(BRAVE_URL, headers=headers, params=p, timeout=30)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exc = e
                time.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code == 429 and attempt < 2:
                time.sleep(2.0 * (attempt + 1))  # free plans allow roughly 1 request/second
                continue
            return r
        raise ValueError(f"Brave did not respond after 3 attempts ({type(last_exc).__name__}). Try again in a minute.")

    resp = _get(params)
    if resp.status_code == 422 and "freshness" in params:
        # Date-range syntax rejected -- retry without it and filter client-side instead.
        params.pop("freshness")
        resp = _get(params)

    if resp.status_code in (401, 403):
        raise ValueError(f"Brave rejected the API key ({resp.status_code}). Check BRAVE_API_KEY and your plan.")
    if resp.status_code == 429:
        raise ValueError("Brave rate limit / monthly quota reached (429).")
    resp.raise_for_status()

    results = []
    for r in resp.json().get("web", {}).get("results", []):
        results.append({
            "title": re.sub(r"<[^>]+>", "", r.get("title", "(no title)") or "(no title)"),
            "url": r.get("url", ""),
            "snippet": re.sub(r"<[^>]+>", "", r.get("description", "") or ""),
            "date_parsed": parse_page_age(r.get("page_age", "")),
            "date": (r.get("page_age", "") or "")[:10],
        })
    return results


def search_platform(names, platform_key, api_key, start_date, end_date) -> list[dict]:
    label, domains = PLATFORMS[platform_key]
    query = build_query(names, domains)
    raw = brave_search(query, api_key, start_date, end_date)

    seen, out = set(), []
    for item in raw:
        url = item["url"]
        host = (urlparse(url).hostname or "").lower()
        if not any(host == d or host.endswith("." + d) for d in domains):
            continue  # keep only results genuinely hosted on the platform
        if url in seen:
            continue
        seen.add(url)
        dt = item["date_parsed"]
        if dt is not None:                        # client-side date check (dated results only)
            if start_date and dt < start_date:
                continue
            if end_date and dt >= end_date + timedelta(days=1):
                continue
        item["platform"] = label
        out.append(item)
    return out


def get_x_recent_posts(name, bearer_token, max_results=15, start_date=None, end_date=None) -> list:
    """X v2 recent search (paid, pay-per-use). Only covers the last 7 days.

    The requested window is clamped to that range and sent to X as
    start_time/end_time, so --from-date/--to-date inside the last week work.
    """
    now = utc_now()
    earliest = now - timedelta(days=7) + timedelta(minutes=5)
    start = max(start_date, earliest) if start_date else None
    end = min(end_date + timedelta(days=1), now - timedelta(seconds=30)) if end_date else None
    if start and end and start >= end:
        raise SourceSkipped("requested window is outside X's 7-day recent-search range")

    headers = {**HEADERS, "Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": f'"{name}" -is:retweet lang:en',
        "max_results": max(10, min(max_results, 100)),
        "tweet.fields": "created_at,public_metrics,author_id",
        "expansions": "author_id",
        "user.fields": "username,name",
    }
    if start:
        params["start_time"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    if end:
        params["end_time"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")

    resp = requests.get("https://api.x.com/2/tweets/search/recent", headers=headers, params=params, timeout=15)
    if resp.status_code == 401:
        raise ValueError("X API rejected the bearer token (401). Check X_BEARER_TOKEN.")
    if resp.status_code == 429:
        raise ValueError("X API rate-limited this request (429). Wait and retry.")
    resp.raise_for_status()
    data = resp.json()

    users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
    results = []
    for post in data.get("data", []):
        created = post.get("created_at", "")
        try:
            dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            dt = None
        author = users.get(post.get("author_id"), {})
        m = post.get("public_metrics", {})
        results.append({
            "text": post.get("text", ""),
            "author": author.get("name", ""),
            "handle": author.get("username", ""),
            "date_parsed": dt,
            "date": dt.strftime("%a, %d %b %Y") if dt else created,
            "likes": m.get("like_count", 0),
            "reposts": m.get("retweet_count", 0),
            "url": f"https://x.com/{author.get('username', 'i')}/status/{post.get('id', '')}",
        })
    results.sort(key=lambda p: p.get("likes", 0), reverse=True)
    return results[:max_results]


# --------------------------------------------------------------------------
# Config-driven sources (YouTube channel feeds, Telegram) + source runner
# --------------------------------------------------------------------------

def _real_entries(values) -> list:
    return [v for v in values or [] if v and not str(v).startswith("REPLACE_")]


def collect_youtube_feeds(entry, start_date, end_date) -> list:
    ids = _real_entries(entry.get("youtube_channel_ids"))
    if not ids:
        raise SourceSkipped("no youtube_channel_ids set for this politician in politician_handles.json")
    out, errs = [], []
    for cid in ids:
        try:
            out.extend(get_youtube_channel_uploads(cid, start_date, end_date))
        except Exception as e:
            errs.append(f"{cid}: {e}")
    if errs and not out:
        raise ValueError("; ".join(errs))
    if errs:
        print(f"Warning: some YouTube channels failed ({'; '.join(errs)})")
    return out


def collect_telegram(entry, start_date, end_date) -> list:
    if BeautifulSoup is None:
        raise SourceSkipped("beautifulsoup4 not installed (pip install beautifulsoup4)")
    chans = _real_entries(entry.get("telegram_channels"))
    if not chans:
        raise SourceSkipped("no telegram_channels set for this politician in politician_handles.json")
    out, errs = [], []
    for ch in chans:
        try:
            out.extend(get_telegram_channel_posts(ch, start_date, end_date))
        except Exception as e:
            errs.append(f"{ch}: {e}")
    if errs and not out:
        raise ValueError("; ".join(errs))
    if errs:
        print(f"Warning: some Telegram channels failed ({'; '.join(errs)})")
    seen, unique = set(), []
    for p in out:
        if p["url"] in seen:
            continue
        seen.add(p["url"])
        unique.append(p)
    unique.sort(key=lambda p: p.get("date_parsed") or datetime.min, reverse=True)
    return unique


def collect_indexed_posts(names, platform_keys, api_key, start_date, end_date) -> "tuple[dict, str]":
    by_platform, errs, dropped_total = {}, [], 0
    for i, key in enumerate(platform_keys):
        label = PLATFORMS[key][0]
        try:
            raw = search_platform(names, key, api_key, start_date, end_date)
            # Search engines match loosely -- drop results whose title/snippet
            # doesn't actually mention the politician by any known name/alias.
            kept, dropped = filter_relevant(raw, names, lambda it: f"{it.get('title', '')} {it.get('snippet', '')}")
            by_platform[label] = kept
            dropped_total += dropped
        except Exception as e:
            by_platform[label] = []
            errs.append(f"{label}: {e}")
        if i < len(platform_keys) - 1:
            time.sleep(1.2)  # stay under ~1 request/second
    total = sum(len(v) for v in by_platform.values())
    msg = f"{total} found" + (f", {dropped_total} unrelated result(s) filtered out" if dropped_total else "")
    if errs:
        msg += f" (failed: {'; '.join(errs)})"
    return by_platform, msg


def collect(status, label, fn, *args, enabled=True, skip_reason="", announce=True):
    """Run one source safely, recording what happened in `status`.

    announce=False lets a caller print its own more specific message
    beforehand (e.g. noting Brave-vs-API precedence) instead of this
    function's generic "- label..." line.
    """
    if not enabled:
        status[label] = f"skipped ({skip_reason})"
        return []
    if announce:
        print(f"  - {label}...")
    try:
        items = fn(*args)
        status[label] = f"{len(items)} found"
        return items
    except SourceSkipped as e:
        status[label] = f"skipped ({e})"
        return []
    except Exception as e:
        status[label] = f"failed: {e}"
        print(f"    Warning: {label} failed ({e})")
        return []


def merge_youtube(rss_videos, api_videos) -> list:
    seen, out = set(), []
    for v in list(rss_videos) + list(api_videos):
        if v["url"] in seen:
            continue
        seen.add(v["url"])
        out.append(v)
    out.sort(key=lambda v: v.get("date_parsed") or datetime.min, reverse=True)
    return out





# --------------------------------------------------------------------------
# Top stories: grouping coverage into distinct stories
# --------------------------------------------------------------------------
# Fifteen outlets running the same story isn't fifteen developments -- it's one
# development that mattered a lot. Grouping headlines by story, and ranking the
# stories by how many SEPARATE outlets carried them, tells both the reader and
# the AI summary what was actually significant this period, instead of handing
# over a duplicate-heavy pile where one story can drown out everything else.

_STORY_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those", "have", "has", "had", "will",
    "would", "could", "should", "been", "being", "were", "their", "they", "them", "about", "after", "over",
    "into", "amid", "against", "says", "said", "say", "news", "live", "updates", "update", "today", "video",
    "watch", "report", "reports", "latest", "breaking", "also", "more", "than", "what", "when", "where", "which",
    "while", "just", "first", "last", "year", "years", "week", "time", "times", "here", "there", "your",
    "india", "indian", "state", "minister", "chief", "leader", "party", "govt", "government", "official",
    "officials", "people", "telugu", "english", "hindi", "photos", "full", "details",
}


def _story_words(text: str, ignore: set) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) >= 4 and w not in _STORY_STOPWORDS and w not in ignore}


def _clean_headline(headline: str, source: str) -> str:
    """Google News titles often end with ' - Outlet Name'; drop that suffix."""
    h = (headline or "").strip()
    if source and h.lower().endswith((" - " + source).lower()):
        h = h[: -(len(source) + 3)].rstrip()
    return h


def _outlet_key(source: str) -> str:
    s = (source or "").strip().lower()
    return s[4:] if s.startswith("www.") else s


def build_top_stories(data: dict, ignore_words=(), max_stories: int = 10, window_days: int = 2) -> list:
    """Group news headlines (plus news coverage of social posts) into distinct
    stories and rank them by how many separate outlets reported each.

    ignore_words: the subject's own names -- every headline mentions them, so
    counting them as "shared words" would lump unrelated stories together.

    Each story: headline (the most representative one), outlets (distinct
    names), count (articles), first_seen/last_seen (datetimes or None), url,
    and items (the articles grouped into it).
    """
    ignore = set()
    for n in ignore_words or ():
        ignore |= {w for w in re.findall(r"[a-z0-9]+", str(n).lower())}
    items = []
    for key in ("headlines", "social_news"):
        for it in data.get(key, []):
            src = it.get("source", "")
            text = _clean_headline(it.get("headline", ""), src)
            words = _story_words(text, ignore)
            if text:
                items.append({"headline": text, "source": src, "url": it.get("url", ""),
                              "dt": it.get("date_parsed"), "date": it.get("date", ""), "words": words})
    items.sort(key=lambda x: (x["dt"] is None, x["dt"] or datetime.min))

    clusters = []
    for it in items:
        best, best_score = None, 0.0
        for c in clusters:
            if it["dt"] and c["last"] and abs((it["dt"] - c["last"]).days) > window_days:
                continue
            shared = it["words"] & c["words"]
            if not it["words"]:
                continue
            ratio = len(shared) / len(it["words"])
            if (len(shared) >= 3 or (len(shared) >= 2 and ratio >= 0.67)) and ratio >= 0.4 and ratio > best_score:
                best, best_score = c, ratio
        if best is None:
            clusters.append({"items": [it], "words": set(it["words"]), "last": it["dt"]})
        else:
            best["items"].append(it)
            best["words"] |= it["words"]
            if it["dt"] and (best["last"] is None or it["dt"] > best["last"]):
                best["last"] = it["dt"]

    stories = []
    for c in clusters:
        outlets, seen = [], set()
        for it in c["items"]:
            k = _outlet_key(it["source"])
            if k and k not in seen:
                seen.add(k)
                outlets.append(it["source"])
        rep = max(c["items"], key=lambda it: (len(it["words"] & c["words"]), -len(it["headline"])))
        dts = [it["dt"] for it in c["items"] if it["dt"]]
        stories.append({"headline": rep["headline"], "url": rep["url"], "outlets": outlets,
                        "count": len(c["items"]), "first_seen": min(dts) if dts else None,
                        "last_seen": max(dts) if dts else None, "items": c["items"]})
    stories.sort(key=lambda s: (-len(s["outlets"]), -s["count"],
                                -(s["last_seen"].timestamp() if s["last_seen"] else 0)))
    return stories[:max_stories]


def _ist(dt):
    """Timestamps are stored as naive UTC; show dates to the reader in India time,
    otherwise an article from 3 a.m. IST on the 9th is labelled the 8th."""
    return dt + timedelta(hours=5, minutes=30)


def build_glance(data: dict, stories: list) -> dict:
    """Headline numbers for the top of the report."""
    news = list(data.get("headlines", [])) + list(data.get("social_news", []))
    outlets = {_outlet_key(it.get("source", "")) for it in news} - {""}
    per_day = {}
    for it in news:
        if it.get("date_parsed"):
            d = _ist(it["date_parsed"]).date()
            per_day[d] = per_day.get(d, 0) + 1
    busiest = max(per_day.items(), key=lambda kv: kv[1]) if per_day else None
    return {"headlines": len(news), "outlets": len(outlets), "stories": len(stories),
            "multi_outlet": sum(1 for s in stories if len(s["outlets"]) >= 2),
            "busiest_day": f"{busiest[0]:%b %d} ({busiest[1]} headlines)" if busiest and len(per_day) > 1 else ""}


def glance_text(g: dict) -> str:
    if not g or not g.get("headlines"):
        return "No news coverage found in this period."
    text = (f"{g['headlines']} news item(s) from {g['outlets']} outlet(s), grouped into the top {g['stories']} "
            f"distinct stories ({g['multi_outlet']} carried by more than one outlet).")
    if g.get("busiest_day"):
        text += f" Busiest day: {g['busiest_day']}."
    return text


def story_date_range(s: dict) -> str:
    a, b = s.get("first_seen"), s.get("last_seen")
    if not a:
        return ""
    a, b = _ist(a), (_ist(b) if b else None)
    return f"{a:%b %d}" if (not b or a.date() == b.date()) else f"{a:%b %d} \u2013 {b:%b %d}"


def story_meta(s: dict, max_outlets: int = 4) -> str:
    n = len(s["outlets"])
    names = ", ".join(s["outlets"][:max_outlets]) + (f" +{n - max_outlets} more" if n > max_outlets else "")
    who = f"{n} outlets: {names}" if n > 1 else (f"1 outlet: {names}" if names else "source unknown")
    return " | ".join(filter(None, [who, story_date_range(s)]))


# --------------------------------------------------------------------------
# Sarvam AI narrative (+ template fallback)
# --------------------------------------------------------------------------

# Briefing structures, in display order. Each category is
# (json_key, display_label, description used in the AI prompt).
# The politician structure keeps every category from the original 7-part
# format and adds two that matter most for daily/weekly check-ins: a dated
# timeline at the top, and a read on media & public sentiment.
TOPLINE_KEY, TOPLINE_LABEL = "topline", "Headline / Top Line"
TIMELINE_KEY, TONE_KEY = "timeline", "coverage_tone"

# Matches the start of a new "<Source> <reported/said/...>" clause, so a
# crammed line can be split right before each one begins.
_REPORT_VERBS = r"(?:reported|said|announced|released|wrote|claimed|alleged|stated|noted|added|confirmed)"
_SOURCE_NAME = r"(?:[A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*){0,4}|[a-z0-9][\w.-]*\.(?:com|in|org|net))"
_NEW_CLAUSE = re.compile(rf",?\s+and\s+(?={_SOURCE_NAME}\s+{_REPORT_VERBS}\b)|,\s+(?={_SOURCE_NAME}\s+{_REPORT_VERBS}\b)")


def _split_crammed_clauses(rest: str) -> list:
    """Split a run-on clause joined by commas/"and" into separate sentence
    fragments, right before each new "<Source> <reported/said/...>" begins.
    """
    return [c.strip().rstrip(",") for c in _NEW_CLAUSE.split(rest) if c.strip()]


def to_paragraph(text: str) -> str:
    """Normalize a category's text into ONE flowing paragraph, regardless of
    what the model did, as a code-level guarantee rather than relying only
    on the prompt. Two things are fixed, independently of each other:

    1. Several distinct facts crammed into one run-on sentence (joined by
       commas/"and", e.g. "X reported A, Y reported B, and Z reported C.")
       become separate sentences, each ending in a period.
    2. Any line breaks the model still used (despite being told not to) are
       collapsed into the same paragraph, space-separated -- never rendered
       as a bulleted list or separate blocks.

    A date marker like "Oct 05 — " at the start of a line is kept once, not
    repeated on every split sentence, so the result reads as prose.
    """
    out_parts = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)\s+—\s+(.*)$", line)
        if not m:
            out_parts.append(line)
            continue
        date_part, rest = m.groups()
        clauses = _split_crammed_clauses(rest)
        sentences = []
        for c in clauses:
            if c and not c.endswith((".", "!", "?")):
                c += "."
            sentences.append(c)
        out_parts.append(f"{date_part} — " + " ".join(sentences))
    return " ".join(out_parts)


# Crisp-report polishing, applied in code after the model replies (so it holds
# even when the model drifts from the style instructions).
EMPTY_SECTION_TEXT = "Nothing reported in this period."
EMPTY_TOPLINE_TEXT = "No single development stood out in the available coverage."
DEFAULT_SENTENCE_CAP = 6           # safety net; the prompt asks for at most 4
SECTION_SENTENCE_CAP = {TOPLINE_KEY: 2, TIMELINE_KEY: 10}

_ABBREV_END = re.compile(
    r"(?:\b[A-Z]|\b(?:Dr|Mr|Mrs|Ms|Shri|Smt|Sri|Rs|St|No|vs|etc|Jr|Sr|Prof|Gen|Lt|Col|Capt|Govt|Dept|Hon|Adv|"
    r"approx|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)|\be\.g|\bi\.e)\.$")
_FILLER_OPENERS = re.compile(
    r"^(?:Notably|Additionally|Furthermore|Moreover|In addition|Also|Overall|In summary|In conclusion|Importantly|"
    r"Interestingly|Significantly|It is (?:also )?(?:worth noting|important to note|notable) that|"
    r"It should be noted that|It was reported that|Reports (?:said|suggest|indicate) that)\s*,?\s+", re.I)


def split_sentences(text: str) -> list:
    """Split prose into sentences without breaking initials ("K. Chandrashekar
    Rao") or common abbreviations ("Dr.", "Rs.", "e.g.")."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\u201c\"'(])", " ".join((text or "").split()))
    out = []
    for p in parts:
        if out and _ABBREV_END.search(out[-1]):
            out[-1] += " " + p
        else:
            out.append(p)
    return [x.strip() for x in out if x.strip()]


def polish_sentence(sentence: str) -> str:
    x = re.sub(r"\s+", " ", sentence).strip()
    x = re.sub(r"\s+([,.;:!?)\]])", r"\1", x)
    x = re.sub(r"([(\[])\s+", r"\1", x)
    x = re.sub(r"([,;:])(?=[A-Za-z])", r"\1 ", x)
    x = re.sub(r"\.{2}(?!\.)", ".", x)
    m = _FILLER_OPENERS.match(x)
    if m and len(x) > m.end() + 1:
        x = x[m.end():]
        x = x[0].upper() + x[1:]
    if x and not re.search(r"[.!?][\"\u201d\u2019')\]]*$", x):
        x += "."
    return x


def polish_narrative(report: dict, subject_type: str = "politician") -> dict:
    """Make every section crisp and consistent: tidy spacing and punctuation,
    drop filler openers, remove repeated sentences (within a section, and
    across sections except the timeline), and trim runaway sections."""
    keys = [TOPLINE_KEY] + [k for k, _, _ in get_profile(subject_type)["categories"]]
    seen_across = set()
    for key in keys:
        text = (report.get(key) or "").strip()
        if not text:
            continue
        kept, seen_here = [], set()
        for sent in split_sentences(text):
            sent = polish_sentence(sent)
            norm = re.sub(r"[^a-z0-9]+", "", sent.lower())
            if not norm or norm in seen_here:
                continue
            if key not in (TOPLINE_KEY, TIMELINE_KEY) and len(norm) > 40 and norm in seen_across:
                continue
            seen_here.add(norm)
            if key not in (TOPLINE_KEY, TIMELINE_KEY):
                seen_across.add(norm)
            kept.append(sent)
        report[key] = " ".join(kept[:SECTION_SENTENCE_CAP.get(key, DEFAULT_SENTENCE_CAP)])
    return report


_TIMELINE_DESC = ("the significant developments in this window as ONE flowing paragraph (not a list), "
                  "oldest first, with dates woven naturally into the prose rather than used as headings")
_UPCOMING_DESC = "scheduled votes, events, deadlines, and unresolved issues still to come"

SUMMARY_PROFILES = {
    "politician": {
        "subject_label": "Politician",
        "report_title": "Politician Report",
        "who": "the politician",
        "categories": [
            (TIMELINE_KEY, "1. Key Developments Timeline", _TIMELINE_DESC),
            ("key_actions", "2. Key Actions and Decisions", "bills, votes, policies, appointments, orders, official meetings"),
            ("public_statements", "3. Public Statements and Messaging",
             "speeches, interviews, press conferences, social media posts, and the main themes of what they said"),
            ("controversies", "4. Controversies and Criticism",
             "disputes, opposition attacks, fact-checks, and the politician's response"),
            ("constituency_work", "5. Constituency / Ground Work", "rallies, local visits, town halls, meetings with voters"),
            ("political_maneuvering", "6. Political Maneuvering",
             "alliances, party developments, negotiations, endorsements, rivalries"),
            (TONE_KEY, "7. Media & Public Sentiment",
             "how news coverage and social discussion framed them in this window (e.g. mostly critical, "
             "mostly supportive, mixed), naming which outlets or platforms drove each view"),
            ("upcoming", "8. Upcoming / What to Watch", _UPCOMING_DESC),
        ],
        "keywords": {
            "controversies": ["slam", "criticiz", "criticis", "controvers", "backlash", "protest", " row", "under fire",
                              "accus", "allegat", "fact-check", "denies", "denied", "clarif", "attack",
                              "condemn", "defend", "oppos"],
            "constituency_work": ["rally", "town hall", "visits", "inaugurat", "foundation stone",
                                  "meets voters", "yatra", "road show", "roadshow", "public meeting", "constituency",
                                  "grassroot"],
            "political_maneuvering": ["alliance", "coalition", "merger", "resign", "joins party", "quits",
                                      "defect", "reshuffle", "endorse", "rift", "rivalry", "infighting",
                                      "in-fighting", "switch", "poach"],
            "upcoming": ["will ", "set to", "scheduled", "to attend", "upcoming", "due to", "expected to",
                         "plans to", "to hold", "to launch", "ahead of"],
        },
        "match_order": ["controversies", "political_maneuvering", "constituency_work", "upcoming"],
        "default_news": "key_actions", "default_social": "public_statements", "default_ads": "political_maneuvering",
    },
    "party": {
        "subject_label": "Political party",
        "report_title": "Political Party Report",
        "who": "the party",
        "categories": [
            (TIMELINE_KEY, "1. Key Developments Timeline", _TIMELINE_DESC),
            ("leadership", "2. Leadership & Organisation",
             "statements and moves by top leaders, appointments, resignations, defections and joinings, "
             "internal party matters"),
            ("policy_messaging", "3. Policy, Governance & Messaging",
             "policy positions, campaigns and slogans, and actions by governments the party leads"),
            ("elections", "4. Elections & Campaigns",
             "elections and by-elections, candidate lists, rallies and yatras, seat-sharing talks, results"),
            ("alliances", "5. Alliances & Rivals", "coalition partners, alliance tensions, and clashes with rival parties"),
            ("controversies", "6. Controversies & Criticism",
             "disputes, allegations, fact-checks, and the party's response"),
            (TONE_KEY, "7. Media & Public Sentiment",
             "how news coverage and social discussion framed the party in this window (e.g. mostly critical, "
             "mostly supportive, mixed), naming which outlets or platforms drove each view"),
            ("upcoming", "8. Upcoming / What to Watch", _UPCOMING_DESC),
        ],
        "keywords": {
            "controversies": ["slam", "criticiz", "criticis", "controvers", "backlash", "protest", " row", "under fire",
                              "accus", "allegat", "fact-check", "denies", "denied", "clarif", "condemn", "scam"],
            "alliances": ["alliance", "coalition", " ally", "allies", "tie-up", "seat-sharing", "seat sharing",
                          " nda", "india bloc", "upa", "rival", "joins hands", "versus", " vs "],
            "elections": ["election", " poll", "bypoll", "by-poll", "by-election", "campaign", "rally", "candidate",
                          "seat", "vote", "voting", "manifesto", "yatra", "road show", "roadshow", "counting"],
            "leadership": ["president", "chief", "leader", "appoint", "resign", "quits", "joins", "defect",
                           "reshuffle", "working committee", "general secretary", "organisation", "organization",
                           "inducted", "expelled", "suspended"],
            "upcoming": ["will ", "set to", "scheduled", "to attend", "upcoming", "due to", "expected to",
                         "plans to", "to hold", "to launch", "ahead of"],
        },
        "match_order": ["controversies", "alliances", "elections", "leadership", "upcoming"],
        "default_news": "policy_messaging", "default_social": "policy_messaging", "default_ads": "elections",
    },
}

# Backward-compatible name: the politician structure.
SUMMARY_CATEGORIES = SUMMARY_PROFILES["politician"]["categories"]


def get_profile(subject_type: str) -> dict:
    return SUMMARY_PROFILES.get(subject_type, SUMMARY_PROFILES["politician"])


def build_system_prompt(subject_type: str = "politician") -> str:
    profile = get_profile(subject_type)
    subject = "an Indian political party" if subject_type == "party" else "an Indian politician"
    who = profile["who"]
    cats = profile["categories"]
    parts = "\n".join(f"{i}. {key} -- {desc}." for i, (key, _, desc) in enumerate(cats, 1))
    schema = ",\n".join(
        [f'  "{TOPLINE_KEY}": "<one crisp sentence, at most 30 words, on the single most important development, or \\"\\" if the data gives no basis>"']
        + [f'  "{key}": "<{desc}; leave as \\"\\" if nothing in the data fits>"' for key, _, desc in cats]
        + ['  "note": "<leave as \\"\\" unless the overall data was too thin to summarize, '
           'in which case a short honest note>"']
    )
    return (
        f"You are a neutral, factual research assistant writing a daily/weekly briefing about {subject}. "
        "You will be given real data already collected for a specific time window: news headlines, "
        "X/Twitter posts, YouTube videos, Telegram channel posts, Reddit discussion, political ad activity, "
        "news stories about social media posts, and search-indexed public posts. Organize it into the "
        "EXACT structure below, based ONLY on the data provided.\n\n"
        "Rules:\n"
        "- Do not invent facts, dates, numbers, quotes, or events not present in the data.\n"
        "- Be strictly neutral: report what the data shows without praising, criticizing, or taking a "
        "political stance.\n"
        "- Sort each item into the ONE category it fits best. Repeat a fact in two categories only when it "
        "genuinely belongs in both.\n"
        "- Within each category, order items chronologically and mention dates so the reader can see how "
        "things unfolded across the window, not just the most recent item.\n"
        "- Be specific: name actual events, statements, places, and figures from the data rather than vague "
        "filler like \"there was some activity\".\n"
        "- Search-indexed items are only titles/snippets; describe them cautiously and do not present them "
        "as verified.\n"
        "- After each specific fact, add its source and date in brackets, e.g. \"(The Hindu, Oct 04)\", using only "
        "outlets and dates that appear in the data.\n"
        "- TOP STORIES groups the same story across outlets and ranks it by how many separate outlets carried it. "
        "Use it to judge importance: build the topline and timeline around the stories carried by the most "
        "outlets, and don't let one widely repeated story crowd out other distinct developments. Treat a "
        "single-outlet story as reported, not established -- especially claims and allegations.\n"
        "- If a category has NOTHING in the data, leave it as a true empty string \"\". Never write placeholder "
        "text such as \"No activity\", \"none\", or \"empty string\" as a value.\n"
        "- EVERY category is a SINGLE FLOWING PARAGRAPH of plain prose. Never use bullet points, dashes, "
        "numbered lists, or line breaks inside a category's text -- write connected sentences instead. "
        "Within that paragraph, give each distinct fact its OWN complete sentence ending in a period; never "
        "chain several distinct facts together with commas or \"and\" into one run-on sentence, even when "
        "they share a date -- that is just as wrong as using bullet points.\n"
        f"- \"{TIMELINE_KEY}\": a single paragraph covering the window chronologically, oldest first. "
        "Mention a date (e.g. \"Oct 05\") at the start of a sentence whenever the date changes or it isn't "
        "otherwise clear, but do not repeat the same date on every sentence, and do not group sentences under "
        "date headings -- it should read as one continuous paragraph, not a structured list. Keep each "
        "sentence short and factual: name what happened, not who reported it -- skip phrases like \"X reported "
        "that\" or \"Y reported on\" and just state the fact, optionally crediting the source briefly "
        "(e.g. \"..., per The Hindu.\"). WRONG (do not do this): \"Oct 05 — Scroll.in reported on the BJP "
        "looking to sweep Nandigram, The New Indian Express reported on Koyel Mallick joining the BJP, and "
        "The Hindu reported on a BJP agent seeking name deletions.\" RIGHT (one paragraph, each fact its own "
        "sentence, dates mentioned naturally): \"Oct 01 — A BJP agent sought the deletion of 7,561 names in "
        "Ballari, per The New Indian Express. Oct 04 — The BJP released a BJYM press release. The party named "
        "three candidates for the Maharashtra Legislative Council elections, per News On AIR. Oct 05 — The "
        "BJP is looking to sweep Nandigram, per Scroll.in. Koyel Mallick joined the BJP, per The New Indian "
        "Express.\" At most about 12 sentences. Only items with a known date belong here.\n"
        f"- \"{TONE_KEY}\": describe how coverage framed {who}, attributing each view to the outlets or "
        "platforms it came from. Do not add your own opinion. Leave \"\" if the data is too thin to judge.\n"
        "- Length scales with the data, within these limits: the top line is ONE sentence of at most 30 words; "
        "the timeline has at most 8 short sentences; every other section has at most 4 sentences. Never pad.\n"
        "STYLE (this is a professional briefing, so keep it crisp):\n"
        "- Lead each section with its most important point.\n"
        "- One fact per sentence, about 25 words at most; active voice; past tense for events.\n"
        "- Use digits for numbers. Give a person's full name on first mention and a short form after.\n"
        "- No filler or hedging openers such as \"Notably\", \"Additionally\", \"It is worth noting that\" or "
        "\"In conclusion\", and no generic sentences without a specific fact.\n"
        "- Don't repeat a fact in more than one section (the timeline may still list it).\n"
        "- When several outlets report the same thing, combine them in one bracket, e.g. \"(The Hindu, NDTV; Oct 04)\".\n\n"
        "The parts, in order:\n"
        f"0. {TOPLINE_KEY} -- the SINGLE most important development for {who} in this window, in one crisp sentence of at most 30 words. "
        "Pick what matters most, not simply the most recent item.\n"
        f"{parts}\n\n"
        "Respond with ONLY a single valid JSON object, no markdown fences, no commentary before or after it:\n\n"
        "{\n" + schema + "\n}\n"
    )


# Backward-compatible name: the politician prompt.
SYSTEM_PROMPT = build_system_prompt("politician")


def build_day_index(data: dict) -> list:
    """Count how many items (across all sources) fall on each calendar day.

    Given to the model as a reference scaffold so it writes a genuinely
    chronological account of the whole window instead of defaulting to
    whatever the most recent item was.
    """
    from collections import Counter
    counts = Counter()
    for key in ("headlines", "x_posts", "youtube", "telegram", "reddit", "social_news"):
        for it in data.get(key, []):
            dt = it.get("date_parsed")
            if dt:
                counts[dt.strftime("%Y-%m-%d (%A)")] += 1
    for items in data.get("indexed", {}).values():
        for it in items:
            dt = it.get("date_parsed")
            if dt:
                counts[dt.strftime("%Y-%m-%d (%A)")] += 1
    return sorted(counts.items())


def build_user_prompt(name, window_label, wiki, data, subject_type: str = "politician", extras=None) -> str:
    L = [f"{get_profile(subject_type)['subject_label']}: {name}", f"Time window: {window_label}", ""]
    if wiki.get("found"):
        L.append(f"Wikipedia description: {wiki.get('description', '')}")
        if wiki.get("extract"):
            L.append(f"Wikipedia summary: {wiki['extract']}")
        L.append("")

    day_index = build_day_index(data)
    if len(day_index) > 1:
        L.append("ITEMS PER DAY ACROSS ALL SOURCES (write chronologically covering these days, not just the most recent):")
        L.extend(f"- {day}: {count} item(s)" for day, count in day_index)
        L.append("")

    def block(title, rows):
        L.append(f"{title} ({len(rows)}):")
        L.extend(rows if rows else ["(none)"])
        L.append("")

    stories = (extras or {}).get("stories") or []
    if stories:
        block("TOP STORIES (the same story grouped across outlets; ranked by how many separate outlets carried it)", [
            f'- [{len(st["outlets"])} outlet{"s" if len(st["outlets"]) != 1 else ""}: '
            f'{", ".join(st["outlets"][:5]) or "unknown"}] "{st["headline"]}" ({story_date_range(st) or "date n/a"})'
            for st in stories])
    block("NEWS HEADLINES", [f'- "{h["headline"]}" ({h.get("source", "")}, {h.get("date", "")})' for h in data["headlines"][:60]])
    block("X / TWITTER POSTS", [f'- @{p.get("handle", "")}: "{p.get("text", "")[:500]}" ({p.get("likes", 0)} likes, {p.get("date", "")})' for p in data["x_posts"][:30]])
    block("YOUTUBE VIDEOS", [f'- "{v.get("title", "")}" by {v.get("channel", "")} ({v.get("date", "")})' for v in data["youtube"][:25]])
    block("TELEGRAM CHANNEL POSTS", [f'- t.me/{p.get("channel", "")} ({p.get("date", "")}): "{p.get("text", "")[:500]}"' for p in data["telegram"][:25]])
    block("REDDIT DISCUSSION", [f'- "{r["title"]}" in {r.get("subreddit", "")} ({r.get("num_comments", 0)} comments)' for r in data["reddit"][:15]])
    block("POLITICAL AD ACTIVITY (Facebook/Instagram Ad Library)", [f'- Page "{a.get("page_name", "")}" ran an ad: "{a.get("text", "")[:400]}" on {a.get("platforms", "")}' for a in data["meta_ads"][:10]])
    block("NEWS STORIES ABOUT THEIR SOCIAL MEDIA POSTS", [f'- "{n["headline"]}" ({n.get("source", "")}, {n.get("date", "")})' for n in data["social_news"][:20]])
    indexed_rows = [
        f'- [{label}] "{i["title"]}": {i["snippet"][:400]} ({i["date"] or "date unknown"})'
        for label, items in data["indexed"].items() for i in items[:10]
    ]
    block("SEARCH-INDEXED PUBLIC POSTS/PAGES", indexed_rows[:40])
    L.append("Write the JSON report now, based only on the above.")
    return "\n".join(L)


def extract_json_object(text: str) -> "dict | None":
    """Find and parse the LARGEST balanced {...} object in `text`.

    More robust than a greedy regex: a regex matching from the first '{' to
    the LAST '}' breaks if the model adds any stray brace in surrounding
    prose (e.g. an example in parentheses), since it would grab everything
    in between as one (invalid) blob. This instead tracks brace depth to
    find each actual matching close, tries every '{' in the text (not just
    the first), and returns the LARGEST valid object found -- so a small
    stray example (e.g. 'fields look like {"example": "value"}') doesn't
    get returned instead of the real, larger answer that follows it.
    Returns None if nothing in the text parses as a JSON object.
    """
    best = None
    for start, c in enumerate(text):
        if c != "{":
            continue
        depth = 0
        in_string, escape = False, False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
            elif ch == "\\" and in_string:
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            parsed = json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break  # this '{' doesn't start valid JSON; try the next one
                        if isinstance(parsed, dict) and (best is None or (i - start) > best[0]):
                            best = (i - start, parsed)
                        break
    return best[1] if best else None


def _call_sarvam(client, model, messages, max_tokens: int = 6000):
    try:
        return client.chat.completions(
            model=model, messages=messages, temperature=0.2, max_tokens=max_tokens,
            reasoning_effort=None,  # direct JSON answer; thinking tokens were eating the budget
        )
    except TypeError:
        return client.chat.completions(model=model, messages=messages, temperature=0.2, max_tokens=max_tokens)


def generate_narrative(client, model, name, window_label, wiki, data, subject_type: str = "politician",
                       extras=None) -> dict:
    """Ask Sarvam for the briefing and parse it.

    If the model's response can't be turned into usable structured data even
    after a corrective retry, this raises rather than returning a broken,
    mostly-empty report -- the caller (gather_report) catches that and falls
    back to the properly-formatted template summary instead, which is always
    better than a wall of unstructured text dumped into one field.
    """
    system_prompt = build_system_prompt(subject_type)
    user_prompt = build_user_prompt(name, window_label, wiki, data, subject_type, extras)
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    last_error, last_snippet = "no response", ""
    for attempt in range(2):
        response = _call_sarvam(client, model, messages)
        message = response.choices[0].message
        content = getattr(message, "content", None) or getattr(message, "reasoning_content", None)

        if not content:
            finish = getattr(response.choices[0], "finish_reason", "unknown")
            last_error = f"empty response (finish_reason: {finish})"
        else:
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
            parsed = extract_json_object(content)
            if parsed is not None:
                result = _sanitize_fields(parsed, subject_type)
                for key, _, _ in get_profile(subject_type)["categories"]:
                    if result.get(key):
                        result[key] = to_paragraph(result[key])
                return polish_narrative(result, subject_type)
            last_error = "response did not contain a valid JSON object"
            last_snippet = content[:300]

        if attempt == 0:
            # One corrective retry: tell it exactly what went wrong and ask again,
            # rather than giving up after a single imperfect response.
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": (content or "")[:2000]},
                {"role": "user", "content": (
                    "That response was not usable: " + last_error + ". Reply again with ONLY the JSON "
                    "object described in the system prompt -- no markdown fences, no explanation, no text "
                    "before or after it. Start your reply with '{' and end it with '}'."
                )},
            ]

    detail = f" Last response started with: {last_snippet!r}" if last_snippet else ""
    raise ValueError(f"Sarvam did not return usable structured output after a retry ({last_error}).{detail}")


_PLACEHOLDER_ECHOES = {"empty string", "empty", "none", "n/a", "na", "null", "blank", "no activity", "", "-"}


def _as_text(value) -> str:
    """Normalize a model-returned field to text. Lists (e.g. a timeline returned
    as a JSON array) become one item per line."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(v).strip() for v in value if str(v).strip())
    return str(value)


def _sanitize_fields(report: dict, subject_type: str = "politician") -> dict:
    """Guard against a model literally echoing a field's placeholder text
    (e.g. outputting the words "empty string" or "none" instead of actually
    leaving it blank). Applies to topline, every category, and note.
    """
    keys = [TOPLINE_KEY, "note"] + [k for k, _, _ in get_profile(subject_type)["categories"]]
    for key in keys:
        value = _as_text(report.get(key)).strip()
        report[key] = "" if value.lower() in _PLACEHOLDER_ECHOES else value
    return report


def attach_profile(narrative: dict, subject_type: str) -> dict:
    """Record which structure a narrative uses, so every renderer (terminal,
    Markdown, PDF, UI) shows the right categories and title."""
    profile = get_profile(subject_type)
    narrative["_subject_type"] = subject_type if subject_type in SUMMARY_PROFILES else "politician"
    narrative["_categories"] = profile["categories"]
    narrative["_report_title"] = profile["report_title"]
    return narrative


def category_lines(text: str) -> list:
    """Split a category's paragraph into individual sentences.

    Categories are flowing paragraphs now, not bulleted lists -- this is no
    longer used for display (every renderer just prints the paragraph
    directly), but is kept as a utility for callers that want the text
    broken into its component sentences (e.g. a plain-text export)."""
    if not text:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _categorize_by_keywords(text: str, default: str, profile: dict = None) -> str:
    """Best-effort, keyword-based bucketing used only without Sarvam.

    This is a heuristic, not real understanding -- it can miscategorize or
    miss things a human (or an LLM) would catch. `default` is the bucket
    used when no keyword matches, chosen by the caller based on source type.
    """
    profile = profile or SUMMARY_PROFILES["politician"]
    t = f" {text.lower()} "
    for cat in profile["match_order"]:
        if any(kw in t for kw in profile["keywords"][cat]):
            return cat
    return default


def build_template_summary(name, wiki, data, window_label, subject_type: str = "politician", extras=None) -> dict:
    """A mechanical (non-AI) briefing used only when Sarvam is unavailable.
    Buckets items into the same structure as Sarvam's output using keyword
    matching rather than real understanding -- flagged honestly in the note.
    """
    profile = get_profile(subject_type)
    buckets = {key: [] for key, _, _ in profile["categories"] if key not in (TIMELINE_KEY, TONE_KEY)}

    def add(text, default, line):
        cat = _categorize_by_keywords(text, default, profile)
        buckets.setdefault(cat, []).append(line)

    for h in data["headlines"]:
        add(h.get("headline", ""), profile["default_news"],
            f"\u201c{h['headline']}\u201d ({h.get('source', '')}, {h.get('date', '')})")
    for label, items, field, default in [
        ("X post", data["x_posts"], "text", profile["default_social"]),
        ("YouTube video", data["youtube"], "title", profile["default_social"]),
        ("Telegram post", data["telegram"], "text", profile["default_social"]),
        ("Reddit thread", data["reddit"], "title", profile["default_news"]),
        ("Political ad", data["meta_ads"], "text", profile["default_ads"]),
        ("Social-media news story", data["social_news"], "headline", profile["default_social"]),
    ]:
        for it in items:
            text = it.get(field, "")
            add(text, default, f"{label}: \u201c{text[:150]}\u201d ({it.get('date', '')})")
    for label, items in data["indexed"].items():
        for it in items:
            add(f"{it.get('title', '')} {it.get('snippet', '')}", profile["default_social"],
                f"[{label}] \u201c{it.get('title', '')}\u201d ({it.get('date') or 'date unknown'})")

    def as_paragraph(items: list) -> str:
        sentences = []
        for it in items[:8]:
            it = it.strip()
            if it and not it.endswith((".", "!", "?")):
                it += "."
            sentences.append(it)
        return " ".join(sentences)

    report = {TOPLINE_KEY: "", "note": ""}
    for key in buckets:
        report[key] = as_paragraph(buckets[key])

    # Timeline: the most recent dated items (up to 12), oldest first, as one paragraph.
    dated = []
    for h in data["headlines"]:
        if h.get("date_parsed"):
            dated.append((h["date_parsed"], f"{h['headline']} ({h.get('source', '')})"))
    for key, field in [("x_posts", "text"), ("youtube", "title"), ("telegram", "text"), ("social_news", "headline")]:
        for it in data[key]:
            if it.get("date_parsed"):
                dated.append((it["date_parsed"], it.get(field, "")[:150]))
    dated = sorted(dated, key=lambda x: x[0])[-12:]
    report[TIMELINE_KEY] = as_paragraph([f"{dt.strftime('%b %d')} — {text}" for dt, text in dated])
    report[TONE_KEY] = ("Sentiment needs the AI summary (Sarvam), so it isn't assessed in this keyword-based "
                        "fallback." if (data["headlines"] or social_item_total(data)) else "")

    stories = (extras or {}).get("stories") or []
    all_dated = [h for h in data["headlines"] if h.get("date_parsed")]
    if stories and len(stories[0]["outlets"]) >= 2:
        top = stories[0]
        report[TOPLINE_KEY] = (f"Most widely covered story: \u201c{top['headline']}\u201d, carried by "
                               f"{len(top['outlets'])} outlets ({', '.join(top['outlets'][:3])}).")
    elif all_dated:
        top = max(all_dated, key=lambda h: h["date_parsed"])
        report[TOPLINE_KEY] = f"Most recent headline: \u201c{top['headline']}\u201d ({top.get('source', '')}, {top.get('date', '')})."
    elif data["x_posts"]:
        top = max(data["x_posts"], key=lambda p: p.get("likes", 0))
        report[TOPLINE_KEY] = f"Most-liked X post: \u201c{top.get('text', '')[:200]}\u201d ({top.get('likes', 0)} likes)."

    polish_narrative(report, subject_type)
    has_content = report[TOPLINE_KEY] or any(report.get(k) for k in buckets) or report[TIMELINE_KEY]
    report["note"] = ("This categorization is keyword-based (no AI available), so it may miscategorize "
                      "or miss items a person would catch -- treat it as a rough sort, not a judgment call."
                      if has_content else f"No data was found for {window_label} to categorize.")
    return report


def social_item_total(data: dict) -> int:
    return (len(data["x_posts"]) + len(data["youtube"]) + len(data["telegram"]) + len(data["reddit"])
            + len(data["meta_ads"]) + len(data["social_news"]) + sum(len(v) for v in data["indexed"].values()))


# --------------------------------------------------------------------------
# Report rendering (terminal + Markdown share the same section definitions)
# --------------------------------------------------------------------------

def _wrap(text, width=70, indent="") -> str:
    return "\n".join(textwrap.wrap(text, width=width, initial_indent=indent, subsequent_indent=indent))


def _item(title, url="", body="", meta="") -> dict:
    return {"title": title, "url": url, "body": body, "meta": meta}


def build_sections(data) -> list:
    """Each section: title, status_keys (for empty-state text), items."""
    def join(*parts):
        return " | ".join(p for p in parts if p)

    sections = [
        {"title": "X / TWITTER POSTS", "keys": ["X / Twitter (API)"], "items": [
            _item(f"@{p.get('handle', '')}" + (f" ({p['author']})" if p.get("author") else ""), p.get("url", ""),
                  p.get("text", ""), join(f"{p.get('likes', 0)} likes", f"{p.get('reposts', 0)} reposts", p.get("date", "")))
            for p in data["x_posts"]]},
        {"title": "YOUTUBE", "keys": ["YouTube search (API)", "YouTube channel feeds (RSS)"], "items": [
            _item(v.get("title", ""), v.get("url", ""), "",
                  join(v.get("channel", ""), v.get("date", ""), f"{v['views']:,} views" if v.get("views") else ""))
            for v in data["youtube"]]},
        {"title": "TELEGRAM CHANNEL POSTS", "keys": ["Telegram channels"], "items": [
            _item(f"t.me/{p.get('channel', '')}", p.get("url", ""), p.get("text", "")[:400],
                  join(p.get("date", ""), f"{p['views']} views" if p.get("views") else ""))
            for p in data["telegram"]]},
        {"title": "SOCIAL DISCUSSION — REDDIT", "keys": ["Reddit"], "items": [
            _item(r["title"], r.get("url", ""), "",
                  join(r.get("subreddit", ""), f"{r.get('num_comments', 0)} comments", r.get("date", "")))
            for r in data["reddit"]]},
        {"title": "POLITICAL ADS — FACEBOOK/INSTAGRAM (Meta Ad Library)", "keys": ["Facebook/Instagram ads (Meta)"], "items": [
            _item(f"Page: {a.get('page_name', '')}", a.get("url", ""), a.get("text", "")[:300],
                  join(a.get("platforms", ""), (a.get("start_date") or "")[:10]))
            for a in data["meta_ads"]]},
        {"title": "NEWS COVERAGE OF THEIR SOCIAL POSTS", "keys": ["News about their social posts"], "items": [
            _item(n["headline"], n.get("url", ""), "", join(n.get("source", ""), n.get("date", "")))
            for n in data["social_news"]]},
    ]
    for label, items in data["indexed"].items():
        sections.append({
            "title": f"SEARCH-INDEXED PUBLIC POSTS — {label.upper()}", "keys": ["Search-indexed posts (Brave)"],
            "items": [_item(i["title"], i.get("url", ""), i.get("snippet", "")[:300], i.get("date") or "date unknown") for i in items],
        })
    return sections


def _empty_note(section, status) -> str:
    notes = [f"{k}: {status[k]}" for k in section["keys"] if k in status]
    return "None found." + (f" ({'; '.join(notes)})" if notes else "")


def _range_text(start_date, end_date) -> str:
    return f"{start_date.strftime('%Y-%m-%d') if start_date else '...'} to {end_date.strftime('%Y-%m-%d') if end_date else 'today'}"


def print_report(name, wiki, data, narrative, start_date, end_date, status, used_template,
                 stories=None) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  {name.upper()} — {narrative.get('_report_title', 'Politician Report').upper()}")
    if start_date or end_date:
        print(f"  Period: {_range_text(start_date, end_date)}")
    print(f"{bar}\n")

    print("BASIC DETAILS\n" + "-" * 70)
    if not wiki.get("found"):
        if wiki.get("disambiguation"):
            print(f"Multiple people match '{name}' on Wikipedia. Try a more specific name.")
        else:
            print("No Wikipedia page found for this name.")
    else:
        if wiki.get("description"):
            print(f"Description : {wiki['description']}\n")
        if wiki.get("extract"):
            print(_wrap(wiki["extract"]))
        if wiki.get("page_url"):
            print(f"\nFull Wikipedia page: {wiki['page_url']}")

    print("\nSUMMARY")
    print("-" * 70)
    if narrative.get("note"):
        print(f"⚠️  {narrative['note']}\n")

    topline = narrative.get(TOPLINE_KEY, "").strip()
    print(f"{TOPLINE_LABEL}:")
    print(_wrap(topline) if topline else "  " + EMPTY_TOPLINE_TEXT)
    print()

    for key, label, _ in narrative.get("_categories") or SUMMARY_CATEGORIES:
        text = (narrative.get(key, "") or "").strip()
        print(f"{label}:")
        print(_wrap(text) if text else "  " + EMPTY_SECTION_TEXT)
        print()

    if stories:
        print("TOP STORIES (grouped across outlets, most widely carried first)\n" + "-" * 70)
        print(_wrap(glance_text(build_glance(data, stories))))
        for i, st in enumerate(stories, 1):
            print(f"\n{i}. " + _wrap(st["headline"], 66, "   ").strip())
            print(f"   {story_meta(st)}")
            if st.get("url"):
                print(f"   Link: {st['url']}")
        print()

    headlines = data["headlines"]
    if start_date or end_date:
        print(f"DAY-BY-DAY HEADLINES ({len(headlines)})\n" + "-" * 70)
        if not headlines:
            print("No headlines found for this window.")
        for day_label, day_items in group_headlines_by_day(headlines):
            print(f"\n{day_label}  ({len(day_items)})\n" + "~" * 50)
            for h in day_items:
                print(f"  • {h['headline']}")
                if h.get("source"):
                    print(f"    {h['source']}")
                if h.get("url"):
                    print(f"    Link: {h['url']}")
    else:
        print(f"HEADLINES ({len(headlines)})\n" + "-" * 70)
        if not headlines:
            print("No headlines found.")
        for i, h in enumerate(headlines, 1):
            print(f"\n{i}. {h['headline']}")
            meta = " | ".join(filter(None, [h.get("source", ""), h.get("date", "")]))
            if meta:
                print(f"   {meta}")
            if h.get("url"):
                print(f"   Link: {h['url']}")

    for sec in build_sections(data):
        print(f"\n{sec['title']} ({len(sec['items'])})\n" + "-" * 70)
        if not sec["items"]:
            print(_wrap(_empty_note(sec, status)))
        for i, it in enumerate(sec["items"], 1):
            print(f"\n{i}. {it['title']}")
            if it["body"]:
                print(_wrap(it["body"], 70, "   "))
            if it["meta"]:
                print(f"   {it['meta']}")
            if it["url"]:
                print(f"   Link: {it['url']}")

    print("\nSOURCES CHECKED\n" + "-" * 70)
    for label, st in status.items():
        first = st.split()[0] if st.split() else ""
        good = st in ("written", "found") or (first.isdigit() and first != "0")
        print(f"  {'✓' if good else '–'} {label}: {st}")
    print(f"\n{bar}\n")


def save_markdown(name, wiki, data, narrative, start_date, end_date, status, used_template,
                  stories=None) -> str:
    os.makedirs("reports", exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_").lower()
    path = os.path.join("reports", f"{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")

    L = [f"# {name} — {narrative.get('_report_title', 'Politician Report')}", ""]
    if start_date or end_date:
        L += [f"_Period: {_range_text(start_date, end_date)}_", ""]

    L += ["## Basic Details", ""]
    if not wiki.get("found"):
        L += ["_No Wikipedia page found for this name._", ""]
    else:
        if wiki.get("description"):
            L += [f"**{wiki['description']}**", ""]
        if wiki.get("extract"):
            L += [wiki["extract"], ""]
        if wiki.get("page_url"):
            L += [f"[Full Wikipedia page]({wiki['page_url']})", ""]

    L += ["## Summary", ""]
    if narrative.get("note"):
        L += [f"> ⚠️ {narrative['note']}", ""]

    topline = narrative.get(TOPLINE_KEY, "").strip()
    L += [f"> **{TOPLINE_LABEL}:** " + (topline if topline else f"_{EMPTY_TOPLINE_TEXT}_"), ""]

    for key, label, _ in narrative.get("_categories") or SUMMARY_CATEGORIES:
        text = (narrative.get(key, "") or "").strip()
        L += [f"### {label}", "", text if text else f"_{EMPTY_SECTION_TEXT}_", ""]

    if stories:
        L += ["## Top Stories", "", f"_{glance_text(build_glance(data, stories))}_", ""]
        for i, st in enumerate(stories, 1):
            L.append(f"{i}. [{st['headline']}]({st['url']})" if st.get("url") else f"{i}. {st['headline']}")
            L.append(f"   - *{story_meta(st)}*")
        L.append("")

    headlines = data["headlines"]
    if start_date or end_date:
        L += [f"## Day-by-Day Headlines ({len(headlines)})", ""]
        for day_label, day_items in group_headlines_by_day(headlines):
            L += [f"### {day_label}", ""]
            for h in day_items:
                L.append(f"- [{h['headline']}]({h['url']})" if h.get("url") else f"- {h['headline']}")
                if h.get("source"):
                    L.append(f"  *{h['source']}*")
            L.append("")
    else:
        L += [f"## Headlines ({len(headlines)})", ""]
        for i, h in enumerate(headlines, 1):
            L.append(f"{i}. [{h['headline']}]({h['url']})" if h.get("url") else f"{i}. {h['headline']}")
            meta = " | ".join(filter(None, [h.get("source", ""), h.get("date", "")]))
            if meta:
                L.append(f"   - *{meta}*")
            L.append("")

    for sec in build_sections(data):
        L += [f"## {sec['title'].title()} ({len(sec['items'])})", ""]
        if not sec["items"]:
            L += [f"_{_empty_note(sec, status)}_", ""]
        for i, it in enumerate(sec["items"], 1):
            L.append(f"{i}. [{it['title']}]({it['url']})" if it["url"] else f"{i}. {it['title']}")
            if it["body"]:
                L.append(f"   - {it['body']}")
            if it["meta"]:
                L.append(f"   - *{it['meta']}*")
            L.append("")

    L += ["## Sources Checked", ""] + [f"- **{label}:** {st}" for label, st in status.items()]
    L += ["", "---", f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}. Verify important facts against the linked sources._"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


def _pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ReportTitle", parent=styles["Title"], spaceAfter=4))
    styles.add(ParagraphStyle("Meta", parent=styles["Normal"], textColor="#555555", spaceAfter=12))
    styles.add(ParagraphStyle("Section", parent=styles["Heading2"], spaceBefore=16, spaceAfter=6))
    styles.add(ParagraphStyle("SubSection", parent=styles["Heading3"], spaceBefore=10, spaceAfter=4))
    styles.add(ParagraphStyle("Category", parent=styles["Heading4"], fontName="Helvetica-Bold", fontSize=10.5,
                              leading=13, textColor="#1a3a63", spaceBefore=11, spaceAfter=3))
    styles.add(ParagraphStyle("Body", parent=styles["BodyText"], leading=14, spaceAfter=6, alignment=TA_LEFT))
    styles.add(ParagraphStyle("TopLine", parent=styles["BodyText"], fontSize=10.5, leading=15))
    styles.add(ParagraphStyle("EmptySection", parent=styles["BodyText"], fontName="Helvetica-Oblique",
                              textColor="#888888", spaceAfter=6))
    styles.add(ParagraphStyle("Item", parent=styles["BodyText"], leftIndent=14, spaceAfter=4, bulletIndent=4))
    styles.add(ParagraphStyle("ItemMeta", parent=styles["Normal"], leftIndent=14, textColor="#555555", fontSize=8.5, spaceAfter=8))
    styles.add(ParagraphStyle("Note", parent=styles["BodyText"], textColor="#8a6d00", spaceAfter=8))
    styles.add(ParagraphStyle("Empty", parent=styles["BodyText"], textColor="#777777", spaceAfter=6))
    return styles


def _pdf_link(url: str, text: str) -> str:
    """Build reportlab markup for a clickable link, with content properly escaped."""
    text = xml_escape(text) if text else xml_escape(url)
    if not url:
        return text
    return f'<link href="{xml_escape(url, {chr(34): "&quot;"})}" color="#1a5fb4">{text}</link>'


def save_pdf(name, wiki, data, narrative, start_date, end_date, status, used_template,
             stories=None) -> str:
    """Render the same report as save_markdown(), as a PDF via reportlab.

    reportlab is pure-Python (no Poppler/pandoc/wkhtmltopdf needed), so this
    works the same way on Windows, macOS, and Linux with just `pip install`.
    """
    if SimpleDocTemplate is None:
        raise RuntimeError("reportlab isn't installed. Run:  pip install reportlab")

    os.makedirs("reports", exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_").lower()
    path = os.path.join("reports", f"{safe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    styles = _pdf_styles()
    S = []

    report_title = narrative.get("_report_title", "Politician Report")
    S.append(Paragraph(xml_escape(f"{name} — {report_title}"), styles["ReportTitle"]))
    if start_date or end_date:
        S.append(Paragraph(xml_escape(f"Period: {_range_text(start_date, end_date)}"), styles["Meta"]))
    S.append(HRFlowable(width="100%", color="#cccccc", spaceAfter=10))

    S.append(Paragraph("Basic Details", styles["Section"]))
    if not wiki.get("found"):
        S.append(Paragraph("No Wikipedia page found for this name.", styles["Empty"]))
    else:
        if wiki.get("description"):
            S.append(Paragraph(f"<b>{xml_escape(wiki['description'])}</b>", styles["Body"]))
        if wiki.get("extract"):
            S.append(Paragraph(xml_escape(wiki["extract"]), styles["Body"]))
        if wiki.get("page_url"):
            S.append(Paragraph(_pdf_link(wiki["page_url"], "Full Wikipedia page"), styles["Body"]))

    S.append(Paragraph("Summary", styles["Section"]))
    if narrative.get("note"):
        S.append(Paragraph(f"⚠ {xml_escape(narrative['note'])}", styles["Note"]))
    topline = narrative.get(TOPLINE_KEY, "").strip()
    box = Table([[Paragraph(f"<b>{xml_escape(TOPLINE_LABEL)}</b><br/>"
                            + (xml_escape(topline) if topline else f"<i>{xml_escape(EMPTY_TOPLINE_TEXT)}</i>"),
                            styles["TopLine"])]], colWidths=[6.9 * inch])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f1ee")),
                             ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor("#6b1f2a")),
                             ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                             ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    S += [box, Spacer(1, 4)]
    for key, label, _ in narrative.get("_categories") or SUMMARY_CATEGORIES:
        text = (narrative.get(key, "") or "").strip()
        S.append(Paragraph(xml_escape(label), styles["Category"]))
        S.append(Paragraph(xml_escape(text), styles["Body"]) if text
                 else Paragraph(xml_escape(EMPTY_SECTION_TEXT), styles["EmptySection"]))

    if stories:
        S.append(Paragraph("Top Stories", styles["Section"]))
        S.append(Paragraph(xml_escape(glance_text(build_glance(data, stories))), styles["ItemMeta"]))
        for i, st in enumerate(stories, 1):
            S.append(Paragraph(f"{i}. {_pdf_link(st.get('url', ''), st['headline'])}", styles["Item"]))
            S.append(Paragraph(xml_escape(story_meta(st)), styles["ItemMeta"]))

    headlines = data["headlines"]
    if start_date or end_date:
        S.append(Paragraph(f"Day-by-Day Headlines ({len(headlines)})", styles["Section"]))
        for day_label, day_items in group_headlines_by_day(headlines):
            S.append(Paragraph(xml_escape(day_label), styles["SubSection"]))
            for h in day_items:
                S.append(Paragraph(f"\u2022 {_pdf_link(h.get('url', ''), h['headline'])}", styles["Item"]))
                if h.get("source"):
                    S.append(Paragraph(xml_escape(h["source"]), styles["ItemMeta"]))
    else:
        S.append(Paragraph(f"Headlines ({len(headlines)})", styles["Section"]))
        for i, h in enumerate(headlines, 1):
            S.append(Paragraph(f"{i}. {_pdf_link(h.get('url', ''), h['headline'])}", styles["Item"]))
            meta = " | ".join(filter(None, [h.get("source", ""), h.get("date", "")]))
            if meta:
                S.append(Paragraph(xml_escape(meta), styles["ItemMeta"]))

    for sec in build_sections(data):
        S.append(Paragraph(f"{sec['title'].title()} ({len(sec['items'])})", styles["Section"]))
        if not sec["items"]:
            S.append(Paragraph(xml_escape(_empty_note(sec, status)), styles["Empty"]))
        for i, it in enumerate(sec["items"], 1):
            S.append(Paragraph(f"{i}. {_pdf_link(it['url'], it['title'])}", styles["Item"]))
            if it["body"]:
                S.append(Paragraph(xml_escape(it["body"]), styles["ItemMeta"]))
            if it["meta"]:
                S.append(Paragraph(xml_escape(it["meta"]), styles["ItemMeta"]))

    S.append(Paragraph("Sources Checked", styles["Section"]))
    for label, st in status.items():
        S.append(Paragraph(f"<b>{xml_escape(label)}:</b> {xml_escape(st)}", styles["ItemMeta"]))

    S.append(Spacer(1, 0.2 * inch))
    S.append(HRFlowable(width="100%", color="#cccccc", spaceAfter=6))
    S.append(Paragraph(
        xml_escape(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}. Verify important facts against the linked sources."),
        styles["Meta"]))

    doc = SimpleDocTemplate(path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.7 * inch, rightMargin=0.7 * inch, title=f"{name} — {report_title}")
    doc.build(S)
    return path


# --------------------------------------------------------------------------
# News wrap-up: Andhra Pradesh and Telangana
# --------------------------------------------------------------------------
# A general news round-up for one day or a date range -- not about any one
# politician. It is built around FOUR HIGHLIGHTED SECTIONS that are always
# shown first, and always given room even when a bigger story dominates the
# coverage:
#   1. Government & Cabinet Decisions   (CM, Governor, cabinet, GOs, appointments)
#   2. Policy & Legislation             (schemes, bills, ordinances, assembly)
#   3. Ministries & Departments         (each story tagged by department)
#   4. Courts & Rulings                 (each story tagged by court)
# followed by the rest of the day's news by topic. Dedicated searches look for
# the highlighted areas specifically, and each highlighted section gets its own
# quota of stories, so a single-outlet High Court ruling or department order is
# not crowded out by one widely repeated story.

WRAP_STATES = {
    "andhra pradesh": {
        "label": "Andhra Pradesh",
        # General searches (state + major cities); split into date chunks for ranges.
        "query_sets": [["Andhra Pradesh", "Amaravati"],
                       ["Visakhapatnam", "Vijayawada", "Tirupati", "Guntur", "Nellore", "Kurnool", "Kakinada",
                        "Rajahmundry", "Anantapur", "Kadapa"]],
        # Focused searches for the highlighted sections (Google News).
        "focus_queries": [
            '("Andhra Pradesh High Court" OR "AP High Court" OR "AP HC")',
            '"Supreme Court" "Andhra Pradesh"',
            '"Andhra Pradesh" (cabinet OR "chief minister" OR "government order" OR governor)',
            '"Andhra Pradesh" (policy OR scheme OR bill OR ordinance OR assembly)',
            '"Andhra Pradesh" (minister OR ministry OR department)',
        ],
        "aliases": {"ap", "andhra", "andhra pradesh", "a.p", "a.p."},
    },
    "telangana": {
        "label": "Telangana",
        "query_sets": [["Telangana"],
                       ["Hyderabad", "Warangal", "Karimnagar", "Nizamabad", "Khammam", "Secunderabad",
                        "Mahabubnagar", "Nalgonda", "Siddipet", "Adilabad"]],
        "focus_queries": [
            '("Telangana High Court" OR "Telangana HC" OR "High Court of Telangana")',
            '"Supreme Court" "Telangana"',
            '"Telangana" (cabinet OR "chief minister" OR "government order" OR governor)',
            '"Telangana" (policy OR scheme OR bill OR ordinance OR assembly)',
            '"Telangana" (minister OR ministry OR department)',
        ],
        "aliases": {"telangana", "ts", "tg", "telengana"},
    },
}

# (key, label, icon) -- the four highlighted sections, in display order.
WRAP_HIGHLIGHTS = [
    ("government", "Government & Cabinet Decisions", "\U0001F3DB\ufe0f"),
    ("policy", "Policy & Legislation", "\U0001F4DC"),
    ("ministries", "Ministries & Departments", "\U0001F3E2"),
    ("courts", "Courts & Rulings", "\u2696\ufe0f"),
]
WRAP_OTHER_SECTIONS = [
    ("politics", "Politics & Parties"),
    ("law_order", "Law & Order"),
    ("economy", "Economy & Business"),
    ("infrastructure", "Infrastructure & Development"),
    ("weather", "Weather & Disasters"),
    ("society", "Society, Health & Culture"),
    ("other", "Other"),
]
WRAP_HIGHLIGHT_KEYS = [k for k, _, _ in WRAP_HIGHLIGHTS]
WRAP_SECTION_ORDER = WRAP_HIGHLIGHT_KEYS + [k for k, _ in WRAP_OTHER_SECTIONS]
WRAP_SECTION_LABELS = {**{k: l for k, l, _ in WRAP_HIGHLIGHTS}, **dict(WRAP_OTHER_SECTIONS)}
WRAP_OTHER = "Other"

# Stories kept per highlighted section (x1.5 for a date range), and for all other news combined.
WRAP_SECTION_CAPS = {"government": 8, "policy": 8, "ministries": 12, "courts": 10}
WRAP_OTHER_CAP = 12
WRAP_CANDIDATE_STORIES = 200
WRAP_MAX_DAYS = 31
# Over a date range, an ongoing story often goes quiet for a few days and then
# resurfaces (approved on Monday, work starts Friday). Items up to this many days
# after a story's latest item still join it, so it shows as ONE story with its
# full date span rather than several fragments. (Single days use 1.)
WRAP_STORY_GAP_DAYS_RANGE = 4
IST_OFFSET = timedelta(hours=5, minutes=30)


def _rx(fragments: list):
    """One case-insensitive pattern from regex fragments; each must start at a
    word start (so 'rain' doesn't match inside 'train'), but may run on
    ('appoint' matches 'appointed')."""
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(fragments) + r")", re.I)


_SECTION_PATTERNS = {
    # A story mentioning a court is a court story, whatever else it mentions.
    # ("ruling" is deliberately NOT here: "ruling party" is everywhere.)
    "courts": _rx([r"high court", r"hc\b", r"supreme court", r"apex court", r"courts?\b", r"tribunal", r"ngt\b",
                   r"bench\b", r"judge", r"justice [a-z]", r"verdict", r"judgm?ent", r"judgement", r"bail\b",
                   r"acquit", r"convicted", r"sentenced", r"pil\b", r"contempt"]),
    "government": _rx([r"cabinet", r"chief minister", r"cm\b", r"deputy cm", r"governor", r"chief secretary",
                       r"g\.?\s?o\.?\s?(ms|rt)\b", r"government order", r"orders? issued", r"issued orders", r"appoint",
                       r"transfer", r"ias\b", r"ips\b", r"collector", r"review meeting", r"review(s|ed)?\b",
                       r"directs? officials", r"directed officials", r"sanction", r"approv", r"inaugurat",
                       r"foundation stone", r"launch(es|ed)?\b", r"ex gratia"]),
    "policy": _rx([r"polic(y|ies)\b", r"scheme", r"bills?\b", r"ordinance", r"assembly", r"legislat", r"budget",
                   r"amendment", r"guidelines", r"rules\b", r"reservation", r"quota", r"notification", r"welfare",
                   r"guarantee", r"subsid", r"pension", r"regulation", r"white paper"]),
    "ministries": _rx([r"ministers?\b", r"ministry", r"department", r"dept\b", r"commissioner", r"principal secretary",
                       r"secretary\b"]),
    "politics": _rx([r"opposition", r"slams?\b", r"attack", r"alleg", r"criticis", r"part(y|ies)\b", r"bjp", r"congress",
                     r"brs\b", r"tdp\b", r"ysrcp", r"ysrc\b", r"jana ?sena", r"aimim", r"cpi\b", r"election", r"polls?\b",
                     r"bypoll", r"by-election", r"campaign", r"rally", r"mlas?\b", r"mps?\b", r"mlc\b", r"defect",
                     r"joins\b", r"quits?\b", r"resign", r"protest", r"dharna", r"padayatra"]),
    "law_order": _rx([r"police", r"arrest", r"murder", r"killed", r"theft", r"robbery", r"assault", r"rape", r"fir\b",
                      r"ganja", r"drugs?\b", r"smuggl", r"raid", r"seiz", r"cyber ?crime", r"fraud", r"scam", r"cheat",
                      r"accused", r"abduct", r"kidnap", r"dowry", r"stabb", r"found dead", r"ransom", r"suspect",
                      r"murdered", r"cyber fraud"]),
    "economy": _rx([r"invest", r"industr", r"compan(y|ies)", r"jobs\b", r"startup", r"revenue", r"econom", r"gdp",
                    r"export", r"mous?\b", r"prices?\b", r"market", r"bank", r"gst\b", r"it sector", r"tech park", r"ipo\b"]),
    "infrastructure": _rx([r"metro", r"roads?\b", r"highway", r"airport", r"seaport", r"railway", r"rail\b", r"train",
                           r"projects?\b", r"dam\b", r"reservoir", r"canal", r"bridge", r"flyover", r"construction",
                           r"water supply", r"power plant"]),
    "weather": _rx([r"rain", r"flood", r"cyclone", r"heat ?wave", r"imd\b", r"weather", r"storm", r"landslide",
                    r"waterlog", r"inundat", r"lash(es|ed)?\b", r"downpour", r"showers\b", r"el ni(n|ñ)o",
                    r"lightning", r"drought", r"temperature", r"monsoon", r"fire\b", r"accident", r"collapse"]),
    "society": _rx([r"hospital", r"health\b", r"dengue", r"fever", r"school", r"students?\b", r"exam", r"temple",
                    r"festival", r"tirumala", r"ttd\b", r"devotee", r"film", r"tollywood", r"movie", r"cricket",
                    r"sport", r"culture", r"bathukamma", r"bonalu", r"sankranti", r"dussehra", r"diwali"]),
}

# Department tags (most specific match wins on hit count). Names follow the
# usual state-government departments of Andhra Pradesh and Telangana.
WRAP_DEPARTMENTS = [
    ("Home & Police", _rx([r"home minister", r"home department", r"police", r"dgp\b", r"law and order"])),
    ("Finance", _rx([r"finance minister", r"finance department", r"budget", r"borrowing", r"debt\b", r"fiscal",
                     r"gst\b", r"treasury"])),
    ("Revenue & Land", _rx([r"revenue department", r"revenue minister", r"land records", r"land acquisition",
                            r"dharani", r"bhu ?bharati", r"registration", r"stamps", r"tahsildar", r"mro\b", r"land\b"])),
    ("Health & Family Welfare", _rx([r"health minister", r"health department", r"hospital", r"aarogyasri", r"medical",
                                     r"doctor", r"health\b", r"dengue", r"vaccin"])),
    ("Education", _rx([r"education minister", r"education department", r"school", r"universit", r"college",
                       r"teacher", r"students?\b", r"exam", r"intermediate", r"ssc\b", r"education"])),
    ("Agriculture & Cooperation", _rx([r"agricultur", r"farmer", r"crop", r"rythu", r"raithu", r"paddy",
                                       r"procurement", r"fertili", r"seeds?\b", r"horticultur"])),
    ("Irrigation & Water Resources", _rx([r"irrigation", r"water resources", r"polavaram", r"kaleshwaram",
                                          r"reservoir", r"canal", r"krishna water", r"godavari", r"barrage"])),
    ("Municipal Administration & Urban Development", _rx([r"municipal", r"ghmc", r"hmda", r"crda", r"urban development",
                                                          r"metro", r"hydraa", r"civic", r"sanitation"])),
    ("Panchayat Raj & Rural Development", _rx([r"panchayat", r"rural development", r"gram sabha", r"nrega", r"mgnregs",
                                               r"village secretariat"])),
    ("Industries, IT & Commerce", _rx([r"industries minister", r"it minister", r"industr", r"investment", r"mous?\b",
                                       r"msmes?\b", r"centre of excellence", r"data cent(er|re)",
                                       r"electronics", r"startup", r"commerce", r"semiconductor"])),
    ("Energy", _rx([r"energy", r"power\b", r"electricity", r"discom", r"transco", r"genco", r"solar", r"tariff"])),
    ("Transport, Roads & Buildings", _rx([r"transport", r"rtc\b", r"tsrtc", r"tgsrtc", r"apsrtc", r"roads and buildings",
                                          r"r&b\b", r"highway", r"bus\b", r"buses"])),
    ("Welfare (SC, ST, BC, Minorities, Women & Child)", _rx([r"social welfare", r"tribal", r"scheduled caste",
                                                             r"scheduled tribe", r"backward class", r"bc welfare",
                                                             r"minorit", r"women (and|&) child", r"anganwadi",
                                                             r"pension", r"welfare"])),
    ("Civil Supplies", _rx([r"civil supplies", r"ration", r"pds\b", r"fine rice", r"rice distribution"])),
    ("Endowments", _rx([r"endowment", r"temple", r"ttd\b", r"devasthanam", r"tirumala"])),
    ("Excise & Prohibition", _rx([r"excise", r"liquor", r"prohibition", r"belt shops"])),
    ("Environment & Forests", _rx([r"forest", r"environment", r"pollution", r"tiger", r"wildlife", r"green cover"])),
    ("Housing", _rx([r"housing", r"indiramma", r"house sites", r"tidco", r"2bhk", r"double bedroom"])),
    ("Labour & Employment", _rx([r"labour", r"employment", r"workers", r"skill", r"jobs\b"])),
    ("Tourism, Culture & Sports", _rx([r"tourism", r"culture", r"sports\b", r"youth", r"heritage"])),
]

# Court tags, most specific first.
WRAP_COURTS = [
    ("Supreme Court", _rx([r"supreme court", r"apex court"])),
    ("Telangana High Court", _rx([r"telangana high court", r"telangana hc\b", r"high court of telangana",
                                  r"t[sg] high court"])),
    ("Andhra Pradesh High Court", _rx([r"andhra pradesh high court", r"ap high court", r"ap hc\b", r"andhra high court",
                                       r"high court of andhra"])),
    ("National Green Tribunal", _rx([r"ngt\b", r"green tribunal"])),
    ("Special / Lower Court", _rx([r"acb court", r"cbi court", r"special court", r"sessions court", r"district court",
                                   r"magistrate", r"pocso court", r"ed court", r"nampally court", r"lower court"])),
    ("High Court", _rx([r"high court", r"hc\b"])),
    ("Tribunal", _rx([r"tribunal"])),
]


def _hits(pattern, text: str) -> int:
    return len({m.group(0).lower() for m in pattern.finditer(text)})


def detect_department(text: str):
    best, best_hits = None, 0
    for label, pat in WRAP_DEPARTMENTS:
        h = _hits(pat, text)
        if h > best_hits:
            best, best_hits = label, h
    return best


def detect_court(text: str) -> str:
    for label, pat in WRAP_COURTS:
        if pat.search(text):
            return label
    return "Court"


# A court mention only makes a story a COURT story when something actually
# happened in or before a court -- a ruling, order, hearing, filing or judicial
# move. "Rahul Gandhi calls for march to Supreme Court" or "courts should not
# drag their feet, says minister" are about courts, not court proceedings.
_COURT_ACTIONS = _rx([
    r"stay(s|ed)?\b", r"quash", r"uph[eo]ld", r"dismiss", r"direct", r"order", r"rul(es|ed)\b", r"verdict",
    r"judgm?ent", r"judgement", r"struck down", r"strikes? down", r"sets? aside", r"reserv(es|ed)\b", r"hear(s|ing)?\b",
    r"heard\b", r"adjourn", r"refus", r"allow(s|ed)\b", r"reject", r"bail", r"acquit", r"convict", r"sentence",
    r"notice\b", r"petition", r"plea\b", r"pils?\b", r"contempt", r"summon", r"warns?\b", r"pulls? up", r"raps?\b",
    r"to decide", r"decides?\b", r"(moves?|moved|approach(es|ed)?|reach(es)?|knocks?) (the )?(hc|high court|supreme court|apex court|court)",
    r"seeks? (response|report|explanation|counter)", r"(transferred|shifted|elevated|sworn in)", r"writ\b", r"trial\b",
    r"links? pils?", r"halt(s|ed)?\b", r"block(s|ed)?\b",
])


def classify_story(text: str) -> dict:
    """{'section', 'department', 'court'} for one headline. A court story
    needs a court AND a court action (see _COURT_ACTIONS). Otherwise the
    section with the most distinct keyword hits wins, and ties go to the
    highlighted sections -- so "CM reviews metro project" is a government
    story, not an infrastructure one."""
    t = " ".join((text or "").split())
    dept = detect_department(t)
    if _SECTION_PATTERNS["courts"].search(t) and _COURT_ACTIONS.search(t):
        return {"section": "courts", "department": dept, "court": detect_court(t)}
    hits = {k: _hits(p, t) for k, p in _SECTION_PATTERNS.items() if k != "courts"}
    if hits["ministries"] and dept:
        hits["ministries"] += 1   # "Health minister inspects hospital" -> ministries, tagged Health
    order = ["policy", "government", "ministries", "politics", "law_order", "economy", "infrastructure", "weather",
             "society"]
    best = max(order, key=lambda k: (hits[k], -order.index(k)))
    if hits[best] == 0:
        # Nothing but a department's subject area (e.g. "Telangana to set up Centre of Excellence for MSMEs"):
        # that IS department news.
        return {"section": "ministries" if dept else "other", "department": dept, "court": None}
    return {"section": best, "department": dept, "court": None}


def classify_cluster(story: dict) -> dict:
    """Classify a grouped story by MAJORITY VOTE over its articles' headlines
    (the representative headline counts twice), rather than over all the
    headlines run together -- one outlet's stray word ("rules" in one of 11
    reports of a diverted flight) can no longer drag the whole story into the
    wrong section."""
    votes = [classify_story(it["headline"]) for it in story.get("items") or []]
    rep = classify_story(story["headline"])
    votes.append(rep)
    counts = {}
    for v in votes:
        counts[v["section"]] = counts.get(v["section"], 0) + 1
    rank = {k: i for i, k in enumerate(WRAP_SECTION_ORDER)}
    section = max(counts, key=lambda k: (counts[k], k != "other", -rank.get(k, 99)))
    def most_common(field, pool):
        vals = [v[field] for v in pool if v.get(field)]
        return max(set(vals), key=vals.count) if vals else None
    same = [v for v in votes if v["section"] == section]
    return {"section": section, "department": most_common("department", same) or rep["department"],
            "court": most_common("court", same) if section == "courts" else None}


def classify_topic(text: str) -> str:
    """The section label for a piece of text (see classify_story)."""
    return WRAP_SECTION_LABELS[classify_story(text)["section"]]


def resolve_wrap_states(choice: str = "") -> list:
    """'both'/'' -> both states; 'ap'/'andhra'/... -> Andhra Pradesh;
    'telangana'/'ts'/'tg' -> Telangana. Raises ValueError for anything else."""
    c = (choice or "both").strip().lower()
    if c in ("both", "all", "ap & telangana", "ap and telangana", "andhra pradesh and telangana"):
        return list(WRAP_STATES)
    for key, info in WRAP_STATES.items():
        if c == key or c in info["aliases"]:
            return [key]
    raise ValueError(f"Unknown state '{choice}'. Use: both, ap (Andhra Pradesh), or telangana.")


_WRAP_TRIGGERS = re.compile(r"\b(wrap[\s-]?up|wrapup|wrap|daily wrap|weekly wrap|news wrap|round[\s-]?up|digest|"
                            r"daily news|weekly news|today'?s news|news today|news of the day|news this week|"
                            r"this week'?s news|daily briefing)\b", re.I)


def detect_wrap_request(text: str, default: str = "both"):
    """If a chat message is asking for the daily wrap-up rather than naming a
    politician (e.g. "daily wrap", "today's news telangana", "AP roundup"),
    return the state choice ('both', 'andhra pradesh' or 'telangana');
    otherwise None. If the message names neither state, `default` is
    returned (e.g. whatever is selected in the UI)."""
    t = (text or "").lower()
    if not _WRAP_TRIGGERS.search(t):
        return None
    ap = bool(re.search(r"\b(andhra|a\.?p\.?)\b", t))
    tg = bool(re.search(r"\b(telangana|telengana|ts|tg|hyderabad)\b", t))
    if ap and not tg:
        return "andhra pradesh"
    if tg and not ap:
        return "telangana"
    return "both" if (ap and tg) else default


def ist_today():
    return (utc_now() + IST_OFFSET).date()


def detect_wrap_range(text: str, today=None):
    """(start, end) dates if a wrap-up request names a period in words --
    "yesterday", "today", "last 5 days", "past 10 days", "this week",
    "weekly" -- otherwise None (the caller then uses its own default dates)."""
    t = (text or "").lower()
    today = today or ist_today()
    m = re.search(r"\b(?:last|past|previous)\s+(\d{1,2})\s+days?\b", t)
    if m:
        n = max(1, min(int(m.group(1)), WRAP_MAX_DAYS))
        return today - timedelta(days=n - 1), today
    if re.search(r"\b(this week|weekly|last week|past week|week'?s)\b", t):
        return today - timedelta(days=6), today
    if "yesterday" in t:
        y = today - timedelta(days=1)
        return y, y
    if re.search(r"\btoday\b", t):
        return today, today
    return None


def validate_wrap_range(start, end) -> int:
    """Number of days in the range; raises ValueError with a plain-English
    reason if the range can't be used."""
    if start > end:
        raise ValueError("The start date must be on or before the end date.")
    if end > ist_today():
        raise ValueError("The end date can't be in the future (India time).")
    days = (end - start).days + 1
    if days > WRAP_MAX_DAYS:
        raise ValueError(f"Please pick a range of at most {WRAP_MAX_DAYS} days ({days} days chosen).")
    return days


def wrap_period_text(start, end) -> str:
    if start == end:
        return f"{start:%A, %d %B %Y}"
    if start.year == end.year:
        return f"{start:%d %b} \u2013 {end:%d %b %Y}"
    return f"{start:%d %b %Y} \u2013 {end:%d %b %Y}"


def ist_day_window(day) -> tuple:
    """A calendar day in India (IST), as a naive-UTC (start, end) pair to match
    the naive-UTC timestamps the news sources are parsed into."""
    start = datetime(day.year, day.month, day.day) - IST_OFFSET
    return start, start + timedelta(days=1) - timedelta(seconds=1)


def ist_range_window(start_day, end_day) -> tuple:
    """Several India calendar days (inclusive) as one naive-UTC window."""
    return ist_day_window(start_day)[0], ist_day_window(end_day)[1]


def _date_chunks(start_day, end_day, max_chunks: int = 8) -> list:
    """Split a date range into at most max_chunks consecutive pieces (one per
    day for ranges up to a week). Google News returns at most ~100 results
    per search, so one search over a whole week or month would silently miss
    most of the coverage -- searching piece by piece avoids that."""
    days = (end_day - start_day).days + 1
    size = max(1, -(-days // max_chunks))
    out, d = [], start_day
    while d <= end_day:
        e = min(end_day, d + timedelta(days=size - 1))
        out.append((d, e))
        d = e + timedelta(days=1)
    return out


def _dedupe_articles(items: list) -> list:
    """Drop repeat copies of the SAME article (same link, or same headline from
    the same outlet). The same headline from DIFFERENT outlets is kept --
    syndicated copy (e.g. PTI) run by four outlets is four outlets carrying the
    story, which is exactly what ranks it as widely reported."""
    seen_urls, seen_titles, out = set(), set(), []
    for it in items:
        u = (it.get("url") or "").split("?")[0].rstrip("/")
        t = re.sub(r"\W+", " ", _clean_headline(it.get("headline", ""), it.get("source", "")).lower()).strip()
        tk = (t, _outlet_key(it.get("source", "")))
        if (u and u in seen_urls) or (t and tk in seen_titles):
            continue
        seen_urls.add(u)
        seen_titles.add(tk)
        out.append(it)
    return out




# Which places (and prominent people/parties) count as "this state", and which
# clearly point elsewhere. People matter because state leaders are constantly
# in Delhi: "Revanth urges Congress leaders to join protest in Delhi" is a
# Telangana story even though it names only Delhi. An
# article is dropped from a state's wrap-up only when its headline names
# somewhere else AND nothing in this state -- e.g. "Tripura strengthens
# district hospitals: CM Saha", which a search for "Telangana" can return
# simply because it was published by Telangana Today.
_WRAP_OWN_PLACES = {
    "andhra pradesh": [r"andhra", r"ap\b", r"amaravati", r"visakhapatnam", r"vizag", r"vijayawada", r"tirupati",
                       r"tirumala", r"guntur", r"nellore", r"kurnool", r"kakinada", r"rajahmundry",
                       r"rajamahendravaram", r"anantapur", r"kadapa", r"srikakulam", r"vizianagaram", r"ongole",
                       r"eluru", r"machilipatnam", r"chittoor", r"polavaram", r"palnadu", r"gvmc\b", r"apsrtc", r"ttd\b",
                       # prominent people and state parties -- UPDATE when leadership changes
                       r"chandrababu", r"naidu", r"pawan kalyan", r"jagan", r"lokesh", r"atchannaidu", r"tdp\b",
                       r"ysrcp", r"ysrc\b", r"jana ?sena"],
    "telangana": [r"telangana", r"hyderabad", r"secunderabad", r"cyberabad", r"warangal", r"karimnagar", r"nizamabad",
                  r"khammam", r"mahabubnagar", r"nalgonda", r"siddipet", r"adilabad", r"medak", r"sangareddy",
                  r"rangareddy", r"malkajgiri", r"ghmc\b", r"hmda\b", r"tgsrtc", r"tsrtc", r"osmania", r"musi\b",
                  # prominent people and state parties -- UPDATE when leadership changes
                  r"revanth", r"kcr\b", r"ktr\b", r"harish rao", r"kavitha", r"bhatti", r"vikramarka", r"sridhar babu",
                  r"ponnam", r"uttam kumar", r"komatireddy", r"seethakka", r"kishan reddy", r"bandi sanjay", r"owaisi",
                  r"brs\b", r"bharat rashtra samithi"],
}
_WRAP_ELSEWHERE = [
    r"tripura", r"kerala", r"karnataka", r"bengaluru", r"bangalore", r"tamil nadu", r"chennai", r"maharashtra",
    r"mumbai", r"pune\b", r"gujarat", r"ahmedabad", r"rajasthan", r"jaipur", r"punjab", r"haryana", r"bihar", r"patna",
    r"uttar pradesh", r"lucknow", r"madhya pradesh", r"bhopal", r"west bengal", r"kolkata", r"odisha", r"bhubaneswar",
    r"assam", r"guwahati", r"jharkhand", r"chhattisgarh", r"goa\b", r"himachal", r"uttarakhand", r"j&k", r"jammu",
    r"kashmir", r"ladakh", r"manipur", r"meghalaya", r"mizoram", r"nagaland", r"sikkim", r"arunachal", r"delhi",
    r"venezuela", r"china", r"pakistan", r"sri lanka", r"nepal", r"russia", r"ukraine", r"israel", r"iran\b",
    r"saudi", r"riyadh", r"dubai", r"uae\b", r"london", r"america", r"canada", r"australia",
]
_WRAP_ELSEWHERE_CASED = re.compile(r"(?<![A-Za-z])(US|U\.S\.|UK|U\.K\.)(?![A-Za-z])")


def _place_patterns(state_key: str) -> tuple:
    own = _rx(_WRAP_OWN_PLACES[state_key])
    others = [frag for k, frags in _WRAP_OWN_PLACES.items() if k != state_key for frag in frags]
    return own, _rx(_WRAP_ELSEWHERE + others)


def is_off_state(headline: str, state_key: str) -> bool:
    own, elsewhere = _place_patterns(state_key)
    h = headline or ""
    if own.search(h):
        return False
    return bool(elsewhere.search(h) or _WRAP_ELSEWHERE_CASED.search(h))


# GDELT asks for about one request every 5 seconds; going faster gets "429 Too
# Many Requests", which is why GDELT contributed almost nothing to the earlier
# wrap-ups. Requests are now spaced out.
GDELT_MIN_INTERVAL = 5.5
_last_gdelt_call = [0.0]


def _gdelt_throttled(*args):
    if _last_gdelt_call[0]:
        wait = GDELT_MIN_INTERVAL - (time.monotonic() - _last_gdelt_call[0])
        if wait > 0:
            time.sleep(wait)
    try:
        return get_gdelt_news(*args)
    finally:
        _last_gdelt_call[0] = time.monotonic()


def _short_error(e) -> str:
    """'429 Client Error: Too Many Requests' -- without the 300-character URL."""
    return str(e).split(" for url")[0].strip()[:120]


# ---- Party wrap-ups -------------------------------------------------------
# The same structured wrap-up, about ONE party in Andhra Pradesh and/or
# Telangana: only news naming the party or its leaders is kept -- plus, for the
# party that LEADS a state's government, that government's decisions, since
# those are the party in power acting. An extra highlighted section, "Party
# Politics & Campaigns", comes first.

# The party leading each state's government. UPDATE after elections.
WRAP_STATE_GOVERNMENT = {"andhra pradesh": "Telugu Desam Party", "telangana": "Indian National Congress"}

# How each AP/Telangana party is recognised in a headline: its names, and its
# prominent leaders. UPDATE the leaders when leadership changes.
WRAP_PARTY_PROFILES = {
    "Bharat Rashtra Samithi": {"short": "BRS", "match": [r"brs\b", r"bharat rashtra samithi", r"trs\b"],
                               "leaders": ["KCR", "Chandrashekar Rao", "Chandrasekhar Rao", "KTR", "Rama Rao",
                                           "Harish Rao"]},
    "Indian National Congress": {"short": "Congress", "match": [r"(?<!ysr )congress", r"indian national congress"],
                                 "leaders": ["Revanth", "Bhatti", "Uttam Kumar", "Mahesh Kumar Goud", "Sharmila"]},
    "Bharatiya Janata Party": {"short": "BJP", "match": [r"bjp\b", r"bharatiya janata"],
                               "leaders": ["Kishan Reddy", "Bandi Sanjay", "Ramchander Rao", "Purandeswari",
                                           "Etela Rajender"]},
    "Telugu Desam Party": {"short": "TDP", "match": [r"tdp\b", r"telugu desam"],
                           "leaders": ["Chandrababu", "Naidu", "Lokesh", "Atchannaidu"]},
    "YSR Congress Party": {"short": "YSRCP", "match": [r"ysrcp", r"ysrc\b", r"ysr congress"],
                           "leaders": ["Jagan", "Botcha", "Sajjala", "Peddireddy"]},
    "Jana Sena Party": {"short": "Jana Sena", "match": [r"jana ?sena", r"jsp\b"],
                        "leaders": ["Pawan Kalyan", "Nadendla"]},
    "All India Majlis-e-Ittehadul Muslimeen": {"short": "AIMIM", "match": [r"aimim", r"mim\b", r"majlis"],
                                               "leaders": ["Owaisi"]},
    "Communist Party of India": {"short": "CPI", "match": [r"cpi\b(?!\s*\(?m)", r"communist party of india(?! \(m)"],
                                 "leaders": []},
    "Communist Party of India (Marxist)": {"short": "CPI(M)", "match": [r"cpi\s*\(?m\b\)?", r"cpim", r"cpm\b",
                                                                       r"communist party of india \(marxist\)"],
                                           "leaders": []},
}
WRAP_STATE_PARTY_QUERY = {"andhra pradesh": '("Andhra Pradesh" OR "Amaravati" OR "Vijayawada" OR "Visakhapatnam")',
                          "telangana": '("Telangana" OR "Hyderabad")'}
WRAP_PARTY_POLITICS_LABEL, WRAP_PARTY_POLITICS_ICON = "Party Politics & Campaigns", "\U0001F4E3"
WRAP_PARTY_POLITICS_CAP = 12


def resolve_wrap_party(name):
    """None for no party, else {name, short, search_terms, leaders, leads, match}.
    Raises ValueError for a party the tool doesn't know."""
    if isinstance(name, dict):     # a ready-made subject: a leader, a constituency or a region (see the AP/TG site)
        return name
    if not name or not str(name).strip():
        return None
    canon = _PARTY_LOOKUP.get(str(name).strip().lower())
    if not canon:
        raise ValueError(f"Unknown party '{name}'. Try: BRS, Congress, BJP, TDP, YSRCP, Jana Sena, AIMIM, CPI, CPI(M).")
    aliases, terms = POLITICAL_PARTIES[canon]
    prof = WRAP_PARTY_PROFILES.get(canon, {})
    frags = prof.get("match") or [re.escape(x.lower()) + r"\b" for x in [canon] + aliases + terms if len(x) >= 3]
    leaders = prof.get("leaders", [])
    return {"name": canon, "short": prof.get("short") or (aliases[0] if aliases else canon), "search_terms": terms,
            "leaders": leaders, "leads": [k for k, v in WRAP_STATE_GOVERNMENT.items() if v == canon],
            "match": _rx(frags + [re.escape(l.lower()) + r"\b" for l in leaders])}


def detect_wrap_party(text: str):
    """The AP/Telangana party a wrap-up request names (e.g. 'BRS wrap', 'TDP
    weekly wrap-up'), as its full name -- or None. Leaders' names don't count:
    'Revanth news wrap' is not a request for a Congress wrap-up."""
    t = (text or "").lower()
    best, best_len = None, 0
    for canon, prof in WRAP_PARTY_PROFILES.items():
        m = _rx(prof["match"]).search(t)
        if m and len(m.group(0)) > best_len:
            best, best_len = canon, len(m.group(0))
    return best


def wrap_section_order(state: dict) -> list:
    """Sections in display order; a party wrap-up puts party politics first."""
    if state.get("party"):
        return ["politics"] + [k for k in WRAP_SECTION_ORDER if k != "politics"]
    return WRAP_SECTION_ORDER


def wrap_is_starred(state: dict, key: str) -> bool:
    return key in WRAP_HIGHLIGHT_KEYS or (bool(state.get("party")) and key == "politics")


def wrap_section_label(state: dict, key: str) -> str:
    return WRAP_PARTY_POLITICS_LABEL if (state.get("party") and key == "politics") else WRAP_SECTION_LABELS[key]


def _party_searches(party: dict, state_key: str) -> tuple:
    """(general, focused) searches for a party in one state. General searches
    go to GDELT and Google News (split into date chunks for a range); focused
    ones to Google News over the whole period."""
    sq = WRAP_STATE_PARTY_QUERY[state_key]
    pq = build_news_query(party["search_terms"])
    general = [(f"{pq} {sq} sourcecountry:IN", f"{pq} {sq}")]
    focus = [f'{pq} ("High Court" OR "Supreme Court" OR court) {sq}']
    if party["leaders"]:
        focus.append(f"{build_news_query(party['leaders'])} {sq}")
    if state_key in party["leads"]:
        focus += WRAP_STATES[state_key]["focus_queries"]
    focus += [f"{q} {sq}" for q in party.get("focus_extra", [])]    # e.g. a constituency's political searches
    return general, focus


def is_party_news(headline: str, party: dict, state_key: str) -> bool:
    """Names the party or one of its leaders -- or, for the party leading this
    state's government, is about that government's decisions."""
    h = headline or ""
    if party.get("require") is not None and not party["require"].search(h):
        return False          # e.g. a constituency wrap-up keeps only POLITICAL news about the place
    if party["match"].search(h):
        return True
    return state_key in party["leads"] and classify_story(h)["section"] in ("government", "policy", "ministries")


# Reuse between wrap-ups in the same session (the app, or interactive CLI mode):
# the SAME state and dates reuse the SAME fetched news, and identical stories
# reuse the SAME written summary -- so Telangana reads identically whether it's
# run on its own or together with Andhra Pradesh. "Run fresh" bypasses both.
WRAP_CACHE_ENABLED = True
WRAP_CACHE_TTL_TODAY = 30 * 60        # ranges that include today: news is still arriving
WRAP_CACHE_TTL_PAST = 6 * 3600        # ranges entirely in the past
WRAP_NARRATIVE_TTL = 24 * 3600        # keyed by the exact stories, so it can't go stale
_WRAP_ARTICLE_CACHE = {}
_WRAP_NARRATIVE_CACHE = {}


def _cache_get_entry(cache: dict, key):
    hit = cache.get(key)
    if hit and hit["until"] > time.time():
        return hit
    cache.pop(key, None)
    return None


def clear_wrap_cache() -> None:
    _WRAP_ARTICLE_CACHE.clear()
    _WRAP_NARRATIVE_CACHE.clear()


def gather_state_news(state_key: str, start_day, end_day=None, pause: float = 1.0, party=None) -> tuple:
    """(articles, status_text) for one state over one or more IST calendar
    days: general searches (GDELT + Google News, Google split into date chunks
    for a range) plus focused Google News searches -- de-duplicated, with
    articles clearly about another state or country removed. With a party
    (see resolve_wrap_party), the searches are about that party in this state,
    and only news about the party (or, for the governing party, its
    government) is kept."""
    end_day = end_day or start_day
    info = WRAP_STATES[state_key]
    start, end = ist_range_window(start_day, end_day)
    days = (end_day - start_day).days + 1
    if party:
        general, focus = _party_searches(party, state_key)
    else:
        general = [(build_news_query(t, india_only=True), build_news_query(t)) for t in info["query_sets"]]
        focus = info.get("focus_queries", [])
    articles, fails = [], []
    counts = {"GDELT": 0, "Google News": 0, "focused searches": 0}
    for i, (gq, nq) in enumerate(general):
        if i:
            time.sleep(pause)
        try:
            got = _gdelt_throttled(gq, min(250, 75 * days), start, end)
            articles += got
            counts["GDELT"] += len(got)
        except Exception as e:
            fails.append(f"GDELT ({_short_error(e)})")
        for cs, ce in _date_chunks(start_day, end_day):
            try:
                q = f"{nq} after:{(cs - timedelta(days=1)):%Y-%m-%d} before:{(ce + timedelta(days=1)):%Y-%m-%d}"
                got = get_google_news_fallback(q, 100, *ist_range_window(cs, ce))
                articles += got
                counts["Google News"] += len(got)
            except Exception as e:
                fails.append(f"Google News ({_short_error(e)})")
            if days > 1:
                time.sleep(0.5)
    for q in focus:
        try:
            full = (f"{q} after:{(start_day - timedelta(days=1)):%Y-%m-%d} "
                    f"before:{(end_day + timedelta(days=1)):%Y-%m-%d}")
            got = get_google_news_fallback(full, 100, start, end)
            articles += got
            counts["focused searches"] += len(got)
        except Exception as e:
            fails.append(f"focused search ({_short_error(e)})")
        time.sleep(0.5)
    articles = _dedupe_articles(_filter_by_date(articles, start, end))
    kept = [a for a in articles if not is_off_state(a.get("headline", ""), state_key)]
    off = len(articles) - len(kept)
    not_party = 0
    if party:
        before = len(kept)
        kept = [a for a in kept if is_party_news(a.get("headline", ""), party, state_key)]
        not_party = before - len(kept)
    note = (f"{len(kept)} articles (GDELT {counts['GDELT']}, Google News {counts['Google News']}, "
            f"focused searches {counts['focused searches']}")
    if off:
        note += f"; {off} about other states/countries removed"
    if not_party:
        note += f"; {not_party} not about {party['short']} removed"
    if fails:
        note += "; failed: " + "; ".join(sorted(set(fails)))[:300]
    return kept, note + ")"


def select_wrap_stories(candidates: list, multi: bool = False, party_mode: bool = False) -> dict:
    """{section_key: [stories]} in display order. Each highlighted section gets
    its own quota (so its stories aren't pushed out by bigger ones); all other
    news shares one quota, most widely carried first. In a party wrap-up, party
    politics gets its own quota too and comes first."""
    scale = 1.5 if multi else 1.0
    by = {}
    for s in candidates:
        by.setdefault(s["section"], []).append(s)
    chosen = {k: by.get(k, [])[:int(WRAP_SECTION_CAPS[k] * scale)] for k in WRAP_HIGHLIGHT_KEYS}
    own = set(WRAP_HIGHLIGHT_KEYS)
    if party_mode:
        chosen["politics"] = by.get("politics", [])[:int(WRAP_PARTY_POLITICS_CAP * scale)]
        own.add("politics")
    others = [s for s in candidates if s["section"] not in own][:int(WRAP_OTHER_CAP * scale)]
    for s in others:
        chosen.setdefault(s["section"], []).append(s)
    order = wrap_section_order({"party": party_mode})
    return {k: chosen[k] for k in order if chosen.get(k)}


def _story_tags(s: dict, multi: bool) -> str:
    tags = []
    if s.get("court"):
        tags.append(f"court: {s['court']}")
    if s.get("department"):
        tags.append(f"department: {s['department']}")
    if multi and story_date_range(s):
        tags.append(f"dates: {story_date_range(s)}")
    return (" {" + "; ".join(tags) + "}") if tags else ""


def _wrap_system_prompt(multi_day: bool = False, party=None, state_key: str = "") -> str:
    period = "a period of several days" if multi_day else "one day"
    party_intro, party_rule = "", ""
    if party and party.get("kind") in ("leader", "region"):
        who = party["name"]
        party_intro = (
            (f"THIS WRAP-UP IS ABOUT ONE POLITICAL LEADER: {who}. The stories have been filtered to ones naming them. "
             f"Write from that angle: what {who} did, said, faced or decided. "
             if party["kind"] == "leader" else
             f"THIS WRAP-UP IS ABOUT THE POLITICS OF ONE AREA: {who}. The stories have been filtered to POLITICAL news "
             "about it -- parties, leaders, elected representatives, elections and government decisions there. "
             "Name the place each story concerns. ")
            + "Stay strictly neutral: do not praise or criticise anyone.\n")
        party_rule = (
            "  Party Politics & Campaigns: campaigns, statements, leadership, alliances, rivalries, defections, "
            "elections. Report claims as claims, attributed to whoever made them, never as established facts.\n")
    elif party:
        leads = state_key in party["leads"]
        party_intro = (
            f"THIS WRAP-UP IS ABOUT ONE PARTY: the {party['name']} ({party['short']}). The stories have been filtered "
            f"to ones involving {party['short']} or its leaders"
            + (f", plus the decisions of the state government, which {party['short']} leads" if leads else "")
            + f". Write from that angle: what {party['short']}, its leaders and its representatives did, said, "
            "faced or decided. Stay strictly neutral: do not praise or criticise the party.\n")
        party_rule = (
            f"  Party Politics & Campaigns: campaigns, statements, leadership, alliances, rivalries, defections, "
            f"elections. Report claims made by or against {party['short']} as claims (e.g. \"{party['short']} "
            f"alleged...\", \"rivals accused {party['short']} of...\"), never as established facts.\n")
    return (
        party_intro
        + f"You are a senior news editor turning ONE Indian state's news, covering {period}, into a bulleted "
        "wrap-up for readers who track government and policy. Each line you are given is ONE story (already merged "
        "across outlets) with an id like [S3], how many separate outlets carried it, and its section. Tags in braces "
        "give the court or government department a story concerns.\n"
        "YOUR JOB: write exactly ONE bullet-point sentence for EVERY story, in story_summaries keyed by its id. The "
        "code places each sentence under its section and links its sources beside it automatically.\n"
        + ("THE FIVE HIGHLIGHTED SECTIONS" if party else "THE FOUR HIGHLIGHTED SECTIONS")
        + " ARE THE PRIORITY OF THIS WRAP-UP (marked with a star): cover EVERY one of them -- every story in them, "
        "including single-outlet stories, because rulings and department news are often reported by only one or "
        "two outlets.\n"
        + party_rule
        + "  Government & Cabinet Decisions: what the CM, Governor, cabinet or officials decided or did (cabinet "
        "decisions, government orders, appointments, transfers, reviews, sanctions).\n"
        "  Policy & Legislation: what the policy, scheme, bill or ordinance is, who it affects, and when it takes "
        "effect if the story says so.\n"
        "  Ministries & Departments: what the minister or department did, announced or was directed to do.\n"
        "  Courts & Rulings: in which matter, and what was decided, ordered or filed (e.g. stayed, quashed, dismissed, "
        "directed, granted bail, issued notice, reserved orders, plea filed), exactly as reported. Say whether it is "
        "an interim order or a final verdict only if the story makes that clear. Never add legal analysis, "
        "consequences or predictions.\n"
        "Rules:\n"
        "- One sentence per story, about 25 words or fewer, plain neutral news English, active voice. Start with "
        "the actor or the action -- no filler openers.\n"
        "- NO REPETITION: never restate another story's point. If two stories are clearly the same event, write the "
        "sentence once (for the first) and list the other in duplicates, e.g. {\"S7\": \"S2\"} means S7 is the "
        "same event as S2.\n"
        "- Do NOT add outlet names, citations or brackets -- the sources are linked beside each point automatically.\n"
        "- Use ONLY the stories provided. Never add facts, names, numbers or context that aren't in them.\n"
        "- A single-outlet claim or allegation is reported, not established -- word it that way (\"X alleged...\").\n"
        + ("- This covers SEVERAL DAYS: cover the whole period, not just the latest day; mention the date (e.g. "
           "\"Oct 05\") when a development belongs to a specific day, and say how a story progressed.\n"
           if multi_day else "")
        + "- what_to_watch: 0-4 short items ONLY about things the stories say are scheduled or pending (hearings, "
        "votes, deadlines, implementation dates) -- never a repeat of what already happened. [] if nothing is "
        "scheduled.\n"
        "Respond with ONLY a JSON object, no markdown fences, in exactly this shape:\n"
        '{"story_summaries": {"S1": "...", "S2": "..."}, "duplicates": {}, "what_to_watch": ["..."]}'
    )


def _assign_story_ids(state: dict) -> None:
    n = 0
    for key in wrap_section_order(state):
        for s in state["by_section"].get(key, []):
            n += 1
            s["_sid"] = f"S{n}"


def _wrap_user_prompt(start_day, end_day, states: list) -> str:
    """The stories for the AI. Called with ONE state at a time, so a state's
    prompt -- and so its summary -- is the same whether it is run on its own or
    alongside the other state."""
    multi = start_day != end_day
    days = (end_day - start_day).days + 1
    L = [f"PERIOD: {wrap_period_text(start_day, end_day)} ({days} days, India)" if multi
         else f"DATE: {start_day:%A, %d %B %Y} (India)", ""]
    for st in states:
        _assign_story_ids(st)
        L.append(f"=== {st['label'].upper()} ({len(st['stories'])} stories) ===")
        for key in wrap_section_order(st):
            stories = st["by_section"].get(key, [])
            star = wrap_is_starred(st, key)
            if not stories and not star:
                continue
            L.append(f"[{'* ' if star else ''}{wrap_section_label(st, key)}]" + ("" if stories else " (none)"))
            for s in stories:
                outlets = ", ".join(s["outlets"][:5]) or "unknown outlet"
                L.append(f'- [{s["_sid"]}] ({len(s["outlets"])} outlet{"s" if len(s["outlets"]) != 1 else ""}: '
                         f'{outlets}) "{s["headline"]}"{_story_tags(s, multi)}')
        L.append("")
    L.append("Write the JSON wrap-up now, based only on the above.")
    return "\n".join(L)


def _polish_paragraph(text, cap: int = 4) -> str:
    if isinstance(text, list):
        text = " ".join(str(x) for x in text)
    sents = [polish_sentence(x) for x in split_sentences(str(text or "")) if x.strip()]
    return " ".join(sents[:cap])




def generate_state_narrative(client, model, start_day, end_day, state: dict, party=None) -> dict:
    """Ask Sarvam for ONE state's bullet sentences (raw dict); one corrective
    retry; raises on failure so the caller can fall back to the headlines."""
    messages = [{"role": "system", "content": _wrap_system_prompt(start_day != end_day, party, state.get("key", ""))},
                {"role": "user", "content": _wrap_user_prompt(start_day, end_day, [state])}]
    last_error = "no response"
    for attempt in range(2):
        response = _call_sarvam(client, model, messages)
        message = response.choices[0].message
        content = getattr(message, "content", None) or getattr(message, "reasoning_content", None)
        if content:
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
            parsed = extract_json_object(content)
            if parsed and isinstance(parsed.get("states"), dict):   # tolerate an older multi-state shape
                inner = parsed["states"].get(state["label"]) or next(
                    (v for k, v in parsed["states"].items() if k.lower() == state["label"].lower()), {}) or {}
                parsed = {**inner, "what_to_watch": parsed.get("what_to_watch", inner.get("what_to_watch"))}
            if parsed and isinstance(parsed.get("story_summaries"), dict):
                return parsed
            last_error = "response did not contain story_summaries"
        else:
            last_error = "empty response"
        if attempt == 0:
            messages = messages[:2] + [{"role": "user", "content":
                f"Your previous reply was unusable ({last_error}). Reply again with ONLY the JSON object in the "
                "exact shape requested."}]
    raise ValueError(last_error)


_CITE_TAIL = re.compile(r"\s*\(([^()]{2,90})\)\s*\.?\s*$")
_DATE_CITE = re.compile(r"^[^,]{2,60},\s*[A-Z][a-z]{2}\s+\d{1,2}(\s*[-\u2013]\s*[A-Za-z]{0,3}\s*\d{1,2})?$")


def _clean_point(text, outlet_names=()) -> str:
    """One tidy sentence for a bullet: citations the AI added anyway, like
    "(The Hindu)" or "(Deccan Chronicle, Oct 04)", are removed -- the sources
    are linked beside the point instead."""
    t = " ".join(str(text or "").split())
    names = [n.lower() for n in outlet_names if n]
    for _ in range(3):
        m = _CITE_TAIL.search(t)
        if not m:
            break
        inner = m.group(1)
        if any(n in inner.lower() for n in names) or _DATE_CITE.match(inner):
            t = t[:m.start()].rstrip()
        else:
            break
    t = t.rstrip(" ,;:-")
    if t and t[-1] not in ".!?":
        t += "."
    return polish_sentence(t) if t else ""


def _story_link_list(stories: list) -> tuple:
    """([{name, url}] one per outlet with an article URL, all outlet keys)."""
    links, seen, okeys = [], set(), set()
    for st_ in stories:
        items = st_.get("items") or [{"source": o, "url": st_.get("url", "")} for o in st_.get("outlets", [])]
        for it in items:
            k = _outlet_key(it.get("source", ""))
            if not k:
                continue
            okeys.add(k)
            if k not in seen and it.get("url"):
                seen.add(k)
                links.append({"name": it["source"], "url": it["url"]})
    return links, okeys


def _make_point(stories: list, text: str, key: str, multi: bool) -> dict:
    lead = stories[0]
    links, okeys = _story_link_list(stories)
    tag = lead.get("court") if key == "courts" else (lead.get("department") if key == "ministries" else None)
    if key == "ministries" and not tag:
        tag = "Other departments"
    if key == "courts" and not tag:
        tag = "Court"
    return {"text": text, "links": links, "okeys": sorted(okeys), "when": story_date_range(lead) if multi else "",
            "tag": tag, "top": False, "sids": [x.get("_sid") for x in stories], "headlines": [x["headline"] for x in stories]}


def _point_words(pt: dict) -> set:
    return _story_words(pt["text"], set())


def _same_point(a: dict, b: dict) -> bool:
    """Two bullets are the same news if they link the same article, or say
    essentially the same thing."""
    if {l["url"] for l in a["links"]} & {l["url"] for l in b["links"]}:
        return True
    wa, wb = _point_words(a), _point_words(b)
    if not wa or not wb:
        return False
    shared = wa & wb
    return len(shared) >= 4 and len(shared) / min(len(wa), len(wb)) >= 0.6


def _absorb(keep: dict, dup: dict) -> None:
    """Fold a repeated point into the one being kept: its sources join the kept point's links."""
    seen = {_outlet_key(l["name"]) for l in keep["links"]}
    for l in dup["links"]:
        if _outlet_key(l["name"]) not in seen:
            seen.add(_outlet_key(l["name"]))
            keep["links"].append(l)
    keep["okeys"] = sorted(set(keep["okeys"]) | set(dup["okeys"]))
    keep["sids"] += dup["sids"]
    keep["headlines"] += dup["headlines"]
    keep["top"] = keep["top"] or dup["top"]


def build_state_points(state: dict, summaries=None, duplicates=None, multi: bool = False) -> tuple:
    """({section_key: [point]}, notes). EXACTLY ONE bullet per story: the AI's
    sentence for it if there is one, otherwise the story's own headline. Sources
    are attached to each point. Repeats are removed -- stories the AI marked as
    the same event, and bullets that link the same article or say the same
    thing -- and their sources are folded into the point that's kept."""
    summaries = summaries if isinstance(summaries, dict) else {}
    by_sid = {x["_sid"]: x for x in state["stories"] if x.get("_sid")}
    merge_into = {}
    for b, a in (duplicates if isinstance(duplicates, dict) else {}).items():
        if b in by_sid and a in by_sid and a != b and a not in merge_into and b not in merge_into.values():
            merge_into[b] = a
    points, kept, used_headline, merged = {}, [], 0, len(merge_into)
    # Any outlet in this state's news counts as a citation to strip -- including
    # one the AI wrongly attributes to a story that outlet never carried.
    state_outlets = sorted({o for x in state["stories"] for o in x.get("outlets", [])})
    for key in wrap_section_order(state):
        for st_ in state["by_section"].get(key, []):
            sid = st_.get("_sid")
            if sid in merge_into:
                continue
            group = [st_] + [by_sid[b] for b, a in merge_into.items() if a == sid]
            text = _clean_point(summaries.get(sid), state_outlets) if summaries.get(sid) else ""
            if not text:
                text = _clean_point(st_["headline"], state_outlets)
                used_headline += 1 if summaries else 0
            pt = _make_point(group, text, key, multi)
            pt["sids"] = [f"{state['key']}:{x}" for x in pt["sids"]]   # ids are per state; keep them unique overall
            dup_of = next((k for k in kept if _same_point(k, pt)), None)
            if dup_of:
                _absorb(dup_of, pt)
                merged += 1
                continue
            kept.append(pt)
            points.setdefault(key, []).append(pt)
    return points, {"used_headline": used_headline, "merged": merged}


def _own_score(pt: dict, state_key: str) -> int:
    """How much a point is about this state: its places/people named, minus the
    other state's (so "Hyderabad metro fares ... AP commuters affected" counts as
    a Telangana story, not an Andhra Pradesh one)."""
    text = " ".join([pt["text"]] + pt["headlines"])
    own = _rx(_WRAP_OWN_PLACES[state_key])
    other = _rx([f for k, frags in _WRAP_OWN_PLACES.items() if k != state_key for f in frags])
    return (len({m.group(0).lower() for m in own.finditer(text)})
            - len({m.group(0).lower() for m in other.finditer(text)}))


def dedupe_across_states(states: list, points_by_label: dict) -> int:
    """A story that turns up in both states' wrap-ups is kept once -- in the
    state it is more about (by its place and people names), else the first."""
    removed = 0
    for j in range(1, len(states)):
        for i in range(j):
            pi_all, pj_all = points_by_label[states[i]["label"]], points_by_label[states[j]["label"]]
            for kj in list(pj_all):
                for pj in list(pj_all[kj]):
                    hit = next(((ki, pi) for ki in pi_all for pi in pi_all[ki] if _same_point(pi, pj)), None)
                    if not hit:
                        continue
                    ki, pi = hit
                    if _own_score(pj, states[j]["key"]) > _own_score(pi, states[i]["key"]):
                        pi_all[ki].remove(pi)
                        _absorb(pj, pi)
                    else:
                        pj_all[kj].remove(pj)
                        _absorb(pi, pj)
                    removed += 1
            for d in (pi_all, pj_all):
                for k in [k for k, v in d.items() if not v]:
                    del d[k]
    return removed


def _clean_watch(items, state: dict, points: dict) -> list:
    """What-to-watch items: upcoming things only -- anything that just restates
    a bullet already in the wrap-up is dropped."""
    names = [o for x in state["stories"] for o in x.get("outlets", [])]
    if isinstance(items, str):
        items = [x for x in split_sentences(items) if x.strip()]
    out, all_points = [], [pt for pts in points.values() for pt in pts]
    for it in (items or [])[:6]:
        t = _clean_point(it, names)
        probe = {"text": t, "links": []}
        if t and not any(_same_point(probe, pt) for pt in all_points) and t not in out:
            out.append(t)
    return out[:4]


def _narrative_key(model, start_day, end_day, state: dict) -> str:
    sig = [model, str(start_day), str(end_day), state["label"], state.get("party") or "",
           [(s.get("_sid"), s["headline"], s["outlets"], s["section"], s.get("department"), s.get("court"),
             story_date_range(s)) for s in state["stories"]]]
    return hashlib.sha1(json.dumps(sig, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def gather_daily_wrap(states_choice: str = "both", day=None, client=None, model: str = DEFAULT_MODEL,
                      stories_per_state=None, end_day=None, fresh: bool = False, party=None) -> dict:
    """Gather and write the structured news wrap-up for one day (day) or an
    inclusive date range (day .. end_day).

    Each state is gathered, grouped, classified and SUMMARISED ON ITS OWN, so
    a state's section comes out the same whether it is run alone or together
    with the other state. Within a session the same state and dates reuse the
    same fetched news (for WRAP_CACHE_TTL_TODAY / _PAST seconds) and identical
    stories reuse the same summary; fresh=True bypasses both.

    Returns: start_day, end_day, days, states (each: label, stories,
    by_section, glance, used_template), the narrative, status, used_template.
    Raises ValueError for an unusable state or date range."""
    keys = resolve_wrap_states(states_choice)
    pinfo = resolve_wrap_party(party)
    start_day = day or ist_today()
    end_day = end_day or start_day
    days = validate_wrap_range(start_day, end_day)
    multi = days > 1
    use_cache = WRAP_CACHE_ENABLED and not fresh
    ttl = WRAP_CACHE_TTL_TODAY if end_day >= ist_today() else WRAP_CACHE_TTL_PAST
    status, states = {}, []
    for key in keys:
        label = WRAP_STATES[key]["label"]
        ckey = (key, str(start_day), str(end_day), pinfo["name"] if pinfo else "")
        hit = _cache_get_entry(_WRAP_ARTICLE_CACHE, ckey) if use_cache else None
        if hit:
            print(f"  - {label}: reusing news fetched at {hit['at']} IST...")
            articles, st_status = hit["articles"], hit["status"] + f" -- reused from the search at {hit['at']} IST"
        else:
            print(f"  - {label}: {pinfo['short'] + ' ' if pinfo else ''}news for {wrap_period_text(start_day, end_day)}...")
            articles, st_status = gather_state_news(key, start_day, end_day, party=pinfo)
            if WRAP_CACHE_ENABLED:
                _WRAP_ARTICLE_CACHE[ckey] = {"articles": articles, "status": st_status, "until": time.time() + ttl,
                                             "at": f"{utc_now() + IST_OFFSET:%H:%M}"}
        status[f"{label} news"] = st_status
        ignore = {w for w in re.findall(r"[a-z]+", label.lower())}
        candidates = build_top_stories({"headlines": articles, "social_news": []}, ignore_words=list(ignore),
                                       max_stories=WRAP_CANDIDATE_STORIES,
                                       window_days=WRAP_STORY_GAP_DAYS_RANGE if multi else 1)
        for s in candidates:
            s.update(classify_cluster(s))
        by_section = select_wrap_stories(candidates, multi, party_mode=bool(pinfo))
        probe = {"party": pinfo["short"] if pinfo else None}
        order = wrap_section_order(probe)
        starred = [k for k in order if wrap_is_starred(probe, k)]
        stories = [s for k in order for s in by_section.get(k, [])]
        n_hl = sum(len(by_section.get(k, [])) for k in starred)
        status[f"{label} sections"] = (f"{n_hl} highlighted (" + ", ".join(
            f"{wrap_section_label(probe, k)} {len(by_section.get(k, []))}" for k in starred)
            + f"), {len(stories) - n_hl} other")
        if pinfo:
            status[f"{label} scope"] = (
                f"news naming {pinfo['short']} or its leaders"
                + (f", plus the decisions of the {label} government, which {pinfo['short']} leads"
                   if key in pinfo["leads"] else ""))
        state = {"key": key, "label": label, "stories": stories, "by_section": by_section,
                 "glance": build_glance({"headlines": articles}, stories), "used_template": False,
                 "party": pinfo["short"] if pinfo else None}
        _assign_story_ids(state)
        states.append(state)

    narr_states, notes = {}, {}
    for st in states:
        label = st["label"]
        if not st["stories"]:
            narr_states[label] = {"points": {}, "what_to_watch": []}
            st["used_template"] = True
            status[f"{label} summary"] = "nothing to summarise (no stories found)"
            continue
        raw, how = None, ""
        if client is not None:
            nkey = _narrative_key(model, start_day, end_day, st)
            nhit = _cache_get_entry(_WRAP_NARRATIVE_CACHE, nkey) if use_cache else None
            if nhit:
                raw, how = nhit["raw"], f"reused the Sarvam summary written at {nhit['at']} IST (identical stories)"
            else:
                print(f"  - Asking Sarvam AI to write the {label} wrap-up...")
                try:
                    raw = generate_state_narrative(client, model, start_day, end_day, st, pinfo)
                    how = "written by Sarvam AI"
                    if WRAP_CACHE_ENABLED:
                        _WRAP_NARRATIVE_CACHE[nkey] = {"raw": raw, "until": time.time() + WRAP_NARRATIVE_TTL,
                                                       "at": f"{utc_now() + IST_OFFSET:%H:%M}"}
                except Exception as e:
                    print(f"    Warning: Sarvam call failed for {label} ({_short_error(e)}). Using the headlines instead.")
                    how = f"Sarvam failed ({_short_error(e)}); headlines used"
        if raw is None:
            st["used_template"] = True
            pts, info = build_state_points(st, None, None, multi)
            narr_states[label] = {"points": pts, "what_to_watch": []}
            how = how or "headlines used (Sarvam not available)"
        else:
            pts, info = build_state_points(st, raw.get("story_summaries"), raw.get("duplicates"), multi)
            narr_states[label] = {"points": pts, "what_to_watch": _clean_watch(raw.get("what_to_watch"), st, pts)}
        extra = []
        if info["used_headline"]:
            extra.append(f"the AI skipped {info['used_headline']} stor{'y' if info['used_headline'] == 1 else 'ies'}, "
                         "so the headline was used")
        if info["merged"]:
            extra.append(f"{info['merged']} repeated point(s) merged")
        status[f"{label} summary"] = how + ("; " + "; ".join(extra) if extra else "")

    if len(states) > 1:
        moved = dedupe_across_states(states, {l: n["points"] for l, n in narr_states.items()})
        if moved:
            status["Across states"] = f"{moved} story(ies) reported for both states kept once, in the state they're more about"

    # Each state's most widely reported story is starred where it sits (not repeated in a banner). Per state,
    # so a state's section reads the same whether it is run alone or alongside the other state.
    for n in narr_states.values():
        state_points = [pt for pts in n["points"].values() for pt in pts]
        top = max(state_points, key=lambda pt: len(pt["okeys"]), default=None)
        if top and len(top["okeys"]) >= 2:
            top["top"] = True
    all_points = [pt for n in narr_states.values() for pts in n["points"].values() for pt in pts]
    # What to watch, checked once against the WHOLE wrap-up: an item that restates any point (in either state)
    # or an item already listed is dropped.
    watch, kept_watch = [], []
    for label, n in narr_states.items():
        mine = []
        for w_ in n["what_to_watch"]:
            probe = {"text": w_, "links": []}
            if any(_same_point(probe, pt) for pt in all_points) or any(_same_point(probe, k) for k in kept_watch):
                continue
            kept_watch.append(probe)
            mine.append(w_)
            watch.append(f"{label}: {w_}" if len(states) > 1 else w_)
        n["what_to_watch"] = mine
    used_template = all(st["used_template"] for st in states)
    return {"day": start_day, "start_day": start_day, "end_day": end_day, "days": days, "states": states,
            "narrative": {"states": narr_states, "what_to_watch": watch},
            "status": status, "used_template": used_template,
            "party": {"name": pinfo["name"], "short": pinfo["short"], "leads": pinfo["leads"]} if pinfo else None}


def wrap_title(wrap: dict) -> str:
    labels = " & ".join(st["label"] for st in wrap["states"])
    start, end = wrap.get("start_day", wrap["day"]), wrap.get("end_day", wrap["day"])
    who = f"{wrap['party']['short']} " if wrap.get("party") else ""
    if start == end:
        return f"{who}Daily News Wrap-up: {labels} \u2014 {start:%A, %d %B %Y}"
    return (f"{who}News Wrap-up: {labels} \u2014 {wrap_period_text(start, end)} "
            f"({wrap.get('days', (end - start).days + 1)} days)")


def wrap_headline_label(wrap: dict) -> str:
    return "Headline of the Day" if wrap.get("days", 1) == 1 else "Top Headline of the Period"




WRAP_EMPTY_HIGHLIGHT = "Nothing reported in this period."


def wrap_state_narrative(wrap: dict, state: dict) -> dict:
    return wrap["narrative"]["states"].get(state["label"]) or {"points": {}, "what_to_watch": []}


def wrap_point_groups(points: list, key: str) -> list:
    """[(group_label or None, [points])]: Ministries grouped by department and
    Courts by court, in first-seen order; other sections as one group."""
    if key not in ("ministries", "courts"):
        return [(None, points)]
    groups = {}
    for pt in points:
        groups.setdefault(pt["tag"], []).append(pt)
    return list(groups.items())


def wrap_sections_for_display(state: dict, narr: dict) -> tuple:
    """([(key, label, icon_or_None, points)] highlighted, [(key, label, points)] other)."""
    pts = narr["points"]
    icons = {k: icon for k, _, icon in WRAP_HIGHLIGHTS}
    icons["politics"] = WRAP_PARTY_POLITICS_ICON
    starred, other = [], []
    for key in wrap_section_order(state):
        if wrap_is_starred(state, key):
            starred.append((key, wrap_section_label(state, key), icons.get(key), pts.get(key, [])))
        elif pts.get(key):
            other.append((key, wrap_section_label(state, key), pts[key]))
    return starred, other


def _md_link_text(t: str) -> str:
    return str(t).replace("[", "(").replace("]", ")")


def _md_url(u: str) -> str:
    return str(u).replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def point_sources_md(pt: dict, max_links: int = 3) -> str:
    shown = pt["links"][:max_links]
    more = max(0, len(pt["okeys"]) - len(shown))
    out = " \u00b7 ".join(f"[{_md_link_text(l['name'])}]({_md_url(l['url'])})" for l in shown)
    if more:
        out += f" +{more} more"
    return out


def point_markdown(pt: dict) -> str:
    """'⭐ Point. — [The Hindu](url) · [Sakshi](url) +2 more · Oct 07 – Oct 11'"""
    src = point_sources_md(pt)
    return (("\u2b50 " if pt["top"] else "") + pt["text"] + (f" \u2014 {src}" if src else "")
            + (f" \u00b7 _{pt['when']}_" if pt.get("when") else ""))


WRAP_TOP_LEGEND = "\u2b50 marks each state's most widely reported story."


def print_wrap(wrap: dict) -> None:
    bar, rule = "=" * 70, "-" * 70
    n = wrap["narrative"]
    print(f"\n{bar}\n{wrap_title(wrap).upper()}\n{bar}")
    if wrap["used_template"]:
        print(_wrap("(Sarvam AI wasn't available, so each point is the story's own headline.)"))
    if any(pt["top"] for nn in n["states"].values() for pts in nn["points"].values() for pt in pts):
        print(_wrap(WRAP_TOP_LEGEND))

    def bullet(pt, indent="  "):
        print(_wrap(("\u2b50 " if pt["top"] else "") + pt["text"], 70, indent + "  ").replace(indent + "  ", indent + "\u2022 ", 1))
        if pt.get("when"):
            print(f"{indent}    {pt['when']}")
        shown = pt["links"][:3]
        for l in shown:
            print(f"{indent}    {l['name']}: {l['url']}")
        more = len(pt["okeys"]) - len(shown)
        if more > 0:
            print(f"{indent}    (+{more} more outlet{'s' if more != 1 else ''})")

    for st in wrap["states"]:
        sn = wrap_state_narrative(wrap, st)
        print(f"\n\n{'#' * 70}\n  {st['label'].upper()}\n{'#' * 70}")
        print(_wrap(glance_text(st["glance"])))
        if not st["stories"]:
            who = f"{st['party']} " if st.get("party") else ""
            print(_wrap(f"No {who}news found for {st['label']} in this period."))
            continue
        starred, other = wrap_sections_for_display(st, sn)
        for key, label, _icon, pts in starred:
            print(f"\n\u2605 {label.upper()}\n{rule}")
            if not pts:
                print("  " + WRAP_EMPTY_HIGHLIGHT)
            for group, gpts in wrap_point_groups(pts, key):
                if group:
                    print(f"  {group}")
                for pt in gpts:
                    bullet(pt, "    " if group else "  ")
        if other:
            print(f"\nOTHER NEWS\n{rule}")
            for key, label, pts in other:
                print(f"  {label}")
                for pt in pts:
                    bullet(pt, "    ")
    if n.get("what_to_watch"):
        print(f"\nWHAT TO WATCH\n{rule}")
        for w in n["what_to_watch"]:
            print(_wrap(w, 70, "    ").replace("    ", "  \u2022 ", 1))
    print(f"\nSOURCES CHECKED\n{rule}")
    for label, st in wrap["status"].items():
        print(_wrap(f"{label}: {st}"))
    print()


def wrap_markdown(wrap: dict) -> str:
    n = wrap["narrative"]
    L = [f"# \U0001F5DE\ufe0f {wrap_title(wrap)}", "", f"_Generated {utc_now() + IST_OFFSET:%Y-%m-%d %H:%M} IST_", ""]
    if wrap["used_template"]:
        L += ["> Sarvam AI wasn't available, so each point is the story's own headline.", ""]
    if any(pt["top"] for nn in n["states"].values() for pts in nn["points"].values() for pt in pts):
        L += [f"_{WRAP_TOP_LEGEND}_", ""]
    for st in wrap["states"]:
        sn = wrap_state_narrative(wrap, st)
        L += ["---", "", f"## {st['label']}", "", f"_{glance_text(st['glance'])}_", ""]
        if not st["stories"]:
            who = f"{st['party']} " if st.get("party") else ""
            L += [f"No {who}news found for {st['label']} in this period.", ""]
            continue
        starred, other = wrap_sections_for_display(st, sn)
        for key, label, icon, pts in starred:
            L += [f"### {icon} {label}", ""]
            if not pts:
                L += [f"_{WRAP_EMPTY_HIGHLIGHT}_", ""]
                continue
            for group, gpts in wrap_point_groups(pts, key):
                if group:
                    L.append(f"- **{group}**")
                L += [("  - " if group else "- ") + point_markdown(pt) for pt in gpts]
            L.append("")
        if other:
            L += ["### \U0001F4F0 Other news", ""]
            for key, label, pts in other:
                L.append(f"- **{label}**")
                L += ["  - " + point_markdown(pt) for pt in pts]
            L.append("")
    if n.get("what_to_watch"):
        L += ["---", "", "## \U0001F440 What to Watch", ""] + [f"- {w}" for w in n["what_to_watch"]] + [""]
    L += ["---", "", "## Sources Checked", ""] + [f"- **{k}:** {v}" for k, v in wrap["status"].items()] + [""]
    return "\n".join(L)


def _wrap_filename(wrap: dict, ext: str) -> str:
    os.makedirs("reports", exist_ok=True)
    states = "_".join(st["key"].replace(" ", "-") for st in wrap["states"])
    start, end = wrap.get("start_day", wrap["day"]), wrap.get("end_day", wrap["day"])
    when = f"{start:%Y%m%d}" if start == end else f"{start:%Y%m%d}-{end:%Y%m%d}"
    prefix = "daily_wrap" if start == end else "news_wrap"
    if wrap.get("party"):
        prefix = re.sub(r"[^a-z0-9]+", "-", wrap["party"]["short"].lower()).strip("-") + "_" + prefix
    return os.path.join("reports", f"{prefix}_{states}_{when}_{datetime.now():%H%M%S}.{ext}")


def save_wrap_markdown(wrap: dict) -> str:
    path = _wrap_filename(wrap, "md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(wrap_markdown(wrap))
    return path




_WRAP_PDF_COLORS = {"politics": "#9a4b00", "government": "#1f3a5f", "policy": "#5b3a8c", "ministries": "#1d6b5a",
                    "courts": "#8a2a2a"}


def save_wrap_pdf(wrap: dict) -> str:
    if SimpleDocTemplate is None:
        raise RuntimeError("reportlab isn't installed. Run:  pip install reportlab")
    path = _wrap_filename(wrap, "pdf")
    styles = _pdf_styles()
    band_style = ParagraphStyle("WrapBand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11,
                                leading=14, textColor=colors.white)
    bullet_style = ParagraphStyle("WrapBullet", parent=styles["BodyText"], fontSize=9.5, leading=13, leftIndent=14,
                                  bulletIndent=4, spaceAfter=3)
    sub_bullet = ParagraphStyle("WrapSubBullet", parent=bullet_style, leftIndent=28, bulletIndent=18)
    group_style = ParagraphStyle("WrapGroup", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9.5,
                                 leading=13, leftIndent=4, spaceBefore=3)
    width = 6.5 * inch

    def band(text, color):
        t = Table([[Paragraph(xml_escape(text), band_style)]], colWidths=[width])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color)),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return [Spacer(1, 8), t, Spacer(1, 4)]

    def point_para(pt, style):
        shown = pt["links"][:3]
        more = len(pt["okeys"]) - len(shown)
        src = " \u00b7 ".join(_pdf_link(l["url"], l["name"]) for l in shown) + (f" +{more} more" if more > 0 else "")
        text = ("<b>[Top story]</b> " if pt["top"] else "") + xml_escape(pt["text"])
        tail = (f" <font color='#666666'>\u2014</font> {src}" if src else "") + (
            f" <font color='#666666'>\u00b7 {xml_escape(pt['when'])}</font>" if pt.get("when") else "")
        return Paragraph(text + tail, style, bulletText="\u2022")

    n = wrap["narrative"]
    S = [Paragraph(xml_escape(wrap_title(wrap)), styles["ReportTitle"]),
         Paragraph(f"Generated {utc_now() + IST_OFFSET:%Y-%m-%d %H:%M} IST", styles["Meta"])]
    if wrap["used_template"]:
        S.append(Paragraph("<i>Sarvam AI wasn't available, so each point is the story's own headline.</i>",
                           styles["Note"]))
    if any(pt["top"] for nn in n["states"].values() for pts in nn["points"].values() for pt in pts):
        S.append(Paragraph("<i>[Top story] marks each state's most widely reported story. Outlet names are links to "
                           "the articles.</i>", styles["ItemMeta"]))
    for st in wrap["states"]:
        sn = wrap_state_narrative(wrap, st)
        S += [Spacer(1, 10), HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#333333")),
              Paragraph(xml_escape(st["label"]), styles["Section"]),
              Paragraph(xml_escape(glance_text(st["glance"])), styles["ItemMeta"])]
        if not st["stories"]:
            who = f"{st['party']} " if st.get("party") else ""
            S.append(Paragraph(xml_escape(f"No {who}news found for {st['label']} in this period."), styles["Empty"]))
            continue
        starred, other = wrap_sections_for_display(st, sn)
        for key, label, _icon, pts in starred:
            S += band(label, _WRAP_PDF_COLORS.get(key, "#333333"))
            if not pts:
                S.append(Paragraph(WRAP_EMPTY_HIGHLIGHT, styles["Empty"]))
            for group, gpts in wrap_point_groups(pts, key):
                if group:
                    S.append(Paragraph(xml_escape(group), group_style))
                S += [point_para(pt, sub_bullet if group else bullet_style) for pt in gpts]
        if other:
            S.append(Paragraph("Other news", styles["SubSection"]))
            for key, label, pts in other:
                S.append(Paragraph(xml_escape(label), group_style))
                S += [point_para(pt, sub_bullet) for pt in pts]
    if n.get("what_to_watch"):
        S.append(Paragraph("What to Watch", styles["Section"]))
        S += [Paragraph(xml_escape(w), bullet_style, bulletText="\u2022") for w in n["what_to_watch"]]
    S.append(Paragraph("Sources Checked", styles["Section"]))
    for k, v in wrap["status"].items():
        S.append(Paragraph(f"<b>{xml_escape(k)}:</b> {xml_escape(v)}", styles["ItemMeta"]))
    SimpleDocTemplate(path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                      title=wrap_title(wrap)).build(S)
    return path


# --------------------------------------------------------------------------
# Daily news carousel (editorial DRAFT)
# --------------------------------------------------------------------------
# A ten-slide daily news carousel for a digital briefing (sports has its own slide), following the
# editorial instructions: national/state, world, business, tech/science/health/
# environment/sports and public-interest news; prioritised by significance;
# every story with source URLs and a verification status; no event repeated
# across slides; nothing invented; and DRAFT ONLY -- nothing here is published
# or represented as verified until an editor has checked and approved it.
#
# The sources (Google News, GDELT) give only headlines, outlets, links and
# dates, so the text of each shortlisted article is fetched from its direct
# link and given to the AI as its ONLY material; figures the AI writes that
# aren't in that material are flagged for the editor.

CAROUSEL_CATEGORIES = [
    # key, label, Google News query, GDELT query
    ("national", "National politics",
     '"India" (government OR parliament OR minister OR "Supreme Court" OR election OR Centre)',
     '(parliament OR "Supreme Court" OR minister OR election) sourcecountry:IN'),
    ("world", "World affairs",
     '("United Nations" OR summit OR war OR ceasefire OR "White House" OR Kremlin OR Beijing OR "European Union")',
     '("United Nations" OR summit OR ceasefire OR "White House" OR Kremlin)'),
    ("business", "Business & economy",
     '(Sensex OR Nifty OR RBI OR economy OR inflation OR GDP OR rupee OR "stock market" OR earnings)',
     '(Sensex OR Nifty OR RBI OR inflation OR GDP OR rupee) sourcecountry:IN'),
    ("tech", "Technology, AI & science",
     '("artificial intelligence" OR technology OR ISRO OR science OR startup OR semiconductor)',
     '("artificial intelligence" OR ISRO OR semiconductor OR startup) sourcecountry:IN'),
    ("health_edu", "Health & education",
     '(health OR hospital OR disease OR vaccine OR education OR exam OR university OR students)',
     '(hospital OR vaccine OR disease OR university OR exam) sourcecountry:IN'),
    ("environment", "Environment & climate",
     '(climate OR environment OR pollution OR cyclone OR flood OR heatwave OR wildlife OR monsoon)',
     '(climate OR pollution OR cyclone OR flood OR heatwave) sourcecountry:IN'),
    ("sports", "Sports",
     '(cricket OR football OR hockey OR Olympics OR "Team India" OR tennis OR badminton OR chess)',
     '(cricket OR football OR hockey OR Olympics OR badminton) sourcecountry:IN'),
]
CAROUSEL_STATE_LABEL = "State developments"
# Order used when the same event turns up in two categories: a topic beats "state", so an AP/Telangana business
# story stays on the Business slide (tagged with its state) rather than the State slide.
CAROUSEL_CATEGORY_ORDER = ["national", "world", "business", "tech", "health_edu", "environment", "sports", "state"]
CAROUSEL_CATEGORY_LABELS = {k: l for k, l, _, _ in CAROUSEL_CATEGORIES}
CAROUSEL_CATEGORY_LABELS["state"] = CAROUSEL_STATE_LABEL

CAROUSEL_SLIDES = [
    {"n": 1, "key": "cover", "title": "Cover and date"},
    {"n": 2, "key": "top", "title": "Top story", "max": 1},
    {"n": 3, "key": "national", "title": "National developments", "cats": ["national"], "max": 3},
    {"n": 4, "key": "state", "title": "State developments", "cats": ["state"], "max": 4},
    {"n": 5, "key": "world", "title": "World affairs", "cats": ["world"], "max": 3},
    {"n": 6, "key": "business", "title": "Business and economy", "cats": ["business"], "max": 3},
    {"n": 7, "key": "more", "title": "Technology, science, health and environment",
     "cats": ["tech", "health_edu", "environment"], "max": 3},
    {"n": 8, "key": "sports", "title": "Sports", "cats": ["sports"], "max": 3},
    {"n": 9, "key": "briefs", "title": "Additional headlines in brief", "max": 5},
    {"n": 10, "key": "takeaway", "title": "Daily takeaway and follow prompt"},
]
CAROUSEL_STORY_SLIDES = ["national", "state", "world", "business", "more", "sports"]

# AP/Telangana-focused search for each topic: these keywords AND the chosen states' names.
CAROUSEL_STATE_TOPIC_TERMS = {
    "national": '(Centre OR "Union government" OR Parliament OR "Supreme Court" OR "Prime Minister" OR "Union Minister")',
    "world": '(abroad OR overseas OR NRI OR diaspora OR Gulf OR "United States" OR visa OR embassy)',
    "business": '(investment OR industry OR company OR jobs OR MoU OR startup OR economy OR budget OR revenue)',
    "tech": '(technology OR "artificial intelligence" OR startup OR "data centre" OR science OR research OR ISRO)',
    "health_edu": '(hospital OR health OR disease OR doctors OR school OR university OR students OR exam)',
    "environment": '(climate OR pollution OR rain OR flood OR cyclone OR heatwave OR forest OR wildlife)',
    "sports": '(cricket OR football OR badminton OR hockey OR athlete OR medal OR tournament OR chess)',
}
_CAROUSEL_STATE_NAMES = {"andhra pradesh": '("Andhra Pradesh" OR Visakhapatnam OR Vijayawada OR Amaravati OR Tirupati)',
                         "telangana": '("Telangana" OR Hyderabad OR Warangal)'}

# Topic of a state story by its headline -- a Hyderabad AI centre belongs on the Tech slide, not the State slide.
_CAROUSEL_TOPIC_PATTERNS = [
    ("business", _rx([r"invest", r"industr", r"compan(y|ies)", r"jobs\b", r"startup", r"mous?\b", r"econom", r"revenue",
                      r"budget", r"gst\b", r"exports?\b", r"market", r"shares?\b", r"stocks?\b", r"ipo\b", r"banks?\b",
                      r"rbi\b", r"sensex", r"nifty", r"rupee", r"inflation", r"gdp\b", r"manufactur", r"factory"])),
    ("tech", _rx([r"ai\b", r"artificial intelligence", r"technolog", r"tech\b", r"software", r"it (sector|company|companies|park|firm)",
                  r"data cent(er|re)", r"semiconductor", r"isro", r"satellite", r"science", r"scientist", r"research",
                  r"innovation", r"digital", r"robot", r"quantum", r"5g\b", r"electronics", r"space\b"])),
    ("health_edu", _rx([r"hospital", r"health", r"doctors?\b", r"medical", r"disease", r"dengue", r"fever", r"vaccin",
                        r"patients?\b", r"aarogyasri", r"schools?\b", r"students?\b", r"universit", r"college", r"exams?\b",
                        r"education", r"teachers?\b", r"admission", r"neet\b", r"eamcet", r"eapcet"])),
    ("environment", _rx([r"climate", r"pollution", r"rain", r"flood", r"cyclone", r"heat ?wave", r"drought", r"forest",
                         r"wildlife", r"tigers?\b", r"environment", r"monsoon", r"imd\b", r"weather", r"waterlog", r"emission"])),
    ("sports", _rx([r"cricket", r"football", r"hockey", r"badminton", r"tennis", r"chess", r"olympi", r"athlet", r"medals?\b",
                    r"tournament", r"championship", r"ipl\b", r"odi\b", r"t20", r"test match", r"kabaddi", r"wrestl",
                    r"boxing", r"sports?\b", r"stadium", r"shuttler", r"cricketer", r"grandmaster"])),
    ("world", _rx([r"abroad", r"overseas", r"nri\b", r"diaspora", r"united states", r"america", r"gulf", r"saudi", r"riyadh",
                   r"dubai", r"uae\b", r"london", r"canada", r"australia", r"russia", r"ukraine", r"china", r"israel",
                   r"gaza", r"embassy"])),
]


def carousel_topic(text: str):
    """The topic slide a headline belongs on (business, tech, ...), or None."""
    best, best_hits = None, 0
    for key, pat in _CAROUSEL_TOPIC_PATTERNS:
        h = _hits(pat, text or "")
        if h > best_hits:
            best, best_hits = key, h
    return best


def related_states(text: str, state_keys: list) -> list:
    """Which of the chosen states a story is about, by its place, people and party names."""
    return [WRAP_STATES[k]["label"] for k in state_keys if _rx(_WRAP_OWN_PLACES[k]).search(text or "")]


CAROUSEL_CANDIDATES_PER_CATEGORY = 4
CAROUSEL_STATE_SHORTLIST_EXTRA = 2   # AP/Telangana stories always added to each topic's shortlist
CAROUSEL_BRIEF_POOL = 8
CAROUSEL_SUMMARY_WORDS = (40, 70)
CAROUSEL_HEADLINE_MAX_WORDS = 12
CAROUSEL_DRAFT_NOTICE = ("DRAFT -- NOT FOR PUBLICATION. Nothing in this carousel has been verified or approved. Every "
                         "story must pass editorial checks and human approval before it is published or scheduled.")
CAROUSEL_VISUAL_RULES = ("Use only an image you are licensed to use: an agency/wire subscription photo, an official "
                         "handout, or your own graphic. Credit the rights holder exactly as the licence requires. Do "
                         "not copy photos from the linked articles. Image credit: to be completed by the editor.")
CAROUSEL_CHECKLIST = [
    "Each story's event date confirmed (not just the publication date)",
    "Every single-source, developing, disputed or flagged story verified independently, or removed",
    "Every figure flagged as 'not found in the source material' checked against the original source",
    "Allegations attributed to whoever made them; facts separated from analysis",
    "No underlying event repeated across slides",
    "The Andhra Pradesh / Telangana angle checked in every section (stories added by the coverage rule reviewed)",
    "Every image licensed, and credited as the licence requires",
    "Caption, hook and hashtags checked for accuracy and neutrality",
    "Final approval by: ____________________   Date/time: ____________",
]

# Established news organisations (and primary sources) -- recognised by name or web domain.
_CAROUSEL_PRIMARY = _rx([r"pib\b", r"press information bureau", r"[a-z0-9-]+\.gov\.in", r"[a-z0-9-]+\.nic\.in",
                         r"rbi\.org\.in", r"un\.org", r"who\.int", r"[a-z0-9-]+\.gov\b"])
_CAROUSEL_ESTABLISHED = _rx([
    r"the hindu\b", r"thehindu", r"indian express", r"indianexpress", r"new indian express", r"newindianexpress",
    r"hindustan times", r"hindustantimes", r"times of india", r"timesofindia", r"ndtv", r"pti\b", r"press trust",
    r"reuters", r"associated press", r"apnews", r"bbc\b", r"livemint", r"mint\b", r"economic times", r"economictimes",
    r"business standard", r"business-standard", r"financial express", r"financialexpress", r"deccan herald",
    r"deccanherald", r"deccan chronicle", r"deccanchronicle", r"theprint", r"the print\b", r"scroll\b", r"india today",
    r"indiatoday", r"telangana today", r"telanganatoday", r"hans india", r"thehansindia", r"moneycontrol",
    r"al jazeera", r"aljazeera", r"the guardian", r"theguardian", r"bloomberg", r"cnbc", r"espncricinfo",
    r"sportstar", r"news minute", r"thenewsminute", r"frontline", r"the wire\b", r"thewire", r"dd news", r"ddnews",
    r"firstpost", r"wion", r"ani\b", r"the federal\b", r"thefederal", r"sakshi", r"eenadu", r"the tribune",
    r"tribuneindia", r"telegraph india", r"telegraphindia", r"outlook india", r"outlookindia", r"down to earth",
    r"downtoearth", r"the quint", r"thequint",
])
CAROUSEL_HASHTAG_ALLOW = {"news", "india", "dailynews", "dailybriefing", "newsupdate", "newsroundup", "telangana",
                          "andhrapradesh", "hyderabad", "world", "worldnews", "business", "economy", "technology",
                          "tech", "ai", "science", "health", "education", "climate", "environment", "sports",
                          "cricket", "politics"}


def outlet_kind(name: str) -> str:
    """'primary' (government/official source), 'established' (recognised news organisation) or 'other'."""
    n = (name or "").lower()
    if _CAROUSEL_PRIMARY.search(n):
        return "primary"
    return "established" if _CAROUSEL_ESTABLISHED.search(n) else "other"


def _carousel_state_queries(state_keys: list) -> list:
    out = []
    for sk in state_keys:
        terms = WRAP_STATES[sk]["query_sets"][0]
        out.append((sk, WRAP_STATES[sk]["label"], build_news_query(terms), build_news_query(terms, india_only=True)))
    return out


CAROUSEL_SEARCH_WORKERS = 8
CAROUSEL_SEARCH_DEADLINE = 25    # seconds for ALL searches; any still running after this are skipped
CAROUSEL_GDELT_CATEGORIES = ("national", "world")   # GDELT is slow (one request per ~5s): only where it adds most
CAROUSEL_GDELT_DEADLINE = 12                        # seconds; GDELT results arriving later are skipped


def gather_carousel_news(day, state_keys: list) -> tuple:
    """({category: [articles]}, status) for one IST calendar day. All Google
    News searches run AT THE SAME TIME: one per category, one AP/Telangana search
    per topic, and the chosen states' general news. GDELT (which only allows a
    request every few seconds) runs in the background for a few categories and
    is cut off at CAROUSEL_GDELT_DEADLINE, so it can never hold the rest up."""
    from concurrent.futures import ThreadPoolExecutor
    started = time.monotonic()
    start, end = ist_day_window(day)
    window = f"after:{(day - timedelta(days=1)):%Y-%m-%d} before:{(day + timedelta(days=1)):%Y-%m-%d}"
    jobs = [(k, l, gq, dq, None) for k, l, gq, dq in CAROUSEL_CATEGORIES]
    jobs += [("state", label, gq, None, sk) for sk, label, gq, _dq in _carousel_state_queries(state_keys)]
    if state_keys:
        names = "(" + " OR ".join(_CAROUSEL_STATE_NAMES[k][1:-1] for k in state_keys) + ")"
        # Their results are placed by what each headline is about, NOT by which search found them: Google
        # matches words anywhere in an article, so the "world" search can return a story that isn't world news.
        jobs += [("state_topic", f"{CAROUSEL_CATEGORY_LABELS[k]} (AP/Telangana)", f"{terms} {names}", None, None)
                 for k, terms in CAROUSEL_STATE_TOPIC_TERMS.items()]

    gdelt_jobs = [j for j in jobs if j[3] and j[0] in CAROUSEL_GDELT_CATEGORIES]
    gdelt_out = {}

    def run_gdelt():
        for _key, label, _gq, dq, _sk in gdelt_jobs:
            try:
                gdelt_out[label] = (_gdelt_throttled(dq, 75, start, end), "")
            except Exception as e:
                gdelt_out[label] = ([], f"GDELT ({_short_error(e)})")

    worker = threading.Thread(target=run_gdelt, daemon=True)
    worker.start()

    def google(job):
        try:
            return get_google_news_fallback(f"{job[2]} {window}", 100, start, end), ""
        except Exception as e:
            return [], f"Google News ({_short_error(e)})"

    from concurrent.futures import wait as _wait
    pool = ThreadPoolExecutor(max_workers=CAROUSEL_SEARCH_WORKERS)
    futures = [pool.submit(google, j) for j in jobs]
    _wait(futures, timeout=CAROUSEL_SEARCH_DEADLINE)
    google_out = [f.result() if f.done() else ([], "Google News (timed out -- skipped)") for f in futures]
    pool.shutdown(wait=False, cancel_futures=True)
    worker.join(timeout=max(0.0, CAROUSEL_GDELT_DEADLINE - (time.monotonic() - started)))
    gdelt_now = dict(gdelt_out)

    by_cat, status = {}, {}
    for (key, label, _gq, dq, state_key), (got, fail) in zip(jobs, google_out):
        fails = [fail] if fail else []
        if (key, label, _gq, dq, state_key) in gdelt_jobs:
            g_got, g_fail = gdelt_now.get(label, ([], "GDELT skipped (too slow today)"))
            got = got + g_got
            if g_fail:
                fails.append(g_fail)
        got = _dedupe_articles(_filter_by_date(got, start, end))
        if state_key:   # a state search: drop stories clearly about another state or country
            got = [a for a in got if not is_off_state(a.get("headline", ""), state_key)]
        for a in got:
            a["category"] = key
            if state_key:
                a["state_origin"] = WRAP_STATES[state_key]["label"]
        by_cat.setdefault(key, []).extend(got)
        status[f"{label} news"] = f"{len(got)} articles" + ("; " + "; ".join(fails) if fails else "")
    return by_cat, status


def _story_link_records(story: dict) -> list:
    """Every outlet's article for a story, one per outlet: primary sources first,
    then established outlets, direct publisher links before Google News links."""
    recs, seen = [], set()
    for it in story.get("items") or []:
        k = _outlet_key(it.get("source", ""))
        if not k or k in seen or not it.get("url"):
            continue
        seen.add(k)
        recs.append({"name": it["source"], "url": it["url"], "kind": outlet_kind(it["source"]),
                     "direct": "news.google." not in it["url"]})
    order = {"primary": 0, "established": 1, "other": 2}
    return sorted(recs, key=lambda r: (order[r["kind"]], not r["direct"]))


def _same_event(a: dict, b: dict) -> bool:
    if {it.get("url") for it in a.get("items", []) if it.get("url")} & {it.get("url") for it in b.get("items", []) if it.get("url")}:
        return True
    wa, wb = _story_words(a["headline"], set()), _story_words(b["headline"], set())
    if not wa or not wb:
        return False
    shared = wa & wb
    return len(shared) >= 3 and len(shared) / min(len(wa), len(wb)) >= 0.6


def _tag_story(s: dict, state_keys: list) -> None:
    states = related_states(_story_material(s), state_keys)
    origin = sorted({it.get("state_origin") for it in s["items"] if it.get("state_origin")})
    s["related_states"] = sorted(set(states) | (set(origin) if s["category"] == "state" else set()))


def build_carousel_candidates(by_cat: dict, state_keys=()) -> dict:
    """Group each category's articles into stories and place every story on the
    right slide:
      * news ABOUT Andhra Pradesh / Telangana that is really business, tech,
        health, environment, sports or world news goes on THAT topic's slide,
        tagged with its state; the rest goes on the State slide;
      * the National slide keeps India-level news not specific to AP/Telangana.
    The same event in two categories is kept once. Stories are then sorted into
    shortlisted main candidates (the top few per category, ALWAYS including the
    best AP/Telangana ones), a pool for 'headlines in brief', and the excluded
    (one source, not an established outlet -- can't be adequately verified)."""
    state_keys = list(state_keys or [])
    rank = lambda s: (s["n_established"] > 0, len(s["outlets"]), s["primary"],
                      s["last_seen"].timestamp() if s.get("last_seen") else 0)
    every, log = [], []
    for cat in CAROUSEL_CATEGORY_ORDER + ["state_topic"]:
        for s in build_top_stories({"headlines": by_cat.get(cat, []), "social_news": []}, max_stories=40, window_days=1):
            s["category"] = "state" if cat == "state_topic" else cat
            _tag_story(s, state_keys)
            topic = carousel_topic(" ".join(it["headline"] for it in s["items"]))
            if cat == "state_topic":
                # from an AP/Telangana topic search: its topic if the headline shows one; the State slide if it's
                # about a state but no topic; otherwise it's noise the search happened to match
                if topic:
                    s["category"] = topic
                elif not s["related_states"]:
                    log.append({"story": {**s, "category": "state"}, "outcome": "Dropped -- found by an AP/Telangana "
                                "search but the headline shows neither a topic nor a state link"})
                    continue
            elif cat == "state" or (cat == "national" and s["related_states"]):
                # news about AP/Telangana: on its topic's slide if it has one, otherwise on the State slide
                s["category"] = topic or "state"
            s["links"] = _story_link_records(s)
            s["n_established"] = sum(1 for r in s["links"] if r["kind"] in ("established", "primary"))
            s["primary"] = any(r["kind"] == "primary" for r in s["links"])
            every.append(s)
    order = {c: i for i, c in enumerate(CAROUSEL_CATEGORY_ORDER)}
    every.sort(key=rank, reverse=True)                  # strongest first...
    every.sort(key=lambda s: order[s["category"]])      # ...within each category (stable sort)
    pool = []
    for s in every:
        dup = next((p for p in pool if _same_event(p, s)), None)
        if dup:
            dup["related_states"] = sorted(set(dup["related_states"]) | set(s["related_states"]))
            log.append({"story": s, "outcome": f"Dropped -- same event as a {CAROUSEL_CATEGORY_LABELS[dup['category']]} "
                                                f"story (\"{dup['headline'][:60]}\")"})
            continue
        pool.append(s)
    eligible = []
    for s in pool:
        if not s["links"]:
            log.append({"story": s, "outcome": "Excluded -- no source link available"})
        elif s["n_established"] == 0 and len(s["outlets"]) < 2:
            log.append({"story": s, "outcome": "Excluded -- one source, not an established outlet: cannot be "
                                               "adequately verified (flag for editorial review if important)"})
        else:
            eligible.append(s)
    mains = []
    for cat in CAROUSEL_CATEGORY_ORDER:
        in_cat = sorted((s for s in eligible if s["category"] == cat), key=rank, reverse=True)
        pick = in_cat[:CAROUSEL_CANDIDATES_PER_CATEGORY + (1 if cat == "state" else 0)]
        if cat == "state":   # at least two from each chosen state, where available
            for label in [WRAP_STATES[k]["label"] for k in state_keys]:
                have = [x for x in pick if label in x["related_states"]]
                pick += [x for x in in_cat if label in x["related_states"] and x not in pick][: max(0, 2 - len(have))]
        else:                # always include the best AP/Telangana stories for this topic
            pick += [x for x in in_cat if x["related_states"] and x not in pick][:CAROUSEL_STATE_SHORTLIST_EXTRA]
        mains += pick
    rest = sorted((s for s in eligible if s not in mains), key=rank, reverse=True)
    briefs = rest[:CAROUSEL_BRIEF_POOL]
    briefs += [x for x in rest if x["related_states"] and x not in briefs][:CAROUSEL_STATE_SHORTLIST_EXTRA]
    for i, s in enumerate(mains, 1):
        s["cid"] = f"C{i}"
    for i, s in enumerate(briefs, 1):
        s["cid"] = f"B{i}"
    return {"mains": mains, "briefs": briefs, "log": log, "state_keys": state_keys}


# Fetching a page the way a normal browser visit would. (News sites often refuse
# requests that announce themselves as a script.) Only publicly readable pages
# are read -- nothing here gets around paywalls or logins.
ARTICLE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}
_GNEWS_RX = re.compile(r"https?://news\.google\.com/(?:rss/)?(?:articles|read)/([A-Za-z0-9_-]+)")
_GNEWS_CACHE = {}

try:
    from googlenewsdecoder import gnewsdecoder   # optional: pip install googlenewsdecoder (kept up to date by its authors)
except Exception:
    gnewsdecoder = None


def _gnews_from_base64(gid: str):
    """Older Google News article ids carry the publisher URL inside them."""
    try:
        raw = base64.urlsafe_b64decode(gid + "=" * (-len(gid) % 4))
    except Exception:
        return None
    m = re.search(rb"https?://[\x21-\x7e]+", raw)
    if not m:
        return None
    url = m.group(0).decode("ascii", "ignore")
    return url if "news.google." not in url else None


def _gnews_from_batchexecute(gid: str):
    """Newer ids: ask Google News for the target URL the way its own web page does
    (read the article page's signature and timestamp, then call its decoding endpoint)."""
    if BeautifulSoup is None:
        return None
    r = requests.get(f"https://news.google.com/rss/articles/{gid}", headers=ARTICLE_HEADERS, timeout=6)
    soup = BeautifulSoup(r.text, "html.parser")
    node = soup.find(attrs={"data-n-a-sg": True, "data-n-a-ts": True})
    if not node:
        return None
    sig, ts = node.get("data-n-a-sg"), node.get("data-n-a-ts")
    inner = ('["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
             f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts},"{sig}"]')
    body = "f.req=" + quote(json.dumps([[["Fbv4je", inner, None, "generic"]]]))
    r2 = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body, timeout=6,
                       headers={**ARTICLE_HEADERS, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    chunk = r2.text.split("\n\n", 1)[1]
    parsed = json.loads(chunk)[:-2]
    url = json.loads(parsed[0][2])[1]
    return url if isinstance(url, str) and url.startswith("http") else None


def resolve_google_news_url(url: str):
    """The publisher's own article URL for a Google News redirect link (or the
    URL unchanged if it isn't one); None if it can't be resolved. Google changes
    this format from time to time -- installing googlenewsdecoder keeps it working."""
    m = _GNEWS_RX.match(url or "")
    if not m:
        return url
    gid = m.group(1)
    if gid in _GNEWS_CACHE:
        return _GNEWS_CACHE[gid]
    found = None
    if gnewsdecoder is not None:
        try:
            res = gnewsdecoder(url)
            if isinstance(res, dict) and res.get("status") and res.get("decoded_url"):
                found = res["decoded_url"]
        except Exception:
            found = None
    found = found or _gnews_from_base64(gid)
    if not found:
        try:
            found = _gnews_from_batchexecute(gid)
        except Exception:
            found = None
    _GNEWS_CACHE[gid] = found
    return found


def _article_text_from_html(html: str, max_chars: int) -> str:
    """Article text from a page: structured data (JSON-LD articleBody), then the
    page's paragraphs, plus its summary metadata (og/meta description) -- which
    almost every news page has, even when the body is loaded by JavaScript."""
    soup = BeautifulSoup(html, "html.parser")
    desc = ""
    for attrs in ({"property": "og:description"}, {"name": "description"}, {"name": "twitter:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            desc = " ".join(tag["content"].split())
            break
    body = ""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        for obj in (data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []):
            if isinstance(obj, dict) and isinstance(obj.get("articleBody"), str) and len(obj["articleBody"]) > 200:
                body = " ".join(obj["articleBody"].split())
                break
        if body:
            break
    if not body:
        paras = [" ".join(p.get_text(" ", strip=True).split()) for p in soup.find_all("p")]
        body = " ".join(p for p in paras if len(p) >= 40)
    text = (desc + " " + body).strip() if desc and desc[:60] not in body else (body or desc)
    return text[:max_chars]


def fetch_article_text(url: str, max_chars: int = 1500) -> tuple:
    """(text, problem): the opening of a news article, or ("", why it failed).
    Google News redirect links are first resolved to the publisher's page."""
    if BeautifulSoup is None:
        return "", "beautifulsoup4 isn't installed"
    if not url:
        return "", "no link available"
    target = resolve_google_news_url(url)
    if not target:
        return "", "the Google News link could not be resolved to the publisher's page"
    try:
        r = requests.get(target, headers=ARTICLE_HEADERS, timeout=7, stream=True)
    except Exception as e:
        return "", f"the publisher's site could not be reached ({_short_error(e)})"
    if r.status_code in (401, 402, 403, 429, 451):
        return "", f"the publisher's site refused automated access (HTTP {r.status_code})"
    if r.status_code >= 400:
        return "", f"the page returned HTTP {r.status_code}"
    try:
        text = _article_text_from_html(_read_capped(r), max_chars)
    except Exception:
        text = ""
    return (text, "") if text else ("", "the page had no readable article text (it may be paywalled or load by script)")


FETCH_MAX_BYTES = 1_500_000   # stop reading a page after this much...
FETCH_MAX_SECONDS = 10        # ...or after this long, whatever the server does


def _read_capped(r) -> str:
    """A response's text, read in chunks and cut off at FETCH_MAX_BYTES or FETCH_MAX_SECONDS."""
    chunks_of = getattr(r, "iter_content", None)
    if chunks_of is None:
        return r.text or ""
    started, size, parts = time.monotonic(), 0, []
    try:
        for chunk in chunks_of(chunk_size=65536):
            if chunk:
                parts.append(chunk)
                size += len(chunk)
            if size >= FETCH_MAX_BYTES or time.monotonic() - started > FETCH_MAX_SECONDS:
                break
    finally:
        close = getattr(r, "close", None)
        if close:
            close()
    return b"".join(parts).decode(getattr(r, "encoding", None) or "utf-8", errors="replace")


CAROUSEL_THIN_TEXT = 300   # fewer characters than this = only a short description was available


CAROUSEL_FETCH_WORKERS = 16
CAROUSEL_FETCH_DEADLINE = 25   # seconds for all article downloads (they run while the AI chooses)


def _fetch_story_text(s: dict, tries: int = 2) -> str:
    """Fetch an excerpt for one story from up to `tries` of its links (direct
    publisher links first, then resolved Google News links). A resolved Google
    News link replaces the redirect link in the story's sources, so the editor
    gets the publisher's own URL. Returns "ok" or the reason it failed."""
    s["excerpt"], s["excerpt_source"], s["excerpt_note"] = "", "", ""
    problems = []
    for rec in sorted(s["links"], key=lambda r: not r["direct"])[:tries]:
        text, problem = fetch_article_text(rec["url"])
        if not rec["direct"]:
            resolved = _GNEWS_CACHE.get((_GNEWS_RX.match(rec["url"]) or [None, None])[1])
            if resolved:
                rec["url"], rec["direct"] = resolved, True
        if text:
            s["excerpt"], s["excerpt_source"] = text, rec["name"]
            return "ok"
        problems.append(problem)
    s["excerpt_note"] = problems[0] if problems else "no link available"
    return s["excerpt_note"]


def _fetch_counts(results: list) -> dict:
    counts = {"fetched": results.count("ok"), "total": len(results)}
    for r in results:
        if r != "ok":
            key = ("unresolved" if "Google News" in r else "blocked" if "refused" in r or "reached" in r
                   else "unreadable" if "readable" in r or "HTTP" in r else "other")
            counts[key] = counts.get(key, 0) + 1
    return counts


def attach_article_text(stories: list, workers: int = CAROUSEL_FETCH_WORKERS, tries: int = 2) -> dict:
    """Fetch an excerpt for every story, in parallel. Returns counts."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda st_: _fetch_story_text(st_, tries), stories))
    return _fetch_counts(results)


def _story_material(s: dict) -> str:
    return " ".join([it["headline"] for it in s.get("items", [])] + [s.get("excerpt", "")])


def _first_published(s: dict) -> str:
    dts = [it["dt"] for it in s.get("items", []) if it.get("dt")]
    return f"{_ist(min(dts)):%d %b %Y, %H:%M} IST" if dts else "unknown"


def _carousel_intro(day) -> str:
    return (f"You are the editorial assistant for a daily digital news briefing, preparing a DRAFT {len(CAROUSEL_SLIDES)}-slide carousel "
            f"for {day:%A, %d %B %Y} (India) that a human editor will check and approve. Nothing you write is "
            "published, scheduled or treated as verified until the editor approves it.\n")


def _carousel_select_prompt(day) -> str:
    return (
        _carousel_intro(day)
        + "STEP 1 OF 3 -- CHOOSE THE STORIES. You are given candidate stories, each with an id ([C3] for main "
        "candidates, [B2] for brief candidates), its category, how many separate outlets reported it and how many of "
        "those are established outlets, when it was first published (IST), and every outlet's headline. "
        "THAT MATERIAL IS ALL YOU KNOW.\n"
        "- Prioritise by public significance, impact, novelty and relevance to Indian readers. Prefer stories carried "
        "by several outlets, including established ones.\n"
        "- top_story: the single most significant main candidate.\n"
        "- slides: for each of national, state, world, business, more and sports, choose main candidates FROM THAT SLIDE'S "
        "categories -- 0-3 each, up to 4 for state (national: National politics -- India-level news NOT specific to "
        "Andhra Pradesh or Telangana; state: State developments in Andhra Pradesh and Telangana; world: World affairs; "
        "business: Business & economy; more: Technology/AI/science, Health & education, Environment & climate; "
        "sports: Sports). "
        "Adapt to the day's news: choose fewer, or none, rather than include something trivial. NEVER manufacture a "
        "story to fill a slide.\n"
        "- ANDHRA PRADESH AND TELANGANA: candidates marked \"related to\" a state concern Andhra Pradesh or Telangana. "
        "Readers want the AP/Telangana angle in EVERY section: whenever such a candidate is newsworthy, include it on "
        "its slide (and on the state slide, cover each state that has news).\n"
        "- briefs: 0-5 brief candidates worth a one-line mention.\n"
        "- NEVER use the same underlying event twice anywhere -- top story, slides or briefs.\n"
        "Respond with ONLY a JSON object, no markdown fences, in exactly this shape:\n"
        '{"top_story": "C1", "slides": {"national": [], "state": [], "world": [], "business": [], "more": [], "sports": []}, '
        '"briefs": []}'
    )


def _carousel_write_prompt(day) -> str:
    lo, hi = CAROUSEL_SUMMARY_WORDS
    return (
        _carousel_intro(day)
        + "STEP 2 OF 3 -- WRITE THE STORIES. You are given a few chosen stories, each with an id, every outlet's "
        "headline and -- where available -- an excerpt of the article text. THAT MATERIAL IS ALL YOU KNOW. Write an "
        "entry for EVERY id given; do not skip any.\n"
        f"- headline: concise and accurate, at most {CAROUSEL_HEADLINE_MAX_WORDS} words; no sensationalism, clickbait "
        "or question headlines.\n"
        f"- summary: {lo}-{hi} words, from the material only. If the material is too thin for {lo} words, write fewer "
        "-- never pad with details that are not there.\n"
        "- key_facts: 2-4 KEY FACTS -- the most important concrete facts in the material: figures and amounts, "
        "dates, names, places, decisions, outcomes. Each under 15 words and each adding something NEW: never repeat "
        "the headline, another key fact, or a sentence of the summary word for word. Skip vague lines (\"stressed "
        "its importance\"); put the most important fact first.\n"
        "- context: one sentence of background ONLY if the material supports it, otherwise \"\".\n"
        "- status: \"established\" (reported as fact by several outlets), \"developing\" (still unfolding; details may "
        "change), \"disputed\" (accounts conflict) or \"allegation\" (a claim by one party). Attribute allegations and "
        "claims to whoever made them; separate facts from analysis.\n"
        "- event_date: the date the event happened ONLY if the material states it explicitly; otherwise \"\". Never "
        "assume it is the publication date.\n"
        "- visual: describe a suitable image or graphic (e.g. \"map of the affected districts\", \"official handout "
        "photo of the cabinet meeting\"). Never name a photographer, agency or credit.\n"
        "- Never invent facts, quotes, statistics, sources or image credits. No partisan framing, no predictions. Do "
        "not add outlet names or citations -- sources are attached automatically.\n"
        "Respond with ONLY a JSON object, no markdown fences, in exactly this shape:\n"
        '{"stories": {"C1": {"headline": "...", "summary": "...", "key_facts": ["..."], "context": "", '
        '"status": "established", "event_date": "", "visual": "..."}}}'
    )


def _carousel_post_prompt(day) -> str:
    n = CAROUSEL_SLIDES[-1]["n"]
    return (
        _carousel_intro(day)
        + "STEP 3 OF 3 -- POST COPY. You are given the carousel's slides and the headlines on each. THAT MATERIAL IS "
        "ALL YOU KNOW: do not add facts that are not in those headlines.\n"
        "- hook: an accurate opening line under 15 words; not sensational.\n"
        "- caption: a platform-appropriate caption of 60-120 words describing the roundup neutrally.\n"
        "- hashtags: 4-8 relevant, non-misleading hashtags.\n"
        "- takeaway: 1-2 sentences tying the day together WITHOUT new facts or predictions.\n"
        "- follow_prompt: a short, non-pushy line inviting readers to follow for tomorrow's roundup.\n"
        f"- alt_text: accessibility text for each slide, keyed \"1\" to \"{n}\", describing what the slide shows.\n"
        "Never call anything verified. Respond with ONLY a JSON object, no markdown fences, in exactly this shape:\n"
        '{"hook": "...", "caption": "...", "hashtags": ["#..."], "takeaway": "...", "follow_prompt": "...", '
        '"alt_text": {"1": "..."}}'
    )


def _carousel_story_block(s: dict, with_excerpt: bool) -> str:
    heads = "; ".join(f'"{it["headline"]}" ({it.get("source", "")})' for it in s["items"][:4])
    line = (f"[{s['cid']}] category: {CAROUSEL_CATEGORY_LABELS[s['category']]}"
            + (f" | related to: {', '.join(s['related_states'])}" if s.get("related_states") else "")
            + f" | {len(s['outlets'])} outlet(s), {s['n_established']} established"
            + (", incl. a primary/official source" if s["primary"] else "")
            + f" | first published {_first_published(s)}\n   headlines: {heads}")
    if with_excerpt and s.get("excerpt"):
        line += f"\n   excerpt ({s['excerpt_source']}): \"{s['excerpt'][:900]}\""
    return line


def _carousel_select_user(day, cands: dict) -> str:
    L = [f"DATE: {day:%A, %d %B %Y} (India)", "", "MAIN CANDIDATES"]
    L += [_carousel_story_block(s, False) for s in cands["mains"]] or ["(none)"]
    L += ["", "BRIEF CANDIDATES"] + ([_carousel_story_block(s, False) for s in cands["briefs"]] or ["(none)"])
    L += ["", "Choose now: reply with the JSON object only."]
    return "\n".join(L)


def _carousel_write_user(day, stories: list) -> str:
    L = [f"DATE: {day:%A, %d %B %Y} (India)", "", "STORIES TO WRITE"] + [_carousel_story_block(s, True) for s in stories]
    L += ["", f"Write entries for these ids: {', '.join(s['cid'] for s in stories)}. Reply with the JSON object only."]
    return "\n".join(L)


def _carousel_post_user(day, plan: dict) -> str:
    L = [f"DATE: {day:%A, %d %B %Y} (India)", ""]
    for sl in plan["slides"]:
        heads = [c["headline"] for c in sl["cards"]] + [b["headline"] for b in sl["briefs"]]
        L.append(f"Slide {sl['n']} -- {sl['title']}: " + ("; ".join(heads) if heads else "(no stories)"))
    L += ["", "Write the post copy now: reply with the JSON object only."]
    return "\n".join(L)


_RETRYABLE = ("429", "rate", "too many", "timeout", "timed out", "temporar", "502", "503", "504", "overload",
              "connection", "unavailable")


def _carousel_ai_json(client, model, system: str, user: str, required: str, max_tokens: int) -> dict:
    """One small AI request. Rate limits and temporary errors are retried with a
    short pause (up to 3 tries); an unusable reply gets one corrective retry.
    Raises if no usable JSON comes back."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_error, corrected = "no response", False
    for attempt in range(3):
        try:
            response = _call_sarvam(client, model, messages, max_tokens=max_tokens)
        except Exception as e:
            last_error = _short_error(e)
            if attempt < 2 and any(k in str(e).lower() for k in _RETRYABLE):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        message = response.choices[0].message
        content = getattr(message, "content", None) or getattr(message, "reasoning_content", None)
        if content:
            content = re.sub(r"^```(?:json)?|```$", "", str(content).strip(), flags=re.MULTILINE).strip()
            parsed = extract_json_object(content)
            if isinstance(parsed, dict) and required in parsed:
                return parsed
            last_error = f"response did not contain '{required}'"
        else:
            last_error = "empty response"
        if corrected:
            break
        corrected = True
        messages = messages[:2] + [{"role": "user", "content":
            f"Your previous reply was unusable ({last_error}). Reply again with ONLY the JSON object."}]
    raise ValueError(last_error)


_ID_RX = re.compile(r"\b([CB])\s*-?\s*(\d+)\b", re.I)


def _norm_ids(v) -> list:
    """Story ids from whatever shape the AI used: ["C1"], "C1", "c1, C2", ["[C3]"], 4 ..."""
    if v is None:
        return []
    items = v if isinstance(v, list) else list(v.values()) if isinstance(v, dict) else [v]
    out = []
    for x in items:
        for m in _ID_RX.finditer(str(x)):
            cid = m.group(1).upper() + m.group(2)
            if cid not in out:
                out.append(cid)
    return out


def _norm_selection(sel) -> dict:
    sel = sel if isinstance(sel, dict) else {}
    slides = sel.get("slides") if isinstance(sel.get("slides"), dict) else {}
    return {"top_story": (_norm_ids(sel.get("top_story")) or [""])[0],
            "slides": {k: _norm_ids(slides.get(k)) for k in CAROUSEL_STORY_SLIDES},
            "briefs": _norm_ids(sel.get("briefs"))}


def _norm_post(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    tags = raw.get("hashtags")
    if isinstance(tags, str):
        tags = re.split(r"[\s,]+", tags)
    alt = raw.get("alt_text")
    if isinstance(alt, list):
        alt = {str(i): v for i, v in enumerate(alt, 1)}
    out = {k: _as_text(raw.get(k)) for k in ("hook", "caption", "takeaway", "follow_prompt") if raw.get(k)}
    if isinstance(tags, list):
        out["hashtags"] = [str(t) for t in tags if str(t).strip()]
    if isinstance(alt, dict):
        out["alt_text"] = {str(k).strip(): _as_text(v) for k, v in alt.items()}
    return out


def _as_text(v) -> str:
    if isinstance(v, list):
        return " ".join(_as_text(x) for x in v)
    if isinstance(v, dict):
        return " ".join(_as_text(x) for x in v.values())
    return " ".join(str(v if v is not None else "").split())


CAROUSEL_WRITE_BATCH = 3      # stories per writing request: small replies, never cut off
CAROUSEL_AI_WORKERS = 3       # writing requests run in parallel (kept modest to avoid rate limits)
CAROUSEL_SELECT_TIMEOUT = 60  # seconds; if choosing takes longer, stories are chosen by coverage
CAROUSEL_WRITE_DEADLINE = 90  # seconds for all writing + post copy; stories not written by then use an extract


def write_carousel_stories(client, model, day, stories: list, deadline=None) -> tuple:
    """({cid: entry}, problems): the chosen stories written in parallel batches;
    any the AI skipped get one more, single-story try. Everything stops at
    `deadline` (a time.monotonic() value): stories not written by then fall
    back to an extract of the article, so a slow AI can never stall the carousel."""
    from concurrent.futures import ThreadPoolExecutor, wait
    deadline = deadline or (time.monotonic() + CAROUSEL_WRITE_DEADLINE)
    written, problems = {}, []

    def batch(group):
        try:
            got = _carousel_ai_json(client, model, _carousel_write_prompt(day), _carousel_write_user(day, group),
                                    "stories", 600 + 450 * len(group))
        except Exception as e:
            problems.append(_short_error(e))
            return {}
        out = {}
        for k, v in (got.get("stories") or {}).items() if isinstance(got.get("stories"), dict) else []:
            ids = _norm_ids(k)
            if ids and isinstance(v, dict):
                out[ids[0]] = v
        return out

    def summary_of(cid):
        return _as_text((written.get(cid) or {}).get("summary"))

    pool = ThreadPoolExecutor(max_workers=CAROUSEL_AI_WORKERS)
    try:
        groups = [stories[i:i + CAROUSEL_WRITE_BATCH] for i in range(0, len(stories), CAROUSEL_WRITE_BATCH)]
        futures = [pool.submit(batch, g) for g in groups]
        done, late = wait(futures, timeout=max(0.0, deadline - time.monotonic()))
        for f in done:
            written.update(f.result())
        if late:
            problems.append(f"{len(late)} writing request(s) ran out of time")
        missing = [x for x in stories if not summary_of(x["cid"])]
        if missing and deadline - time.monotonic() > 3:
            futures = [pool.submit(batch, [x]) for x in missing]
            done, late = wait(futures, timeout=max(0.0, deadline - time.monotonic()))
            for f in done:
                written.update(f.result())
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return written, problems


def _template_carousel_raw(cands: dict) -> dict:
    """Without the AI: the strongest candidates, with their own headlines, and
    every piece of writing left for the editor (and flagged). (The AP/Telangana
    coverage rule is applied afterwards, as for the AI's choices.)"""
    mains = cands["mains"]
    rank = lambda s: (s["n_established"] > 0, len(s["outlets"]))
    top = max(mains, key=rank, default=None)
    slides = {}
    for sl in CAROUSEL_SLIDES:
        if sl.get("cats"):
            slides[sl["key"]] = [s["cid"] for s in sorted((s for s in mains if s["category"] in sl["cats"] and s is not top),
                                                          key=rank, reverse=True)[:2]]
    return {"top_story": top["cid"] if top else "", "slides": slides,
            "briefs": [s["cid"] for s in cands["briefs"][:5]], "stories": {}, "hook": "", "caption": "",
            "hashtags": [], "takeaway": "", "follow_prompt": "", "alt_text": {}}


_CREDIT_RX = re.compile(r"(?i)\b(photo|image|picture|courtesy|credit)s?\s*(credit)?\s*[:\-]\s*[^,.;]+")


def _scrub_visual(text: str) -> str:
    """Keep the visual idea, drop any credit the AI invented: "Photo: Reuters/John Doe, crowd outside parliament"
    -> "crowd outside parliament (credit to be confirmed by the editor)"."""
    t = " ".join(str(text or "").split())
    if not _CREDIT_RX.search(t):
        return t
    t = _CREDIT_RX.sub("", t).strip(" ,;:-")
    return (t or "Image") + " (credit to be confirmed by the editor)"


def _numbers(text: str) -> set:
    return {n.replace(",", "").rstrip(".") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")}


_FACT_STOP = set("a an the of in on at to for and or but with by from as is are was were be been has have had it its "
                 "this that these those which who will would could should may also into over after before than "
                 "their his her they he she said says".split())
_FACT_DECISION = re.compile(r"\b(approv|announc|pass|sanction|allocat|arrest|order|launch|sign|elect|win|won|lost|"
                            r"resign|appoint|ban|stay|quash|dismiss|uphold|upheld|releas|cut|rais|hike|reduc|declar|"
                            r"inaugurat|file|charge|convict|acquit|suspend|join|defect|merg|form|award|grant)", re.I)
_FACT_VAGUE = re.compile(r"\b(stress|important|significan|key|crucial|various|several|discuss|highlight|underlin|"
                         r"emphasi|noted|expressed)", re.I)
_FACT_DATE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|"
                        r"may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|"
                        r"sept|oct|nov|dec|today|yesterday|tomorrow)\b", re.I)


def _fact_words(text: str) -> set:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _FACT_STOP and len(w) > 1}


def _fact_overlap(a: str, b: str) -> float:
    """Shared meaningful words as a share of the shorter text (1.0 = one says nothing the other doesn't)."""
    wa, wb = _fact_words(a), _fact_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def fact_importance(text: str) -> int:
    """How much hard fact a line carries: figures, amounts, dates, names and decisions count; vague words don't."""
    t = text or ""
    score = 3 * min(2, len(re.findall(r"(?:₹|rs\.?\s*)?\d[\d,.]*\s*(?:%|per cent|crore|lakh|million|billion|km|mw|acres)?",
                                     t, re.I)))
    score += 2 * min(1, len(_FACT_DATE.findall(t)))
    score += min(3, len(re.findall(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-zA-Z]{2,}", t)))
    score += 2 if _FACT_DECISION.search(t) else 0
    score -= 2 if _FACT_VAGUE.search(t) else 0
    score -= 1 if len(t.split()) > 18 else 0
    return score


def select_key_facts(candidates: list, headline: str, summary: str, excerpt: str = "", max_n: int = 4) -> list:
    """The key facts for a story card: the most important concrete facts, each saying something new.

    A candidate is dropped if it repeats the headline, a fact already kept, or a sentence of the summary word for
    word. If fewer than two remain, sentences of the ARTICLE TEXT that carry hard facts and add something the summary
    doesn't say are used. Kept facts are ordered most important first."""
    summary_sents = [x for x in split_sentences(summary or "") if x.strip()]

    def repeats(f, kept):
        if _fact_overlap(f, headline) >= 0.75:
            return True
        if any(_fact_overlap(f, k) >= 0.6 for k in kept):
            return True
        return any(_fact_overlap(f, ss) >= 0.9 and len(f.split()) >= 0.7 * len(ss.split()) for ss in summary_sents)

    kept = []
    for f in candidates:
        f = " ".join(str(f).split()).strip(" -•")
        if f and not repeats(f, kept):
            kept.append(f)
    if len(kept) < 2 and excerpt:
        for sent in split_sentences(excerpt):
            sent = " ".join(sent.split())
            words = sent.split()
            if len(words) > 22:
                sent = " ".join(words[:20]) + "…"
            adds_new = all(_fact_overlap(sent, ss) < 0.6 for ss in summary_sents)
            if fact_importance(sent) >= 4 and adds_new and not repeats(sent, kept):
                kept.append(sent)
            if len(kept) >= max_n:
                break
    kept.sort(key=fact_importance, reverse=True)       # stable: equally important facts keep the AI's order
    solid = [f for f in kept if fact_importance(f) > 0]
    if len(solid) >= 2:                                 # vague lines go when there are real facts to show
        kept = solid
    return kept[:max_n]


def _carousel_card(s: dict, ai: dict, day, all_names=None) -> dict:
    ai = ai if isinstance(ai, dict) else {}
    lo, hi = CAROUSEL_SUMMARY_WORDS
    # Any outlet in the shortlist counts as a citation to strip -- including one wrongly attributed to this story.
    names = sorted(set(all_names or []) | {r["name"] for r in s["links"]})
    ai = {k: (v if k == "key_facts" else _as_text(v)) for k, v in ai.items()}
    if isinstance(ai.get("key_facts"), str):
        ai["key_facts"] = [ai["key_facts"]]
    headline = _clean_point(ai.get("headline"), names).rstrip(".") or _clean_headline(s["headline"], "").rstrip(".")
    summary = _clean_point(ai.get("summary"), names) if ai.get("summary") else ""
    extracted = False
    if not summary and len(s.get("excerpt") or "") >= 200:
        # The AI's summary isn't available but the article was read: use its opening, clearly flagged.
        out = []
        for sent in split_sentences(s["excerpt"]):
            if len(" ".join(out + [sent]).split()) > CAROUSEL_SUMMARY_WORDS[1]:
                break
            out.append(sent)
        summary = " ".join(out) or " ".join(s["excerpt"].split()[:CAROUSEL_SUMMARY_WORDS[1]])
        extracted = True
    ai_facts = [_clean_point(f, names) for f in (ai.get("key_facts") or []) if str(f).strip()] \
        if isinstance(ai.get("key_facts"), list) else []
    facts = select_key_facts(ai_facts, headline, summary, s.get("excerpt") or "")
    context = _clean_point(ai.get("context"), names) if ai.get("context") else ""
    flags = []
    words = len(summary.split())
    if len(facts) < 2:
        flags.append(f"Only {len(facts)} distinct key fact(s) -- add the most important facts (figures, dates, names, "
                     "decisions) from the sources")
    if extracted:
        flags.append(f"Summary is an extract from {s.get('excerpt_source') or 'the source'}'s article (the AI summary "
                     "wasn't available) -- rewrite it in your own words before use")
    if not summary:
        flags.append(f"Summary missing -- editor to write {lo}-{hi} words from the linked sources")
    elif not lo <= words <= hi:
        flags.append(f"Summary is {words} words (target {lo}-{hi}) -- edit")
    if len(headline.split()) > CAROUSEL_HEADLINE_MAX_WORDS:
        flags.append(f"Headline is {len(headline.split())} words (max {CAROUSEL_HEADLINE_MAX_WORDS}) -- shorten")
    allowed = _numbers(_story_material(s)) | {str(day.day), str(day.year), f"{day.day:02d}"}
    unsupported = sorted(_numbers(" ".join([headline, summary, context] + facts)) - allowed)
    if unsupported:
        flags.append("Figures not found in the source material: " + ", ".join(unsupported)
                     + " -- check against the original before use")
    if not s.get("excerpt"):
        why = s.get("excerpt_note") or "article text could not be fetched"
        flags.append(f"Only headlines were available ({why}) -- read the source before use")
    elif len(s["excerpt"]) < CAROUSEL_THIN_TEXT:
        flags.append("Only the article's short description was available -- read the source before use")
    n, est = len(s["outlets"]), s["n_established"]
    if est == 0:
        level = f"UNVERIFIED -- flagged for editorial review (reported by {n} outlet(s), none established)"
    elif n >= 2:
        level = f"Corroborated by {n} outlets ({est} established) -- pending editorial check"
    else:
        level = f"Single source ({s['outlets'][0]}) -- verify independently before publishing"
    st_ = str(ai.get("status") or "").lower()
    heads = " ".join(it["headline"].lower() for it in s["items"])
    if st_ == "developing" or re.search(r"\b(live|updates|breaking|developing)\b", heads):
        level += "; DEVELOPING -- details may change"
    if st_ == "disputed":
        level += "; DISPUTED -- accounts differ, present both"
    if st_ == "allegation":
        level += "; ALLEGATION -- attribute to whoever made it; not established"
    visual = _scrub_visual(ai.get("visual"))
    return {"cid": s["cid"], "category": CAROUSEL_CATEGORY_LABELS[s["category"]],
            "related_states": list(s.get("related_states") or []),
            "headline": headline, "summary": summary, "summary_words": words, "key_facts": facts, "context": context,
            "event_date": str(ai.get("event_date") or "").strip() or "Not stated in the sources -- confirm",
            "published": _first_published(s), "sources": s["links"], "verification": level, "flags": flags,
            "visual": visual or "Your own text card or graphic (no photo needed)", "visual_rules": CAROUSEL_VISUAL_RULES}


def _clean_hashtags(tags, text_blob: str) -> list:
    blob = re.sub(r"[^a-z0-9]", "", text_blob.lower())
    out = []
    for t in tags if isinstance(tags, list) else []:
        t = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(t).lstrip("#"))
        word = t[1:].lower()
        if 2 <= len(word) <= 30 and t not in out and (word in CAROUSEL_HASHTAG_ALLOW or word in blob):
            out.append(t)
    return out[:8]


def assemble_carousel(raw: dict, cands: dict, day, used_template: bool, status: dict) -> dict:
    """Validate the AI's choices and build the carousel: unknown ids, a story
    used twice, the same event under two ids, or a story on the wrong slide
    are all removed (and noted for the editor)."""
    by_id = {s["cid"]: s for s in cands["mains"] + cands["briefs"]}
    all_names = sorted({r["name"] for s in by_id.values() for r in s["links"]})
    stories_ai = raw.get("stories") if isinstance(raw.get("stories"), dict) else {}
    used, notes = {}, []

    def take(cid, slide_n, cats=None, mains_only=True):
        s = by_id.get(str(cid))
        if not s:
            notes.append(f"Slide {slide_n}: the AI chose '{cid}', which is not a candidate -- ignored")
            return None
        if mains_only and not s["cid"].startswith("C"):
            notes.append(f"Slide {slide_n}: {cid} is a brief candidate -- not used as a full story")
            return None
        if s["cid"] in used:
            notes.append(f"{cid} was chosen twice -- kept on slide {used[s['cid']]} only")
            return None
        twin = next((o for o in used if _same_event(by_id[o], s)), None)
        if twin:
            notes.append(f"{cid} is the same event as {twin} (slide {used[twin]}) -- not repeated")
            return None
        if cats and s["category"] not in cats:
            notes.append(f"{cid} ({CAROUSEL_CATEGORY_LABELS[s['category']]}) does not belong on slide {slide_n} -- removed")
            return None
        used[s["cid"]] = slide_n
        return s

    state_labels = [WRAP_STATES[k]["label"] for k in cands.get("state_keys", [])]
    rank = lambda s: (s["n_established"] > 0, len(s["outlets"]), s["primary"])

    def ensure_states(entry, sl, labels, pool, as_brief=False):
        """The AP/Telangana coverage rule: if this section has no story about a state (one of `labels`) but a
        verifiable one is available, add the best one -- replacing the slide's last pick if it is full."""
        items = entry["briefs"] if as_brief else entry["cards"]
        for label in labels:
            if any(label in it["related_states"] for it in items):
                continue
            cand = next((x for x in sorted(pool, key=rank, reverse=True)
                         if label in x["related_states"] and x["cid"] not in used
                         and (as_brief or x["category"] in sl.get("cats", []))
                         and not any(_same_event(by_id[o], x) for o in used)), None)
            if not cand:
                continue
            dropped = ""
            if len(items) >= sl["max"]:
                # Make room by replacing the last story that is NOT about AP/Telangana -- never one already
                # there for a state (e.g. the Telangana story this rule has just added).
                idx = next((i for i in range(len(items) - 1, -1, -1) if not items[i]["related_states"]), None)
                if idx is None:
                    continue
                gone = items.pop(idx)
                used.pop(gone["cid"], None)
                dropped = f", replacing {gone['cid']}"
            used[cand["cid"]] = sl["n"]
            card = _carousel_card(cand, stories_ai.get(cand["cid"]), day, all_names)
            items.append({k: card[k] for k in ("cid", "category", "related_states", "headline", "sources",
                                               "verification", "published")} if as_brief else card)
            notes.append(f"Slide {sl['n']}: added {cand['cid']} ({label}){dropped} -- AP/Telangana coverage rule")

    slides = []
    top = take(raw.get("top_story"), 2)
    if not top and cands["mains"]:
        best = max((s for s in cands["mains"] if s["cid"] not in used),
                   key=lambda s: (s["n_established"] > 0, len(s["outlets"])), default=None)
        top = take(best["cid"], 2) if best else None
        notes.append("Top story chosen by coverage (the AI's choice was missing or invalid)")
    raw_slides = raw.get("slides") if isinstance(raw.get("slides"), dict) else {}
    for sl in CAROUSEL_SLIDES:
        title = sl["title"] + (f": {' & '.join(state_labels)}" if sl["key"] == "state" and state_labels else "")
        entry = {"n": sl["n"], "key": sl["key"], "title": title, "cards": [], "briefs": [], "note": ""}
        if sl["key"] == "top":
            entry["cards"] = [_carousel_card(top, stories_ai.get(top["cid"]), day, all_names)] if top else []
        elif sl.get("cats"):
            for cid in (raw_slides.get(sl["key"]) or [])[: sl["max"]]:
                s = take(cid, sl["n"], sl["cats"])
                if s:
                    entry["cards"].append(_carousel_card(s, stories_ai.get(s["cid"]), day, all_names))
            if sl["key"] != "national":
                ensure_states(entry, sl, state_labels, cands["mains"])
        elif sl["key"] == "briefs":
            for cid in (raw.get("briefs") or [])[: sl["max"]]:
                s = take(cid, sl["n"], None, mains_only=False)
                if s:
                    ai = stories_ai.get(s["cid"]) if isinstance(stories_ai.get(s["cid"]), dict) else {}
                    card = _carousel_card(s, ai, day, all_names)
                    entry["briefs"].append({k: card[k] for k in ("cid", "category", "related_states", "headline", "sources",
                                                                   "verification", "published")})
            if state_labels and not any(b["related_states"] for b in entry["briefs"]):
                # at least one AP/Telangana item among the briefs, where a verifiable one is left
                pool = [x for x in cands["briefs"] + cands["mains"] if x["related_states"]]
                best = next((x for x in sorted(pool, key=rank, reverse=True) if x["cid"] not in used
                             and not any(_same_event(by_id[o], x) for o in used)), None)
                if best:
                    ensure_states(entry, sl, best["related_states"][:1], [best], as_brief=True)
        if sl.get("cats") or sl["key"] in ("top", "briefs"):
            has = entry["cards"] or entry["briefs"]
            avail = sl["key"] == "briefs" and cands["briefs"] or any(s["category"] in sl.get("cats", []) for s in cands["mains"])
            if not has:
                entry["note"] = ("State developments were not requested (national-only carousel) -- drop this slide."
                                 if sl["key"] == "state" and not state_labels else
                                 "No story selected for this slide -- the editor may drop the slide or reallocate it."
                                 if avail or sl["key"] == "top" else
                                 "No qualifying stories found for this slide today -- drop or reallocate it.")
        slides.append(entry)

    used_cards = [c for sl in slides for c in sl["cards"]]
    # Hashtags must relate to the stories actually used: checked against their source headlines and the draft text.
    blob = " ".join([c["headline"] + " " + c["summary"] for c in used_cards]
                    + [_story_material(by_id[cid]) for cid in used])
    hook = _clean_point(raw.get("hook"), []) if raw.get("hook") else ""
    post = {"hook": hook or f"The day's key developments, {day:%d %B %Y}.",
            "caption": " ".join(str(raw.get("caption") or "").split()),
            "hashtags": _clean_hashtags(raw.get("hashtags"), blob) or ["#News", "#India", "#DailyBriefing"],
            "takeaway": " ".join(str(raw.get("takeaway") or "").split()),
            "follow_prompt": " ".join(str(raw.get("follow_prompt") or "").split()) or "Follow for tomorrow's roundup."}
    post_flags = []
    if not post["caption"]:
        post_flags.append("Caption missing -- editor to write")
    if not post["takeaway"]:
        post_flags.append("Takeaway missing -- editor to write")
    if len(post["hook"].split()) > 15:
        post_flags.append(f"Hook is {len(post['hook'].split())} words (aim for under 15)")
    if re.search(r"\bverified\b", " ".join(str(v) for v in post.values()), re.I):
        post_flags.append("Post copy uses the word 'verified' -- remove: nothing is verified until approved")
    alt_raw = raw.get("alt_text") if isinstance(raw.get("alt_text"), dict) else {}
    alt = {}
    for sl in slides:
        a = " ".join(str(alt_raw.get(str(sl["n"])) or "").split())
        if not a:
            heads = "; ".join([c["headline"] for c in sl["cards"]] + [b["headline"] for b in sl["briefs"]])
            a = {1: f"Cover slide: Daily News Wrap-Up for {day:%d %B %Y}. {post['hook']}",
                 CAROUSEL_SLIDES[-1]["n"]: f"Closing slide: {post['takeaway'] or 'daily takeaway'} {post['follow_prompt']}"}.get(
                sl["n"], f"Slide {sl['n']}, {sl['title']}: {heads or 'no stories'}.")
        alt[sl["n"]] = a

    used_ids = {c["cid"]: sl["n"] for sl in slides for c in sl["cards"] + sl["briefs"]}
    source_log = []
    for s in cands["mains"] + cands["briefs"]:
        outcome = (f"Used -- slide {used_ids[s['cid']]}" if s["cid"] in used_ids else "Shortlisted, not selected")
        source_log.append(_log_entry(s, outcome))
    source_log += [_log_entry(e["story"], e["outcome"]) for e in cands["log"]]
    if state_labels:
        cov = []
        for sl in slides:
            if sl["key"] in ("cover", "takeaway"):
                continue
            items = sl["cards"] + sl["briefs"]
            names = sorted({x for it in items for x in it["related_states"]})
            cov.append(f"slide {sl['n']}: {', '.join(names) if names else 'none found'}")
        status["AP/Telangana coverage"] = "; ".join(cov)
    return {"day": day, "generated": f"{utc_now() + IST_OFFSET:%Y-%m-%d %H:%M} IST", "slides": slides, "post": post,
            "post_flags": post_flags, "alt_text": alt, "source_log": source_log, "notes": notes, "status": status,
            "used_template": used_template, "notice": CAROUSEL_DRAFT_NOTICE, "checklist": CAROUSEL_CHECKLIST}


def _log_entry(s: dict, outcome: str) -> dict:
    return {"id": s.get("cid", "--"), "headline": s["headline"], "category": CAROUSEL_CATEGORY_LABELS[s["category"]],
            "outlets": len(s["outlets"]), "established": s.get("n_established", 0), "published": _first_published(s),
            "sources": s.get("links") or _story_link_records(s), "outcome": outcome}


def gather_daily_carousel(day=None, state_choice: str = "both", client=None, model: str = DEFAULT_MODEL) -> dict:
    """The full daily carousel DRAFT for one IST calendar day (default today).
    state_choice: both / ap / telangana / none -- which states feed 'state developments'.

    Built for speed and reliability:
      1. all searches run at once (GDELT in the background, with a deadline);
      2. article text starts downloading for every shortlisted story WHILE the AI
         chooses the stories (a short request: headlines only);
      3. the code applies the editorial rules to the choice (coverage, no repeats);
      4. only the chosen stories are written -- in small parallel batches, with a
         retry for any skipped -- while the post copy is written alongside.
    Small requests can't be cut off half-way, which is what used to lose summaries."""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.monotonic()
    timing = {}
    day = day or ist_today()
    validate_wrap_range(day, day)
    state_keys = [] if str(state_choice).lower() in ("none", "no", "") else resolve_wrap_states(state_choice)
    print(f"  - Searching the day's news ({len(CAROUSEL_CATEGORIES) + len(state_keys)} categories, in parallel)...")
    by_cat, status = gather_carousel_news(day, state_keys)
    cands = build_carousel_candidates(by_cat, state_keys)
    timing["searching"] = time.monotonic() - t0
    status["Shortlist"] = (f"{len(cands['mains'])} main candidates, {len(cands['briefs'])} brief candidates, "
                           f"{sum(1 for e in cands['log'] if e['outcome'].startswith('Excluded'))} excluded as "
                           f"unverifiable, {sum(1 for e in cands['log'] if e['outcome'].startswith('Dropped'))} "
                           "duplicates or off-topic results dropped")

    # 2. article text downloads in the background while the AI chooses
    fetcher = ThreadPoolExecutor(max_workers=CAROUSEL_FETCH_WORKERS)
    fetching = {x["cid"]: fetcher.submit(_fetch_story_text, x) for x in cands["mains"]}
    fetch_deadline = time.monotonic() + CAROUSEL_FETCH_DEADLINE
    sel, from_ai, problems = None, False, []
    t1 = time.monotonic()
    if client is not None and cands["mains"]:
        print("  - Asking Sarvam AI to choose the stories...")
        picker = ThreadPoolExecutor(max_workers=1)
        try:
            sel = picker.submit(_carousel_ai_json, client, model, _carousel_select_prompt(day),
                                _carousel_select_user(day, cands), "slides", 800).result(timeout=CAROUSEL_SELECT_TIMEOUT)
            sel = _norm_selection(sel)
            from_ai = True
        except Exception as e:
            sel = None
            problems.append("choosing: " + ("took too long" if type(e).__name__ == "TimeoutError" else _short_error(e)))
        finally:
            picker.shutdown(wait=False, cancel_futures=True)
    if sel is None:
        sel = _template_carousel_raw(cands)

    # 3. editorial rules applied to the choice
    plan = assemble_carousel({**sel, "stories": {}}, cands, day, True, {})
    by_id = {x["cid"]: x for x in cands["mains"] + cands["briefs"]}
    card_ids = [c["cid"] for sl in plan["slides"] for c in sl["cards"]]

    # only the chosen stories' text is waited for; the rest of the downloads are abandoned
    from concurrent.futures import wait as _wait
    _wait([fetching[c] for c in card_ids], timeout=max(0.0, fetch_deadline - time.monotonic()))
    results = []
    for cid in card_ids:          # one shared deadline -- waits never add up story by story
        f = fetching[cid]
        if f.done() and not f.exception():
            results.append(f.result())
        else:
            by_id[cid]["excerpt"], by_id[cid]["excerpt_note"] = "", "the article took too long to download"
            results.append(by_id[cid]["excerpt_note"])
    fetcher.shutdown(wait=False, cancel_futures=True)
    got = _fetch_counts(results)
    for cid in card_ids:          # the article text can reveal a state link the headline didn't show
        _tag_story(by_id[cid], state_keys)
    why = ", ".join(f"{n} {label}" for key, label in (("unresolved", "Google News links not resolvable"),
                                                     ("blocked", "sites refused or unreachable"),
                                                     ("unreadable", "pages without readable text"),
                                                     ("other", "other")) if (n := got.get(key)))
    status["Article text"] = (f"fetched for {got['fetched']} of {got['total']} chosen stories"
                              + (f" (missing: {why})" if why else "")
                              + ("" if gnewsdecoder else "; tip: pip install googlenewsdecoder resolves more Google News links"))

    # 4. writing (parallel batches) and post copy at the same time
    stories_ai, post_raw = {}, {}
    if client is not None and card_ids:
        print(f"  - Asking Sarvam AI to write {len(card_ids)} stories and the post copy (in parallel)...")
        write_deadline = time.monotonic() + CAROUSEL_WRITE_DEADLINE
        poster = ThreadPoolExecutor(max_workers=1)
        try:
            post_future = poster.submit(_carousel_ai_json, client, model, _carousel_post_prompt(day),
                                        _carousel_post_user(day, plan), "caption", 1500)
            stories_ai, write_problems = write_carousel_stories(client, model, day, [by_id[c] for c in card_ids],
                                                                write_deadline)
            problems += [f"writing: {p}" for p in write_problems]
            try:
                post_raw = _norm_post(post_future.result(timeout=max(0.5, write_deadline - time.monotonic())))
            except Exception as e:
                problems.append("post copy: " + ("took too long" if type(e).__name__ == "TimeoutError" else _short_error(e)))
        finally:
            poster.shutdown(wait=False, cancel_futures=True)
    timing["AI and article text"] = time.monotonic() - t1

    written = sum(1 for c in card_ids if _as_text((stories_ai.get(c) or {}).get("summary")))
    used_template = written == 0
    if client is None:
        status["Draft"] = "Sarvam not available; stories chosen by coverage, writing left to the editor"
    elif not cands["mains"]:
        status["Draft"] = "no stories found"
    else:
        status["Draft"] = (f"{'stories chosen by Sarvam AI' if from_ai else 'stories chosen by coverage'}; "
                           f"{written} of {len(card_ids)} summaries written by Sarvam AI"
                           + (f" (the rest use an extract of the article, flagged)" if written < len(card_ids) else "")
                           + " -- DRAFT, pending editorial checks"
                           + (f"; problems: {'; '.join(problems)[:300]}" if problems else ""))
    final = {"top_story": plan["slides"][1]["cards"][0]["cid"] if plan["slides"][1]["cards"] else "",
             "slides": {sl["key"]: [c["cid"] for c in sl["cards"]] for sl in plan["slides"] if sl["key"] in CAROUSEL_STORY_SLIDES},
             "briefs": [b["cid"] for sl in plan["slides"] for b in sl["briefs"]],
             "stories": stories_ai, **{k: post_raw.get(k) for k in ("hook", "caption", "hashtags", "takeaway",
                                                                     "follow_prompt", "alt_text") if post_raw.get(k)}}
    try:
        c = assemble_carousel(final, cands, day, used_template, status)
    except Exception as e:   # last resort: never end without a draft -- rebuild from coverage alone
        status["Draft"] = (f"the AI-assisted draft could not be assembled ({_short_error(e)}); rebuilt from coverage "
                           "with all writing left to the editor")
        c = assemble_carousel(_template_carousel_raw(cands), cands, day, True, status)
    c["notes"] = plan["notes"] + [n for n in c["notes"] if n not in plan["notes"]]
    timing["total"] = time.monotonic() - t0
    status["Timing"] = ", ".join(f"{k} {v:.0f}s" for k, v in timing.items())
    return c


_CAROUSEL_TRIGGER = re.compile(r"\bcarousel\b", re.I)


def detect_carousel_request(text: str) -> bool:
    return bool(_CAROUSEL_TRIGGER.search(text or ""))


def carousel_title(c: dict) -> str:
    return f"DRAFT Daily News Carousel \u2014 {c['day']:%A, %d %B %Y}"


def _md_src(r: dict) -> str:
    tag = {"primary": " (primary source)", "established": "", "other": " (not an established outlet)"}[r["kind"]]
    note = "" if r["direct"] else " _(Google News link)_"
    return f"[{_md_link_text(r['name'])}]({_md_url(r['url'])}){tag}{note}"


def carousel_slide_markdown(c: dict, sl: dict) -> list:
    """Markdown lines for one slide's content (shared by the saved file and the app)."""
    L = []
    if sl["key"] == "cover":
        L += [f"**Daily News Wrap-Up** \u00b7 {c['day']:%A, %d %B %Y}", "", f"**Hook:** {c['post']['hook']}", ""]
    elif sl["key"] == "takeaway":
        L += [f"**Takeaway:** {c['post']['takeaway'] or '_editor to write_'}", "",
              f"**Follow prompt:** {c['post']['follow_prompt']}", ""]
    if sl["note"]:
        L += [f"_{sl['note']}_", ""]
    for card in sl["cards"]:
        L += [f"### {card['headline']}", "",
              f"- **Summary** ({card['summary_words']} words): {card['summary'] or '_editor to write_'}",
              "- **Key facts:**"] + [f"  - {f}" for f in card["key_facts"]]
        if card["context"]:
            L.append(f"- **Context:** {card['context']}")
        if card["related_states"]:
            L.append(f"- **\U0001F4CD Related to:** {', '.join(card['related_states'])}")
        L += [f"- **Category:** {card['category']}",
              f"- **Event date:** {card['event_date']} \u00b7 **First published:** {card['published']}",
              "- **Sources:** " + " \u00b7 ".join(_md_src(r) for r in card["sources"]),
              f"- **Verification status:** {card['verification']}",
              f"- **Suggested visual:** {card['visual']}", f"  - _Usage: {card['visual_rules']}_"]
        if card["flags"]:
            L += ["- **\u26a0\ufe0f Editor flags:**"] + [f"  - {f}" for f in card["flags"]]
        L.append("")
    for b in sl["briefs"]:
        L.append(f"- **{b['headline']}**" + (f" \U0001F4CD {', '.join(b['related_states'])}" if b["related_states"] else "")
                 + " \u2014 " + " \u00b7 ".join(_md_src(r) for r in b["sources"][:3])
                 + f"  \n  _{b['verification']}_")
    if sl["briefs"]:
        L.append("")
    return L


def carousel_markdown(c: dict) -> str:
    L = [f"# {carousel_title(c)}", "", f"> \u26a0\ufe0f **{c['notice']}**", "", f"_Generated {c['generated']}_", ""]
    if c["used_template"]:
        L += ["> Sarvam AI wasn't available: stories were chosen by coverage and all writing is left to the editor.", ""]
    for sl in c["slides"]:
        L += ["---", "", f"## Slide {sl['n']} \u2014 {sl['title']}", ""] + carousel_slide_markdown(c, sl)
    p = c["post"]
    L += ["---", "", "## Post copy", "", f"**Opening hook:** {p['hook']}", "", f"**Caption:** {p['caption'] or '_editor to write_'}",
          "", "**Hashtags:** " + " ".join(p["hashtags"]), ""]
    if c["post_flags"]:
        L += ["**\u26a0\ufe0f Editor flags:**"] + [f"- {f}" for f in c["post_flags"]] + [""]
    L += ["## Alt text (accessibility)", ""] + [f"- **Slide {n}:** {a}" for n, a in c["alt_text"].items()] + [""]
    L += ["## Source log (for the editor)", ""]
    for e in c["source_log"]:
        L.append(f"- **[{e['id']}] {e['headline']}** \u2014 {e['category']} \u00b7 {e['outlets']} outlet(s), "
                 f"{e['established']} established \u00b7 first published {e['published']}  \n  _{e['outcome']}_  \n  "
                 + (" \u00b7 ".join(_md_src(r) for r in e["sources"]) or "no links"))
    L.append("")
    if c["notes"]:
        L += ["## Selection notes", ""] + [f"- {n}" for n in c["notes"]] + [""]
    L += ["## Editorial checklist (complete before approval)", ""] + [f"- [ ] {x}" for x in c["checklist"]] + [""]
    L += ["## Sources checked", ""] + [f"- **{k}:** {v}" for k, v in c["status"].items()] + [""]
    return "\n".join(L)


def print_carousel(c: dict) -> None:
    bar, rule = "=" * 70, "-" * 70
    print(f"\n{bar}\n{carousel_title(c).upper()}\n{bar}")
    print(_wrap(c["notice"]))
    for sl in c["slides"]:
        print(f"\nSLIDE {sl['n']} -- {sl['title'].upper()}\n{rule}")
        if sl["key"] == "cover":
            print(_wrap(f"Daily News Wrap-Up, {c['day']:%A, %d %B %Y}. Hook: {c['post']['hook']}"))
        if sl["key"] == "takeaway":
            print(_wrap(f"Takeaway: {c['post']['takeaway'] or '(editor to write)'}"))
            print(_wrap(f"Follow prompt: {c['post']['follow_prompt']}"))
        if sl["note"]:
            print(_wrap(sl["note"]))
        for card in sl["cards"]:
            print(_wrap(f"\u2022 {card['headline']}" + (f"  [{', '.join(card['related_states'])}]" if card["related_states"] else ""),
                        70, "  "))
            print(_wrap(f"Summary ({card['summary_words']} words): {card['summary'] or '(editor to write)'}", 70, "    "))
            for f in card["key_facts"]:
                print(_wrap(f"- {f}", 70, "      "))
            print(_wrap(f"Event date: {card['event_date']} | First published: {card['published']}", 70, "    "))
            print(_wrap(f"Status: {card['verification']}", 70, "    "))
            for r in card["sources"][:4]:
                print(f"      {r['name']}: {r['url']}")
            for f in card["flags"]:
                print(_wrap(f"FLAG: {f}", 70, "    "))
        for b in sl["briefs"]:
            print(_wrap(f"\u2022 {b['headline']} -- {b['sources'][0]['name'] if b['sources'] else ''}", 70, "  "))
    print(f"\nPOST COPY\n{rule}")
    for k in ("hook", "caption"):
        print(_wrap(f"{k.title()}: {c['post'][k] or '(editor to write)'}"))
    print(_wrap("Hashtags: " + " ".join(c["post"]["hashtags"])))
    print(f"\nEDITORIAL CHECKLIST\n{rule}")
    for x in c["checklist"]:
        print(_wrap(f"[ ] {x}"))
    print(f"\nSOURCES CHECKED\n{rule}")
    for k, v in c["status"].items():
        print(_wrap(f"{k}: {v}"))
    print()


def _carousel_filename(c: dict, ext: str) -> str:
    os.makedirs("reports", exist_ok=True)
    return os.path.join("reports", f"DRAFT_carousel_{c['day']:%Y%m%d}_{datetime.now():%H%M%S}.{ext}")


def save_carousel_markdown(c: dict) -> str:
    path = _carousel_filename(c, "md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(carousel_markdown(c))
    return path


def save_carousel_pdf(c: dict) -> str:
    if SimpleDocTemplate is None:
        raise RuntimeError("reportlab isn't installed. Run:  pip install reportlab")
    path = _carousel_filename(c, "pdf")
    styles = _pdf_styles()
    bullet = ParagraphStyle("CarBullet", parent=styles["BodyText"], fontSize=9.5, leading=13, leftIndent=14,
                            bulletIndent=4, spaceAfter=2)
    flag = ParagraphStyle("CarFlag", parent=bullet, textColor=colors.HexColor("#8a2a2a"))
    width = 6.5 * inch

    def banner(text, bg, fg="#000000"):
        t = Table([[Paragraph(f"<font color='{fg}'><b>{xml_escape(text)}</b></font>", styles["Body"])]], colWidths=[width])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg)), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        return t

    def links(recs):
        return " \u00b7 ".join(_pdf_link(r["url"], r["name"] + (" (primary)" if r["kind"] == "primary" else "")) for r in recs)

    S = [Paragraph(xml_escape(carousel_title(c)), styles["ReportTitle"]),
         Paragraph(f"Generated {c['generated']}", styles["Meta"]), banner(c["notice"], "#fde2e2", "#8a2a2a"), Spacer(1, 6)]
    for sl in c["slides"]:
        S += [Spacer(1, 6), banner(f"Slide {sl['n']} \u2014 {sl['title']}", "#1f3a5f", "#ffffff"), Spacer(1, 3)]
        if sl["key"] == "cover":
            S.append(Paragraph(f"<b>Daily News Wrap-Up</b> \u00b7 {c['day']:%A, %d %B %Y}<br/><b>Hook:</b> "
                               f"{xml_escape(c['post']['hook'])}", styles["Body"]))
        if sl["key"] == "takeaway":
            S.append(Paragraph(f"<b>Takeaway:</b> {xml_escape(c['post']['takeaway'] or 'editor to write')}<br/>"
                               f"<b>Follow prompt:</b> {xml_escape(c['post']['follow_prompt'])}", styles["Body"]))
        if sl["note"]:
            S.append(Paragraph(f"<i>{xml_escape(sl['note'])}</i>", styles["Empty"]))
        for card in sl["cards"]:
            S.append(Paragraph(f"<b>{xml_escape(card['headline'])}</b>", styles["SubSection"]))
            items = [f"<b>Summary</b> ({card['summary_words']} words): {xml_escape(card['summary'] or 'editor to write')}"]
            items += [f"<b>Key fact:</b> {xml_escape(f)}" for f in card["key_facts"]]
            if card["context"]:
                items.append(f"<b>Context:</b> {xml_escape(card['context'])}")
            if card["related_states"]:
                items.append(f"<b>Related to:</b> {xml_escape(', '.join(card['related_states']))}")
            items += [f"<b>Event date:</b> {xml_escape(card['event_date'])} \u00b7 <b>First published:</b> {xml_escape(card['published'])}",
                      f"<b>Sources:</b> {links(card['sources'])}",
                      f"<b>Verification status:</b> {xml_escape(card['verification'])}",
                      f"<b>Suggested visual:</b> {xml_escape(card['visual'])} <i>({xml_escape(card['visual_rules'])})</i>"]
            S += [Paragraph(x, bullet, bulletText="\u2022") for x in items]
            S += [Paragraph(f"FLAG: {xml_escape(f)}", flag, bulletText="!") for f in card["flags"]]
        for b in sl["briefs"]:
            S.append(Paragraph(f"<b>{xml_escape(b['headline'])}</b> \u2014 {links(b['sources'][:3])}", bullet,
                               bulletText="\u2022"))
    p = c["post"]
    S += [Paragraph("Post copy", styles["Section"]),
          Paragraph(f"<b>Opening hook:</b> {xml_escape(p['hook'])}", styles["Body"]),
          Paragraph(f"<b>Caption:</b> {xml_escape(p['caption'] or 'editor to write')}", styles["Body"]),
          Paragraph(f"<b>Hashtags:</b> {xml_escape(' '.join(p['hashtags']))}", styles["Body"])]
    S += [Paragraph(f"FLAG: {xml_escape(f)}", flag, bulletText="!") for f in c["post_flags"]]
    S.append(Paragraph("Alt text (accessibility)", styles["Section"]))
    S += [Paragraph(f"<b>Slide {n}:</b> {xml_escape(a)}", bullet, bulletText="\u2022") for n, a in c["alt_text"].items()]
    S.append(Paragraph("Source log (for the editor)", styles["Section"]))
    for e in c["source_log"]:
        S.append(Paragraph(f"<b>[{xml_escape(e['id'])}] {xml_escape(e['headline'])}</b> \u2014 {xml_escape(e['category'])}, "
                           f"{e['outlets']} outlet(s), {e['established']} established, first published "
                           f"{xml_escape(e['published'])}. <i>{xml_escape(e['outcome'])}</i><br/>{links(e['sources'])}",
                           bullet, bulletText="\u2022"))
    if c["notes"]:
        S.append(Paragraph("Selection notes", styles["Section"]))
        S += [Paragraph(xml_escape(n), bullet, bulletText="\u2022") for n in c["notes"]]
    S.append(Paragraph("Editorial checklist (complete before approval)", styles["Section"]))
    S += [Paragraph(xml_escape(x), bullet, bulletText="\u2610") for x in c["checklist"]]
    S.append(Paragraph("Sources checked", styles["Section"]))
    S += [Paragraph(f"<b>{xml_escape(k)}:</b> {xml_escape(v)}", styles["ItemMeta"]) for k, v in c["status"].items()]
    SimpleDocTemplate(path, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                      title=carousel_title(c)).build(S)
    return path


# --------------------------------------------------------------------------
# Carousel: editorial review and FINAL slides (PowerPoint, CamPen template)
# --------------------------------------------------------------------------
# The draft carousel is turned into an editable review: the editor checks and
# edits every story, adds licensed images with credits, completes the
# checklist and approves. Only an approved review can be built into the final
# PowerPoint, laid out exactly like the CamPen Media master template
# (TNW_Mastertemplate.pdf): 3:4 portrait, 810 x 1080 pt, the template's nine slides plus Sports --
#   1 cover  2 top story  3 national  4 state (AP & Telangana)  5 world
#   6 business & technology  7 sports  8 in brief  9 today's takeaway  10 sources (QR)
# in English, and in Telugu from a reviewed Sarvam translation.
#
# The template's brand artwork (backgrounds, logos, globe, pillars, dividers,
# fixed lettering) is in the carousel_assets/ folder next to this file, taken
# from the master template itself. Everything that changes daily is real,
# editable PowerPoint text.

try:
    from pptx import Presentation
    from pptx.util import Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn
except ImportError:          # pip install python-pptx
    Presentation = None

import io as _io
import copy as _copy

CAROUSEL_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "carousel_assets")
DECK_W, DECK_H = 810, 1080            # points: the template's 3:4 portrait page
DECK_TOP, DECK_BOTTOM = 112, 982      # content area of the light slides (between header and footer rules)

# Colours measured from the master template.
DECK_COLORS = {
    "navy": "102848", "ink": "081830", "black": "181818", "body": "081028", "blue": "1058C0",
    "chip_blue": "0C60D0", "chip_red": "CC0404", "chip_teal": "044C50", "chip_world": "184CD0",
    "telangana": "0850D0", "andhra": "C02828", "brief_num": "084040", "white": "F8F8F8", "qr_bg": "FFFFFF",
}
# Fonts the master template uses. PowerPoint uses these if they're installed on the computer that opens the
# deck (they are all available in Canva, so a deck imported into Canva keeps them); otherwise PowerPoint
# substitutes. Free downloads: Inter, Heebo, Noto Sans Telugu, Ramabhadra (Google Fonts), Neue Montreal
# (Pangram Pangram). Change any of them here.
DECK_FONTS = {
    "brand": "Neue Montreal",          # header date, top story, in-brief items
    "sans": "Heebo",                   # national / state headlines and summaries
    "body": "Inter",                   # world / business summaries, cover text
    "serif": "Times New Roman",        # world headlines (the template's TeX Gyre Termes is a Times design)
    "serif_alt": "Brixton TC",         # business & technology headlines, state names
    "display": "Sugo Pro Display",     # takeaway headline, dates on dark slides
    "chip": "Arial",                   # label chips
    "telugu": "Noto Sans Telugu",      # all Telugu text
    "telugu_display": "Ramabhadra",    # Telugu takeaway headline
}

DECK_CHIP_DEFAULTS = {"national": "INDIA", "world": "WORLD AFFAIRS", "business": "BUSINESS & ECONOMY",
                      "tech": "TECHNOLOGY", "health_edu": "HEALTH & EDUCATION", "environment": "ENVIRONMENT",
                      "sports": "SPORTS", "state": ""}
DECK_SECTIONS = [  # key, review title, most stories on the slide
    ("top", "Slide 2 -- Top story", 1), ("national", "Slide 3 -- National developments", 3),
    ("state", "Slide 4 -- State developments: AP & Telangana", 4), ("world", "Slide 5 -- World affairs", 2),
    ("biztech", "Slide 6 -- Business & technology", 3), ("sports", "Slide 7 -- Sports", 3)]
DECK_MAX_BRIEFS = 5
DECK_STATUS_LABELS = {"developing": "DEVELOPING", "allegation": "ALLEGATION", "disputed": "DISPUTED"}
DECK_FOLLOW_DEFAULT = "Follow CamPen Media for tomorrow's wrap-up. Share this with someone who'd find it useful."
DECK_DEVELOPING_NOTE = "Details may change as these stories develop."

# Telugu for the fixed labels (the template's own wording where it has one). Every Telugu line can still be
# edited in the review before the Telugu deck is built.
TE_LABELS = {
    "TOP STORY": "ముఖ్య వార్త", "NATIONAL": "జాతీయ", "INDIA": "భారతదేశం", "COURTS": "న్యాయస్థానాలు",
    "DEVELOPING": "అభివృద్ధి", "ALLEGATION": "ఆరోపణ", "DISPUTED": "వివాదాస్పదం", "STATE": "రాష్ట్రాలు",
    "TELANGANA": "తెలంగాణ", "ANDHRA PRADESH": "ఆంధ్రప్రదేశ్", "AP & TELANGANA": "ఆంధ్రప్రదేశ్ & తెలంగాణ",
    "WORLD AFFAIRS": "ప్రపంచ వ్యవహారాలు", "BUSINESS & ECONOMY": "వ్యాపారం & ఆర్థికం", "TECHNOLOGY": "సాంకేతికత",
    "CYBERSECURITY": "సైబర్ భద్రత", "HEALTH & EDUCATION": "ఆరోగ్యం & విద్య", "ENVIRONMENT": "పర్యావరణం",
    "SPORTS": "క్రీడలు", "SOURCES:": "మూలాలు:", "IMAGE CREDITS:": "ఇమేజ్ క్రెడిట్:",
    DECK_DEVELOPING_NOTE: "ఈ వార్తలు కొనసాగుతున్నందున వివరాలు మారవచ్చు.",
    DECK_FOLLOW_DEFAULT: "రేపటి వార్తల సంక్షిప్తం కోసం క్యామ్‌పెన్ మీడియాను ఫాలో అవ్వండి. ఈ పోస్ట్‌ను ఉపయోగకరంగా భావించే వారితో షేర్ చేయండి.",
}
TE_DAYS = ["సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం"]
TE_MONTHS = ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్",
             "నవంబర్", "డిసెంబర్"]


def te_label(text: str) -> str:
    """Telugu for a fixed label or chip ("INDIA - COURTS", "WORLD AFFAIRS"); unknown words stay as they are."""
    t = (text or "").strip()
    if t in TE_LABELS:
        return TE_LABELS[t]
    if t.upper() in TE_LABELS:
        return TE_LABELS[t.upper()]
    parts = re.split(r"(\s*[·\-–&]\s*)", t)
    return "".join(TE_LABELS.get(p.strip().upper(), p) if p.strip() and not re.fullmatch(r"\s*[·\-–&]\s*", p) else p
                   for p in parts)


def _deck_category_key(label: str) -> str:
    inv = {v: k for k, v in CAROUSEL_CATEGORY_LABELS.items()}
    return inv.get(label, "national")


def _deck_status(verification: str) -> str:
    v = verification or ""
    return ("allegation" if "ALLEGATION" in v else "disputed" if "DISPUTED" in v
            else "developing" if "DEVELOPING" in v else "")


# ---------------------------------------------------------------- review state
def carousel_edit_state(c: dict) -> dict:
    """The draft carousel as an editable review, in the template's slide structure (plus a Sports slide)."""
    slides = {sl["key"]: sl for sl in c["slides"]}

    def story(card, section, include=True):
        cat = _deck_category_key(card["category"])
        return {"id": card["cid"], "section": section, "include": include,
                "chip": DECK_CHIP_DEFAULTS.get(cat, "") or "", "status": _deck_status(card["verification"]),
                "state": (card.get("related_states") or [""])[0] if section == "state" else "",
                "headline": card["headline"], "summary": card["summary"],
                "bullets": [f for f in card["key_facts"][:3] if f] if section == "top" else [],
                "sources": [r["name"] for r in card["sources"]], "links": [{"name": r["name"], "url": r["url"]}
                                                                           for r in card["sources"]],
                "image_caption": "", "image_credit": "", "flags": list(card["flags"]),
                "verification": card["verification"], "te": {}}

    stories = []
    for key, src in (("top", "top"), ("national", "national"), ("state", "state"), ("world", "world")):
        stories += [story(card, key) for card in slides.get(src, {}).get("cards", [])]
    biz = slides.get("business", {}).get("cards", []) + slides.get("more", {}).get("cards", [])
    stories += [story(card, "biztech", include=i < 3) for i, card in enumerate(biz)]
    stories += [story(card, "sports") for card in slides.get("sports", {}).get("cards", [])]
    briefs = []
    for b in slides.get("briefs", {}).get("briefs", []):
        names = ", ".join(r["name"] for r in b["sources"][:2])
        note = " An allegation; not yet verified." if "ALLEGATION" in b["verification"] else ""
        briefs.append({"id": b["cid"], "include": True, "text": f"{b['headline'].rstrip('.')}.{note} ({names}).",
                       "links": [{"name": r["name"], "url": r["url"]} for r in b["sources"]], "te": {}})
    takeaway = [x for x in split_sentences(c["post"].get("takeaway") or "") if x.strip()]
    return {"day": c["day"].isoformat(), "cover": {"hook": c["post"]["hook"], "te": {}}, "stories": stories,
            "briefs": briefs, "takeaway": {"headline": takeaway[0] if takeaway else "",
                                           "detail": " ".join(takeaway[1:]), "follow": DECK_FOLLOW_DEFAULT, "te": {}},
            "sources_url": "", "checklist": {item: False for item in CAROUSEL_CHECKLIST}, "approver": "",
            "draft_notes": list(c.get("notes") or [])}


def deck_section_stories(edit: dict, section: str, included_only: bool = True) -> list:
    return [s for s in edit["stories"] if s["section"] == section and (s["include"] or not included_only)]


# ---------------------------------------------------------------- text measuring (for fitting text to slides)
_FONT_DIRS = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"), os.path.expanduser("~/Library/Fonts"),
              "/Library/Fonts", "/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/usr/share/fonts",
              "/usr/local/share/fonts", os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")]
_MEASURE_FILES = {   # metric stand-ins used only to MEASURE text (the deck itself names DECK_FONTS)
    ("sans", False): ["arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"],
    ("sans", True): ["arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
    ("serif", False): ["times.ttf", "Times New Roman.ttf", "LiberationSerif-Regular.ttf", "texgyretermes-regular.otf"],
    ("serif", True): ["timesbd.ttf", "Times New Roman Bold.ttf", "LiberationSerif-Bold.ttf", "texgyretermes-bold.otf"],
    ("display", False): ["DejaVuSansCondensed.ttf", "arialn.ttf", "LiberationSansNarrow-Regular.ttf"],
    ("display", True): ["DejaVuSansCondensed-Bold.ttf", "arialnb.ttf", "LiberationSansNarrow-Bold.ttf"],
    ("telugu", False): ["NotoSansTelugu-Regular.ttf", "Nirmala.ttc", "Nirmala.ttf", "gautami.ttf", "Lohit-Telugu.ttf"],
    ("telugu", True): ["NotoSansTelugu-Bold.ttf", "NirmalaB.ttf", "Nirmala.ttc", "gautamib.ttf", "Lohit-Telugu.ttf"],
}
_HEURISTIC_WIDTH = {"sans": 0.60, "serif": 0.50, "display": 0.60, "telugu": 0.55}
# False (default): text is measured as if the computer opening the deck does NOT have the template fonts and
# substitutes a wide one -- text then always fits, at the cost of being a little smaller than the template when
# the fonts ARE installed. Set True if every computer (or Canva) that opens the decks has the DECK_FONTS.
DECK_FONTS_INSTALLED = False
_WIDE_FILES = {  # (kind, bold): [(file, width factor)] -- DejaVu is among the widest common substitutes
    ("sans", False): [("DejaVuSans.ttf", 1.0), ("arial.ttf", 1.15), ("Arial.ttf", 1.15), ("LiberationSans-Regular.ttf", 1.15)],
    ("sans", True): [("DejaVuSans-Bold.ttf", 1.0), ("arialbd.ttf", 1.15), ("Arial Bold.ttf", 1.15), ("LiberationSans-Bold.ttf", 1.15)],
    ("serif", False): [("LiberationSerif-Regular.ttf", 1.03), ("times.ttf", 1.03), ("Times New Roman.ttf", 1.03)],
    ("serif", True): [("LiberationSerif-Bold.ttf", 1.03), ("timesbd.ttf", 1.03), ("Times New Roman Bold.ttf", 1.03)],
}
_FONT_PATHS, _MEASURE_CACHE = None, {}


def _font_index() -> dict:
    global _FONT_PATHS
    if _FONT_PATHS is None:
        _FONT_PATHS = {}
        for d in _FONT_DIRS:
            if os.path.isdir(d):
                for root, _dirs, files in os.walk(d):
                    for f in files:
                        _FONT_PATHS.setdefault(f.lower(), os.path.join(root, f))
    return _FONT_PATHS


def _measure_font(kind: str, bold: bool, size: float):
    """(PIL font, width factor) used to MEASURE text, or (None, 1.0) for the character-count estimate."""
    key = (kind, bold, round(size * 4), DECK_FONTS_INSTALLED)
    if key not in _MEASURE_CACHE:
        found = (None, 1.0)
        candidates = ([(f, 1.03) for f in _MEASURE_FILES.get((kind, bold), [])] if DECK_FONTS_INSTALLED
                      else _WIDE_FILES.get((kind, bold), [(f, 1.03) for f in _MEASURE_FILES.get((kind, bold), [])]))
        try:
            from PIL import ImageFont
            for name, factor in candidates:
                path = _font_index().get(name.lower())
                if path:
                    found = (ImageFont.truetype(path, max(1, int(round(size * 4)))), factor)   # 4x for precision
                    break
        except Exception:
            found = (None, 1.0)
        _MEASURE_CACHE[key] = found
    return _MEASURE_CACHE[key]


def _text_width(text: str, size: float, kind: str, bold: bool) -> float:
    font, factor = _measure_font(kind, bold, size)
    if font is not None:
        try:
            return font.getlength(text) / 4.0 * factor
        except Exception:
            pass
    return len(text) * size * _HEURISTIC_WIDTH[kind] * (1.06 if bold else 1.0)


def _line_count(text: str, size: float, width: float, kind: str, bold: bool) -> int:
    lines = 0
    for para in (text or "").split("\n"):
        words, cur = para.split(), ""
        n = 1
        for w in words:
            trial = (cur + " " + w).strip()
            if cur and _text_width(trial, size, kind, bold) > width:
                n, cur = n + 1, w
            else:
                cur = trial
        lines += n
    return max(1, lines)


def _text_height(text, size, width, kind, bold, spacing=1.0) -> float:
    return _line_count(text, size, width, kind, bold) * size * 1.2 * spacing


def _is_telugu(text: str) -> bool:
    return bool(re.search(r"[\u0C00-\u0C7F]", text or ""))


# ---------------------------------------------------------------- drawing on a slide (or just measuring)
class _DeckCanvas:
    """Draws on a slide -- or, with slide=None, only measures, so each slide can be laid out at several text
    scales until it fits."""

    def __init__(self, slide, lang: str, images: dict, scale: float = 1.0):
        self.slide, self.lang, self.images, self.k = slide, lang, images or {}, scale

    def font_for(self, role: str) -> str:
        if self.lang == "te":
            return DECK_FONTS["telugu_display"] if role == "display" else DECK_FONTS["telugu"]
        return DECK_FONTS[role]

    def kind_for(self, role: str) -> str:
        if self.lang == "te":
            return "telugu"
        if DECK_FONTS_INSTALLED:
            return {"serif": "serif", "serif_alt": "serif", "display": "display"}.get(role, "sans")
        # Without the template fonts, Brixton TC and Sugo Pro Display fall back to a wide sans: measure as one.
        return "serif" if role == "serif" else "sans"

    def image(self, name, x, y, w, h):
        if self.slide is not None:
            self.slide.shapes.add_picture(os.path.join(CAROUSEL_ASSETS_DIR, f"{name}.png"), Pt(x), Pt(y), Pt(w), Pt(h))

    def crop(self, name):
        geom = _deck_crops()[name]
        self.image(name, *geom)

    def picture(self, data: bytes, x, y, w, h) -> tuple:
        """A user image fitted inside the box (aspect kept, left-aligned); returns (w, h) used."""
        from PIL import Image
        im = Image.open(_io.BytesIO(data))
        iw, ih = im.size
        r = min(w / iw, h / ih)
        pw, ph = iw * r, ih * r
        if self.slide is not None:
            buf = _io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=90)
            buf.seek(0)
            self.slide.shapes.add_picture(buf, Pt(x), Pt(y), Pt(pw), Pt(ph))
        return pw, ph

    def text(self, x, y, w, runs, size, role="body", color="body", bold=False, italic=False, align="left",
             spacing=1.0, scaled=True, h=None, anchor="top") -> float:
        """Paragraph(s) of text; `runs` is a string or [(text, {overrides})]. Returns the height used."""
        size = size * self.k if scaled else size
        if isinstance(runs, str):
            runs = [(runs, {})]
        full = "".join(t for t, _ in runs)
        height = _text_height(full, size, w, self.kind_for(role), bold, spacing)
        if self.slide is not None and full.strip():
            box = self.slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h if h is not None else height + size * 0.35))
            tf = box.text_frame
            tf.word_wrap = True
            tf.auto_size = MSO_AUTO_SIZE.NONE
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}[anchor]
            first = True
            for chunk_i, (t, opt) in enumerate(runs):
                for li, line in enumerate(t.split("\n")):
                    if li > 0 or first:
                        p = tf.paragraphs[0] if first else tf.add_paragraph()
                        first = False
                        p.alignment = {"left": PP_ALIGN.LEFT, "right": PP_ALIGN.RIGHT, "center": PP_ALIGN.CENTER,
                                       "justify": PP_ALIGN.JUSTIFY}[align]
                        p.line_spacing = spacing
                    if not line:
                        continue
                    r = p.add_run()
                    r.text = line
                    f = r.font
                    f.size = Pt(opt.get("size", size))
                    f.bold = opt.get("bold", bold)
                    f.italic = opt.get("italic", italic)
                    f.color.rgb = RGBColor.from_string(DECK_COLORS.get(opt.get("color", color), opt.get("color", color)))
                    _deck_set_font(r, self.font_for(opt.get("role", role)), _is_telugu(line) or self.lang == "te")
                    if opt.get("link"):
                        r.hyperlink.address = opt["link"]
        return height

    def chip(self, x, y, label, fill="chip_blue", size=22, scaled=True) -> tuple:
        """A rounded label chip sized to its text; returns (w, h)."""
        size = size * self.k if scaled else size
        label = label.strip()
        w = _text_width(label, size, self.kind_for("chip"), True) + size * 1.6
        h = size * 2.0
        if self.slide is not None and label:
            shp = self.slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Pt(x), Pt(y), Pt(w), Pt(h))
            shp.adjustments[0] = 0.12
            shp.fill.solid()
            shp.fill.fore_color.rgb = RGBColor.from_string(DECK_COLORS[fill])
            shp.line.fill.background()
            shp.shadow.inherit = False
            tf = shp.text_frame
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            r = p.add_run()
            r.text = label
            r.font.size, r.font.bold = Pt(size), True
            r.font.color.rgb = RGBColor.from_string("FFFFFF")
            _deck_set_font(r, self.font_for("chip"), _is_telugu(label) or self.lang == "te")
        return (w, h) if label else (0, 0)


def _deck_set_font(run, name: str, telugu: bool) -> None:
    run.font.name = name
    if telugu:     # Telugu is a "complex script": PowerPoint takes its font from <a:cs>
        rpr = run._r.get_or_add_rPr()
        rpr.set("lang", "te-IN")
        cs = rpr.find(qn("a:cs"))
        if cs is None:
            from lxml import etree
            cs = etree.SubElement(rpr, qn("a:cs"))
            hl = rpr.find(qn("a:hlinkClick"))
            if hl is not None:              # schema order: ... latin, ea, cs, sym, hlinkClick
                hl.addprevious(cs)
        cs.set("typeface", name)


_DECK_CROPS = None


def _deck_crops() -> dict:
    global _DECK_CROPS
    if _DECK_CROPS is None:
        with open(os.path.join(CAROUSEL_ASSETS_DIR, "crops.json"), encoding="utf-8") as f:
            _DECK_CROPS = json.load(f)
    return _DECK_CROPS


# ---------------------------------------------------------------- the slides
def _deck_text(edit_item: dict, field: str, lang: str) -> str:
    if lang == "te":
        return (edit_item.get("te") or {}).get(field, "")
    v = edit_item.get(field, "")
    return "\n".join(v) if isinstance(v, list) else v


def _deck_bullets(story: dict, lang: str) -> list:
    v = (story.get("te") or {}).get("bullets") if lang == "te" else story.get("bullets")
    if isinstance(v, str):
        v = [x for x in v.split("\n")]
    out = []
    for x in (v or []):
        x = (x or "").strip()
        if x and not any(x.lower() == o.lower() or (lang == "en" and _fact_overlap(x, o) >= 0.6) for o in out):
            out.append(x)
    return out


def _deck_header_light(cv, final, n, total):
    cv.image("bg_light", 0, -7.9, DECK_W, DECK_H)
    cv.image("logo_red", 23.7, -6.5, 101.3, 101.3)
    cv.crop("light_header")
    cv.text(540, 39, 224, f"{_deck_date(final)} \u00b7 {n}/{total}", 19, role="brand", color="navy", bold=True,
            align="right", scaled=False)
    cv.image("divider_header", 30.6, 86.1, 748.5, 14.2)


def _deck_footer_light(cv, stories, lang, with_sources=True):
    cv.image("divider_footer", 30.6, 990.8, 748.5, 14.2)
    cv.crop(f"swipe_{lang}")
    if not with_sources:
        return
    names, links = [], []
    for s in stories:
        for l in s.get("links") or [{"name": n, "url": ""} for n in s.get("sources", [])]:
            if l["name"] not in names:
                names.append(l["name"])
                links.append(l)
    if not names:
        return
    prefix = te_label("SOURCES:") if lang == "te" else "Sources:"
    shown, more = links[:6], len(links) - 6
    runs = [(prefix + " ", {})]
    for i, l in enumerate(shown):
        runs.append((l["name"], {}))
        if i < len(shown) - 1:
            runs.append((", ", {}))
    if more > 0:
        runs.append((f" +{more} more" if lang == "en" else f" +{more}", {}))
    cv.text(39, 1010, 590, runs, 17, role="brand", color="navy", bold=True, scaled=False, h=60)


def _deck_date(final) -> str:
    d = datetime.fromisoformat(final["day"]) if isinstance(final["day"], str) else final["day"]
    return f"{d:%d %b %Y}".upper()


def _deck_long_date(final, lang) -> str:
    d = datetime.fromisoformat(final["day"]) if isinstance(final["day"], str) else final["day"]
    if lang == "te":
        return f"{TE_DAYS[d.weekday()]}, {d.day} {TE_MONTHS[d.month - 1]} {d.year}"
    return f"{d:%A}, {d.day} {d:%B %Y}"


def _deck_story_label(story: dict, lang: str) -> str:
    label = story.get("chip") or ""
    return te_label(label) if lang == "te" else label


def _deck_status_label(story: dict, lang: str) -> str:
    lab = DECK_STATUS_LABELS.get(story.get("status") or "", "")
    return te_label(lab) if (lang == "te" and lab) else lab


def _slide_cover(cv, final, n, total):
    lang = cv.lang
    cv.image("bg_dark", 0, -7.9, DECK_W, DECK_H)
    cv.image("globe", 419.9, 585.8, 390, 486)
    cv.image("logo_white", 30.6, 14.4, 79.5, 79.5)
    cv.crop("cover_header_en")
    cv.text(560, 42, 207, f"{_deck_date(final)} \u00b7 {n}/{total}", 17, role="body", color="white", align="right",
            scaled=False)
    cv.image("logo_big", 192.2, 36.4, 425.2, 425.2)
    cv.crop(f"cover_title_{lang}")
    cv.image("line_cover", 61.9, 707.4, 249.7, 14.2)
    y_date = 735 if lang == "en" else 727
    cv.text(61, y_date, 640, _deck_long_date(final, lang), 34 if lang == "en" else 30, role="body", color="white",
            scaled=False)
    hook = _deck_text(final["cover"], "hook", lang)
    top, bottom = (805, 962) if lang == "en" else (797, 952)
    for size in (34, 32, 30, 28, 26, 24, 22):
        if _text_height(hook, size, 650, cv.kind_for("body"), False, 1.0) <= bottom - top:
            break
    cv.text(61, top, 650, hook, size, role="body", color="white", scaled=False)
    cv.crop(f"cover_swipe_{lang}")
    return bottom - top - _text_height(hook, size, 650, cv.kind_for("body"), False, 1.0)


def _story_block(cv, x, y, w, story, lang, head_size, body_size, head_role, body_role, head_color="ink",
                 body_color="body", image_mode=None, body_align="justify", inline_status=False) -> float:
    """Headline + (image) + summary for one story; returns the new y."""
    headline = _deck_text(story, "headline", lang)
    summary = _deck_text(story, "summary", lang)
    runs = [(headline, {})]
    status = _deck_status_label(story, lang) if inline_status else ""
    if status:
        runs.append(("   " + status, {"color": "andhra", "size": max(14, body_size * cv.k), "role": "chip"}))
    y += cv.text(x, y, w, runs, head_size, role=head_role, color=head_color, bold=True, spacing=0.95) + 10 * cv.k
    img = cv.images.get(story["id"])
    if img and image_mode == "right":
        thumb_w = 175 * cv.k
        pw, ph = cv.picture(img, x + w - thumb_w, y, thumb_w, 210 * cv.k)
        sh = cv.text(x, y, w - thumb_w - 18, summary, body_size, role=body_role, color=body_color, align=body_align,
                     spacing=1.05)
        credit = story.get("image_credit") or ""
        ch = 0
        if credit:
            label = te_label("IMAGE CREDITS:") if lang == "te" else "Image credits:"
            ch = cv.text(x + w - thumb_w, y + ph + 4, thumb_w, f"{label} {credit}", 12, role="body", color="body",
                         scaled=False)
        return y + max(sh, ph + ch + 6) + 6
    sh = cv.text(x, y, w, summary, body_size, role=body_role, color=body_color, align=body_align, spacing=1.05)
    y += sh
    if img and image_mode == "below":
        y += 12 * cv.k
        pw, ph = cv.picture(img, x, y, min(w, 420 * cv.k), 230 * cv.k)
        y += ph + 4
        cap = " \u00b7 ".join(filter(None, [_deck_text(story, "image_caption", lang),
                                             ((te_label("IMAGE CREDITS:") if lang == "te" else "Image credits:")
                                              + " " + story["image_credit"]) if story.get("image_credit") else ""]))
        if cap:
            y += cv.text(x, y, w, cap, 13, role="body", color="body", scaled=False) + 2
    return y


def _slide_top(cv, final, n, total, stories):
    lang = cv.lang
    s = stories[0]
    _deck_header_light(cv, final, n, total)
    y = 124
    label = (te_label("TOP STORY") if lang == "te" else "TOP STORY") + " \u00b7 " + _deck_story_label(s, lang)
    y += cv.text(42, y, 700, label, 24, role="brand", color="blue", bold=True) + 14 * cv.k
    y += cv.text(38, y, 720, _deck_text(s, "headline", lang), 48, role="brand", color="navy", bold=True,
                 spacing=0.95) + 18 * cv.k
    img = cv.images.get(s["id"])
    if img:
        pw, ph = cv.picture(img, 54.4, y, 433.5 * cv.k + 200 * (1 - cv.k), 243.7 * cv.k)
        y += ph + 6
        cap = _deck_text(s, "image_caption", lang)
        credit = s.get("image_credit") or ""
        line = " \u00b7 ".join(filter(None, [cap, ((te_label("IMAGE CREDITS:") if lang == "te" else "Image credits:")
                                                  + " " + credit) if credit else ""]))
        if line:
            y += cv.text(52, y, 600, line, 15, role="brand", color="ink", bold=True, scaled=False)
        y += 18 * cv.k
    y += cv.text(31, y, 717, _deck_text(s, "summary", lang), 22, role="brand", color="body", align="justify",
                 spacing=1.05) + 14 * cv.k
    for b in _deck_bullets(s, lang):
        bh = cv.text(75, y, 650, b, 21, role="brand", color="body")
        cv.image("bullet_dot", 46.2, y + (21 * cv.k * 1.2 - 27.7) / 2, 16.5, 27.7)
        y += bh + 8 * cv.k
    _deck_footer_light(cv, stories, lang)
    return y


def _slide_flow(cv, final, n, total, stories, kind):
    """National, world and business & technology slides: stacked stories with chips."""
    lang = cv.lang
    _deck_header_light(cv, final, n, total)
    y = 108
    head_role = {"national": "sans", "world": "serif", "biztech": "serif_alt", "sports": "serif_alt"}[kind]
    body_role = {"national": "sans", "world": "body", "biztech": "body", "sports": "body"}[kind]
    head_color = "ink" if kind == "national" else "black"
    developing = False
    for i, s in enumerate(stories):
        if i:
            y += 6 * cv.k
            cv.image("divider_light" if kind in ("biztech", "sports") else "divider_row", 30.6, y, 748.5, 14.2)
            y += 22 * cv.k
        chip_x, chip_h = 46, 0
        own_chip = kind == "sports" and (s.get("chip") or "").strip().upper() not in ("", "SPORTS")
        if kind == "biztech" or i == 0 or own_chip:   # sports: one SPORTS chip on top, unless a story has its own
            fill = "chip_teal" if (kind == "biztech" and s.get("chip", "").upper().startswith("BUSINESS")) else \
                ("chip_world" if kind == "world" else "chip_blue")
            cw, chip_h = cv.chip(chip_x, y, _deck_story_label(s, lang), fill)
            chip_x += cw + 14 if cw else 0
        status = _deck_status_label(s, lang)
        if status:
            cw, ch = cv.chip(chip_x, y, status, "chip_red")
            chip_h = max(chip_h, ch)
        developing = developing or s.get("status") == "developing"
        if chip_h:
            y += chip_h + 12 * cv.k
        bar = s.get("status") == "allegation" and kind == "national"
        x0 = 63 if bar else 42
        head = {"national": 50 if i == 0 else 38, "world": 48, "biztech": 36, "sports": 38}[kind]
        y_start = y
        y = _story_block(cv, x0, y, 720 - (x0 - 42), s, lang, head, 21, head_role, body_role, head_color=head_color,
                         image_mode="right" if kind in ("biztech", "sports") else "below")
        if bar:
            cv.image("bar_blue", 40, y_start - chip_h - 8 * cv.k, 16.5, (y - y_start) + chip_h + 8 * cv.k)
    if developing:
        note = te_label(DECK_DEVELOPING_NOTE) if lang == "te" else DECK_DEVELOPING_NOTE
        y += 12 * cv.k
        y += cv.text(63, y, 680, note, 19, role="chip", color="ink", bold=True, italic=True)
    _deck_footer_light(cv, stories, lang)
    return y


def _slide_state(cv, final, n, total, stories):
    lang = cv.lang
    _deck_header_light(cv, final, n, total)
    states = []
    for s in stories:
        if s.get("state") not in states:
            states.append(s.get("state"))
    order = [st_ for st_ in ("Telangana", "Andhra Pradesh") if st_ in states] + [st_ for st_ in states
                                                                                 if st_ not in ("Telangana", "Andhra Pradesh")]
    title = " & ".join({"Telangana": "TELANGANA", "Andhra Pradesh": "AP"}.get(st_, (st_ or "").upper()) for st_ in order
                       if st_) or "AP & TELANGANA"
    if title == "TELANGANA & AP":
        title = "AP & TELANGANA"
    label = (te_label("STATE") + " \u00b7 " + te_label(title)) if lang == "te" else f"STATE \u00b7 {title}"
    cw, ch = cv.chip(46.2, 104, label, "chip_blue", 26)
    y = 104 + ch + 22 * cv.k
    first = True
    for st_ in order:
        if not first:
            y += 4 * cv.k
            cv.image("divider_row", 60, y, 690, 14.2)
            y += 22 * cv.k
        first = False
        heading = {"Telangana": "TELANGANA", "Andhra Pradesh": "ANDHRA PRADESH"}.get(st_, (st_ or "").upper())
        if heading:
            y += cv.text(54, y, 400, te_label(heading) if lang == "te" else heading, 26, role="serif_alt",
                         color="telangana" if st_ == "Telangana" else "andhra", bold=True) + 8 * cv.k
        group = [s for s in stories if s.get("state") == st_]
        for j, s in enumerate(group):
            if j:
                y += 6 * cv.k
                cv.image("divider_row", 90, y, 650, 14.2)
                y += 20 * cv.k
            y = _story_block(cv, 58, y, 680, s, lang, 30, 21, "sans", "sans", inline_status=True,
                             image_mode="right")
    _deck_footer_light(cv, stories, lang)
    return y


def _slide_briefs(cv, final, n, total, briefs):
    lang = cv.lang
    _deck_header_light(cv, final, n, total)
    cv.crop(f"brief_chip_{lang}")
    cv.crop(f"brief_title_{lang}")
    cv.image("divider_footer", 30.6, 302.7, 748.5, 14.2)
    y = 340
    for i, b in enumerate(briefs, 1):
        if i > 1:
            cv.image("divider_row", 46.2, y - 18 * cv.k, 717.7, 14.2)
        text = _deck_text(b, "text", lang)
        h = cv.text(169, y, 560, text, 24, role="brand", color="black", bold=True)
        cv.text(60, y - 4, 60, f"{i})", 44, role="brand", color="brief_num", bold=True)
        cv.image("brief_bar", 139.5, y - 6, 16.5, max(h + 8, 44 * cv.k * 1.2))
        y += max(h, 44 * cv.k * 1.2) + 36 * cv.k
    cv.image("divider_footer", 30.6, 990.8, 748.5, 14.2)
    cv.crop(f"swipe_{lang}")
    return y - 36 * cv.k


def _deck_header_dark(cv, final, n, total):
    cv.image("bg_dark", 0, -7.9, DECK_W, DECK_H)
    cv.image("pillars", 124.6, 395.6, 685.5, 486.7)
    cv.image("logo_white", 19.5, 9.1, 79.5, 79.5)
    cv.crop("dark_header")
    if cv.slide is not None:
        rule = cv.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(102.5), Pt(30), Pt(1.2), Pt(52))
        rule.fill.solid()
        rule.fill.fore_color.rgb = RGBColor.from_string("C8CCD4")
        rule.line.fill.background()
        rule.shadow.inherit = False
    cv.text(470, 35, 302, f"{_deck_date(final)} \u00b7 {n}/{total}", 20, role="display", color="white", bold=True,
            align="right", scaled=False)


def _slide_takeaway(cv, final, n, total):
    lang = cv.lang
    _deck_header_dark(cv, final, n, total)
    cv.crop(f"takeaway_chip_{lang}")
    t = final["takeaway"]
    head = _deck_text(t, "headline", lang)
    hs = 76
    for hs in (76, 70, 64, 58, 52, 48, 44, 40, 36):
        if _text_height(head, hs, 470, cv.kind_for("display"), True, 0.92) <= 500:
            break
    cv.text(37, 210, 470, head, hs, role="display", color="white", bold=True, spacing=0.92, scaled=False)
    detail = _deck_text(t, "detail", lang)
    ds = 26
    for ds in (26, 24, 22, 20, 18):
        if _text_height(detail, ds, 580, cv.kind_for("chip"), True, 1.0) <= 140:
            break
    cv.text(46, 727, 580, detail, ds, role="chip", color="white", bold=True, scaled=False)
    cv.image("short_bar", 30.6, 882.6, 188.3, 14.2)
    cv.image("share_icon", 46.2, 925.3, 78, 81)
    follow = _deck_text(t, "follow", lang)
    fs = 22
    for fs in (22, 20, 18, 16):
        if _text_height(follow, fs, 560, cv.kind_for("body"), False, 1.0) <= 100:
            break
    cv.text(135, 936, 560, follow, fs, role="body", color="white", scaled=False)
    return min(500 - _text_height(head, hs, 470, cv.kind_for("display"), True, 0.92),
               140 - _text_height(detail, ds, 580, cv.kind_for("chip"), True, 1.0))


def make_qr_png(url: str, box: int = 12, border: int = 4) -> bytes:
    """A QR code for `url` as PNG bytes (reportlab's encoder; error correction level M)."""
    from reportlab.graphics.barcode.qrencoder import QRCode, QRErrorCorrectLevel
    from PIL import Image, ImageDraw
    qr = QRCode(None, QRErrorCorrectLevel.M)   # None = smallest QR version that fits the link
    qr.addData(url)
    qr.make()
    n = qr.getModuleCount()
    size = (n + 2 * border) * box
    im = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(im)
    for r in range(n):
        for c in range(n):
            if qr.isDark(r, c):
                x, y = (c + border) * box, (r + border) * box
                d.rectangle([x, y, x + box - 1, y + box - 1], fill="black")
    buf = _io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _slide_sources(cv, final, n, total, all_links):
    lang = cv.lang
    _deck_header_dark(cv, final, n, total)
    cv.crop(f"sources_chip_{lang}")
    url = (final.get("sources_url") or "").strip()
    if url:
        if cv.slide is not None:
            sq = cv.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Pt(218.7), Pt(333.4), Pt(412.6), Pt(412.6))
            sq.fill.solid()
            sq.fill.fore_color.rgb = RGBColor.from_string("FFFFFF")
            sq.line.fill.background()
            sq.shadow.inherit = False
            cv.slide.shapes.add_picture(_io.BytesIO(make_qr_png(url, border=1)), Pt(236.7), Pt(351.4), Pt(376.6),
                                        Pt(376.6))
        cv.image("share_icon", 110.1, 950.4, 78, 81)
        cv.crop(f"scan_{lang}")
        return 1
    names = []
    for l in all_links:
        if l["name"] not in names:
            names.append(l["name"])
    lines = ", ".join(names[:24])
    cv.text(60, 300, 690, lines, 24, role="body", color="white", bold=True, scaled=False)
    return 1


# ---------------------------------------------------------------- layout: fit every slide
DECK_SCALES = (1.0, 0.94, 0.88, 0.82, 0.76, 0.70, 0.64)


def _deck_plan(final: dict, lang: str = "en") -> list:
    """[(kind, payload)] for the slides that have content, in template order."""
    plan = [("cover", None)]
    for key, _title, _mx in DECK_SECTIONS:
        st_ = deck_section_stories(final, key)
        if st_:
            plan.append((key, st_))
    briefs = [b for b in final["briefs"] if b["include"]][:DECK_MAX_BRIEFS]
    if briefs:
        plan.append(("briefs", briefs))
    plan += [("takeaway", None), ("sources", None)]
    return plan


def _deck_draw(kind, cv, final, n, total, payload, all_links):
    if kind == "cover":
        return _slide_cover(cv, final, n, total)
    if kind == "top":
        return DECK_BOTTOM - _slide_top(cv, final, n, total, payload)
    if kind in ("national", "world", "biztech", "sports"):
        return DECK_BOTTOM - _slide_flow(cv, final, n, total, payload, kind)
    if kind == "state":
        return DECK_BOTTOM - _slide_state(cv, final, n, total, payload)
    if kind == "briefs":
        return DECK_BOTTOM - _slide_briefs(cv, final, n, total, payload)
    if kind == "takeaway":
        return _slide_takeaway(cv, final, n, total)
    return _slide_sources(cv, final, n, total, all_links)


def _deck_fit(kind, final, n, total, payload, lang, images, all_links) -> tuple:
    """(scale, room_left_pt): the largest text scale at which the slide fits; room < 0 means it doesn't."""
    room = -1
    for k in DECK_SCALES:
        room = _deck_draw(kind, _DeckCanvas(None, lang, images, k), final, n, total, payload, all_links)
        if room >= 0:
            return k, room
    return DECK_SCALES[-1], room


def deck_overflow_report(final: dict, images=None, lang: str = "en") -> list:
    """[(slide_number, title, points_over)] for slides whose text cannot fit even at the smallest size."""
    plan = _deck_plan(final, lang)
    links = [l for s in final["stories"] if s["include"] for l in s.get("links", [])]
    out = []
    titles = {"cover": "Cover", "top": "Top story", "national": "National developments", "state": "State developments",
              "world": "World affairs", "biztech": "Business & technology", "sports": "Sports", "briefs": "In brief",
              "takeaway": "Today's takeaway", "sources": "Sources"}
    for i, (kind, payload) in enumerate(plan, 1):
        k, room = _deck_fit(kind, final, i, len(plan), payload, lang, images or {}, links)
        if room < 0:
            out.append((i, titles[kind], int(-room)))
    return out


# ---------------------------------------------------------------- review checks, approval, translation
def review_problems(edit: dict, images=None, lang: str = "en") -> tuple:
    """(errors, warnings). Errors block approval; warnings are shown to the editor."""
    images = images or {}
    errors, warnings = [], []
    included = [s for s in edit["stories"] if s["include"]]
    if not included:
        errors.append("No stories are included -- tick at least one.")
    if not deck_section_stories(edit, "top"):
        errors.append("The top story (slide 2) is not included.")
    for key, title, mx in DECK_SECTIONS:
        n = len(deck_section_stories(edit, key))
        if n > mx:
            errors.append(f"{title.split(' -- ')[1]} has {n} stories ticked; the slide takes at most {mx}.")
    for s in included:
        name = f"\u201c{(s['headline'] or s['id'])[:60]}\u201d"
        if not s["headline"].strip():
            errors.append(f"{s['id']}: the headline is empty.")
        if not s["summary"].strip():
            errors.append(f"{name}: the summary is empty.")
        if s["id"] in images and not s.get("image_credit", "").strip():
            errors.append(f"{name}: an image is added but its credit is empty (image credits are never filled in "
                          "automatically).")
        words = len(s["summary"].split())
        lo, hi = CAROUSEL_SUMMARY_WORDS
        if s["summary"].strip() and not lo <= words <= hi and s["section"] in ("top",):
            warnings.append(f"{name}: the summary is {words} words (the brief asks for {lo}-{hi}).")
        open_flags = [f for f in s.get("flags", []) if not f.startswith("Only headlines")]
        if open_flags:
            warnings.append(f"{name}: draft flags to check -- " + "; ".join(open_flags))
    if len([b for b in edit["briefs"] if b["include"]]) > DECK_MAX_BRIEFS:
        errors.append(f"In brief has more than {DECK_MAX_BRIEFS} items ticked.")
    if not edit["cover"]["hook"].strip():
        errors.append("The cover line (hook) is empty.")
    if not edit["takeaway"]["headline"].strip():
        errors.append("The takeaway headline is empty.")
    url = (edit.get("sources_url") or "").strip()
    if url and not re.match(r"https?://\S+$", url):
        errors.append("The sources link must start with http:// or https:// (it becomes the QR code).")
    if not url:
        warnings.append("No sources link: slide 9 will list the outlets instead of a QR code.")
    for slide_no, title, over in deck_overflow_report(edit, images, lang):
        errors.append(f"Slide {slide_no} ({title}) has too much text by about {over} pt even at the smallest "
                      "size -- shorten it or untick a story.")
    if not all(edit["checklist"].values()):
        errors.append("Complete every item of the editorial checklist.")
    if not (edit.get("approver") or "").strip():
        errors.append("Enter the approving editor's name.")
    return errors, warnings


def finalize_carousel(edit: dict, images=None) -> dict:
    """The approved final carousel (a copy of the review, stamped with who approved it and when).
    Raises ValueError listing what still blocks approval."""
    errors, _ = review_problems(edit, images)
    if errors:
        raise ValueError("Not ready for approval:\n- " + "\n- ".join(errors))
    final = _copy.deepcopy(edit)
    final["approved_by"] = edit["approver"].strip()
    final["approved_at"] = f"{utc_now() + IST_OFFSET:%Y-%m-%d %H:%M} IST"
    return final


def _sarvam_translate(client, text: str) -> str:
    resp = client.text.translate(input=text, source_language_code="en-IN", target_language_code="te-IN",
                                 model="sarvam-translate:v1")
    out = getattr(resp, "translated_text", None)
    if out is None and isinstance(resp, dict):
        out = resp.get("translated_text")
    if not out or not str(out).strip():
        raise ValueError("empty translation")
    return str(out).strip()


def translate_carousel(edit: dict, client, deadline_s: int = 90) -> list:
    """Fill every Telugu field (edit[...]['te']) with Sarvam translations, in parallel. Fixed labels use the
    template's own Telugu wording. Returns problems (fields left untranslated) -- those keep the English text
    so the editor can see and fix them in the Telugu review."""
    from concurrent.futures import ThreadPoolExecutor, wait
    jobs = []
    for s in edit["stories"]:
        if not s["include"]:
            continue
        for field in ("headline", "summary", "image_caption"):
            if s.get(field, "").strip():
                jobs.append((s["te"], field, s[field]))
        for i, b in enumerate(s.get("bullets") or []):
            if b.strip():
                s["te"].setdefault("bullets", [""] * len(s["bullets"]))
                jobs.append((s["te"]["bullets"], i, b))
    for b in edit["briefs"]:
        if b["include"] and b["text"].strip():
            jobs.append((b["te"], "text", b["text"]))
    jobs.append((edit["cover"]["te"], "hook", edit["cover"]["hook"]))
    t = edit["takeaway"]
    for field in ("headline", "detail", "follow"):
        if t.get(field, "").strip():
            if t[field].strip() in TE_LABELS:
                t["te"][field] = TE_LABELS[t[field].strip()]
            else:
                jobs.append((t["te"], field, t[field]))
    problems = []

    def run(job):
        target, key, text = job
        try:
            target[key] = _sarvam_translate(client, text[:1900])
        except Exception as e:
            target[key] = text
            problems.append(f"\u201c{text[:50]}\u201d: {_short_error(e)}")

    pool = ThreadPoolExecutor(max_workers=6)
    try:
        futures = [pool.submit(run, j) for j in jobs]
        done, late = wait(futures, timeout=deadline_s)
        for f in late:
            problems.append("a translation ran out of time")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    for target, key, text in jobs:
        if isinstance(target, dict) and key not in target:
            target[key] = text
    return problems


def telugu_missing(edit: dict) -> list:
    """Telugu fields still empty or still in English (to fix before building the Telugu deck)."""
    out = []

    def check(where, en, te):
        if en.strip() and (not te.strip() or not _is_telugu(te)):
            out.append(f"{where}: \u201c{en[:50]}\u201d")
    for s in edit["stories"]:
        if s["include"]:
            check(f"{s['id']} headline", s["headline"], (s["te"] or {}).get("headline", ""))
            check(f"{s['id']} summary", s["summary"], (s["te"] or {}).get("summary", ""))
    for b in edit["briefs"]:
        if b["include"]:
            check(f"brief {b['id']}", b["text"], (b["te"] or {}).get("text", ""))
    check("cover line", edit["cover"]["hook"], edit["cover"]["te"].get("hook", ""))
    check("takeaway headline", edit["takeaway"]["headline"], edit["takeaway"]["te"].get("headline", ""))
    return out


# ---------------------------------------------------------------- build the PowerPoint
def build_carousel_pptx(final: dict, images=None, lang: str = "en") -> bytes:
    """The final carousel as a PowerPoint (.pptx) in the CamPen master-template format. `final` must come from
    finalize_carousel(); `images` maps story ids to image bytes the editor uploaded."""
    if Presentation is None:
        raise RuntimeError("python-pptx isn't installed. Run:  pip install python-pptx")
    if not os.path.isdir(CAROUSEL_ASSETS_DIR):
        raise RuntimeError(f"The carousel_assets folder is missing (expected at {CAROUSEL_ASSETS_DIR}).")
    if not final.get("approved_by"):
        raise ValueError("Only an approved carousel can be built into final slides (use finalize_carousel).")
    if lang == "te":
        missing = telugu_missing(final)
        if missing:
            raise ValueError("These Telugu fields are not translated yet:\n- " + "\n- ".join(missing[:12]))
    images = images or {}
    prs = Presentation()
    prs.slide_width, prs.slide_height = Pt(DECK_W), Pt(DECK_H)
    blank = prs.slide_layouts[6]
    plan = _deck_plan(final, lang)
    links = [l for s in final["stories"] if s["include"] for l in s.get("links", [])]
    for i, (kind, payload) in enumerate(plan, 1):
        k, _room = _deck_fit(kind, final, i, len(plan), payload, lang, images, links)
        slide = prs.slides.add_slide(blank)
        _deck_draw(kind, _DeckCanvas(slide, lang, images, k), final, i, len(plan), payload, links)
        items = payload if isinstance(payload, list) else []
        notes = [f"{l['name']}: {l['url']}" for it in items for l in it.get("links", [])]
        slide.notes_slide.notes_text_frame.text = ("Sources:\n" + "\n".join(notes)) if notes else \
            f"Approved by {final['approved_by']} at {final['approved_at']}."
    cp = prs.core_properties
    cp.title = f"CamPen Media Daily Wrap {final['day']}" + (" (Telugu)" if lang == "te" else "")
    cp.author = final["approved_by"]
    cp.comments = f"Approved by {final['approved_by']} at {final['approved_at']}."
    buf = _io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def carousel_sources_html(final: dict, lang: str = "en") -> str:
    """A simple web page listing every story's source links -- host it and use its address for the QR code.
    lang="te": the Telugu page, using the reviewed Telugu headlines and briefs (links and outlet names unchanged)."""
    import html as _h
    te = lang == "te"
    d = _deck_long_date(final, lang)

    def head(item, field):
        return (item.get("te") or {}).get(field) or item.get(field, "") if te else item.get(field, "")

    rows = []
    for key, title, _mx in DECK_SECTIONS:
        for s in deck_section_stories(final, key):
            links = "".join(f'<li><a href="{_h.escape(l["url"])}">{_h.escape(l["name"])}</a></li>' for l in s["links"])
            rows.append(f"<h3>{_h.escape(head(s, 'headline'))}</h3><ul>{links}</ul>")
    for b in [b for b in final["briefs"] if b["include"]]:
        links = "".join(f'<li><a href="{_h.escape(l["url"])}">{_h.escape(l["name"])}</a></li>' for l in b["links"])
        rows.append(f"<h3>{_h.escape(head(b, 'text'))}</h3><ul>{links}</ul>")
    heading = "CamPen Media \u00b7 Daily Wrap \u2014 " + ("\u0c2e\u0c42\u0c32\u0c3e\u0c32\u0c41" if te else "sources")
    intro = ("\u0c28\u0c47\u0c1f\u0c3f \u0c15\u0c25\u0c28\u0c3e\u0c32 \u0c2e\u0c42\u0c32 \u0c32\u0c3f\u0c02\u0c15\u0c41\u0c32\u0c41"
             if te else "Source links for today's stories")
    font = ("<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Noto+Sans+Telugu:wght@400;700&display=swap'>"
            if te else "")
    family = "'Noto Sans Telugu','Nirmala UI','Gautami',Arial,sans-serif" if te else "Arial,sans-serif"
    return (f"<!doctype html><html lang='{'te' if te else 'en'}'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_h.escape(heading)} -- {_h.escape(d)}</title>{font}"
            f"<style>body{{font-family:{family};max-width:720px;margin:2em auto;padding:0 1em;color:#102848;line-height:1.5}}"
            "h1{font-size:1.5em}h3{font-size:1.05em;margin:1.4em 0 .3em}a{color:#1058C0}</style>"
            f"<h1>{_h.escape(heading)}</h1><p>{_h.escape(d)} \u00b7 {_h.escape(intro)}</p>" + "".join(rows) + "</html>")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def run_self_test(client, model, config_path) -> None:
    print("\nConfiguration check")
    print("-" * 40)
    checks = [
        ("SARVAM_API_KEY", "written narrative"), ("X_BEARER_TOKEN", "X / Twitter posts (backup to Brave)"),
        ("YOUTUBE_API_KEY", "YouTube search"), ("META_ACCESS_TOKEN", "Facebook/Instagram ads"),
        ("BRAVE_API_KEY", "PRIMARY social search: X/Instagram/Facebook/YouTube"),
    ]
    for var, what in checks:
        print(f"  {'✓' if os.environ.get(var) else '–'} {var:<18} {what}")
    print(f"  {'✓' if BeautifulSoup else '–'} beautifulsoup4       Telegram channels")
    cfg = load_config(config_path)
    print(f"  {'✓' if cfg else '–'} {config_path:<22} {len(cfg)} politician(s) configured" if cfg
          else f"  – {config_path:<22} not found (YouTube feeds/Telegram need it)")

    print("\nSarvam API check...", end=" ", flush=True)
    if client is None:
        sys.exit("SKIPPED\nSarvam isn't available (pip install sarvamai, and set SARVAM_API_KEY).")
    try:
        response = client.chat.completions(model=model, messages=[{"role": "user", "content": "Reply with just the word OK."}], max_tokens=10)
        _ = response.choices[0].message.content
        print("OK\n\n✅ Setup check passed. Sources marked '–' above will simply be skipped.\n")
    except Exception as e:
        print("FAILED")
        sys.exit(f"Sarvam API call failed: {e}\nCheck SARVAM_API_KEY, your credits, and the model name (--model).")


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid date. Use YYYY-MM-DD.")


def gather_report(
    raw: str,
    start_date=None, end_date=None,
    config_path: str = CONFIG_PATH,
    platforms_csv: str = "x,instagram,facebook,youtube",
    model: str = DEFAULT_MODEL,
    headlines_limit: int = 10,
    no_reddit=False, no_x=False, x_always=False, no_youtube=False,
    no_ads=False, no_telegram=False, no_brave=False, no_social_news=False,
    subject_type: str = "auto",
    client=None,
) -> dict:
    """Run the full gathering + analysis pipeline for one politician and return
    everything needed to render a report. This is the single source of truth
    used by both the command-line tool (main(), below) and the UI (app.py) --
    neither duplicates this logic, so they can never drift apart.

    Prints progress messages as it goes (the CLI shows these directly; the UI
    captures them via contextlib.redirect_stdout for its processing log).
    Returns a dict: name, window_label, wiki, data, narrative, status, used_template.
    Raises ValueError for a bad platforms_csv list; everything else degrades
    gracefully into `status` rather than raising.
    """
    subject = resolve_subject(raw, config_path, subject_type)
    kind = subject["type"]
    name, search_names, entry = subject["name"], subject["search_names"], subject["entry"]
    kind_label = "political party" if kind == "party" else "politician"
    if subject["recognized"] or name.lower() != raw.lower():
        print(f"\nRecognized '{raw}' as '{name}' ({kind_label}).")
    else:
        print(f"\nReport type: {kind_label}.")

    # Politicians are searched by their exact name, as before. Parties are
    # searched by all their common names OR'd together, and GDELT is limited
    # to Indian sources so e.g. "Congress party" doesn't pull in US news.
    if kind == "party":
        gdelt_query = build_news_query(subject["news_terms"], india_only=True)
        google_query = build_news_query(subject["news_terms"])
    else:
        gdelt_query = google_query = name
    term = subject["primary_term"]  # single-keyword sources (Reddit, YouTube, X, Meta)

    if start_date and not end_date:
        end_date = utc_now()
    using_range = bool(start_date or end_date)
    window_label = _range_text(start_date, end_date) if using_range else "recent (last month)"
    headline_limit = 60 if using_range else headlines_limit

    keys = [k.strip().lower() for k in platforms_csv.split(",") if k.strip()]
    bad = [k for k in keys if k not in PLATFORMS]
    if bad:
        raise ValueError(f"Unknown platform(s): {', '.join(bad)}. Choose from: {', '.join(PLATFORMS)}")

    print(f"\nGathering data on '{name}' ({window_label})...")
    status = {}

    try:
        wiki = get_wikipedia_summary(name)
        status["Wikipedia"] = "found" if wiki.get("found") else "no page found"
    except Exception as e:
        wiki = {"found": False}
        status["Wikipedia"] = f"failed: {e}"
        print(f"  Warning: Wikipedia lookup failed ({e})")

    print("  - News headlines...")
    headlines, news_label = [], "News headlines (GDELT)"
    try:
        headlines = get_gdelt_news(gdelt_query, headline_limit, start_date, end_date)
    except Exception as e:
        print(f"    Warning: GDELT failed ({e})")
    if not headlines:
        print("    Falling back to Google News RSS...")
        news_label = "News headlines (Google News fallback)"
        try:
            headlines = get_google_news_fallback(google_query, headline_limit, start_date, end_date)
        except Exception as e:
            status[news_label] = f"failed: {e}"
            print(f"    Warning: Google News fallback also failed ({e})")
    status.setdefault(news_label, f"{len(headlines)} found")

    x_token, yt_key = os.environ.get("X_BEARER_TOKEN"), os.environ.get("YOUTUBE_API_KEY")
    meta_token, brave_key = os.environ.get("META_ACCESS_TOKEN"), os.environ.get("BRAVE_API_KEY")

    def gate(flag, key, var):
        return (not flag and bool(key)), ("disabled by flag" if flag else f"{var} not set")

    ok, why = gate(no_reddit, True, "")
    reddit = collect(status, "Reddit", get_reddit_mentions, term, 10, start_date, end_date, enabled=ok, skip_reason=why)
    reddit, dropped = filter_relevant(reddit, search_names, lambda r: r.get("title", ""))
    if dropped and "Reddit" in status:
        status["Reddit"] += f", {dropped} unrelated result(s) filtered out"
    ok, why = gate(no_youtube, yt_key, "YOUTUBE_API_KEY")
    yt_api = collect(status, "YouTube search (API)", get_youtube_videos, term, yt_key, 10, start_date, end_date, enabled=ok, skip_reason=why)
    yt_rss = collect(status, "YouTube channel feeds (RSS)", collect_youtube_feeds, entry, start_date, end_date,
                     enabled=not no_youtube, skip_reason="disabled by flag")
    telegram = collect(status, "Telegram channels", collect_telegram, entry, start_date, end_date,
                       enabled=not no_telegram, skip_reason="disabled by flag")
    ok, why = gate(no_ads, meta_token, "META_ACCESS_TOKEN")
    meta_ads = collect(status, "Facebook/Instagram ads (Meta)", get_meta_ads, term, meta_token, 10, start_date, end_date, enabled=ok, skip_reason=why)
    social_news = collect(status, "News about their social posts", get_social_news_coverage, google_query, 20, start_date, end_date,
                          enabled=not no_social_news, skip_reason="disabled by flag")
    social_news, dropped = filter_relevant(social_news, search_names, lambda n: n.get("headline", ""))
    if dropped and "News about their social posts" in status:
        status["News about their social posts"] += f", {dropped} unrelated result(s) filtered out"

    # PRIMARY social source: Brave Search (X, Instagram, Facebook, YouTube).
    # This always runs BEFORE any X API call is even considered.
    print("  - Search-indexed posts (Brave) [primary social source]...")
    indexed = {}
    ok, why = gate(no_brave, brave_key, "BRAVE_API_KEY")
    if ok:
        indexed, status["Search-indexed posts (Brave)"] = collect_indexed_posts(search_names, keys, brave_key, start_date, end_date)
    else:
        status["Search-indexed posts (Brave)"] = f"skipped ({why})"
        print(f"    Brave not configured ({why}) -- X API will be used directly instead, if available.")

    # BACKUP for X only: the paid X API (billed per post read) runs ONLY when
    # Brave found too few X results (below X_BACKUP_THRESHOLD), or when Brave
    # itself isn't configured/available. This check always happens AFTER Brave.
    brave_x = len(indexed.get(PLATFORMS["x"][0], []))
    ok, why = gate(no_x, x_token, "X_BEARER_TOKEN")
    if ok and brave_key and not no_brave and brave_x >= X_BACKUP_THRESHOLD and not x_always:
        ok = False
        why = (f"not needed: Brave already found {brave_x} X result(s); the API is only a backup "
               f"(use --x-always to force it)")
    elif ok and brave_key and not no_brave:
        print(f"  - X / Twitter (API) [backup only -- Brave found just {brave_x} X result(s)]...")
    elif ok:
        print("  - X / Twitter (API) [used directly -- Brave unavailable]...")
    x_posts = collect(status, "X / Twitter (API)", get_x_recent_posts, term, x_token, 15, start_date, end_date,
                      enabled=ok, skip_reason=why, announce=False)

    data = {
        "headlines": headlines, "reddit": reddit, "x_posts": x_posts,
        "youtube": merge_youtube(yt_rss, yt_api), "telegram": telegram,
        "meta_ads": meta_ads, "social_news": social_news, "indexed": indexed,
    }

    # Group the coverage into distinct stories, ranked by how many separate
    # outlets reported each one -- a far better signal of what actually
    # mattered this period than a raw, duplicate-heavy pile of headlines.
    stories = build_top_stories(data, ignore_words=search_names + [name])
    glance = build_glance(data, stories)
    status["Story grouping"] = (f"{len(stories)} distinct stories from {glance['outlets']} outlets"
                                if stories else "no news stories to group")
    extras = {"stories": stories}

    used_template = False
    narrative = {}
    if client is not None:
        print("  - Asking Sarvam AI to write the summary...")
        try:
            narrative = generate_narrative(client, model, name, window_label, wiki, data, kind, extras)
            status["Sarvam AI summary"] = "written"
        except Exception as e:
            print(f"    Warning: Sarvam call failed ({e}). Using a template summary instead.")
            status["Sarvam AI summary"] = f"failed: {e}"
            used_template = True
    else:
        why = "SARVAM_API_KEY not set" if SarvamAI else "sarvamai not installed"
        print(f"  (Sarvam not available: {why}. Using a template summary.)")
        status["Sarvam AI summary"] = f"skipped ({why})"
        used_template = True
    if used_template:
        narrative = build_template_summary(name, wiki, data, window_label, kind, extras)

    attach_profile(narrative, kind)

    return {
        "subject_type": kind,
        "name": name, "window_label": window_label, "wiki": wiki, "data": data,
        "narrative": narrative, "status": status, "used_template": used_template,
        "start_date": start_date, "end_date": end_date,
        "stories": stories, "glance": glance,
    }


def main():
    ap = argparse.ArgumentParser(description="Indian Politician & Party Intelligence Agent (all-in-one)")
    ap.add_argument("name", nargs="?", help="Politician or party: full name or a short form, e.g. 'KCR' or 'BJP'")
    ap.add_argument("--type", choices=["auto", "politician", "party"], default="auto", dest="subject_type",
                    help="Report type. 'auto' (default) detects known parties like BJP, Congress, BRS, TDP")
    ap.add_argument("--party", action="store_true", help="Shortcut for --type party (e.g. for a party not in the built-in list)")
    ap.add_argument("--save", action="store_true", help="Save a Markdown report to ./reports/")
    ap.add_argument("--pdf", action="store_true", help="Also save a PDF report to ./reports/ (needs: pip install reportlab)")
    ap.add_argument("--headlines", type=int, default=10, help="Max headlines when no date range is given (default: 10)")
    ap.add_argument("--from-date", type=_parse_date, dest="from_date", metavar="YYYY-MM-DD")
    ap.add_argument("--to-date", type=_parse_date, dest="to_date", metavar="YYYY-MM-DD")
    ap.add_argument("--daily", action="store_true", help="Shortcut: last 1 day")
    ap.add_argument("--weekly", action="store_true", help="Shortcut: last 7 days")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Sarvam model (default: {DEFAULT_MODEL})")
    ap.add_argument("--config", default=CONFIG_PATH, help=f"Handles file (default: {CONFIG_PATH})")
    ap.add_argument("--platforms", default="x,instagram,facebook,youtube", help="Platforms Brave should search: " + ",".join(PLATFORMS))
    ap.add_argument("--no-reddit", action="store_true")
    ap.add_argument("--no-x", action="store_true")
    ap.add_argument("--x-always", action="store_true", help="Always call the X API too, even if Brave already found X results")
    ap.add_argument("--no-youtube", action="store_true")
    ap.add_argument("--no-ads", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--no-brave", action="store_true")
    ap.add_argument("--no-social-news", action="store_true")
    ap.add_argument("--carousel", nargs="?", const="both", default=None, metavar="STATES",
                    help="DRAFT ten-slide daily news carousel (national, AP/Telangana, world, business, tech/science/"
                         "health/environment, sports). STATES for the state slide: both (default), ap, telangana or "
                         "none. Use --date for another day; --save/--pdf to keep it")
    ap.add_argument("--wrap-party", default="", metavar="PARTY",
                    help="With --wrap: a wrap-up about one party in AP/Telangana, e.g. BRS, TDP, YSRCP, Congress, BJP, "
                         "\"Jana Sena\", AIMIM")
    ap.add_argument("--wrap", nargs="?", const="both", default=None, metavar="STATE",
                    help="Daily news wrap-up instead of a politician report: both (default), ap, or telangana")
    ap.add_argument("--date", type=_parse_date, default=None, metavar="YYYY-MM-DD",
                    help="Day for --wrap (default: today, India time). For a range of days with --wrap, use "
                         f"--from-date/--to-date instead (up to {WRAP_MAX_DAYS} days)")
    ap.add_argument("--test", action="store_true", help="Check your setup, then exit")
    args = ap.parse_args()

    sarvam_key = os.environ.get("SARVAM_API_KEY")
    client = SarvamAI(api_subscription_key=sarvam_key) if (SarvamAI and sarvam_key) else None

    if args.test:
        run_self_test(client, args.model, args.config)
        return

    if args.wrap is not None:
        run_wrap(args.wrap, args, client)
        return

    if args.carousel is not None:
        run_carousel(args.carousel, args, client)
        return

    # Scripted/one-shot usage (name given on the command line, e.g. in a shell
    # script or cron job) runs exactly once and exits -- unchanged from before.
    # Interactive usage (no name given) keeps prompting for the next one,
    # reusing the same flags (time window, sources, --save, --pdf, etc.) each
    # time, until you enter nothing or type exit/quit.
    interactive = args.name is None
    raw = args.name

    while True:
        if raw is None:
            try:
                raw = input("\nEnter a politician or party (e.g. 'KCR' or 'BJP'), 'daily wrap' for today's AP & "
                            "Telangana news, 'carousel' for the daily news carousel, or press Enter to quit: ").strip()
            except EOFError:
                raw = ""
            if not raw or raw.lower() in ("exit", "quit"):
                break

        wrap_choice = detect_wrap_request(raw)
        if detect_carousel_request(raw):
            run_carousel("both", args, client)
        elif wrap_choice:
            rng = detect_wrap_range(raw)
            run_wrap(wrap_choice, args, client, *(rng or (None, None)), party=detect_wrap_party(raw) or "")
        else:
            run_one_report(raw, args, client)

        if not interactive:
            break
        raw = None  # prompt again on the next loop


def run_one_report(raw: str, args, client) -> None:
    """Gather and print/save one report for `raw`, using the parsed CLI args."""
    start_date, end_date = args.from_date, args.to_date
    if args.daily and not start_date:
        start_date = utc_now() - timedelta(days=1)
    if args.weekly and not start_date:
        start_date = utc_now() - timedelta(days=7)

    try:
        result = gather_report(
            raw, start_date, end_date, config_path=args.config, platforms_csv=args.platforms,
            model=args.model, headlines_limit=args.headlines, no_reddit=args.no_reddit,
            no_x=args.no_x, x_always=args.x_always, no_youtube=args.no_youtube, no_ads=args.no_ads,
            no_telegram=args.no_telegram, no_brave=args.no_brave, no_social_news=args.no_social_news,
            subject_type="party" if args.party else args.subject_type, client=client,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return

    name, wiki, data = result["name"], result["wiki"], result["data"]
    narrative, status, used_template = result["narrative"], result["status"], result["used_template"]
    start_date, end_date = result["start_date"], result["end_date"]

    stories = result.get("stories")
    print_report(name, wiki, data, narrative, start_date, end_date, status, used_template, stories=stories)
    if args.save:
        print(f"Saved report to: {save_markdown(name, wiki, data, narrative, start_date, end_date, status, used_template, stories)}\n")
    if args.pdf:
        if SimpleDocTemplate is None:
            print("Skipped PDF export: reportlab isn't installed. Run:  pip install reportlab")
        else:
            print(f"Saved PDF report to: {save_pdf(name, wiki, data, narrative, start_date, end_date, status, used_template, stories)}\n")


def run_carousel(states: str, args, client) -> None:
    """Build the DRAFT daily news carousel and print/save it."""
    day = args.date.date() if getattr(args, "date", None) else None
    try:
        if str(states).lower() not in ("none", "no"):
            resolve_wrap_states(states)
        validate_wrap_range(day or ist_today(), day or ist_today())
    except ValueError as e:
        print(f"Error: {e}")
        return
    print(f"\nBuilding the DRAFT daily news carousel for {(day or ist_today()):%d %b %Y}...")
    c = gather_daily_carousel(day, states, client, args.model)
    print_carousel(c)
    if args.save:
        print(f"Saved DRAFT carousel to: {save_carousel_markdown(c)}\n")
    if args.pdf:
        if SimpleDocTemplate is None:
            print("Skipped PDF export: reportlab isn't installed. Run:  pip install reportlab")
        else:
            print(f"Saved DRAFT carousel PDF to: {save_carousel_pdf(c)}\n")


def run_wrap(choice: str, args, client, start_day=None, end_day=None, party=None) -> None:
    """Gather and print/save the news wrap-up for one day or a date range.
    Range: --from-date/--to-date (or a period typed in interactive mode, e.g.
    "weekly wrap"); single day: --date; default: today, India time."""
    if start_day is None:
        f, t = getattr(args, "from_date", None), getattr(args, "to_date", None)
        if f or t:
            start_day = (f or t).date()
            end_day = t.date() if t else ist_today()
        elif getattr(args, "date", None):
            start_day = end_day = args.date.date()
        else:
            start_day = end_day = ist_today()
    end_day = end_day or start_day
    try:
        keys = resolve_wrap_states(choice)
        validate_wrap_range(start_day, end_day)
    except ValueError as e:
        print(f"Error: {e}")
        return
    party = getattr(args, "wrap_party", "") if party is None else party
    try:
        pinfo = resolve_wrap_party(party)
    except ValueError as e:
        print(f"Error: {e}")
        return
    labels = " & ".join(WRAP_STATES[k]["label"] for k in keys)
    print(f"\nBuilding the {pinfo['short'] + ' ' if pinfo else ''}news wrap-up for {labels} "
          f"({wrap_period_text(start_day, end_day)})...")
    wrap = gather_daily_wrap(choice, start_day, client, args.model, end_day=end_day, party=party)
    print_wrap(wrap)
    if args.save:
        print(f"Saved wrap-up to: {save_wrap_markdown(wrap)}\n")
    if args.pdf:
        if SimpleDocTemplate is None:
            print("Skipped PDF export: reportlab isn't installed. Run:  pip install reportlab")
        else:
            print(f"Saved PDF wrap-up to: {save_wrap_pdf(wrap)}\n")


if __name__ == "__main__":
    main()

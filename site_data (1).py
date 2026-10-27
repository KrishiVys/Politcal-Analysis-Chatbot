"""
Data and logic for the AP & Telangana political news site: constituencies (with official numbers), districts,
regions, parties and leaders; building a news "subject" for any of them; tagging news with the places it
mentions; and the map.

Constituency data: ap_tg_data.json (Election Commission delimitation order, as listed on Wikipedia; validated).
"""
from __future__ import annotations

import html
import json
import os
import re

import updatedcode as uc

DATA = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ap_tg_data.json"), encoding="utf-8"))
STATE_KEY = {"Andhra Pradesh": "andhra pradesh", "Telangana": "telangana"}
STATE_SHORT = {"Andhra Pradesh": "AP", "Telangana": "TG"}
SHORT_STATE = {v: k for k, v in STATE_SHORT.items()}

ACS = DATA["assembly"]
PCS = DATA["lok_sabha"]
DISTRICTS = DATA["districts"]
REGIONS = DATA["regions"]
AC_BY_KEY = {(a["state"], a["ac_no"]): a for a in ACS}
PC_BY_NAME = {(p["state"], p["name"]): p for p in PCS}
DISTRICT_BY_NAME = {(d["state"], d["name"]): d for d in DISTRICTS}

# Parties covered, the states they are mainly active in, and how the news engine knows them.
PARTIES = [
    {"short": "TDP", "name": "Telugu Desam Party", "states": ["Andhra Pradesh"]},
    {"short": "YSRCP", "name": "YSR Congress Party", "states": ["Andhra Pradesh"]},
    {"short": "Jana Sena", "name": "Jana Sena Party", "states": ["Andhra Pradesh"]},
    {"short": "BRS", "name": "Bharat Rashtra Samithi", "states": ["Telangana"]},
    {"short": "Congress", "name": "Indian National Congress", "states": ["Andhra Pradesh", "Telangana"]},
    {"short": "BJP", "name": "Bharatiya Janata Party", "states": ["Andhra Pradesh", "Telangana"]},
    {"short": "AIMIM", "name": "All India Majlis-e-Ittehadul Muslimeen", "states": ["Telangana"]},
    {"short": "CPI", "name": "Communist Party of India", "states": ["Andhra Pradesh", "Telangana"]},
    {"short": "CPI(M)", "name": "Communist Party of India (Marxist)", "states": ["Andhra Pradesh", "Telangana"]},
]
# Leaders: party affiliation only (roles change -- edit this list as things change).
LEADERS = [
    {"name": "N. Chandrababu Naidu", "party": "TDP", "state": "Andhra Pradesh", "aliases": ["Chandrababu Naidu", "Chandrababu", "CBN"]},
    {"name": "Nara Lokesh", "party": "TDP", "state": "Andhra Pradesh", "aliases": ["Nara Lokesh", "Lokesh"]},
    {"name": "K. Atchannaidu", "party": "TDP", "state": "Andhra Pradesh", "aliases": ["Atchannaidu", "Atchennaidu"]},
    {"name": "K. Ram Mohan Naidu", "party": "TDP", "state": "Andhra Pradesh", "aliases": ["Ram Mohan Naidu", "Rammohan Naidu"]},
    {"name": "Pawan Kalyan", "party": "Jana Sena", "state": "Andhra Pradesh", "aliases": ["Pawan Kalyan"]},
    {"name": "Nadendla Manohar", "party": "Jana Sena", "state": "Andhra Pradesh", "aliases": ["Nadendla Manohar", "Nadendla"]},
    {"name": "Y. S. Jagan Mohan Reddy", "party": "YSRCP", "state": "Andhra Pradesh", "aliases": ["Jagan Mohan Reddy", "YS Jagan", "Jagan"]},
    {"name": "Botcha Satyanarayana", "party": "YSRCP", "state": "Andhra Pradesh", "aliases": ["Botcha Satyanarayana", "Botcha"]},
    {"name": "Peddireddy Ramachandra Reddy", "party": "YSRCP", "state": "Andhra Pradesh", "aliases": ["Peddireddy"]},
    {"name": "Y. S. Sharmila", "party": "Congress", "state": "Andhra Pradesh", "aliases": ["Sharmila"]},
    {"name": "Daggubati Purandeswari", "party": "BJP", "state": "Andhra Pradesh", "aliases": ["Purandeswari"]},
    {"name": "A. Revanth Reddy", "party": "Congress", "state": "Telangana", "aliases": ["Revanth Reddy", "Revanth"]},
    {"name": "Mallu Bhatti Vikramarka", "party": "Congress", "state": "Telangana", "aliases": ["Bhatti Vikramarka", "Bhatti"]},
    {"name": "N. Uttam Kumar Reddy", "party": "Congress", "state": "Telangana", "aliases": ["Uttam Kumar Reddy"]},
    {"name": "K. Chandrashekar Rao", "party": "BRS", "state": "Telangana", "aliases": ["KCR", "Chandrashekar Rao", "Chandrasekhar Rao"]},
    {"name": "K. T. Rama Rao", "party": "BRS", "state": "Telangana", "aliases": ["KTR", "K.T. Rama Rao", "KT Rama Rao"]},
    {"name": "T. Harish Rao", "party": "BRS", "state": "Telangana", "aliases": ["Harish Rao"]},
    {"name": "G. Kishan Reddy", "party": "BJP", "state": "Telangana", "aliases": ["Kishan Reddy"]},
    {"name": "Bandi Sanjay Kumar", "party": "BJP", "state": "Telangana", "aliases": ["Bandi Sanjay"]},
    {"name": "N. Ramchander Rao", "party": "BJP", "state": "Telangana", "aliases": ["Ramchander Rao"]},
    {"name": "Eatala Rajender", "party": "BJP", "state": "Telangana", "aliases": ["Eatala Rajender", "Etela Rajender"]},
    {"name": "Asaduddin Owaisi", "party": "AIMIM", "state": "Telangana", "aliases": ["Asaduddin Owaisi", "Asaduddin", "Owaisi"]},
]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


LEADER_BY_SLUG = {_slug(l["name"]): l for l in LEADERS}
REGION_BY_SLUG = {(r["state"], _slug(r["name"])): r for r in REGIONS}


def _rx_words(words) -> re.Pattern:
    words = sorted({w for w in words if w}, key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(w) for w in words) + r")(?![A-Za-z0-9])", re.I)


# "Is this political news?" -- a party, a leader, or a political office or event.
_POLITICAL_WORDS = ["MLA", "MLAs", "MP", "MPs", "MLC", "MLCs", "minister", "ministers", "chief minister", "CM",
                    "deputy CM", "election", "elections", "poll", "polls", "bypoll", "by-election", "candidate",
                    "candidates", "campaign", "rally", "party", "parties", "corporator", "sarpanch", "ZPTC", "MPTC",
                    "legislator", "assembly", "opposition", "ruling", "cabinet", "government", "govt", "manifesto",
                    "defection", "alliance", "councillor", "mayor", "municipal chairman", "panchayat"]
POLITICAL_RX = re.compile(
    "|".join([uc._rx(p["match"]).pattern for p in uc.WRAP_PARTY_PROFILES.values()]
             + [_rx_words([a for l in LEADERS for a in l["aliases"]]).pattern, _rx_words(_POLITICAL_WORDS).pattern]),
    re.I)


# ---------------------------------------------------------------- the search box
def ac_label(a: dict) -> str:
    res = f" ({a['reserved']})" if a["reserved"] else ""
    return f"{a['name']}{res} — AC {a['ac_no']} · {', '.join(a['districts'])} · {STATE_SHORT[a['state']]}"


def search_options() -> list:
    """[(key, label)] for every party, leader, constituency, Lok Sabha seat, district and region."""
    out = []
    for p in PARTIES:
        out.append((f"party:{p['short']}", f"🚩 {p['short']} — {p['name']}"))
    for l in LEADERS:
        out.append((f"leader:{_slug(l['name'])}", f"👤 {l['name']} — {l['party']}, {STATE_SHORT[l['state']]}"))
    for a in sorted(ACS, key=lambda a: (a["state"], a["ac_no"])):
        out.append((f"ac:{STATE_SHORT[a['state']]}:{a['ac_no']}", "🏛️ " + ac_label(a)))
    for p in PCS:
        res = f" ({p['reserved']})" if p["reserved"] else ""
        out.append((f"pc:{STATE_SHORT[p['state']]}:{p['pc_no']}",
                    f"🗳️ {p['name']}{res} — Lok Sabha PC {p['pc_no']} · {STATE_SHORT[p['state']]}"))
    for d in DISTRICTS:
        out.append((f"district:{STATE_SHORT[d['state']]}:{d['name']}", f"📍 {d['name']} district · {STATE_SHORT[d['state']]}"))
    for r in REGIONS:
        out.append((f"region:{STATE_SHORT[r['state']]}:{_slug(r['name'])}", f"🗺️ {r['name']} · {STATE_SHORT[r['state']]}"))
    return out


# ---------------------------------------------------------------- news subjects
def _region_subject(name: str, terms: list, match_words: list, state: str) -> dict:
    q = uc.build_news_query(terms[:8])
    return {"kind": "region", "name": name, "short": name, "search_terms": terms[:8], "leaders": [], "leads": [],
            "match": _rx_words(match_words), "require": POLITICAL_RX,
            "focus_extra": [f"{q} (MLA OR MP OR minister OR party OR election)"]}


def _ac_words(a: dict) -> list:
    return ([a["name"]] if a.get("match_name", True) else []) + a["aliases"]


def _district_words(d: dict) -> list:
    return [d["name"]] + d["aliases"]


def resolve(key: str) -> dict:
    """{title, kind, subject (for the news engine), states (engine's states choice), highlight (districts),
    info (facts to show)} for a search key. Raises KeyError for an unknown key."""
    kind, _, rest = key.partition(":")
    if kind == "overview":
        st = SHORT_STATE[rest]
        subj = {"kind": "region", "name": f"{st} politics", "short": st, "leaders": [], "leads": [],
                "search_terms": ["TDP", "YSRCP", "Jana Sena", "BJP", "Congress", "MLA", "minister"] if rest == "AP"
                else ["Congress", "BRS", "BJP", "AIMIM", "MLA", "minister", "Revanth"],
                "match": POLITICAL_RX}
        return {"title": f"{st} politics today", "kind": "overview", "subject": subj, "states": STATE_KEY[st],
                "highlight": [], "info": {}}
    if kind == "party":
        p = next(p for p in PARTIES if p["short"] == rest)
        states = "both" if len(p["states"]) == 2 else STATE_KEY[p["states"][0]]
        return {"title": f"{p['short']} — {p['name']}", "kind": "party", "subject": p["name"], "states": states,
                "highlight": [], "info": {"Party": p["name"], "Covered in": " & ".join(p["states"])}}
    if kind == "leader":
        l = LEADER_BY_SLUG[rest]
        subj = {"kind": "leader", "name": l["name"], "short": l["name"], "search_terms": l["aliases"][:3], "leaders": [],
                "leads": [], "match": _rx_words(l["aliases"])}
        return {"title": l["name"], "kind": "leader", "subject": subj, "states": STATE_KEY[l["state"]], "highlight": [],
                "info": {"Party": l["party"], "State": l["state"]}}
    st_short, _, rest2 = rest.partition(":")
    st = SHORT_STATE[st_short]
    if kind == "ac":
        a = AC_BY_KEY[(st, int(rest2))]
        words = _ac_words(a)
        pc = PC_BY_NAME[(st, a["lok_sabha"])]
        info = {"Assembly constituency": f"No. {a['ac_no']}", "Reserved for": a["reserved"] or "None (general)",
                "District": ", ".join(a["districts"]), "Lok Sabha seat": f"{pc['name']} (PC {pc['pc_no']})",
                "State": st, "Electors": f"{a['electors']:,}"}
        return {"title": f"{a['name']} (AC {a['ac_no']})", "kind": "ac",
                "subject": _region_subject(f"{a['name']} Assembly constituency ({st})", words, words, st),
                "states": STATE_KEY[st], "highlight": [(st, d) for d in a["districts"]], "info": info, "ac": a}
    if kind == "pc":
        p = next(p for p in PCS if p["state"] == st and p["pc_no"] == int(rest2))
        segs = [a for a in ACS if a["state"] == st and a["lok_sabha"] == p["name"]]
        words = [p["name"]] + [w for a in segs for w in _ac_words(a)]
        info = {"Lok Sabha constituency": f"PC {p['pc_no']}", "Reserved for": p["reserved"] or "None (general)", "State": st,
                "Assembly segments": ", ".join(f"{a['name']} ({a['ac_no']})" for a in segs)}
        return {"title": f"{p['name']} Lok Sabha (PC {p['pc_no']})", "kind": "pc",
                "subject": _region_subject(f"{p['name']} Lok Sabha constituency ({st})",
                                           [f"{p['name']} Lok Sabha", f"{p['name']} MP"] + [a["name"] for a in segs], words, st),
                "states": STATE_KEY[st], "highlight": sorted({(st, d) for a in segs for d in a["districts"]}), "info": info,
                "segments": segs}
    if kind == "district":
        d = DISTRICT_BY_NAME[(st, rest2)]
        segs = [a for a in ACS if a["state"] == st and d["name"] in a["districts"]]
        words = _district_words(d) + [w for a in segs for w in _ac_words(a)]
        info = {"District": d["name"], "Headquarters": d["hq"], "State": st,
                "Assembly constituencies": ", ".join(f"{a['name']} ({a['ac_no']})" for a in segs)}
        return {"title": f"{d['name']} district", "kind": "district",
                "subject": _region_subject(f"{d['name']} district ({st})", _district_words(d), words, st),
                "states": STATE_KEY[st], "highlight": [(st, d["name"])], "info": info, "segments": segs}
    if kind == "region":
        r = REGION_BY_SLUG[(st, rest2)]
        ds = [DISTRICT_BY_NAME[(st, n)] for n in r["districts"]]
        segs = [a for a in ACS if a["state"] == st and set(a["districts"]) & set(r["districts"])]
        # the region's name, its districts AND every constituency in it (news often names only the constituency)
        words = r["aliases"] + [w for d in ds for w in _district_words(d)] + [w for a in segs for w in _ac_words(a)]
        info = {"Region": r["name"], "State": st, "Districts": ", ".join(r["districts"]),
                "Assembly constituencies": str(sum(1 for a in ACS if a["state"] == st and set(a["districts"]) & set(r["districts"])))}
        return {"title": r["name"], "kind": "region",
                "subject": _region_subject(f"{r['name']} ({st})", r["aliases"] + [d["name"] for d in ds], words, st),
                "states": STATE_KEY[st], "highlight": [(st, n) for n in r["districts"]], "info": info}
    raise KeyError(key)


# ---------------------------------------------------------------- tagging news with places
def _build_matchers():
    acs = []
    for a in ACS:
        for w in _ac_words(a):
            acs.append((w, a))
    acs.sort(key=lambda x: -len(x[0]))
    dists = []
    for d in DISTRICTS:
        for w in _district_words(d):
            dists.append((w, d))
    dists.sort(key=lambda x: -len(x[0]))
    return acs, dists


_AC_MATCHERS, _DISTRICT_MATCHERS = _build_matchers()
_WORD = lambda w: re.compile(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])", re.I)
_RX_CACHE = {}


def _find(word, text):
    rx = _RX_CACHE.get(word) or _RX_CACHE.setdefault(word, _WORD(word))
    return list(rx.finditer(text))


def tag_places(text: str, states=None) -> dict:
    """{'acs': [constituency], 'districts': [(state, district)]} mentioned in `text` (longest names first, so
    'Gangadhara Nellore' is not also read as Nellore district). `states` limits to those states."""
    states = set(states or STATE_KEY)
    masked = text or ""
    found_acs, found_d = [], []
    for w, a in _AC_MATCHERS:
        if a["state"] not in states:
            continue
        hits = _find(w, masked)
        if hits:
            if a not in found_acs:
                found_acs.append(a)
            for m in reversed(hits):
                masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]
    for w, d in _DISTRICT_MATCHERS:
        if d["state"] in states and _find(w, masked) and (d["state"], d["name"]) not in found_d:
            found_d.append((d["state"], d["name"]))
    for a in found_acs:
        for dn in a["districts"]:
            if (a["state"], dn) not in found_d:
                found_d.append((a["state"], dn))
    return {"acs": found_acs, "districts": found_d}


# ---------------------------------------------------------------- the wrap-up, simplified for the page
SECTION_ICONS = {"politics": "📣", "government": "🏛️", "policy": "📜", "ministries": "🏢", "courts": "⚖️",
                 "law_order": "🚓", "economy": "💼", "infrastructure": "🏗️", "weather": "🌦️", "society": "🧑‍🤝‍🧑", "other": "📰"}


def simplify_wrap(w: dict) -> dict:
    """Plain, small structure for the page: per state, sections of bullets, each with its links and places."""
    out = {"states": [], "period": uc.wrap_period_text(w["start_day"], w["end_day"]), "used_ai": not w.get("used_template", True)}
    for label, n in w["narrative"]["states"].items():
        order = uc.wrap_section_order({"party": True})
        sections = []
        for key in order:
            pts = n["points"].get(key) or []
            if not pts:
                continue
            items = []
            for p in pts:
                text_for_places = " ".join([p.get("text", "")] + list(p.get("headlines") or []))
                places = tag_places(text_for_places, [label])
                items.append({"text": p.get("text", ""), "links": [{"name": l["name"], "url": l["url"]} for l in p.get("links", [])],
                              "when": p.get("when", ""), "tag": p.get("tag") or "",
                              "acs": [{"state": a["state"], "ac_no": a["ac_no"], "name": a["name"], "reserved": a["reserved"]}
                                      for a in places["acs"]],
                              "districts": [list(x) for x in places["districts"]]})
            sections.append({"key": key, "label": uc.wrap_section_label({"party": True}, key),
                             "icon": SECTION_ICONS.get(key, "📰"), "items": items})
        out["states"].append({"label": label, "sections": sections, "watch": list(n.get("what_to_watch") or [])})
    return out


def items_of(result: dict) -> list:
    return [it for st in result["states"] for sec in st["sections"] for it in sec["items"]]


def by_district(result: dict) -> list:
    """[(state, district, [item])], busiest first; items naming no place go under (state, None)."""
    groups = {}
    for st in result["states"]:
        for sec in st["sections"]:
            for it in sec["items"]:
                keys = [tuple(d) for d in it["districts"]] or [(st["label"], None)]
                for k in keys:
                    groups.setdefault(k, [])
                    if it not in groups[k]:
                        groups[k].append(it)
    return sorted(groups.items(), key=lambda kv: (kv[0][1] is None, -len(kv[1]), kv[0][1] or ""))


# ---------------------------------------------------------------- the map
def map_html(result=None, highlight=(), height: int = 460) -> str:
    """A Leaflet map of AP & Telangana: one marker per district, sized by the political stories mentioning it;
    popups list the constituencies (with numbers) and headlines. Highlighted districts are outlined."""
    result = result or {"states": []}
    counts, acs_in, heads = {}, {}, {}
    for it in items_of(result):
        for st, dn in it["districts"]:
            counts[(st, dn)] = counts.get((st, dn), 0) + 1
            heads.setdefault((st, dn), [])
            if len(heads[(st, dn)]) < 3 and it["links"]:
                heads[(st, dn)].append((it["text"], it["links"][0]["url"]))
        for a in it["acs"]:
            for dn in AC_BY_KEY[(a["state"], a["ac_no"])]["districts"]:
                acs_in.setdefault((a["state"], dn), set()).add((a["ac_no"], a["name"], a["reserved"]))
    hl = {tuple(h) for h in highlight}
    markers = []
    for d in DISTRICTS:
        k = (d["state"], d["name"])
        n = counts.get(k, 0)
        seats = sorted(acs_in.get(k, set()))
        all_seats = [a for a in ACS if a["state"] == d["state"] and d["name"] in a["districts"]]
        pop = (f"<b>{html.escape(d['name'])}</b> district · {html.escape(d['state'])}<br>"
               f"<span class='muted'>{len(all_seats)} Assembly constituencies · HQ {html.escape(d['hq'])}</span>")
        if n:
            pop += f"<br><b>{n}</b> political stor{'y' if n == 1 else 'ies'}"
        if seats:
            pop += "<br>In the news: " + ", ".join(
                f"{html.escape(nm)} <span class='no'>AC {no}</span>" for no, nm, _r in seats[:8])
        for t, u in heads.get(k, []):
            pop += f"<br>• <a href='{html.escape(u, quote=True)}' target='_blank' rel='noopener'>{html.escape(t[:110])}</a>"
        markers.append({"lat": d["lat"], "lon": d["lon"], "n": n, "hl": k in hl, "ap": d["state"] == "Andhra Pradesh",
                        "popup": pop, "name": d["name"]})
    data = json.dumps(markers)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>html,body{{margin:0;height:100%;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}}
#map{{height:{height}px;border-radius:14px}}
.leaflet-popup-content{{font-size:13px;line-height:1.45;color:#0f172a}} .muted{{color:#64748b}}
.no{{background:#eef2ff;color:#3730a3;border-radius:6px;padding:0 5px;font-size:11px;font-weight:600}}
.legend{{background:#fff;padding:6px 10px;border-radius:10px;font-size:12px;color:#334155;box-shadow:0 1px 4px rgba(0,0,0,.15)}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin:0 4px 0 8px;vertical-align:-1px}}</style>
</head><body><div id="map"></div><script>
const M = {data};
const map = L.map('map', {{scrollWheelZoom:false}});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
  {{maxZoom:12, attribution:'&copy; OpenStreetMap contributors'}}).addTo(map);
const pts = [];
M.forEach(m => {{
  const r = m.n ? 7 + 4*Math.sqrt(m.n) : 5;
  const c = m.ap ? '#0f766e' : '#4338ca';
  const mk = L.circleMarker([m.lat, m.lon], {{radius:r, color: m.hl ? '#f59e0b' : c, weight: m.hl ? 4 : 1.5,
     fillColor:c, fillOpacity: m.n ? 0.55 : 0.15}}).addTo(map).bindPopup(m.popup);
  mk.bindTooltip(m.name + (m.n ? ' · ' + m.n : ''));
  pts.push([m.lat, m.lon]);
}});
const hl = M.filter(m => m.hl).map(m => [m.lat, m.lon]);
map.fitBounds(hl.length ? L.latLngBounds(hl).pad(hl.length > 1 ? 0.6 : 2.5) : L.latLngBounds(pts).pad(0.05));
const lg = L.control({{position:'bottomleft'}});
lg.onAdd = () => {{ const d = L.DomUtil.create('div','legend');
  d.innerHTML = '<span class="dot" style="background:#0f766e"></span>Andhra Pradesh<span class="dot" style="background:#4338ca"></span>Telangana'
    + '<br><span class="muted">Bigger circle = more political stories</span>'; return d; }};
lg.addTo(map);
</script></body></html>"""


# ---------------------------------------------------------------- understanding a typed request (chat box)
_STATE_HINTS = [("Andhra Pradesh", re.compile(r"(?<![a-z])(andhra|ap)(?![a-z])", re.I)),
                ("Telangana", re.compile(r"(?<![a-z])(telangana|tg|ts)(?![a-z])", re.I))]


def detect_period(text: str):
    """'Yesterday' / 'Last 7 days' if the text asks for it, else None."""
    t = (text or "").lower()
    if "yesterday" in t:
        return "Yesterday"
    if re.search(r"week|7 days|seven days|last few days", t):
        return "Last 7 days"
    return None


def detect_regional(text: str):
    """The search key a typed request names -- an Assembly constituency (by name, or by number with a state:
    'AC 175 AP'), a Lok Sabha seat ('Chittoor Lok Sabha', 'PC 25 AP'), a district ('Warangal district') or a region
    ('Rayalaseema') -- or None. Returns ('ask-state', number) when a number needs a state to be clear."""
    t = text or ""
    states = [s for s, rx in _STATE_HINTS if rx.search(t)]
    m = re.search(r"(?<![a-z])(?:ac|assembly constituency|constituency|seat)\s*(?:no\.?|number|#)?\s*(\d{1,3})(?!\d)", t, re.I)
    if m:
        no = int(m.group(1))
        cands = [s for s in (states or ["Andhra Pradesh", "Telangana"]) if (s, no) in AC_BY_KEY]
        if len(cands) == 1:
            return f"ac:{STATE_SHORT[cands[0]]}:{no}"
        if len(cands) > 1:
            return ("ask-state", no)
    m = re.search(r"(?<![a-z])(?:pc|lok sabha)\s*(?:no\.?|number|#)?\s*(\d{1,2})(?!\d)", t, re.I)
    if m:
        no = int(m.group(1))
        cands = [p for p in PCS if p["pc_no"] == no and (not states or p["state"] in states)]
        if len(cands) == 1:
            return f"pc:{STATE_SHORT[cands[0]['state']]}:{no}"
        if len(cands) > 1:
            return ("ask-state", no)
    for r in REGIONS:                                  # regions ('Rayalaseema', 'erstwhile Warangal')
        if _rx_words([r["name"]] + r["aliases"]).search(t):
            return f"region:{STATE_SHORT[r['state']]}:{_slug(r['name'])}"
    for p in PCS:                                      # 'Chittoor Lok Sabha', 'Chittoor MP seat'
        if re.search(r"(?<![a-z])" + re.escape(p["name"]) + r"\s+(lok sabha|parliament|mp seat|pc)(?![a-z])", t, re.I):
            return f"pc:{STATE_SHORT[p['state']]}:{p['pc_no']}"
    for d in DISTRICTS:                                # 'Warangal district'
        if re.search(r"(?<![a-z])(" + "|".join(re.escape(w) for w in _district_words(d)) + r")\s+district(?![a-z])", t, re.I):
            return f"district:{STATE_SHORT[d['state']]}:{d['name']}"
    best = None                                        # a constituency named anywhere (longest name wins)
    for w, a in _AC_MATCHERS:
        if (not states or a["state"] in states) and _find(w, t):
            if best is None or len(w) > len(best[0]):
                best = (w, a)
    if best:
        return f"ac:{STATE_SHORT[best[1]['state']]}:{best[1]['ac_no']}"
    for d in DISTRICTS:                                # a district named on its own ('Kadapa news')
        if (not states or d["state"] in states) and any(_find(w, t) for w in _district_words(d)):
            return f"district:{STATE_SHORT[d['state']]}:{d['name']}"
    return None

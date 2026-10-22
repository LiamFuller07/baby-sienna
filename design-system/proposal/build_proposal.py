#!/usr/bin/env python3
"""Build a Source proposal deck: proposal.json -> one self-contained HTML file.

    python3 build_proposal.py example-proposal.json                 # writes example-proposal.html
    python3 build_proposal.py proposal.json out.html --strict       # warnings become errors
    python3 build_proposal.py proposal.json --check                 # validate only, write nothing
    python3 build_proposal.py template.json template.html --linked  # link deck.css and fonts/

Every slide is a 1280 x 720 px frame. The output inlines deck.css, both Source
font weights and the wordmark, and loads nothing from the network. On screen the
slides stack, scaled to the window width (arrow keys, Page Up/Down and Space
step through them). Printed, each slide is one 1280 x 720 px page, so "Save as
PDF" gives one page per slide.

The JSON is validated against proposal.schema.json first (a stdlib validator for
the subset of JSON Schema 2020-12 the schema uses). Nothing is written while any
error stands: a missing required field, a field past its layout limit, an
unknown field, a missing required slide, or a client claim with no citation.
Python 3.8+, standard library only.
"""
import argparse
import base64
import datetime
import html
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "proposal.schema.json"
CSS_PATH = HERE / "deck.css"
FONTS = HERE / "fonts"

REQUIRED_TYPES = ["cover", "situation", "focus", "deliverables", "process", "needs", "commercials"]
PURPOSE = {
    "cover": "title, lead and the client label",
    "situation": "what we understand about the client, with citations",
    "focus": "the areas the client can choose to look at",
    "deliverables": "the key deliverables",
    "process": "how it will work, in numbered steps",
    "needs": "what we need from the client",
    "commercials": "next step and commercial terms",
}
EYEBROW = {
    "situation": "The situation",
    "focus": "What we\u2019d look at",
    "outputs": "Example outputs",
    "deliverables": "Key deliverables",
    "process": "How it will work",
    "needs": "What we need from you",
    "team": "Team",
    "commercials": "Next step and commercials",
    "sources": "Appendix",
}
ART_LABEL = {
    "report": "Report",
    "process_map": "Process map",
    "ai_map": "AI opportunities",
    "recommendation": "Recommendation",
}
KIND_LABEL = {
    "document": "Document", "workbook": "Workbook", "meeting-notes": "Meeting notes",
    "interview": "Interview", "public-filing": "Public filing", "website": "Website",
    "data": "Data", "other": "Other",
}
SOURCES_PER_SLIDE = 6   # rows per Sources slide; a "to confirm" item takes one row
PATTERN_MSG = {
    "[^.]$": "must not end with a full stop",
    "^\\d{4}-\\d{2}-\\d{2}$": "must be an ISO date, YYYY-MM-DD",
    "^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$": "must be a source ID: capitals, digits and hyphens, such as S1 or WB-2",
    "^https?://": "must start with http:// or https://",
}


def esc(s):
    return html.escape(str(s), quote=True)


class BuildError(Exception):
    pass


# --- 1. Validation: the JSON Schema subset proposal.schema.json uses ----------------

def jtype(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def type_ok(v, t):
    if isinstance(t, list):
        return any(type_ok(v, x) for x in t)
    actual = jtype(v)
    return actual == t or (t == "number" and actual == "integer")


class Validator:
    """Supports: $ref (local), type, const, enum, minLength, maxLength, pattern,
    minItems, maxItems, items, required, properties, additionalProperties: false,
    allOf, if/then/else and anyOf. x-messages gives a keyword its own message."""

    def __init__(self, schema):
        self.root = schema

    def resolve(self, ref):
        if not ref.startswith("#/"):
            raise BuildError(f"schema: only local $ref is supported, not {ref}")
        node = self.root
        for part in ref[2:].split("/"):
            node = node[part]
        return node

    def errors(self, inst, schema=None, path=()):
        out = []
        self._check(inst, self.root if schema is None else schema, path, out)
        return out

    def _check(self, inst, sch, path, out):
        if "$ref" in sch:
            self._check(inst, self.resolve(sch["$ref"]), path, out)
            rest = {k: v for k, v in sch.items() if k not in ("$ref", "description")}
            if rest:
                self._check(inst, rest, path, out)
            return
        msg = sch.get("x-messages", {})
        t = sch.get("type")
        if t is not None and not type_ok(inst, t):
            out.append((path, msg.get("type", f"must be {'an' if str(t)[0] in 'aeiou' else 'a'} {t}, not {jtype(inst)}")))
            return
        if "const" in sch and inst != sch["const"]:
            out.append((path, f"must be {json.dumps(sch['const'])}"))
        if "enum" in sch and inst not in sch["enum"]:
            out.append((path, msg.get("enum", f"{json.dumps(inst)} is not allowed; use one of: " + ", ".join(json.dumps(e) for e in sch["enum"]))))
        if isinstance(inst, str):
            lo = sch.get("minLength", 0)
            if len(inst.strip()) < lo:
                out.append((path, msg.get("minLength", "must not be empty" if lo == 1 else f"needs at least {lo} characters")))
            hi = sch.get("maxLength")
            if hi is not None and len(inst) > hi:
                out.append((path, msg.get("maxLength", f"is {len(inst)} characters; the slide has room for {hi}. Shorten it")))
            pat = sch.get("pattern")
            if pat and not re.search(pat, inst):
                out.append((path, msg.get("pattern", PATTERN_MSG.get(pat, f"must match {pat}"))))
        if isinstance(inst, list):
            lo, hi = sch.get("minItems"), sch.get("maxItems")
            if lo is not None and len(inst) < lo:
                out.append((path, msg.get("minItems", f"has {len(inst)} item(s); it needs at least {lo}")))
            if hi is not None and len(inst) > hi:
                out.append((path, msg.get("maxItems", f"has {len(inst)} items; the slide has room for {hi}. Cut or split")))
            if "items" in sch:
                for i, x in enumerate(inst):
                    self._check(x, sch["items"], path + (i,), out)
        if isinstance(inst, dict):
            props = sch.get("properties", {})
            for k in sch.get("required", []):
                if k not in inst:
                    out.append((path + (k,), "required field is missing"))
            for k, v in inst.items():
                if k in props:
                    self._check(v, props[k], path + (k,), out)
                elif sch.get("additionalProperties") is False:
                    out.append((path + (k,), "unknown field; allowed here: " + ", ".join(p for p in props if p != "$schema")))
        for sub in sch.get("allOf", []):
            if "if" in sub:
                branch = "then" if not self.errors(inst, sub["if"], path) else "else"
                if branch in sub:
                    self._check(inst, sub[branch], path, out)
            else:
                self._check(inst, sub, path, out)
        if "anyOf" in sch and not any(not self.errors(inst, s, path) for s in sch["anyOf"]):
            out.append((path, msg.get("anyOf", "does not match any allowed form")))


def where(path, data):
    """('slides', 2, 'points', 1) -> 'slide 3 (situation) points[1]'."""
    parts, rest = [], list(path)
    if len(rest) >= 2 and rest[0] == "slides" and isinstance(rest[1], int):
        i = rest[1]
        slides = data.get("slides") if isinstance(data, dict) else None
        typ = slides[i].get("type", "?") if isinstance(slides, list) and i < len(slides) and isinstance(slides[i], dict) else "?"
        parts.append(f"slide {i + 1} ({typ})")
        rest = rest[2:]
    s = ""
    for p in rest:
        s += f"[{p}]" if isinstance(p, int) else (f".{p}" if s else p)
    if s:
        parts.append(s)
    return " ".join(parts) or "(top level)"


def lookup(data, path):
    node = data
    try:
        for p in path:
            node = node[p]
    except (KeyError, IndexError, TypeError):
        return None
    return node


def validate(data, schema, strict, client_hint=None):
    """Schema first, then the deck rules. Returns warnings; raises BuildError on errors."""
    v = Validator(schema)
    errs = []
    seen = set()
    for path, msg in v.errors(data):
        key = (path, msg)
        if key in seen:
            continue
        seen.add(key)
        node = lookup(data, path)
        snippet = ""
        label = node.get("text") or node.get("label") if isinstance(node, dict) else None
        if isinstance(label, str):
            t = label
            snippet = f' ("{t[:60]}{"..." if len(t) > 60 else ""}")'
        errs.append(f"{where(path, data)}: {msg}{snippet}")
    if errs:
        raise BuildError("\n".join(errs))

    warns = []
    slides = data["slides"]
    types = [s["type"] for s in slides]
    if types[0] != "cover":
        errs.append(f"slide 1 ({types[0]}): the first slide must be the cover")
    if types.count("cover") > 1:
        errs.append("there is more than one cover slide; keep one, first")
    for t in REQUIRED_TYPES:
        if t not in types:
            errs.append(f"missing required slide: add a \"{t}\" slide ({PURPOSE[t]})")
    if types.count("sources") > 1:
        errs.append("there is more than one sources slide; keep one, last (it splits itself when long)")
    elif "sources" in types and types.index("sources") != len(types) - 1:
        errs.append(f"slide {types.index('sources') + 1} (sources): the sources slide must be the last slide")

    ids = [s["id"] for s in data["sources"]]
    for sid in sorted({i for i in ids if ids.count(i) > 1}):
        errs.append(f"sources: the ID {sid} is used more than once")
    known = set(ids)
    used = set()
    client = data["meta"]["client"]["name"]

    def walk(node, path):
        if isinstance(node, dict):
            if "cite" in node or "to_confirm" in node:
                for j, c in enumerate(node.get("cite", [])):
                    used.add(c["source"])
                    if c["source"] not in known:
                        errs.append(f"{where(path + ('cite', j), data)}: cites {c['source']}, which is not in sources[]. "
                                    f"Add it to the register or fix the ID (known: {', '.join(ids) or 'none'})")
                return
            for k, x in node.items():
                walk(x, path + (k,))
        elif isinstance(node, list):
            for j, x in enumerate(node):
                walk(x, path + (j,))
        elif isinstance(node, str) and path and path[-1] not in ("type", "kind", "eyebrow", "label"):
            # A plain field that names the client next to a figure reads like a claim.
            if re.search(re.escape(client), node, re.I) and re.search(r"\d", node):
                warns.append(f"{where(path, data)}: names {client} with a figure but is not a cited claim "
                             f"(\"{node[:60]}\"). If it is a fact about {client}, move it to a cited field "
                             f"(situation points or stats, focus evidence)")

    for i, s in enumerate(slides):
        walk(s, ("slides", i))
        eb, ti = s.get("eyebrow", EYEBROW.get(s["type"], "")), s.get("title", "")
        if eb and ti and re.sub(r"\W", "", eb.lower()) == re.sub(r"\W", "", ti.lower()):
            warns.append(f"slide {i + 1} ({s['type']}): the title repeats the eyebrow \"{eb}\". "
                         "Make the title the slide's message, or set a different eyebrow")
    for sid in ids:
        if sid not in used:
            warns.append(f"sources: {sid} is never cited (it is still listed on the Sources slide)")
    if errs:
        raise BuildError("\n".join(errs))
    if strict and warns:
        raise BuildError("\n".join(f"{w} [--strict]" for w in warns))
    return warns


# --- 2. Art: inline SVG illustrations ---------------------------------------------

def _arrow(x, y, d, s=4.6, w=2.8):
    pts = {"r": f"{x},{y} {x - s},{y - w} {x - s},{y + w}",
           "l": f"{x},{y} {x + s},{y - w} {x + s},{y + w}",
           "d": f"{x},{y} {x - w},{y - s} {x + w},{y - s}",
           "u": f"{x},{y} {x - w},{y + s} {x + w},{y + s}"}[d]
    return f'<polygon class="pm-arw" points="{pts}"/>'


def _node(x, y, w, h, title, owner="", detail="", cls=""):
    cx = x + w / 2
    spans = "".join(f'<tspan x="{cx}" dy="{0 if i == 0 else 8.2}">{esc(t)}</tspan>' for i, t in enumerate(title))
    out = f'<rect class="pm-node {cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="2.5"/>'
    out += f'<text class="pm-t" x="{cx}" y="{y + 11.5}" text-anchor="middle">{spans}</text>'
    if owner:
        out += f'<text class="pm-o" x="{cx}" y="{y + h - 14}" text-anchor="middle">{esc(owner)}</text>'
    if detail:
        out += f'<text class="pm-d" x="{cx}" y="{y + h - 6.5}" text-anchor="middle">{esc(detail)}</text>'
    return out


def _gap(cx, cy, n):
    return f'<circle class="pm-gap" cx="{cx}" cy="{cy}" r="5.6"/><text class="pm-gn" x="{cx}" y="{cy + 2.3}" text-anchor="middle">{n}</text>'


def _clar(cx, cy, n="?"):
    return f'<circle class="pm-clar" cx="{cx}" cy="{cy}" r="5.4"/><text class="pm-cn" x="{cx}" y="{cy + 2.3}" text-anchor="middle">{n}</text>'


def _ai(x, y, w, h, n, named=True):
    """AI mark: a square at the node's bottom-right corner (named = filled)."""
    sx, sy = x + w - 14, y + h - 6
    cls, tcls = ("pm-ai-named", "pm-ain") if named else ("pm-ai-sugg", "pm-ais")
    return (f'<rect class="{cls}" x="{sx}" y="{sy}" width="13" height="10" rx="1.5"/>'
            f'<text class="{tcls}" x="{sx + 6.5}" y="{sy + 7.1}" text-anchor="middle">{n}</text>')


def _halo(x, y, w, h):
    return f'<rect class="pm-halo" x="{x - 3}" y="{y - 3}" width="{w + 6}" height="{h + 6}" rx="4"/>'


def _pill(cx, cy, label):
    w = 6 + 3.4 * len(label)
    return (f'<rect class="pm-pill" x="{cx - w / 2}" y="{cy - 4.6}" width="{w}" height="9.2" rx="4.6"/>'
            f'<text class="pm-pt" x="{cx}" y="{cy + 1.9}" text-anchor="middle">{esc(label)}</text>')


def _svg(body, label, vb="0 0 320 220"):
    return f'<svg viewBox="{vb}" role="img" aria-label="{esc(label)}" preserveAspectRatio="xMidYMid meet">{body}</svg>'


def art_process_map(ai=False):
    """A slice of a swimlane board: three lanes, a decision, a gap and a clarification."""
    W, NW, NH = 320, 66, 46
    b = f'<rect class="pm-bg" width="{W}" height="220"/>'
    b += '<rect class="pm-l0" y="0" width="320" height="72"/><rect class="pm-l1" y="72" width="320" height="74"/><rect class="pm-l0" y="146" width="320" height="74"/>'
    b += '<line class="pm-gutter" x1="50" y1="0" x2="50" y2="220"/>'
    for y, name in ((38.5, "Requester"), (111.5, "Team lead"), (185.5, "Finance")):
        b += f'<text class="pm-lab" x="7" y="{y}">{name}</text>'
    n1, n2, n3, n4 = (58, 13), (132, 86), (244, 160), (244, 13)
    # flows: N1 -> N2 -> decision -> (yes) N3 / (no) N4, with N4 feeding back to N1
    b += f'<path class="pm-flow" d="M91 59 V109 H126"/>' + _arrow(132, 109, "r")
    b += f'<path class="pm-flow" d="M198 109 H207"/>' + _arrow(213, 109, "r")
    b += f'<path class="pm-flow" d="M226 122 V183 H238"/>' + _arrow(244, 183, "r")
    b += f'<path class="pm-flow" d="M226 96 V36 H238"/>' + _arrow(244, 36, "r")
    b += f'<path class="pm-feed" d="M277 13 V6.5 H91 V8"/>' + _arrow(91, 13, "d", 4, 2.6)
    b += _pill(226, 70, "No") + _pill(226, 150, "Yes")
    if ai:
        b += _halo(*n2, NW, NH) + _halo(*n3, NW, NH)
    b += _node(*n1, NW, NH, ["Submit request"], "Requester", "Email form")
    b += _node(*n2, NW, NH, ["Check request"], "Team lead", "Manual review")
    b += _node(*n4, NW, NH, ["Return to", "requester"], "Team lead", "Not written down", "inf")
    b += _node(*n3, NW, NH, ["Record in", "system"], "Finance", "Re-keyed by hand", "inf")
    b += '<path class="pm-dec" d="M226 96 L239 109 L226 122 L213 109 Z"/><text class="pm-dl" x="226" y="111.3" text-anchor="middle">OK?</text>'
    b += _gap(n3[0] + NW, n3[1], 1) + _clar(n4[0] + NW, n4[1] + 1)
    if ai:
        b += _ai(*n2, NW, NH, "01", True) + _ai(*n3, NW, NH, "02", False)
    label = "Illustrative AI-opportunity map: a swimlane process with AI marks on two steps" if ai else \
        "Illustrative process map: a swimlane process with a decision, a gap and a point to clarify"
    return _svg(b, label)


def art_ai_map():
    return art_process_map(ai=True)


def art_report():
    b = '<rect width="320" height="220" fill="#fff"/><rect x="0.5" y="0.5" width="319" height="219" fill="none" class="rp-line"/>'
    b += '<text class="rp-t" x="18" y="26" font-size="11" font-weight="600">Findings report</text>'
    b += '<text class="rp-k" x="302" y="25" text-anchor="end">SUMMARY</text>'
    b += '<line class="rp-line" x1="18" y1="35" x2="302" y2="35"/>'
    for i, (k, val) in enumerate((("STEPS MAPPED", "48"), ("GAPS FOUND", "7"), ("AI IDEAS", "5"))):
        x = 18 + i * 96
        if i:
            b += f'<line class="rp-line" x1="{x - 10}" y1="45" x2="{x - 10}" y2="80"/>'
        b += f'<text class="rp-k" x="{x}" y="52">{k}</text><text class="rp-v" x="{x}" y="75">{val}</text>'
    b += '<line class="rp-line" x1="18" y1="90" x2="302" y2="90"/>'
    b += '<text class="rp-k" x="18" y="104">WHERE TIME IS LOST</text>'
    rows = (("Re-keying between systems", 104, True), ("Waiting for approval", 78, False),
            ("Chasing missing details", 58, False), ("Checks done by hand", 36, False))
    for i, (t, w, hot) in enumerate(rows):
        y = 119 + i * 14
        b += f'<text class="rp-x" x="18" y="{y}">{t}</text>'
        b += f'<rect class="rp-trk" x="176" y="{y - 6}" width="126" height="6"/>'
        b += f'<rect class="{"rp-acc" if hot else "rp-bar"}" x="176" y="{y - 6}" width="{w}" height="6"/>'
    b += '<line class="rp-line" x1="18" y1="174" x2="302" y2="174"/>'
    for y, w in ((184, 284), (193, 270), (202, 196)):
        b += f'<rect class="rp-txt" x="18" y="{y}" width="{w}" height="4" rx="2"/>'
    return _svg(b, "Illustrative findings report: summary figures, where time is lost, and commentary")


def art_recommendation():
    b = '<rect width="320" height="220" fill="#fff"/><rect x="0.5" y="0.5" width="319" height="219" fill="none" class="rp-line"/>'
    x0, y0, w, h = 44, 16, 262, 168
    b += f'<rect x="{x0 + w / 2}" y="{y0}" width="{w / 2}" height="{h / 2}" fill="#e9ede8"/>'
    b += f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="none" class="rp-line"/>'
    b += f'<line class="rp-line" x1="{x0 + w / 2}" y1="{y0}" x2="{x0 + w / 2}" y2="{y0 + h}"/><line class="rp-line" x1="{x0}" y1="{y0 + h / 2}" x2="{x0 + w}" y2="{y0 + h / 2}"/>'
    b += f'<text class="rp-k" x="{x0 + w - 8}" y="{y0 + 13}" text-anchor="end" style="fill:var(--accent)">RECOMMENDED</text>'
    b += f'<text class="rp-k" x="{x0 + 8}" y="{y0 + h - 8}">RULED OUT</text>'
    pts = (("Option A", 92, 62, False), ("Option B", 236, 50, True), ("Option C", 118, 142, False), ("Option D", 252, 128, False))
    for t, cx, cy, best in pts:
        b += f'<circle cx="{cx}" cy="{cy}" r="4.2" class="{"rp-acc" if best else "rp-bar"}"/>'
        b += f'<text class="rp-x" x="{cx}" y="{cy + 14}" text-anchor="middle">{t}</text>'
    b += f'<text class="rp-k" x="{x0 + w / 2}" y="204" text-anchor="middle">FIT TO NEEDS &#8594;</text>'
    b += f'<text class="rp-k" x="20" y="{y0 + h / 2}" text-anchor="middle" transform="rotate(-90 20 {y0 + h / 2})">LOWER EFFORT &#8594;</text>'
    return _svg(b, "Illustrative recommendation: four options placed by fit and effort, one recommended")


ART = {"report": art_report, "process_map": art_process_map, "ai_map": art_ai_map,
       "recommendation": art_recommendation}

CHECK = '<svg viewBox="0 0 10 10" aria-hidden="true"><path d="M2 5.2 L4.2 7.3 L8 3" fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
PERSON = ('<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="7" r="3.4" fill="none" stroke="#153e2f" stroke-width="1.4"/>'
          '<path d="M3.6 17 C3.6 13.4 6.5 11.4 10 11.4 S16.4 13.4 16.4 17" fill="none" stroke="#153e2f" stroke-width="1.4" stroke-linecap="round"/></svg>')
DOCUMENT = ('<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 2.8 H11.6 L15 6.2 V17.2 H5 Z M11.4 3 V6.4 H14.8 M7.6 10 H12.4 M7.6 13 H12.4" '
            'fill="none" stroke="#153e2f" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/></svg>')
AVATAR = ('<svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="10.5" r="4.6" fill="#dce2dc"/>'
          '<path d="M5.5 23.5 C5.5 18.6 9.3 16.2 14 16.2 S22.5 18.6 22.5 23.5 Z" fill="#dce2dc"/></svg>')


# --- 3. Slides -------------------------------------------------------------------

def fmt_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B')} {d.year}"


class Deck:
    def __init__(self, data):
        self.data = data
        self.meta = data["meta"]
        self.client = self.meta["client"]["name"]
        self.sources = {s["id"]: s for s in data["sources"]}
        self.cited_on = {}   # source id -> [slide numbers]
        self.tbc = []        # (slide number, claim text, what to confirm)
        self.slide_cites = []
        self.slide_tbc = 0
        self.n = 0

        slides = list(data["slides"])
        self.auto_sources = False
        has_cites = self._has_cites(slides)
        if has_cites and slides[-1]["type"] != "sources":
            slides.append({"type": "sources"})
            self.auto_sources = True
        self.slides = slides
        pages = max(1, math.ceil((len(data["sources"]) + self._count_tbc(slides)) / SOURCES_PER_SLIDE))
        self.total = len(slides) - 1 + pages if slides[-1]["type"] == "sources" else len(slides)
        self.sources_pages = pages
        foot = [self.meta.get("status", "Proposal for discussion"), fmt_date(self.meta["date"])]
        if self.meta.get("confidential"):
            foot.append(self.meta["confidential"])
        self.foot_text = " / ".join(foot)

    @staticmethod
    def _count_tbc(node):
        if isinstance(node, dict):
            if "to_confirm" in node and "cite" not in node:
                return 1
            return sum(Deck._count_tbc(v) for v in node.values())
        if isinstance(node, list):
            return sum(Deck._count_tbc(v) for v in node)
        return 0

    @staticmethod
    def _has_cites(node):
        if isinstance(node, dict):
            if "cite" in node or "to_confirm" in node:
                return True
            return any(Deck._has_cites(v) for v in node.values())
        if isinstance(node, list):
            return any(Deck._has_cites(v) for v in node)
        return False

    # citations ---------------------------------------------------------------
    def mark(self, claim):
        """The visible marker after a claim: [S1 p. 2] or TO CONFIRM."""
        if "cite" in claim:
            parts = []
            for c in claim["cite"]:
                sid = c["source"]
                if sid not in self.slide_cites:
                    self.slide_cites.append(sid)
                on = self.cited_on.setdefault(sid, [])
                if self.n not in on:
                    on.append(self.n)
                label = sid + (" " + c["locator"] if c.get("locator") else "")
                parts.append(f'<cite class="c"><a href="#src-{esc(sid)}">{esc(label)}</a></cite>')
            return parts[0] if len(parts) == 1 else '<span class="cites">' + "; ".join(parts) + "</span>"
        self.tbc.append((self.n, claim.get("text") or claim.get("label", ""), claim["to_confirm"]))
        self.slide_tbc += 1
        return f'<span class="tbc" title="{esc(claim["to_confirm"])}">To confirm</span>'

    def srcline(self):
        if not self.slide_cites and not self.slide_tbc:
            return ""
        order = [sid for sid in self.sources if sid in self.slide_cites]
        names = [f"{esc(sid)} {esc(self.sources[sid]['title'])}" for sid in order]
        sep = '<span class="sep">|</span>'
        budget = 168 - (22 if self.slide_tbc else 0)
        if sum(len(sid) + len(self.sources[sid]["title"]) + 4 for sid in order) > budget:
            names = [esc(sid) for sid in order]
            names.append(f"full names on slide {self.total - self.sources_pages + 1}")
        out = '<p class="srcline"><b>Sources</b>' + sep.join(names)
        if self.slide_tbc:
            n = self.slide_tbc
            out += (sep if names else "") + f'<span class="tbc-count">{n} point{"s" if n > 1 else ""} to confirm</span>'
        return out + "</p>"

    # chrome -------------------------------------------------------------------
    def foot(self, cover=False):
        wm = "" if cover else '<span class="wm" role="img" aria-label="Source"></span>'
        folio = "" if cover else f'<span class="folio">{self.n} / {self.total}</span>'
        return f'<footer class="slide-foot">{wm}<span>{esc(self.foot_text)}</span>{folio}</footer>'

    def head(self, s, typ):
        eb = s.get("eyebrow", EYEBROW.get(typ, ""))
        out = '<header class="slide-head">'
        if eb:
            out += f'<p class="eyebrow">{esc(eb)}</p>'
        out += f'<h1>{esc(s["title"])}</h1>'
        if s.get("lead"):
            out += f'<p class="lead">{esc(s["lead"])}</p>'
        return out + "</header>"

    def frame(self, typ, inner, title, extra_cls=""):
        cls = f"slide slide--{typ}" + (f" {extra_cls}" if extra_cls else "")
        label = f"Slide {self.n} of {self.total}: {title}"
        return (f'<div class="frame" id="slide-{self.n}"><section class="{cls}" aria-label="{esc(label)}">'
                f"{inner}</section></div>")

    # slide types ----------------------------------------------------------------
    def cover(self, s):
        label = s.get("label") or self.meta["client"].get("label") or self.client
        t = esc(s["title"]) + (f' <span>{esc(s["qualifier"])}</span>' if s.get("qualifier") else "")
        art = s.get("art")
        txt = f'<div class="cover-text"><h1>{t}</h1><p class="cover-lead">{esc(s["lead"])}</p>'
        if s.get("support"):
            txt += f'<p class="cover-support">{esc(s["support"])}</p>'
        txt += "</div>"
        art_html = f'<div class="cover-art"><div class="art">{ART[art]()}</div></div>' if art else ""
        inner = (f'<div class="cover-top"><span class="wm" role="img" aria-label="Source"></span>'
                 f'<span class="cover-label">{esc(label)}</span></div>'
                 f'<div class="cover-main{" has-art" if art else ""}">{txt}{art_html}</div>')
        return inner + self.foot(cover=True), s["title"], ""

    def divider(self, s):
        inner = '<div class="slide-body">'
        if s.get("eyebrow"):
            inner += f'<p class="eyebrow">{esc(s["eyebrow"])}</p>'
        inner += f'<h1>{esc(s["title"])}</h1>'
        if s.get("subtitle"):
            inner += f'<p class="dark-sub">{esc(s["subtitle"])}</p>'
        return inner + "</div>" + self.foot(), s["title"], "slide--dark"

    def closing(self, s):
        inner = '<div class="slide-body">'
        if s.get("eyebrow"):
            inner += f'<p class="eyebrow">{esc(s["eyebrow"])}</p>'
        inner += f'<h1>{esc(s["title"])}</h1>'
        if s.get("text"):
            inner += f'<p class="dark-sub">{esc(s["text"])}</p>'
        c = s.get("contact")
        if c:
            cells = [("Contact", c["name"]), ("Role", c.get("role")), ("Email", c.get("email")), ("Phone", c.get("phone"))]
            inner += '<div class="contact">' + "".join(
                f'<div><span class="k">{k}</span><span class="v">{esc(v)}</span></div>' for k, v in cells if v) + "</div>"
        return inner + "</div>" + self.foot(), s["title"], "slide--dark"

    def situation(self, s):
        pts = "".join(f'<li><h3>{esc(p["heading"])}</h3><p>{esc(p["text"])} {self.mark(p)}</p></li>' for p in s["points"])
        side = ""
        stats = s.get("stats", [])
        if stats:
            side += f'<div class="stats" style="--n:{len(stats)}">' + "".join(
                f'<div class="stat"><span class="v">{esc(t["value"])}</span><span class="l">{esc(t["label"])} {self.mark(t)}</span></div>'
                for t in stats) + "</div>"
        imp = s.get("implication")
        if imp:
            side += f'<div class="callout"><h2>{esc(imp.get("heading", "What this means"))}</h2><p>{esc(imp["text"])}</p></div>'
        body = f'<div class="sit{"" if side else " no-side"}"><ol class="points">{pts}</ol>'
        body += (f'<div class="sit-side">{side}</div>' if side else "") + "</div>"
        return body

    def focus(self, s):
        opts = s["options"]
        cards = ""
        for i, o in enumerate(opts):
            label = o.get("label") or f"Option {chr(65 + i)}"
            rec = '<span class="rec">Recommended</span>' if o.get("recommended") else ""
            c = f'<article class="card{" is-rec" if rec else ""}"><div class="card-top"><p class="eyebrow">{esc(label)}</p>{rec}</div>'
            c += f'<h2>{esc(o["title"])}</h2><p>{esc(o["text"])}</p>'
            if o.get("questions"):
                c += '<div class="qs"><span class="k">Questions it answers</span><ul>' + "".join(
                    f"<li>{esc(q)}</li>" for q in o["questions"]) + "</ul></div>"
            ev = o.get("evidence")
            if ev:
                c += f'<p class="evidence"><span class="k">Why this area</span>{esc(ev["text"])} {self.mark(ev)}</p>'
            cards += c + "</article>"
        body = f'<div class="cards" style="--n:{len(opts)}">{cards}</div>'
        if s.get("note"):
            body += f'<p class="note">{esc(s["note"])}</p>'
        return body

    def outputs(self, s):
        items = s["items"]
        n = len(items)
        out = ""
        for i, it in enumerate(items):
            eb = it.get("eyebrow") or f"{i + 1:02d} {ART_LABEL[it['kind']]}"
            out += f'<article class="example"><div class="art">{ART[it["kind"]]()}</div><div class="ex-text">'
            out += f'<p class="eyebrow">{esc(eb)}</p><h3>{esc(it["title"])}</h3><p>{esc(it["text"])}</p>'
            if it.get("caption"):
                out += f'<p class="caption">{esc(it["caption"])}</p>'
            out += "</div></article>"
        body = f'<div class="examples{" one" if n == 1 else ""}" style="--n:{n}">{out}</div>'
        if s.get("note"):
            body += f'<p class="note">{esc(s["note"])}</p>'
        return body

    def deliverables(self, s):
        items = s["items"]
        n = len(items)
        rows = math.ceil(n / 2)
        lis = ""
        for i, it in enumerate(items):
            opt = bool(it.get("optional"))
            cls = ["is-opt"] if opt else []
            if i == rows - 1 or i == n - 1:
                cls.append("last-in-col")
            tag = '<span class="opt">Optional</span>' if opt else ""
            lis += (f'<li class="{" ".join(cls)}"><span class="mark">{"" if opt else CHECK}</span><div>'
                    f'<h3>{esc(it["title"])}{tag}</h3>' + (f'<p>{esc(it["text"])}</p>' if it.get("text") else "") + "</div></li>")
        body = f'<ul class="deliv" style="--rows:{rows}">{lis}</ul>'
        legend = ""
        if any(it.get("optional") for it in items):
            legend = (f'<p class="legend"><span><span class="mark">{CHECK}</span>Included</span>'
                      '<span class="is-opt"><span class="mark"></span>Optional, agreed at scoping</span></p>')
        note = f'<p class="note">{esc(s["note"])}</p>' if s.get("note") else ""
        if legend or note:
            body += f'<div class="deliv-foot">{note}{legend}</div>'
        return body

    def process(self, s):
        steps = s["steps"]
        if s.get("layout") == "steps":
            body = '<ol class="steps">' + "".join(
                f'<li><span class="num">{i + 1:02d}</span><div><div class="s-head"><h3>{esc(st["title"])}</h3>'
                + (f'<span class="when">{esc(st["when"])}</span>' if st.get("when") else "")
                + f'</div><p>{esc(st["text"])}</p>'
                + (f'<p class="s-out"><span class="k">Output</span> {esc(st["output"])}</p>' if st.get("output") else "")
                + "</div></li>" for i, st in enumerate(steps)) + "</ol>"
        else:
            body = f'<ol class="timeline" style="--n:{len(steps)}">' + "".join(
                f'<li><div class="t-top"><span class="num">{i + 1:02d}</span><span class="when">{esc(st.get("when", ""))}</span></div>'
                f'<div class="t-track"></div><h3>{esc(st["title"])}</h3><p>{esc(st["text"])}</p>'
                + (f'<p class="t-out"><span class="k">Output</span><span>{esc(st["output"])}</span></p>' if st.get("output") else "")
                + "</li>"
                for i, st in enumerate(steps)) + "</ol>"
        if s.get("total"):
            body += f'<p class="total">{esc(s["total"])}</p>'
        return body

    def needs(self, s):
        lis = ""
        for it in s["items"]:
            icon = DOCUMENT if re.search(r"document|file|data|access|record|system", it["role"], re.I) else PERSON
            lis += (f'<li><span class="role-ic">{icon}</span><div><h3>{esc(it["role"])}</h3>'
                    + (f'<p class="time">{esc(it["time"])}</p>' if it.get("time") else "")
                    + f'</div><p class="what">{esc(it["text"])}</p></li>')
        body = f'<ol class="needs">{lis}</ol>'
        if s.get("note"):
            body += f'<p class="note">{esc(s["note"])}</p>'
        return body

    def team(self, s):
        people, firms = s.get("people", []), s.get("firms")
        cls = "team" + ("" if firms else " no-firms") + ("" if people else " no-people")
        body = f'<div class="{cls}">'
        if people:
            body += '<div class="people">' + "".join(
                f'<div class="person"><span class="avatar">{AVATAR}</span><div><h3>{esc(p["name"])}</h3>'
                f'<p class="role">{esc(p["role"])}</p>' + (f'<p class="bio">{esc(p["text"])}</p>' if p.get("text") else "")
                + "</div></div>" for p in people) + "</div>"
        if firms:
            body += f'<aside class="firms"><h2>{esc(firms.get("heading", "Firms we work with"))}</h2><div class="logos">'
            body += "".join(f'<div class="logo-ph" role="img" aria-label="Logo placeholder: {esc(l["name"])}">'
                            f'<span class="k">Logo</span><span>{esc(l["name"])}</span></div>' for l in firms["logos"])
            body += "</div>" + (f'<p class="note">{esc(firms["note"])}</p>' if firms.get("note") else "") + "</aside>"
        return body + "</div>"

    def commercials(self, s):
        ns, tm = s["next_step"], s["terms"]
        left = f'<section class="callout"><h2>{esc(ns.get("heading", "Next step"))}</h2><p>{esc(ns["text"])}</p>'
        if ns.get("actions"):
            left += '<ol class="actions">' + "".join(
                f'<li><span class="num">{i + 1:02d}</span><span>{esc(a)}</span></li>' for i, a in enumerate(ns["actions"])) + "</ol>"
        left += "</section>"
        right = f'<section class="terms"><h2>{esc(tm.get("heading", "Commercial terms"))}</h2><span class="price">{esc(tm["price"])}</span>'
        if tm.get("price_note"):
            right += f'<p class="price-note">{esc(tm["price_note"])}</p>'
        if tm.get("rows"):
            right += "<dl>" + "".join(f'<div><dt>{esc(r["label"])}</dt><dd>{esc(r["value"])}</dd></div>' for r in tm["rows"]) + "</dl>"
        if tm.get("note"):
            right += f'<p class="note">{esc(tm["note"])}</p>'
        right += "</section>"
        return f'<div class="comm">{left}{right}</div>'

    def sources_pages_html(self, s):
        """The register, SOURCES_PER_SLIDE rows a slide; claims still to confirm follow as rows."""
        units = [("src", x) for x in self.data["sources"]] + [("tbc", x) for x in self.tbc]
        chunks = [units[i:i + SOURCES_PER_SLIDE] for i in range(0, len(units), SOURCES_PER_SLIDE)] or [[]]
        title = s.get("title", "Sources")
        lead = s.get("lead") or f"Every claim about {self.client} cites one of these records. The marker beside it gives the place."
        out = []
        for k, chunk in enumerate(chunks):
            self.n += 1
            self.slide_cites, self.slide_tbc = [], 0
            t = title
            eb = s.get("eyebrow", EYEBROW["sources"]) + (f" \u00b7 {k + 1} of {len(chunks)}" if len(chunks) > 1 else "")
            head = self.head(dict(s, title=t, eyebrow=eb, lead=lead if k == 0 else s.get("lead", "")), "sources")
            rows = ""
            for kind, x in chunk:
                if kind == "src":
                    on = self.cited_on.get(x["id"], [])
                    links = ", ".join(f'<a href="#slide-{n}">{n}</a>' for n in sorted(on)) or '<span class="none">Not cited</span>'
                    det = " · ".join(v for v in (x.get("detail"), urlparse(x["url"]).netloc if x.get("url") else "") if v)
                    rows += (f'<tr id="src-{esc(x["id"])}"><td>{esc(x["id"])}</td><td>{esc(x["title"])}'
                             + (f'<span class="d">{esc(det)}</span>' if det else "")
                             + f'</td><td>{esc(KIND_LABEL[x["kind"]])}</td><td>{esc(x.get("date", ""))}</td><td class="on">{links}</td></tr>')
                else:
                    n, text, why = x
                    rows += (f'<tr class="tbc-row"><td><span class="tbc">To confirm</span></td><td>{esc(text)}'
                             f'<span class="d">{esc(why)}</span></td><td>No source yet</td><td></td>'
                             f'<td class="on"><a href="#slide-{n}">{n}</a></td></tr>')
            table = ('<table class="src-table"><colgroup><col style="width:11%"><col><col style="width:13%"><col style="width:11%"><col style="width:12%"></colgroup>'
                     '<thead><tr><th>ID</th><th>Source record</th><th>Kind</th><th>Date</th><th>Cited on slide</th></tr></thead>'
                     f"<tbody>{rows}</tbody></table>")
            out.append(self.frame("sources", head + f'<div class="slide-body">{table}</div>' + self.foot(),
                                  t + (f" ({k + 1} of {len(chunks)})" if len(chunks) > 1 else "")))
        return "".join(out)

    def render(self):
        frames = []
        for s in self.slides:
            typ = s["type"]
            if typ == "sources":
                frames.append(self.sources_pages_html(s))
                continue
            self.n += 1
            self.slide_cites, self.slide_tbc = [], 0
            if typ in ("cover", "divider", "closing"):
                inner, title, extra = getattr(self, typ)(s)
                frames.append(self.frame(typ, inner, title, extra))
                continue
            body = getattr(self, typ)(s)
            inner = self.head(s, typ) + f'<div class="slide-body">{body}</div>' + self.srcline() + self.foot()
            frames.append(self.frame(typ, inner, s["title"]))
        return "".join(frames)


# --- 4. Page -----------------------------------------------------------------------

SCRIPT = """(function(){
var d=document,root=d.documentElement,frames=[].slice.call(d.querySelectorAll('.frame'));
function fit(){var w=root.clientWidth,g=w<700?12:24;root.style.setProperty('--g',g+'px');root.style.setProperty('--s',Math.max(.1,(w-2*g)/1280));}
fit();addEventListener('resize',fit);
function cur(){var best=0,bd=1e9;frames.forEach(function(f,i){var t=Math.abs(f.getBoundingClientRect().top);if(t<bd){bd=t;best=i}});return best}
function go(i){i=Math.max(0,Math.min(frames.length-1,i));frames[i].scrollIntoView({block:'start'});if(history.replaceState)history.replaceState(null,'','#'+frames[i].id)}
addEventListener('keydown',function(e){if(e.altKey||e.ctrlKey||e.metaKey)return;var k=e.key,t=e.target&&e.target.tagName;if(t==='INPUT'||t==='TEXTAREA')return;
if(k==='ArrowRight'||k==='ArrowDown'||k==='PageDown'||(k===' '&&!e.shiftKey)){e.preventDefault();go(cur()+1)}
else if(k==='ArrowLeft'||k==='ArrowUp'||k==='PageUp'||(k===' '&&e.shiftKey)){e.preventDefault();go(cur()-1)}
else if(k==='Home'){e.preventDefault();go(0)}else if(k==='End'){e.preventDefault();go(frames.length-1)}});
})();"""


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def inline_css():
    css = CSS_PATH.read_text(encoding="utf-8")
    for name, mime in (("source-400.ttf", "font/ttf"), ("source-600.ttf", "font/ttf"), ("source-wordmark.png", "image/png")):
        css = css.replace(f"url(fonts/{name})", f"url({data_uri(FONTS / name, mime)})")
    left = re.findall(r"url\((?!data:)[^)]*\)", css)
    if left:
        raise BuildError(f"deck.css: cannot inline {', '.join(left)}; only fonts/ assets are inlined")
    return css


def page(deck, slides_html, linked, src_name):
    meta = deck.meta
    if linked:
        style = '<link rel="stylesheet" href="deck.css">'
        note = ("<!-- Source proposal deck template, generated by build_proposal.py from "
                f"{esc(src_name)}. Keep deck.css and fonts/ next to this file.\n"
                "     Every slide type appears once as <section class=\"slide slide--TYPE\">, with placeholder copy.\n"
                "     To make a deck, fill a proposal.json (see STRUCTURE.md) and run build_proposal.py,\n"
                "     which validates it and inlines everything into one file. -->\n")
    else:
        style = f"<style>\n{inline_css()}\n</style>"
        note = f"<!-- Built by build_proposal.py from {esc(src_name)}. Self-contained: no external requests. -->\n"
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            f"<title>{esc(meta['title'])}</title>\n{style}\n</head>\n<body>\n{note}"
            f'<main class="deck" aria-label="{esc(meta["title"])}">\n{slides_html}\n</main>\n'
            f"<script>{SCRIPT}</script>\n</body>\n</html>\n")


def build(src, out, strict=False, linked=False, check=False):
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BuildError(f"{src.name} is not valid JSON: line {e.lineno}, column {e.colno}: {e.msg}")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    warns = validate(data, schema, strict)
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    deck = Deck(data)
    if deck.auto_sources:
        print("note: no sources slide given; one was added at the end", file=sys.stderr)
    slides_html = deck.render()
    if check:
        return deck, None
    doc = page(deck, slides_html, linked, src.name)
    out.write_text(doc, encoding="utf-8")
    return deck, len(doc.encode("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a Source proposal deck (HTML, 1280x720 slides) from proposal.json.")
    ap.add_argument("json", type=Path, help="proposal.json to build")
    ap.add_argument("out", type=Path, nargs="?", help="output .html (default: next to the JSON, same name)")
    ap.add_argument("--strict", action="store_true", help="treat warnings (unused sources, possible uncited claims) as errors")
    ap.add_argument("--linked", action="store_true", help="link deck.css and fonts/ instead of inlining them (for template.html)")
    ap.add_argument("--check", action="store_true", help="validate and render in memory; write nothing")
    a = ap.parse_args(argv)
    out = a.out or a.json.with_suffix(".html")
    try:
        deck, size = build(a.json, out, a.strict, a.linked, a.check)
    except BuildError as e:
        lines = str(e).splitlines()
        print(f"build_proposal.py: {a.json.name}: {len(lines)} error(s); nothing was written.", file=sys.stderr)
        for line in lines:
            print(f"  - {line}", file=sys.stderr)
        return 1
    except (OSError, KeyError, ValueError) as e:
        print(f"build_proposal.py: {e}", file=sys.stderr)
        return 2
    claims = sum(len(v) for v in deck.cited_on.values())
    msg = (f"{deck.total} slides, {len(deck.cited_on)} of {len(deck.sources)} sources cited "
           f"({claims} slide citations), {len(deck.tbc)} point(s) to confirm")
    if a.check:
        print(f"ok: {a.json.name} is valid: {msg}")
    else:
        print(f"wrote {out} ({size // 1024} KB): {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

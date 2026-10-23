#!/usr/bin/env python3
"""build_map.py: one self-contained page from a map JSON plus its records, for both map sections.

  python3 design-system/process-map/build_map.py <ws> process-map <name> <out.html>
  python3 design-system/process-map/build_map.py <ws> process-map-ai-opportunity <name> <out.html>
  python3 design-system/process-map/build_map.py --specimen <ws>

The second form builds the base map named by the layer, then fills the board's slots from
design-system/process-map-ai-opportunity/fills.html. --specimen builds both gitignored specimen.html
files from <ws> (examples/), adding a generated variant for each state the examples lack.

Everything the READMEs call derived is computed here: columns, rows, coordinates and routes (README
section 2), badge numbers, the citation points and their markers, group meta, lane notes, {count:...} tokens,
provenance lines, the Citation points section, the tooltips and the footer; and on an AI page the List rows,
the Flow view (the AI README section 3) and the board marks. The build fails on build-6 (a line crossing a card, or a
branch pill with no free stretch of its width plus 16; in the Flow, a line through a step or a label), and warns
when two Flow lines cross or run closer than 12 units. Same inputs, same bytes: no timestamps, no random ids, and
no build meta (bs.py adds that).

Standard library only. Exit codes: 0 ok, 1 data error, 2 cannot run.
"""

import html
import itertools
import json
import os
import pathlib
import re
import sys
import unicodedata

HERE = pathlib.Path(os.path.abspath(__file__)).parent
ROOT = HERE.parent.parent
BOARD_HTML = HERE / "board.html"
AI_DIR = ROOT / "design-system" / "process-map-ai-opportunity"
FILLS_HTML = AI_DIR / "fills.html"
RULES_JSON = ROOT / "formats" / "citation-types.json"


class DataError(Exception):
    """The inputs are wrong: exit 1."""


class CannotRun(Exception):
    """The builder cannot run: exit 2."""


WARNINGS = []


def warn(msg):
    if msg not in WARNINGS:
        WARNINGS.append(msg)


# ------------------------------------------------------------------ text metrics
# Advance widths per 1000 em of the font stack's Arial-metric face (Liberation Sans / Arial / Helvetica),
# measured once in Chromium. SAFETY widens them for wider system faces (SF Pro, Segoe UI), so text that
# fits here fits there.
_CH = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
    "’‘“”…·–—×→←↔▾■□¶éèàüöäçñ€£§°•"
)
_W400 = [
    278,
    278,
    355,
    556,
    556,
    889,
    667,
    191,
    333,
    333,
    389,
    584,
    278,
    333,
    278,
    278,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    278,
    278,
    584,
    584,
    584,
    556,
    1015,
    667,
    667,
    722,
    722,
    667,
    611,
    778,
    722,
    278,
    500,
    667,
    556,
    833,
    722,
    778,
    667,
    778,
    722,
    667,
    611,
    722,
    667,
    944,
    667,
    667,
    611,
    278,
    278,
    278,
    469,
    556,
    333,
    556,
    556,
    500,
    556,
    556,
    278,
    556,
    556,
    222,
    222,
    500,
    222,
    833,
    556,
    556,
    556,
    556,
    333,
    500,
    278,
    556,
    500,
    722,
    500,
    500,
    500,
    334,
    260,
    334,
    584,
    222,
    222,
    333,
    333,
    1000,
    333,
    556,
    1000,
    584,
    1000,
    1000,
    1000,
    502,
    604,
    604,
    537,
    556,
    556,
    556,
    556,
    556,
    556,
    500,
    556,
    556,
    556,
    556,
    400,
    350,
]
_W700 = [
    278,
    333,
    474,
    556,
    556,
    889,
    722,
    238,
    333,
    333,
    389,
    584,
    278,
    333,
    278,
    278,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    556,
    333,
    333,
    584,
    584,
    584,
    611,
    975,
    722,
    722,
    722,
    722,
    667,
    611,
    778,
    722,
    278,
    556,
    722,
    611,
    833,
    722,
    778,
    667,
    778,
    722,
    667,
    611,
    722,
    667,
    944,
    667,
    667,
    611,
    333,
    278,
    333,
    584,
    556,
    333,
    556,
    611,
    556,
    611,
    556,
    333,
    611,
    611,
    278,
    278,
    556,
    278,
    889,
    611,
    611,
    611,
    611,
    389,
    556,
    333,
    611,
    556,
    778,
    556,
    556,
    500,
    389,
    280,
    389,
    584,
    278,
    278,
    500,
    500,
    1000,
    333,
    556,
    1000,
    584,
    1000,
    1000,
    1000,
    502,
    604,
    604,
    556,
    556,
    556,
    556,
    611,
    611,
    556,
    556,
    611,
    556,
    556,
    556,
    400,
    350,
]
_WIDTH = {False: dict(zip(_CH, _W400, strict=True)), True: dict(zip(_CH, _W700, strict=True))}
SAFETY = 1.08


def tw(text, size, bold=False):
    tab = _WIDTH[bold]
    return sum(tab.get(c, 640) for c in str(text)) * size / 1000 * SAFETY


def fit(text, size, bold, max_w):
    """The text, cut with … to fit max_w."""
    text = str(text)
    if tw(text, size, bold) <= max_w:
        return text
    s = text
    while len(s) > 1 and tw(s + "…", size, bold) > max_w:
        s = s[:-1]
    return re.sub(r"[\s·,;:/–—-]+$", "", s) + "…"


def wrap(text, size, bold, max_w, max_lines):
    """Greedy word wrap into at most max_lines lines; returns (lines, cut)."""
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        t = f"{cur} {w}" if cur else w
        if not cur or tw(t, size, bold) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    cut = False
    if len(lines) > max_lines:
        cut = True
        rest = " ".join(lines[max_lines - 1 :])
        lines = lines[: max_lines - 1] + [fit(rest + " …", size, bold, max_w).replace(" …", "…")]
    out = []
    for ln in lines:
        f = fit(ln, size, bold, max_w)
        cut = cut or f != ln
        out.append(f)
    return out, cut


def wrap_bal(text, size, bold, max_w, max_lines):
    """Wrap, then narrow the measure while the line count holds, so lines come out even."""
    base, cut = wrap(text, size, bold, max_w, max_lines)
    if cut or len(base) < 2:
        return base, cut
    lo, hi, best = 0.0, float(max_w), base
    for _ in range(14):
        mid = (lo + hi) / 2
        t, c = wrap(text, size, bold, mid, 99)
        if not c and len(t) == len(base):
            hi, best = mid, t
        else:
            lo = mid
    return best, False


# ------------------------------------------------------------------ small helpers


def esc(s):
    return html.escape(str(s), quote=True)


def num(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pdate(iso):
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def anchor(address):
    """FORMATS section 2.6: src- plus the address in lower case, ¶ as para, other runs as -."""
    s = address.lower().replace("¶", "para")
    return "src-" + re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", str(s)).lower()).strip("-") or "x"


def jdump(obj):
    return (
        json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("<!--", "\\u003c!--")
    )


SLOTS = (
    "style",
    "legend-end",
    "views",
    "board-head",
    "toolbar",
    "board-over:gutter",
    "board-under",
    "board-over",
    "script",
)
TOKEN = re.compile(r"\{\{([a-z-]+)\}\}|<!--slot:([a-z:-]+)-->")


def fill(tpl, slots=None, **kw):
    """One pass over a template: {{name}} takes kw[name], <!--slot:name--> takes slots[name] (empty when not
    given). Inserted text is never scanned again, so record text such as {{name}} is printed as it is."""

    def one(m):
        if m.group(1):
            if m.group(1) not in kw:
                raise CannotRun(f"template placeholder {{{{{m.group(1)}}}}} has no value")
            return str(kw[m.group(1)])
        if m.group(2) not in SLOTS:
            raise CannotRun(f"unknown template slot <!--slot:{m.group(2)}-->")
        return str((slots or {}).get(m.group(2), ""))

    return TOKEN.sub(one, tpl)


def domain(url):
    m = re.match(r"^[a-z]+://([^/:?#]+)", url or "", re.I)
    d = m.group(1).lower() if m else ""
    return d[4:] if d.startswith("www.") else d


# ------------------------------------------------------------------ records and resolution


class Index:
    """The workspace's record files and the locator grammar of citation-types.json."""

    def __init__(self, ws, rules):
        self.rules, self.kinds = rules, rules["kinds"]
        self.unit_re = {k: re.compile(v["record"]) for k, v in self.kinds.items()}
        self.span_re = {k: {n: re.compile(r) for n, r in v["spans"].items()} for k, v in self.kinds.items()}
        self.src = {}
        rd = ws / "records"
        if not rd.is_dir():
            raise DataError(f"{ws}/records/ does not exist")
        for p in sorted(rd.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except ValueError as e:
                raise DataError(f"records/{p.name} is not valid JSON: {e}") from e
            kind = d.get("kind")
            if kind not in self.kinds:
                raise DataError(f"records/{p.name} has an unknown kind {kind!r}")
            recs = []
            for i, r in enumerate(d.get("records", [])):
                recs.append(
                    {
                        "locator": r["locator"],
                        "text": r["text"],
                        "context": r.get("context"),
                        "key": self.unit_key(kind, r["locator"]),
                        "i": i,
                    }
                )
            self.src[d["id"]] = {"h": d, "recs": recs, "kind": kind}

    @staticmethod
    def _col(s):
        n = 0
        for ch in s:
            n = n * 26 + ord(ch) - 64
        return n

    @staticmethod
    def _ms(h, m, s, frac=None):
        return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + (int(frac) if frac else 0)

    def unit_key(self, kind, loc):
        m = self.unit_re[kind].match(loc)
        if not m:
            return None
        g = m.groups()
        if kind == "sheet":
            return (g[0], int(g[2]), self._col(g[1]))
        if kind in ("document", "web"):
            return (int(g[0]) if g[0] else 0, int(g[1]))
        return self._ms(*g)

    def span_pred(self, kind, loc):
        k = self.unit_key(kind, loc)
        if k is not None:
            return lambda x: x == k
        for name, rx in self.span_re[kind].items():
            m = rx.match(loc)
            if not m:
                continue
            g = m.groups()
            if kind == "sheet":
                sh = g[0]
                if name == "range":
                    c1, r1, c2, r2 = self._col(g[1]), int(g[2]), self._col(g[3]), int(g[4])
                    return lambda x: x[0] == sh and r1 <= x[1] <= r2 and c1 <= x[2] <= c2
                if name == "row":
                    r = int(g[1])
                    return lambda x: x[0] == sh and x[1] == r
                a, b = int(g[1]), int(g[2])
                return lambda x: x[0] == sh and a <= x[1] <= b
            if kind in ("document", "web"):
                if name == "page":
                    p = int(g[0])
                    return lambda x: x[0] == p
                p, a, b = (int(g[0]) if g[0] else 0), int(g[1]), int(g[2])
                return lambda x: x[0] == p and a <= x[1] <= b
            a = self._ms(*g[:4])
            b = self._ms(*g[4:]) + (0 if g[7] else 999)
            return lambda x: a <= x <= b
        return None

    def resolve(self, ref):
        sid, loc = ref.get("source"), ref.get("locator")
        s = self.src.get(sid)
        if not s:
            raise DataError(f"citation names {sid!r}, which has no record file records/{sid}.json")
        if loc is None:
            return list(s["recs"])
        pred = self.span_pred(s["kind"], loc)
        recs = [r for r in s["recs"] if pred and r["key"] is not None and pred(r["key"])] if pred else []
        if not recs:
            raise DataError(f"'{sid} {loc}' resolves to no record (run bs.py check)")
        return recs

    def label(self, sid):
        return self.kinds[self.src[sid]["kind"]]["label"]


def address(ref):
    return f"{ref['source']} {ref['locator']}" if ref.get("locator") else ref["source"]


def ctype(c):
    return c.get("type", "grounded")


# ------------------------------------------------------------------ the citation points register

USE_WORD = {"grounded": "Grounded", "inferred": "Inferred from", "absent": "Absent search"}


class Register:
    """Every citation point the page uses, numbered in the order the page first uses it, with the elements that
    use it (build-1, build-4). A point is a record address, or an absent search of one address for one needle.
    The base map registers first (systems, lanes, nodes, gaps, clarifications), so an AI page numbers the base's
    points exactly as the base page does, and its own points after them."""

    def __init__(self, idx, pre):
        self.idx, self.pre, self.entries, self.order = idx, pre, {}, []

    def _new(self, key, e):
        e["n"] = len(self.order) + 1
        self.entries[key] = e
        self.order.append(e)
        return e

    @staticmethod
    def _use(e, used, kind):
        u = (used[0], used[1], kind)
        if u not in e["used"]:
            e["used"].append(u)
        return e

    def add(self, ref, used, kind="grounded"):
        a = address(ref)
        e = self.entries.get(a)
        if not e:
            recs = self.idx.resolve(ref)
            e = self._new(
                a,
                {
                    "kind": "rec" if len(recs) == 1 and ref.get("locator") else "span",
                    "source": ref["source"],
                    "loc": ref.get("locator") or "",
                    "recs": recs,
                    "address": a,
                    "anchor": self.pre + anchor(a),
                    "used": [],
                },
            )
        return self._use(e, used, kind)

    def add_absent(self, ref, needle, used):
        a = address(ref)
        key = f"{a}\u0000{needle}"
        e = self.entries.get(key)
        if not e:
            recs = self.idx.resolve(ref)
            partial = self.idx.src[ref["source"]]["h"].get("coverage") != "complete"
            e = self._new(
                key,
                {
                    "kind": "absent",
                    "source": ref["source"],
                    "loc": ref.get("locator") or "",
                    "recs": recs,
                    "address": a,
                    "needle": needle,
                    "partial": partial,
                    "anchor": self.pre + anchor(a) + "-not-" + slug(needle),
                    "used": [],
                },
            )
        return self._use(e, used, "absent")

    def cites(self, cites, used):
        """Register an element's citations; returns them with their entries, in order."""
        out = []
        for c in cites or []:
            t = ctype(c)
            if t == "grounded":
                out.append((c, [self.add(c, used)]))
            elif t == "inferred":
                out.append((c, [self.add(f, used, "inferred") for f in c["from"]]))
            elif t == "absent":
                out.append((c, [self.add_absent(s, c["needle"], used) for s in c["in"]]))
        return out


def first_point(pairs):
    """An element's one marker: the first point of its first citation."""
    return pairs[0][1][0] if pairs and pairs[0][1] else None


def mk_label(e):
    """What a screen reader hears for a marker, as on every template: Citation 3: WB1 Steps!D3."""
    a = e["address"] if e["loc"] else f"{e['source']} · whole source"
    return f"Citation {e['n']}: {a}" + (f", searched for “{e['needle']}”" if e["kind"] == "absent" else "")


def mk(e):
    """A citation marker: the point's number, linked to its row in the page's Citation points section."""
    return f'<a class="cp-mk" href="#{e["anchor"]}" aria-label="{esc(mk_label(e))}">{e["n"]}</a>'


def mks(es):
    """One or more markers as one superscript, in ascending order: ³ or ³,⁷."""
    seen, out = set(), []
    for e in sorted(es, key=lambda e: e["n"]):
        if e["n"] not in seen:
            seen.add(e["n"])
            out.append(mk(e))
    return f'<sup class="cp-mks">{",".join(out)}</sup>' if out else ""


def mk_svg(e, x, y, anchor_mid=False):
    """A marker on a board or a flow: a muted numeral whose baseline sits at y, with a hit area around it."""
    w = tw(str(e["n"]), 9, True)
    x0 = x - w / 2 if anchor_mid else x
    return (
        f'<a class="cp-mk" href="#{e["anchor"]}" aria-label="{esc(mk_label(e))}"><rect class="cp-mk-hit" x="{num(x0 - 3)}" y="{num(y - 10)}" '
        f'width="{num(w + 6)}" height="13"/><text class="cp-mk-t" x="{num(x0)}" y="{num(y)}">{e["n"]}</text></a>'
    )


def prov_html(pairs, cls="pm-prov"):
    """FORMATS 2.6, with markers for addresses: one Gap clause with each needle and its searches, one Grounded
    clause, one Inferred clause per reading; each its own colour. Full addresses are in Citation points."""
    gaps = [(c, es) for c, es in pairs if ctype(c) == "absent"]
    grounded = [es[0] for c, es in pairs if ctype(c) == "grounded"]
    inferred = [(c, es) for c, es in pairs if ctype(c) == "inferred"]
    parts = []
    if gaps:
        bits = [f"“{esc(c['needle'])}” not found{mks(es)}" for c, es in gaps]
        tag = (
            '<span class="pm-tag">Provisional</span>'
            if any(e["partial"] for c, es in gaps for e in es)
            else ""
        )
        parts.append(f'<span class="pm-prov-gap"><b>Gap</b> · {" · ".join(bits)}{tag}</span>')
    if grounded:
        parts.append(f'<span class="pm-prov-grounded"><b>Grounded</b>{mks(grounded)}</span>')
    for c, es in inferred:
        parts.append(f'<span class="pm-prov-inferred"><b>Inferred</b> · {esc(c["reading"])}{mks(es)}</span>')
    return f'<span class="{cls}">{"".join(parts)}</span>' if parts else ""


# ------------------------------------------------------------------ prose with [SRC locator] markers

BRACKET = re.compile(r"(?<!\\)\[([^\[\]]+)\]")
BRACKET_PART = re.compile(r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)(?:\s+(.+))?$")


def prose_html(text, reg, used):
    """Claim prose: escaped, with each [SRC locator] bracket printed in place as its markers (³ or ³,⁷), each
    linked to its row in Citation points. A space before a bracket is dropped, so the marker sits on the word."""
    out, pos = [], 0
    for m in BRACKET.finditer(text):
        out.append(esc(text[pos : m.start()].rstrip(" ")))
        es = []
        for part in m.group(1).split(";"):
            pm = BRACKET_PART.match(part.strip())
            if not pm or pm.group(1) not in reg.idx.src:
                raise DataError(f"[{m.group(1)}] is not a citation (run bs.py check)")
            ref = (
                {"source": pm.group(1), "locator": pm.group(2).strip()}
                if pm.group(2)
                else {"source": pm.group(1)}
            )
            es.append(reg.add(ref, used))
        out.append(mks(es))
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out).replace("\\[", "[").replace("\\]", "]")


# ------------------------------------------------------------------ geometry

GUT, X0, PITCH, CW, CH, ROW, EMPTY = 150, 170, 196, 156, 104, 144, 56
MID = (PITCH - CW) / 2  # the middle of the 40-unit gap between two columns, where the group divider runs
HALF = 60.2 * 2**0.5 / 2  # half diagonal of the decision square: 42.57
BAND_TOP, BAND_BOT, LANES_BAND, LANES_PLAIN = 8, 44, 52, 18
MAX_COLUMNS = 14
FEED = 16  # a channel runs this far above (or below) its row: clear of the 11-unit corner marks
TRACKS = (0, -6, 6)  # a gap's tracks, from its middle: one per source (route)
LABEL_RESERVE = 70  # right end of a band cell kept for a view's squares (AI section 2)
DEC_FONT, DEC_MEASURE = 10, 80  # a decision's question: font size and measure (see decision_svg)
ICONS = {
    "spreadsheet": '<rect x="2" y="2.8" width="12" height="10.4" rx="1.2"/><path d="M2 6.2 H14 M2 9.8 H14 M6.2 6.2 V13.2 M10 6.2 V13.2"/>',
    "database": '<ellipse cx="8" cy="3.9" rx="5.6" ry="2.2"/><path d="M2.4 3.9 v8.2 c0 1.3 2.5 2.3 5.6 2.3 s5.6-1 5.6-2.3 V3.9"/><path d="M2.4 8 c0 1.3 2.5 2.3 5.6 2.3 s5.6-1 5.6-2.3"/>',
    "document": '<path d="M3.8 1.8 H9.6 L12.6 4.9 V14.2 H3.8 z"/><path d="M9.6 1.8 V4.9 H12.6"/><path d="M5.7 8.2 H10.7 M5.7 10.8 H10.7"/>',
    "email": '<rect x="1.8" y="3.4" width="12.4" height="9.2" rx="1.2"/><path d="M2.4 4.2 L8 9 L13.6 4.2"/>',
    "shared-drive": '<path d="M1.8 5 c0-.7.5-1.2 1.2-1.2 h2.9 l1.4 1.7 h5.7 c.7 0 1.2.5 1.2 1.2 v5.6 c0 .7-.5 1.2-1.2 1.2 H3 c-.7 0-1.2-.5-1.2-1.2 z"/>',
    "web-app": '<rect x="1.8" y="2.6" width="12.4" height="10.8" rx="1.2"/><path d="M1.8 5.8 H14.2"/><path d="M4 4.2 h.01 M5.8 4.2 h.01"/><path d="M4.6 8.6 H11.4 M4.6 10.9 H9"/>',
}


def icon_svg(icon, cls="pm-ic"):
    return f'<svg class="{cls}" viewBox="0 0 16 16" aria-hidden="true">{ICONS[icon]}</svg>'


class Node:
    def __init__(self, d, i):
        self.d, self.i, self.id = d, i, d["id"]
        self.kind = d.get("kind", "step")
        self.dec = self.kind == "decision"
        self.state = d.get("state", "grounded")
        self.col = self.row = 0
        self.x = self.y = self.cx = self.cy = 0.0
        self.bottom_used = False  # a line leaves a decision's bottom vertex (set by route)

    def place(self, col, row, lane_top):
        self.col, self.row = col, row
        self.x = X0 + PITCH * col
        self.y = lane_top + 20 + ROW * row
        self.cx, self.cy = self.x + CW / 2, self.y + CH / 2

    def port(self, p):
        h = HALF if self.dec else None
        if p == "L":
            return (self.cx - h, self.cy) if h else (self.x, self.cy)
        if p == "R":
            return (self.cx + h, self.cy) if h else (self.x + CW, self.cy)
        if p == "T":
            return (self.cx, self.cy - h) if h else (self.cx, self.y)
        return (self.cx, self.cy + h) if h else (self.cx, self.y + CH)

    def crosses(self, a, b, eps=0.5):
        """Does the axis-aligned segment a-b enter this node's interior?"""
        (x1, y1), (x2, y2) = a, b
        if self.dec:
            if y1 == y2:
                dy = abs(y1 - self.cy)
                if dy >= HALF - eps:
                    return False
                half = HALF - dy - eps
                lo, hi = min(x1, x2), max(x1, x2)
                return lo < self.cx + half and hi > self.cx - half
            dx = abs(x1 - self.cx)
            if dx >= HALF - eps:
                return False
            half = HALF - dx - eps
            lo, hi = min(y1, y2), max(y1, y2)
            return lo < self.cy + half and hi > self.cy - half
        if y1 == y2:
            return (
                self.y + eps < y1 < self.y + CH - eps
                and min(x1, x2) < self.x + CW - eps
                and max(x1, x2) > self.x + eps
            )
        return (
            self.x + eps < x1 < self.x + CW - eps
            and min(y1, y2) < self.y + CH - eps
            and max(y1, y2) > self.y + eps
        )


def seg_box(a, b, box, pad=1.0):
    """Does the axis-aligned segment a-b pass through the box (x0, y0, x1, y1), grown by pad (a line's stroke)?"""
    x0, y0, x1, y1 = box
    lo_x, hi_x, lo_y, hi_y = min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])
    return lo_x < x1 + pad and hi_x > x0 - pad and lo_y < y1 + pad and hi_y > y0 - pad


def seg_cross(a1, b1, a2, b2, eps=0.5):
    """Do a horizontal and a vertical segment cross at a point inside both?"""
    if a1[1] == b1[1] and a2[0] == b2[0]:
        (h1, h2), (v1, v2) = (a1, b1), (a2, b2)
    elif a1[0] == b1[0] and a2[1] == b2[1]:
        (h1, h2), (v1, v2) = (a2, b2), (a1, b1)
    else:
        return False
    x, y = v1[0], h1[1]
    return (
        min(h1[0], h2[0]) + eps < x < max(h1[0], h2[0]) - eps
        and min(v1[1], v2[1]) + eps < y < max(v1[1], v2[1]) - eps
    )


def seg_overlap(a1, b1, a2, b2, eps=0.5):
    """Do two segments lie on one line and share a stretch, or meet end to end so they read as one line?"""
    if a1[1] == b1[1] == a2[1] == b2[1] and a1[0] != b1[0] and a2[0] != b2[0]:
        i = 0
    elif a1[0] == b1[0] == a2[0] == b2[0] and a1[1] != b1[1] and a2[1] != b2[1]:
        i = 1
    else:
        return False
    lo1, hi1 = sorted((a1[i], b1[i]))
    lo2, hi2 = sorted((a2[i], b2[i]))
    return min(hi1, hi2) - max(lo1, lo2) > -eps


def simplify(pts):
    out = []
    for p in pts:
        p = (round(p[0], 2), round(p[1], 2))
        if out and out[-1] == p:
            continue
        if len(out) >= 2 and ((out[-2][0] == out[-1][0] == p[0]) or (out[-2][1] == out[-1][1] == p[1])):
            out[-1] = p
            continue
        out.append(p)
    return out


# ------------------------------------------------------------------ the map model


class MapModel:
    """Everything derived from one process-map file (README section 2 and the element table)."""

    def __init__(self, m, idx, where, pre="", links="../"):
        self.m, self.idx, self.where, self.pre, self.links = m, idx, where, pre, links
        self.reg = Register(idx, pre)
        meta = m["meta"]
        self.meta = meta
        self.lanes = m["lanes"]
        self.groups = m.get("groups", [])
        self.systems = {s["id"]: s for s in m.get("systems", [])}
        self.nodes = [Node(n, i) for i, n in enumerate(m["nodes"])]
        self.N = {n.id: n for n in self.nodes}
        self.edges = m.get("edges", [])
        self.gaps = m.get("gaps", [])
        self.clars = m.get("clarifications", [])
        self.lane_ix = {lane["id"]: i for i, lane in enumerate(self.lanes)}
        self.group_ix = {g["id"]: i for i, g in enumerate(self.groups)}
        for n in self.nodes:
            if n.d["lane"] not in self.lane_ix:
                raise DataError(
                    f"{where}: {n.id} names lane {n.d['lane']!r}, which is not in lanes[] (map-1)"
                )
            if self.groups and n.d.get("group") not in self.group_ix:
                raise DataError(f"{where}: {n.id} names no group of groups[] (map-2)")
            for s in n.d.get("systems", []):
                if s not in self.systems:
                    raise DataError(f"{where}: {n.id} names system {s!r}, which is not in systems[] (map-1)")
        for e in self.edges:
            for k in ("from", "to"):
                if e[k] not in self.N:
                    raise DataError(f"{where}: an edge names {e[k]!r}, which is not a node (map-1)")
        self.band = len(self.groups) >= 2
        self.layout()
        self.badges()
        self.route()
        self.evidence()

    # -- columns, rows, coordinates
    def layout(self):
        nodes, ix = self.nodes, {n.id: n.i for n in self.nodes}
        preds = {n.id: [] for n in nodes}
        for e in self.edges:
            a, b = self.N[e["from"]], self.N[e["to"]]
            if ix[b.id] > ix[a.id] and a.d.get("group") == b.d.get("group"):
                preds[b.id].append(a.id)
        local = {}
        for n in nodes:
            c = max([local[p] + 1 for p in preds[n.id]], default=1)
            if "col" in n.d:
                if n.d["col"] < c:
                    raise DataError(
                        f"{self.where}: {n.id} has col {n.d['col']}, left of its derived column {c} (map-10)"
                    )
                c = n.d["col"]
            local[n.id] = c
        col, start, self.gcols = {}, 0, {}
        for g in [g["id"] for g in self.groups] or [None]:
            members = [n.id for n in nodes if n.d.get("group") == g]
            width = max((local[i] for i in members), default=0)
            self.gcols[g] = (start, start + width - 1)
            for nid in members:
                col[nid] = start + local[nid] - 1
            start += width
        self.ncols = start
        if start > MAX_COLUMNS:
            raise DataError(
                f"{self.where}: the board needs {start} columns, more than {MAX_COLUMNS} (map-10): split the map"
            )
        rows, seen = {}, {}
        for n in nodes:
            k = (n.d["lane"], col[n.id])
            rows[n.id] = seen.get(k, 0)
            seen[k] = rows[n.id] + 1
        self.lane_rows = {lane["id"]: 0 for lane in self.lanes}
        for n in nodes:
            self.lane_rows[n.d["lane"]] = max(self.lane_rows[n.d["lane"]], rows[n.id] + 1)
        y = LANES_BAND if self.band else LANES_PLAIN
        self.lanes_top = y
        self.lane_geo = {}
        for lane in self.lanes:
            h = ROW * self.lane_rows[lane["id"]] or EMPTY
            self.lane_geo[lane["id"]] = (y, h)
            y += h
        self.lanes_bottom = y
        self.H = y + 16
        self.W = X0 + PITCH * (self.ncols - 1) + CW + 28
        for n in nodes:
            n.place(col[n.id], rows[n.id], self.lane_geo[n.d["lane"]][0])
        self.cells = {}
        for gi, g in enumerate(self.groups):
            c0, c1 = self.gcols[g["id"]]
            x0 = GUT + PITCH * c0
            x1 = self.W if gi == len(self.groups) - 1 else GUT + PITCH * (c1 + 1)
            self.cells[g["id"]] = (x0 + 4, x1 - x0 - 8, x0)

    # -- badges: list positions of gap and clarification cards
    def badges(self):
        self.badge = {n.id: [] for n in self.nodes}
        for i, g in enumerate(self.gaps):
            for nid in g["nodes"]:
                if nid not in self.N:
                    raise DataError(f"{self.where}: {g['id']} lists {nid!r}, which is not a node (map-1)")
                self.badge[nid].append(("gap", i + 1, g["id"], g["title"]))
        for i, c in enumerate(self.clars):
            for nid in c["nodes"]:
                if nid not in self.N:
                    raise DataError(f"{self.where}: {c['id']} lists {nid!r}, which is not a node (map-1)")
                self.badge[nid].append(("clar", i + 1, c["id"], c["title"]))

    def badge_slots(self, n):
        """Centres of a node's badges (up to three) and of its +n chip (or None). Both read left to right: a
        step's run starts at its top-left corner, a decision's ends just left of its top vertex."""
        b = self.badge[n.id]
        k, chip = min(len(b), 3), len(b) > 3
        if not n.dec:
            return [(n.x + 24 * i, n.y) for i in range(k)], ((n.x + 76, n.y) if chip else None)
        y, right = n.cy - HALF + 6, n.cx - 22
        first = right - (28 if chip else 0)
        return [(first - 24 * (k - 1 - i), y) for i in range(k)], ((right, y) if chip else None)

    def marks(self):
        """Every badge, system icon and chip on the board, the decisions' id labels and the room the AI layer keeps
        under each step's bottom-right corner, as (box (x0, y0, x1, y1), node id, what): lines keep clear of them
        and pills sit off them (build-6)."""
        out = []
        for n in self.nodes:
            pos, chip = self.badge_slots(n)
            for x, y in pos:
                out.append(((x - 11, y - 11, x + 11, y + 11), n.id, "badge"))
            if chip:
                x, y = chip
                out.append(((x - 14, y - 8, x + 14, y + 8), n.id, "badge chip"))
            sy = n.d.get("systems", [])
            for i in range(min(len(sy), 2)):
                out.append(
                    (
                        (n.x + CW - 24 * i - 11, n.y - 11, n.x + CW - 24 * i + 11, n.y + 11),
                        n.id,
                        "system icon",
                    )
                )
            if len(sy) > 2:
                out.append(((n.x + CW - 64, n.y - 8, n.x + CW - 36, n.y + 8), n.id, "system chip"))
            if n.dec:  # the id and marker: right of a bottom-vertex line, else centred under the vertex
                out.append(
                    (
                        (n.cx + 2, n.cy + HALF, n.cx + 64, n.cy + HALF + 18)
                        if n.bottom_used
                        else (n.cx - 40, n.cy + HALF, n.cx + 40, n.cy + HALF + 18),
                        n.id,
                        "id label",
                    )
                )
            else:  # the AI layer's squares hang from the bottom-right corner (AI README section 2)
                out.append(((n.x + CW - 50, n.y + CH - 3, n.x + CW + 8, n.y + CH + 13), n.id, "AI room"))
        return out

    # -- routing (README section 2, the case table) and build-6
    def fwd(self, s, t, p, gx):
        """A forward line from port p of s to t's left edge; gx is its track in the gap left of t's column."""
        tl = t.port("L")
        if p == "R":
            a = s.port("R")
            return [a, tl] if abs(t.cy - s.cy) < 0.01 else [a, (gx, a[1]), (gx, t.cy), tl]
        v = s.port(p)
        if abs(t.cy - s.cy) > 0.01:
            return [v, (s.cx, t.cy), tl]
        ch = s.y - FEED if p == "T" else s.y + CH + FEED
        return [v, (s.cx, ch), (gx, ch), (gx, t.cy), tl]

    def route(self):
        ix = {n.id: n.i for n in self.nodes}
        used_ports = {n.id: set() for n in self.nodes}
        port = {}
        for e in self.edges:
            s = self.N[e["from"]]
            if s.dec and e.get("kind") == "conditional" and ix[e["to"]] > ix[e["from"]]:
                t = self.N[e["to"]]
                if not used_ports[s.id]:
                    p = "R"
                else:
                    want = "T" if t.cy < s.cy else "B"
                    p = next(
                        (q for q in (want, "B" if want == "T" else "T", "R") if q not in used_ports[s.id]),
                        "R",
                    )
                used_ports[s.id].add(p)
                port[id(e)] = p
        self.routes = []
        for k, e in enumerate(self.edges):
            s, t = self.N[e["from"]], self.N[e["to"]]
            if s is t:
                raise DataError(f"{self.where}#/edges/{k}: {s.id} -> {t.id} is a self-loop (map-5)")
            feedback = ix[t.id] < ix[s.id]
            p, gap = port.get(id(e), "R"), None
            if feedback and "T" in used_ports[s.id] and "B" not in used_ports[s.id]:
                # a decision's top vertex already carries a forward branch: leave from the bottom vertex,
                # through the channel below the row, so the two lines never share a segment
                ch = s.y + CH + FEED
                end = t.port("B") if t.cy <= s.cy else t.port("T")
                pts = [s.port("B"), (s.cx, ch), (t.cx, ch), end]
            elif feedback:  # through the channel above the row, clear of the corner marks
                ch = s.y - FEED
                end = t.port("T") if t.cy >= s.cy else t.port("B")
                pts = [s.port("T"), (s.cx, ch), (t.cx, ch), end]
            else:
                pts = self.fwd(s, t, p, t.x - MID)
                gap = t.col if len(pts) >= 4 else None  # its vertical runs in the gap left of t's column
            pts = simplify(pts)
            self.routes.append(
                {"e": e, "k": k, "pts": pts, "feedback": feedback, "pill": None, "port": p, "gap": gap}
            )
            if s.dec and pts[0] == (round(s.cx, 2), round(s.cy + HALF, 2)):
                s.bottom_used = True
            if t.dec and pts[-1] == (round(t.cx, 2), round(t.cy + HALF, 2)):
                t.bottom_used = True  # a line into the bottom vertex: the id label moves right of it too
        marks = self.marks()
        self.spread(marks)
        errors = self.lines_clear(marks)
        errors += self.pills(marks)
        if errors:
            raise DataError("\n".join(errors))

    def name(self, r):
        e = r["e"]
        return f"{self.where}#/edges/{r['k']} ({e['from']} -> {e['to']})"

    def spread(self, marks):
        """Lines from different sources into one column's gap each take their own track, 6 units apart, so no two
        sources share a vertical line (README section 2). Sources whose stretches of the gap do not meet share a
        track; the tracks are ordered for no line through a mark and then the fewest crossings."""
        by_col = {}
        for r in self.routes:
            if r["gap"] is not None:
                by_col.setdefault(r["gap"], []).append(r)
        for col, rs in sorted(by_col.items()):
            x0, ext = self.N[rs[0]["e"]["to"]].x - MID, {}
            for r in rs:
                ys = [y for (x, y) in r["pts"] if abs(x - x0) < 0.01]
                lo, hi = ext.get(r["e"]["from"], (min(ys), max(ys)))
                ext[r["e"]["from"]] = (min(lo, *ys), max(hi, *ys))
            track, ends = {}, []
            for sid in sorted(ext, key=lambda x: (ext[x][0], self.N[x].i)):
                lo, hi = ext[sid]
                k = next((i for i, end in enumerate(ends) if lo > end + 8), None)
                if k is None:
                    k, ends = len(ends), ends + [hi]
                else:
                    ends[k] = hi
                track[sid] = k
            if len(ends) == 1:
                continue
            if len(ends) > len(TRACKS):
                raise DataError(
                    f"build-6 {self.where}: {len(ends)} lines from different sources ({', '.join(sorted(ext))}) "
                    f"meet in the gap left of column {col + 1}, which has room for {len(TRACKS)} -> move one of "
                    "those sources to another column (col), or join them in a step before the gap"
                )
            others = [o for o in self.routes if o["gap"] != col]
            best = None
            for perm in itertools.permutations(TRACKS, len(ends)):
                paths = [
                    simplify(
                        self.fwd(
                            self.N[r["e"]["from"]],
                            self.N[r["e"]["to"]],
                            r["port"],
                            x0 + perm[track[r["e"]["from"]]],
                        )
                    )
                    for r in rs
                ]
                hits = sum(
                    1
                    for pts in paths
                    for a, b in itertools.pairwise(pts)
                    for box, _nid, _what in marks
                    if seg_box(a, b, box)
                )
                segs = [
                    (r["e"], a, b)
                    for r, pts in zip(rs, paths, strict=True)
                    for a, b in itertools.pairwise(pts)
                ]
                segs_o = [(o["e"], a, b) for o in others for a, b in itertools.pairwise(o["pts"])]
                pairs = [
                    (e1, a1, b1, e2, a2, b2)
                    for i, (e1, a1, b1) in enumerate(segs)
                    for e2, a2, b2 in segs[i + 1 :] + segs_o
                    if e1["from"] != e2["from"]
                ]
                shared = sum(
                    1
                    for e1, a1, b1, e2, a2, b2 in pairs
                    if e1["to"] != e2["to"] and seg_overlap(a1, b1, a2, b2)
                )
                cross = sum(1 for e1, a1, b1, e2, a2, b2 in pairs if seg_cross(a1, b1, a2, b2))
                score = (hits + shared, cross, [abs(perm[k]) for k in range(len(ends))])
                if best is None or score < best[0]:
                    best = (score, paths)
            for r, pts in zip(rs, best[1], strict=True):
                r["pts"] = pts

    def lines_clear(self, marks):
        """build-6: no line crosses a card or a mark, and no two lines from different sources to different targets
        share a stretch (the board would show a path the sources never describe)."""
        errors = []
        for r in self.routes:
            s, t = self.N[r["e"]["from"]], self.N[r["e"]["to"]]
            hit = None
            for a, b in itertools.pairwise(r["pts"]):
                n = next((n for n in self.nodes if n.crosses(a, b)), None)
                if n is not None:
                    if a[1] == b[1] and abs(a[1] - s.cy) < 0.01 and not r["feedback"]:
                        fix = (
                            f"the line runs along {s.id}'s row through {n.id} -> move {n.id} to another lane, "
                            f"or move {s.id} next to {t.id} (col)"
                        )
                    elif a[0] == b[0] and abs(a[0] - s.cx) < 0.01 and s.dec:
                        fix = (
                            f"the branch leaves {s.id}'s {'top' if b[1] < a[1] else 'bottom'} vertex through {n.id} "
                            f"-> list {s.id}'s branch to {t.id} first (the first-listed branch takes the right vertex), "
                            f"or move {n.id} to another lane"
                        )
                    else:
                        fix = f"the line crosses {n.id} -> move {n.id} to another lane, or set col on {t.id} to open a column"
                    hit = f"build-6 {self.name(r)}: {fix}"
                    break
                box = next(((nid, what) for bx, nid, what in marks if seg_box(a, b, bx)), None)
                if box is not None:
                    hit = (
                        f"build-6 {self.name(r)}: the line runs through the {box[1]} of {box[0]} -> move {box[0]} "
                        "to another lane or column, or reorder the nodes"
                    )
                    break
            if hit:
                errors.append(hit)
        for i, r1 in enumerate(self.routes):
            for r2 in self.routes[i + 1 :]:
                e1, e2 = r1["e"], r2["e"]
                if e1["from"] == e2["from"] or e1["to"] == e2["to"]:
                    continue
                if any(
                    seg_overlap(a1, b1, a2, b2)
                    for a1, b1 in itertools.pairwise(r1["pts"])
                    for a2, b2 in itertools.pairwise(r2["pts"])
                ):
                    errors.append(
                        f"build-6 {self.name(r1)} and {e2['from']} -> {e2['to']} share a stretch of line, so the "
                        f"board could read {e1['from']} -> {e2['to']} or {e2['from']} -> {e1['to']} -> move "
                        f"{e2['from']} or {e1['from']} to another lane, or set col to give one of them its own column"
                    )
        return errors

    def pills(self, marks):
        """Each branch pill on its line's longest free horizontal stretch: clear of cards and the AI halo around
        each step, of marks, of other pills and of every other line (at least 4 units from a line that crosses
        its stretch). A pill that fits nowhere fails build-6."""
        errors, placed = [], []
        for r in self.routes:
            e = r["e"]
            if e.get("kind") != "conditional" or not e.get("label"):
                continue
            label = e["label"]
            w = tw(label, 11, True) + 14
            best = None
            other = [(a, b) for o in self.routes if o is not r for a, b in itertools.pairwise(o["pts"])]
            for a, b in itertools.pairwise(r["pts"]):
                if a[1] != b[1]:
                    continue
                y, lo, hi = a[1], min(a[0], b[0]), max(a[0], b[0])
                blocked = []
                for n in self.nodes:
                    if n.dec:
                        if abs(y - n.cy) < HALF + 9:
                            blocked.append((n.cx - HALF, n.cx + HALF))
                    elif n.y - 18 < y < n.y + CH + 18:  # the card and the AI halo 4 units round it
                        blocked.append((n.x - 5, n.x + CW + 5))
                for bx0, by0, bx1, by1 in [m[0] for m in marks] + placed:
                    if by0 - 9 < y < by1 + 9:
                        blocked.append((bx0, bx1))
                for (x1, y1), (x2, y2) in other:
                    if x1 == x2 and min(y1, y2) < y + 9 and max(y1, y2) > y - 9:
                        blocked.append((x1 - 4, x1 + 4))
                    elif y1 == y2 and abs(y1 - y) < 11:
                        blocked.append((min(x1, x2), max(x1, x2)))
                free = [(lo, hi)]
                for c0, c1 in sorted(blocked):
                    nxt = []
                    for f0, f1 in free:
                        if c1 <= f0 or c0 >= f1:
                            nxt.append((f0, f1))
                            continue
                        if c0 > f0:
                            nxt.append((f0, c0))
                        if c1 < f1:
                            nxt.append((c1, f1))
                    free = nxt
                for f0, f1 in free:
                    if best is None or f1 - f0 > best[2] - best[1]:
                        best = (y, f0, f1)
            if best is None or best[2] - best[1] < w + 16:
                have = 0 if best is None else best[2] - best[1]
                errors.append(
                    f"build-6 {self.name(r)} “{label}”: the pill needs a free stretch of {num(w + 16)} units and has "
                    f"{num(have)} -> shorten the label, list {e['from']}'s branches in another order (the first-listed "
                    f"branch takes the right vertex), or set col on {e['to']} to open a column"
                )
                continue
            px = (best[1] + best[2]) / 2
            r["pill"] = (px, best[0], w, label)
            placed.append((px - w / 2, best[0] - 9, px + w / 2, best[0] + 9))
        return errors

    # -- derived text: counts, notes, provenance, tooltips, cards, citation points
    def counts(self):
        return {
            "steps": sum(1 for n in self.nodes if not n.dec),
            "decisions": sum(1 for n in self.nodes if n.dec),
            "groups": len(self.groups),
            "gaps": len(self.gaps),
            "clarifications": len(self.clars),
            "systems": len(self.systems),
        }

    def fill_counts(self, text):
        c = self.counts()

        def one(m):
            if m.group(1) not in c:
                raise DataError(
                    f"{self.where}#/meta/subtitle: {{count:{m.group(1)}}} is not a count selector (prose-5)"
                )
            return str(c[m.group(1)])

        return re.sub(r"\{count:([a-z-]+)\}", one, text)

    def note(self, nodes):
        steps = sum(1 for n in nodes if not n.dec)
        decs = len(nodes) - steps
        if steps or not decs:
            return plural(steps, "step")
        return plural(decs, "decision")

    def evidence(self):
        reg, pre = self.reg, self.pre
        # file order: systems, lanes, nodes, gaps, clarifications (the AI layer adds its items after)
        self.other_pairs = []
        for s in self.m.get("systems", []):
            u = (s["label"], f"{pre}sys-{s['id']}")
            self.other_pairs.append((u, reg.cites(s["cite"], u)))
        for lane in self.lanes:
            u = (lane["label"], f"{pre}lane-{lane['id']}")
            self.other_pairs.append((u, reg.cites(lane.get("cite"), u)))
        self.npairs = {}
        for n in self.nodes:
            self.npairs[n.id] = reg.cites(n.d["cite"], (n.id, pre + n.id))
        self.gap_html = []
        for i, g in enumerate(self.gaps):
            u = (f"Gap {i + 1}", pre + g["id"])  # Used by names an element as its page shows it
            title = prose_html(g["title"], reg, u)
            text = prose_html(g["text"], reg, u)
            pairs = reg.cites(g["cite"], u)
            self.gap_html.append((g, i + 1, title, text, prov_html(pairs)))
        self.clar_html = []
        for i, c in enumerate(self.clars):
            u = (f"Clarification {i + 1}", pre + c["id"])
            title, shows, ask = (prose_html(c[k], reg, u) for k in ("title", "shows", "ask"))
            pairs = reg.cites(c["cite"], u)
            self.clar_html.append((c, i + 1, title, shows, ask, prov_html(pairs)))
        self.notes()

    def point(self, key):
        """The one marker of an element: a node id, or a system or lane id prefixed sys- or lane-."""
        if key in self.npairs:
            return first_point(self.npairs[key])
        for (_name, href), pairs in self.other_pairs:
            if href == self.pre + key:
                return first_point(pairs)
        return None

    def notes(self):
        """A reading its element does not print (a system's, a lane's or a node's: cards show no reading) is
        printed in the Citation points row of its first record, so every reading is visible text (build-4)."""

        def note(c, es, used):
            es[0].setdefault("notes", []).append((c["reading"], used))

        for used, pairs in self.other_pairs:
            for c, es in pairs:
                if ctype(c) == "inferred":
                    note(c, es, used)
        for n in self.nodes:
            for c, es in self.npairs[n.id]:
                if ctype(c) == "inferred":
                    note(c, es, (n.id, self.pre + n.id))

    def tip(self, n):
        g = self.groups[self.group_ix[n.d["group"]]] if self.groups else None
        head = f"{n.id} · {g['id']} {g['label']}" if g else n.id
        rows = [("Lane", self.lanes[self.lane_ix[n.d["lane"]]]["label"])]
        if n.d.get("owner"):
            rows.append(("Owner", n.d["owner"]))
        if n.d.get("systems"):
            rows.append(("Systems", ", ".join(self.systems[s]["label"] for s in n.d["systems"])))
        for c, _es in self.npairs[n.id]:
            if ctype(c) == "inferred":
                rows.append(("Inferred", c["reading"]))
        s = f'<span class="pm-tip-id">{esc(head)}</span><span class="pm-tip-title">{esc(n.d["title"])}</span>'
        s += "".join(f'<span class="pm-tip-row"><b>{k}:</b> {esc(v)}</span>' for k, v in rows)
        for kind, i, _id, title in self.badge[n.id]:
            word = "Gap" if kind == "gap" else "To confirm"
            s += (
                f'<span class="pm-tip-mark"><span class="pm-tip-mk is-{kind}">{i}</span>'
                f"<span>{word}: {esc(title)}</span></span>"
            )
        pts = []
        for _c, es in self.npairs[n.id]:
            for e in es:
                if e["n"] not in pts:
                    pts.append(e["n"])
        return s + f'<span class="pm-tip-cp">Citation points {", ".join(str(x) for x in pts)}</span>'


# ------------------------------------------------------------------ SVG rendering of the base board


def text_lines(cls, x, y, lines, lead, anchor_mid=True):
    a = ' text-anchor="middle"' if anchor_mid else ""
    sp = "".join(f'<tspan x="{num(x)}" dy="{lead if i else 0}">{esc(t)}</tspan>' for i, t in enumerate(lines))
    return f'<text class="{cls}" x="{num(x)}" y="{num(y)}"{a}>{sp}</text>'


def chip(cx, cy, label):
    w = tw(label, 9.5, True) + 10
    return (
        f'<g class="pm-more"><rect class="pm-more-bg" x="{num(cx - w / 2)}" y="{num(cy - 8)}" width="{num(w)}" '
        f'height="16" rx="8"/><text class="pm-more-text" x="{num(cx)}" y="{num(cy + 3.5)}">{esc(label)}</text></g>'
    )


def badge_svg(mm, kind, i, cid, x, y):
    word = "Gap" if kind == "gap" else "Clarification"
    return (
        f'<a class="pm-badge-link" href="#{mm.pre}{cid}" aria-label="{word} {i}"><g class="pm-badge pm-badge-{kind}">'
        f'<circle class="pm-badge-ring" cx="{num(x)}" cy="{num(y)}" r="11"/>'
        f'<text class="pm-badge-num" x="{num(x)}" y="{num(y + 4)}">{i}</text></g></a>'
    )


def badges_svg(mm, n):
    b = mm.badge[n.id]
    pos, ch = mm.badge_slots(n)
    s = "".join(
        badge_svg(mm, kind, k, cid, bx, by) for (kind, k, cid, _t), (bx, by) in zip(b, pos, strict=False)
    )
    if ch:
        s += chip(ch[0], ch[1], f"+{len(b) - 3}")
    return s


def sys_svg(mm, sid, cx, cy):
    s = mm.systems[sid]
    return (
        f'<g class="pm-sys"><circle class="pm-sys-bg" cx="{num(cx)}" cy="{num(cy)}" r="11"/>'
        f'<g class="pm-ic" transform="translate({num(cx - 6.5)},{num(cy - 6.5)}) scale(0.81)">{ICONS[s["icon"]]}</g></g>'
    )


TITLE_MEASURE = CW - 32  # a card title's measure: room for its marker after the last line


def title_marker(e, lines, cx, y0, lead, size):
    """The marker after a centred bold title's last line, raised like a footnote."""
    if e is None:
        return ""
    return mk_svg(e, cx + tw(lines[-1], size, True) / 2 + 2, y0 + lead * (len(lines) - 1) - size * 0.38)


def node_svg(mm, n, ui=""):
    """A card: the title with its one citation marker, the owner, a gap step's tag, and the step id. Nothing
    else: every address and reading is in the page's Citation points section."""
    x, y, cx = n.x, n.y, n.cx
    cls = f"pm-node is-{n.state}" + (f" is-{ui}" if ui else "")
    lab = esc(f"{n.id} {n.d['title']}")
    s = (
        f'<g class="{cls}" id="{mm.pre}{n.id}" data-node="{n.id}" data-tip="{n.id}" tabindex="0" role="group" aria-label="{lab}">'
        f'<rect class="pm-focus-ring" x="{num(x - 8)}" y="{num(y - 8)}" width="{CW + 16}" height="{CH + 16}" rx="4"/>'
        f'<rect class="pm-node-rect is-{n.state}" x="{num(x)}" y="{num(y)}" width="{CW}" height="{CH}" rx="2"/>'
    )
    title, cut = wrap_bal(n.d["title"], 12, True, TITLE_MEASURE, 3)
    if cut:  # a long title takes the full measure before it is cut; its marker then sits closer to the edge
        title, cut = wrap_bal(n.d["title"], 12, True, CW - 24, 3)
    if cut:
        warn(f"build-6 {mm.where}: the title of {n.id} is cut with … on its card")
    s += text_lines("pm-node-title", cx, y + 24, title, 13)
    s += title_marker(mm.point(n.id), title, cx, y + 24, 13, 12)
    # the low block, bottom up: the step id on the last line (93), then a gap step's tag, then the owner
    low = [("pm-node-id", n.id)]
    if n.state == "gap":
        low.append(("pm-node-tag", "Needs confirmation"))
    if n.d.get("owner"):
        low.append(("pm-node-owner", fit(n.d["owner"], 9.5, True, CW - 12)))
    for i, (tcls, v) in enumerate(low):
        s += f'<text class="{tcls}" x="{num(cx)}" y="{num(y + 93 - 13 * i)}" text-anchor="middle">{esc(v)}</text>'
    s += badges_svg(mm, n)
    sy = n.d.get("systems", [])
    for i, sid in enumerate(sy[:2]):
        s += sys_svg(mm, sid, x + CW - 24 * i, y)
    if len(sy) > 2:
        s += chip(x + CW - 52, y, f"+{len(sy) - 2}")
    return s + "</g>"


def decision_svg(mm, n, ui=""):
    cx, cy = n.cx, n.cy
    cls = f"pm-decision-group is-{n.state}" + (f" is-{ui}" if ui else "")
    rot = f'transform="rotate(45 {num(cx)} {num(cy)})"'
    a = 30.1
    s = (
        f'<g class="{cls}" id="{mm.pre}{n.id}" data-node="{n.id}" data-tip="{n.id}" tabindex="0" role="group" '
        f'aria-label="{esc(n.id + " " + n.d["title"])}">'
        f'<rect class="pm-focus-ring" x="{num(cx - a - 6)}" y="{num(cy - a - 6)}" width="{num(2 * a + 12)}" height="{num(2 * a + 12)}" rx="4" {rot}/>'
        f'<rect class="pm-decision is-{n.state}" x="{num(cx - a)}" y="{num(cy - a)}" width="60.2" height="60.2" rx="2" {rot}/>'
    )
    # the question: 10px on at most two lines of up to 80 units, so any realistic 24-character question
    # fits uncut; a line may run a few units past the slanted edges, over a paper halo (.pm-decision-label)
    lines, cut = wrap_bal(n.d["title"], DEC_FONT, True, DEC_MEASURE, 2)
    if cut:
        warn(f"build-6 {mm.where}: the question of {n.id} is cut with … in its diamond")
    y0 = cy - 2 if len(lines) > 1 else cy + 3.5
    s += text_lines("pm-decision-label", cx, y0, lines, 11)
    # under the bottom vertex: the id and the marker, centred; right of the line when a branch leaves there
    e = mm.point(n.id)
    yy = cy + HALF + 13
    idw = tw(n.id, 9, False)
    mw = tw(str(e["n"]), 9, True) + 2 if e else 0
    x0 = cx + 6 if n.bottom_used else cx - (idw + mw) / 2
    s += f'<text class="pm-node-id" x="{num(x0)}" y="{num(yy)}">{esc(n.id)}</text>'
    if e:
        s += mk_svg(e, x0 + idw + 2, yy - 3.5)
    s += badges_svg(mm, n)
    return s + "</g>"


def path_d(pts):
    return "M " + " L ".join(f"{num(x)} {num(y)}" for x, y in pts)


def arrow(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / ln, dy / ln
    bx, by = b[0] - ux * 5, b[1] - uy * 5
    px, py = -uy * 3.4, ux * 3.4
    return (
        f'<polygon class="pm-arrow" points="{num(b[0])},{num(b[1])} {num(bx + px)},{num(by + py)} '
        f'{num(bx - px)},{num(by - py)}"/>'
    )


def edges_svg(mm, ui=None):
    s = ""
    for r in mm.routes:
        e, d = r["e"], path_d(r["pts"])
        cls = "pm-feed" if r["feedback"] else "pm-flow"
        kind = ("is-feedback " if r["feedback"] else "") + (
            "is-branch" if e.get("kind") == "conditional" else "is-flow"
        )
        extra = " is-hover" if ui and (e["from"], e["to"]) in ui else ""
        s += (
            f'<g class="pm-edge {kind.strip()}{extra}" data-from="{e["from"]}" data-to="{e["to"]}">'
            f'<path class="pm-hit" d="{d}"/><path class="{cls}" d="{d}"/>{arrow(r["pts"][-2], r["pts"][-1])}</g>'
        )
    return s


def pills_svg(mm):
    s = ""
    for r in mm.routes:
        if not r["pill"]:
            continue
        px, py, w, label = r["pill"]
        s += (
            f'<g class="pm-pill-g"><rect class="pm-pill" x="{num(px - w / 2)}" y="{num(py - 9)}" width="{num(w)}" height="18" rx="9"/>'
            f'<text class="pm-pill-text" x="{num(px)}" y="{num(py + 3.8)}">{esc(label)}</text></g>'
        )
    return s


def lane_label_svg(label, y, h, note, e=None, gid="", lx=14, max_w=134):
    """The role in the gutter, its marker when the lane cites, and the derived note."""
    lines, cut = wrap(label, 15, True, max_w, 3)
    lh = 17
    block = (len(lines) - 1) * lh + (16 if note else 0)
    ty = y + h / 2 - block / 2 + 5
    gid = f' id="{gid}"' if gid else ""
    s = f'<g class="pm-lane-head"{gid}>' + text_lines("pm-lane-label", lx, ty, lines, lh, anchor_mid=False)
    if e:  # after the last line, or after the note when the line leaves no room
        mx, my = lx + tw(lines[-1], 15, True) + 2, ty + (len(lines) - 1) * lh - 6
        if mx + tw(str(e["n"]), 9, True) > GUT - 4:
            mx, my = lx + (tw(note, 11) + 3 if note else 0), ty + (len(lines) - 1) * lh + (12 if note else 14)
        s += mk_svg(e, mx, my)
    if note:
        s += f'<text class="pm-lane-note" x="{lx}" y="{num(ty + (len(lines) - 1) * lh + 16)}">{esc(note)}</text>'
    return s + "</g>", cut


def board_parts(mm, ui=None):
    """The board's SVG parts in draw order: gutter, lanes, band, edges, nodes, pills (README section 2)."""
    ui = ui or {}
    W, H = mm.W, mm.H
    gut = f'<rect class="pm-bg" width="{GUT}" height="{num(H)}"/>'
    lanes = f'<rect class="pm-bg" x="{GUT}" width="{num(W - GUT)}" height="{num(H)}"/>'
    lane_data = []
    for i, lane in enumerate(mm.lanes):
        y, h = mm.lane_geo[lane["id"]]
        members = [n for n in mm.nodes if n.d["lane"] == lane["id"]]
        note = mm.note(members) if members else ""
        gut += f'<rect class="pm-lane-{i % 2}" y="{num(y)}" width="{GUT}" height="{num(h)}"/>'
        e = mm.point(f"lane-{lane['id']}")
        lbl, cut = lane_label_svg(lane["label"], y, h, note, e, f"{mm.pre}lane-{lane['id']}")
        if cut:
            warn(f"build-6 {mm.where}: the lane label {lane['label']!r} is cut with …")
        gut += lbl
        lanes += (
            f'<rect class="pm-lane-{i % 2}" x="{GUT}" y="{num(y)}" width="{num(W - GUT)}" height="{num(h)}"/>'
        )
        if not members:
            lanes += f'<text class="pm-lane-empty" x="{GUT + 16}" y="{num(y + h / 2 + 4)}">No steps in this lane</text>'
        lane_data.append([lane["label"], y, h, note] + ([e["n"], e["anchor"], mk_label(e)] if e else []))
    gut += f'<line class="pm-gutter-divider" x1="{GUT}" y1="{num(mm.lanes_top)}" x2="{GUT}" y2="{num(mm.lanes_bottom)}"/>'
    for g in mm.groups[1:]:
        x0 = mm.cells[g["id"]][2]
        lanes += f'<line class="pm-group-divider" x1="{num(x0)}" y1="{num(mm.lanes_top)}" x2="{num(x0)}" y2="{num(mm.lanes_bottom)}"/>'
    band = ""
    if mm.band:
        band = '<g class="pm-band">'
        for gi, g in enumerate(mm.groups):
            gx, gw, x0 = mm.cells[g["id"]]
            members = [n for n in mm.nodes if n.d.get("group") == g["id"]]
            idw = tw(g["id"], 11, True)
            room = gw - 8 - LABEL_RESERVE - idw - 6
            label = fit(g["label"], 12, True, room)
            if label != g["label"]:
                warn(f"build-6 {mm.where}: the label of {g['id']} is cut with … in the band")
            tcls = " is-target" if ui.get("group") == g["id"] else ""
            band += (
                f'<g class="pm-group{tcls}" id="{mm.pre}{g["id"]}" data-group="{g["id"]}">'
                f'<rect class="pm-band-cell" x="{num(gx)}" y="{BAND_TOP}" width="{num(gw)}" height="{BAND_BOT - BAND_TOP}"/>'
            )
            if gi:
                band += f'<line class="pm-band-sep" x1="{num(x0)}" y1="14" x2="{num(x0)}" y2="34"/>'
            band += (
                f'<text x="{num(gx + 8)}" y="23"><tspan class="pm-band-id">{esc(g["id"])}</tspan>'
                f'<tspan class="pm-band-label" dx="6">{esc(label)}</tspan></text>'
                f'<text class="pm-band-meta" x="{num(gx + 8)}" y="35.5">{esc(mm.note(members))}</text></g>'
            )
        band += f'<line class="pm-band-line" x1="{GUT}" y1="{BAND_BOT}" x2="{num(W)}" y2="{BAND_BOT}"/></g>'
    nodes = ""
    for n in mm.nodes:
        if not n.dec:
            nodes += node_svg(mm, n, ui.get(n.id, ""))
    for n in mm.nodes:
        if n.dec:
            nodes += decision_svg(mm, n, ui.get(n.id, ""))
    data = {
        "w": round(W, 2),
        "h": round(H, 2),
        "lanes": lane_data,
        "tips": {n.id: mm.tip(n) for n in mm.nodes},
    }
    return {
        "gutter": gut,
        "lanes": lanes,
        "band": band,
        "edges": edges_svg(mm, ui.get("edges")),
        "nodes": nodes,
        "pills": pills_svg(mm),
        "data": data,
    }


# ------------------------------------------------------------------ HTML around the board


def header_html(meta, systems, kicker, title, subtitle, mm=None):
    flags = meta.get("flags", [])
    chips = "".join(
        f'<span class="pm-flag{" is-confidential" if f == "confidential" else ""}">'
        f"{'Confidential' if f == 'confidential' else 'Draft'}</span>"
        for f in flags
    )
    flags_html = f'<div class="pm-flags">{chips}</div>' if chips else ""
    s = f'<div class="pm-kicker-row"><p class="pm-kicker">{esc(kicker)}</p>{flags_html}</div><h1>{esc(title)}</h1>'
    if subtitle:
        s += f'<p class="pm-subtitle">{esc(subtitle)}</p>'
    if systems:
        s += system_key(systems, mm)
    return s


def system_key(systems, mm):
    """The system key: one item per system, with its icon and its one citation marker."""

    def item(x):
        e = mm.point(f"sys-{x['id']}") if mm else None
        return f'<li id="{mm.pre if mm else ""}sys-{x["id"]}">{icon_svg(x["icon"])}{esc(x["label"])}{mks([e]) if e else ""}</li>'

    return '<ul class="pm-key" aria-label="Systems">' + "".join(item(x) for x in systems) + "</ul>"


def gaps_html(mm, target=None):
    """The Gaps card: required, so it always lists at least one gap (build-7)."""
    pre = mm.pre
    body = '<ol class="pm-ev-list pm-ev-gaps">'
    for g, i, title, text, prov in mm.gap_html:
        t = ' class="is-target"' if target == g["id"] else ""
        steps = ", ".join(f'<a href="#{pre}{x}">{x}</a>' for x in g["nodes"])
        body += (
            f'<li id="{pre}{g["id"]}" data-n="{i}"{t}><strong>{title}</strong>{text}'
            f'<span class="pm-ev-steps">Steps: {steps}</span>{prov}</li>'
        )
    body += "</ol>"
    return f'<article class="pm-ev-card" id="{pre}gaps"><h2>Gaps</h2>{body}</article>'


def clar_html(mm, target=None):
    """The Clarifications card: required, so it always lists at least one question (build-7)."""
    pre = mm.pre
    body = '<ol class="pm-ev-list pm-ev-clar">'
    for c, i, title, shows, ask, prov in mm.clar_html:
        t = ' class="is-target"' if target == c["id"] else ""
        steps = ", ".join(f'<a href="#{pre}{x}">{x}</a>' for x in c["nodes"])
        body += (
            f'<li id="{pre}{c["id"]}" data-n="{i}"{t}><strong>{title}</strong>'
            f'<span class="pm-ev-row"><b>What the sources show:</b> {shows}</span>'
            f'<span class="pm-ev-row"><b>To confirm:</b> {ask}</span>'
            f'<span class="pm-ev-steps">Steps: {steps}</span>{prov}</li>'
        )
    body += "</ol>"
    return (
        f'<article class="pm-ev-card" id="{pre}clarifications"><h2>Clarifications needed</h2>{body}</article>'
    )


def quote(r, ctx=True):
    c = f"{esc(r['context'])} · " if ctx and r.get("context") else ""
    return f"{c}<q>{esc(r['text'])}</q>"


def cp_html(reg, links, target=None, only=None):
    """The page's Citation points section (FORMATS 2.6): one row per point, numbered as
    its markers, at the point's anchor. Each row prints the address, the verbatim text, how it is used and by what
    (linked to the element), and links to the record's row in Original data received and to the workspace's
    Citation points page. Above the rows, one line per record the page uses."""
    idx = reg.idx
    rows = [e for e in reg.order if not only or e["source"] in only]
    srcs = sorted({e["source"] for e in rows})
    heads = ""
    for sid in srcs:
        h = idx.src[sid]["h"]
        bits = [esc(h["title"])] + ([esc(h["detail"])] if h.get("detail") else []) + [esc(idx.label(sid))]
        if h["kind"] == "web" and h.get("url"):
            bits.append(esc(domain(h["url"])))
        bits.append(f"captured {pdate(h['captured'])}")
        heads += (
            f'<li id="{reg.pre}src-{slug(sid)}"><a href="{links}data-received.html#{esc(sid)}" '
            f'title="Open {esc(sid)} in Original data received">{esc(sid)}</a> · {" · ".join(bits)}</li>'
        )
    out = ""
    for e in rows:
        t = " is-target" if target == e["anchor"] else ""
        if e["kind"] == "absent":
            state = "PROVISIONAL" if e["partial"] else "PROVEN"
            text = f'<span class="cp-absent">Searched for “{esc(e["needle"])}”: not found · {state}</span>'
        elif e["kind"] == "rec":
            text = quote(e["recs"][0])
        else:
            recs = e["recs"]
            text = " · ".join(f"<q>{esc(r['text'])}</q>" for r in recs[:10])
            if len(recs) > 10:
                text += f" · and {len(recs) - 10} more"
            text = f'<span class="cp-recs">{text}</span>'
        for reading, (name, href) in e.get("notes", []):
            text += f'<span class="cp-note"><b>Inferred</b> · {esc(reading)} · {link(name, href)}</span>'
        uses = {}
        for name, href, kind in e["used"]:
            uses.setdefault(kind, []).append(link(name, href))
        used = "".join(
            f'<span class="cp-use"><b>{USE_WORD[k]}</b> · {", ".join(v)}</span>'
            for k, v in sorted(uses.items(), key=lambda kv: list(USE_WORD).index(kv[0]))
        )
        addr = e["address"] if e["loc"] else f"{e['source']} · whole source"
        out += (
            f'<li class="cp-row{t}" id="{e["anchor"]}" data-n="{e["n"]}"><span class="cp-n">{e["n"]}</span>'
            f'<a class="cp-addr" href="{links}data-received.html#{esc(e["source"])}" '
            f'title="Open {esc(e["source"])} in Original data received">{esc(addr)}</a>'
            f'<span class="cp-text">{text}</span><span class="cp-used">{used}</span>'
            f'<a class="cp-all" href="{links}citation-points.html#{e["anchor"][len(reg.pre) :]}" '
            f'aria-label="Point {e["n"]} in Citation points" title="Open in Citation points">↗</a></li>'
        )
    count = f"{plural(len(rows), 'point')} from {plural(len(srcs), 'record')}"
    return (
        f'<section class="cp" id="{reg.pre}citation-points" aria-labelledby="{reg.pre}cp-h"><div class="cp-head">'
        f'<h2 id="{reg.pre}cp-h">Citation points</h2><span class="cp-count">{count}</span></div>'
        f'<ul class="cp-srcs">{heads}</ul><ol class="cp-list">{out}</ol></section>'
    )


def link(name, href):
    return f'<a href="#{href}">{esc(name)}</a>' if href else esc(name)


def cp_tip(e):
    """A marker's one-line tooltip, as the page script writes it: the address and the first words of the text."""
    if e["kind"] == "absent":
        t = f"Searched for “{e['needle']}”: not found"
    else:
        t = " · ".join(f"“{r['text']}”" for r in e["recs"][:3])
    if len(t) > 72:
        t = t[:70].rsplit(" ", 1)[0] + " …"
    addr = e["address"] if e["loc"] else f"{e['source']} · whole source"
    return f"<b>{esc(addr)}</b> · {esc(t)}"


def footer_html(meta, date):
    left = meta.get("footer") or "Source · process map"
    right = []
    if "confidential" in meta.get("flags", []):
        right.append(f"Contains {meta['client']} confidential information")
    if "draft" in meta.get("flags", []):
        right.append("Draft")
    right.append(pdate(date))
    return f'<footer class="pm-footer"><span>{esc(left)}</span><span>{esc(" · ".join(right))}</span></footer>'


# ------------------------------------------------------------------ templates


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise CannotRun(f"cannot read {path}: {e}") from e


def board_template():
    """board.html as (page template, board shell template, legend template)."""
    t = read(BOARD_HTML)
    t = re.sub(r"^<!doctype html>\n<!--.*?-->\n", "<!doctype html>\n", t, count=1, flags=re.S)
    lg = re.search(r"<!--bs:legend-->\n(.*?)<!--/bs:legend-->\n", t, re.S)
    m = re.search(r"<!--bs:shell-->\n(.*?)<!--/bs:shell-->\n", t, re.S)
    if not m or not lg:
        raise CannotRun("board.html has no <!--bs:shell--> or <!--bs:legend--> block")
    t = t.replace(lg.group(0), "")
    return t.replace(m.group(0), "{{shell}}"), m.group(1), lg.group(1).rstrip("\n")


def board_style_script():
    t = read(BOARD_HTML)
    st = re.search(r'<style id="pm-style">.*?</style>', t, re.S).group(0)
    sc = re.search(r'<script id="pm-script">.*?</script>', t, re.S).group(0)
    return st, sc


def fills():
    t = read(FILLS_HTML)
    parts = dict(re.findall(r"<!--fill:([a-z-]+)-->\n(.*?)(?=<!--fill:|\Z)", t, re.S))
    for k in ("style", "legend-end", "toggle", "toggle-none", "card", "card-empty", "script"):
        if k not in parts:
            raise CannotRun(f"fills.html has no <!--fill:{k}--> part")
    return {k: v.rstrip("\n") for k, v in parts.items()}


def shell_html(shell_tpl, mm, parts, label, zoom="fit", slots=None, panel=""):
    return fill(
        shell_tpl,
        slots,
        pre=mm.pre,
        label=esc(label),
        fit=str(zoom != "100").lower(),
        full=str(zoom == "100").lower(),
        zoom=zoom,
        h=num(mm.H),
        cw=num(mm.W - GUT),
        gutter=parts["gutter"],
        lanes=parts["lanes"],
        panel=panel,
        band=parts["band"],
        edges=parts["edges"],
        nodes=parts["nodes"],
        pills=parts["pills"],
        data=jdump(parts["data"]),
    )


# ------------------------------------------------------------------ the AI layer: three views of one layer
# The AI page leads with the List (default), then the Flow, then On the map (the base board with the layer in its
# slots). All three are computed from the same base map and layer file.

AI_WORD = {"named": "Named by the client", "suggested": "Our suggestion"}
SQ = 16
VIEWS = (("list", "List"), ("flow", "Flow"), ("map", "On the map"))


class AiModel:
    def __init__(self, layer, mm, where):
        self.layer, self.mm, self.where = layer, mm, where
        self.items = layer.get("ai", [])
        # the List and the Flow read named items first, then our suggestions, each by id
        self.order = sorted(self.items, key=lambda i: (i["origin"] != "named", i["id"]))
        self.by_node, self.by_group, self.all = {}, {}, []
        for it in self.items:
            for nid in it.get("nodes", []):
                n = mm.N.get(nid)
                if not n or n.dec:
                    raise DataError(
                        f"{where}: {it['id']} lists {nid!r}, which is not a step of the base (ai-2)"
                    )
                self.by_node.setdefault(nid, []).append(it)
            g = it.get("groups", [])
            if g == "all":
                self.all.append(it)
            else:
                for gid in g:
                    if gid not in mm.group_ix or not mm.band:
                        raise DataError(
                            f"{where}: {it['id']} lists view {gid!r}, which is not a group of a base with two or more groups (ai-2)"
                        )
                    self.by_group.setdefault(gid, []).append(it)
        if self.all and not mm.band:
            raise DataError(f"{where}: an all-views item needs a base with two or more groups (ai-2)")
        reg = mm.reg
        self.pairs = {it["id"]: reg.cites(it["cite"], (it["id"], mm.pre + it["id"])) for it in self.items}
        for it in self.items:
            for sid in (it.get("agentic") or {}).get("systems", []):
                if sid not in mm.systems:
                    raise DataError(
                        f"{where}: {it['id']}'s agentic version names system {sid!r}, which is not in the base (ai-4)"
                    )

    # -- squares
    def square(self, it, cx, cy, extra=""):
        h = SQ / 2
        return (
            f'<g class="pm-ai-sq is-{it["origin"]}" data-ai="{it["id"]}"{extra}><title>{esc(it["id"] + " " + it["title"] + " · " + AI_WORD[it["origin"]])}</title>'
            f'<rect x="{num(cx - h)}" y="{num(cy - h)}" width="{SQ}" height="{SQ}" rx="2"/>'
            f'<text x="{num(cx)}" y="{num(cy + 3.3)}">{it["id"][3:]}</text></g>'
        )

    def more(self, cx, cy, rest):
        h = SQ / 2
        ids = " ".join(i["id"] for i in rest)
        return (
            f'<g class="pm-ai-more" data-ai="{ids}"><title>{len(rest)} more AI items: {esc(ids)}</title>'
            f'<rect x="{num(cx - h)}" y="{num(cy - h)}" width="{SQ}" height="{SQ}" rx="2"/>'
            f'<text x="{num(cx)}" y="{num(cy + 3.2)}">+{len(rest)}</text></g>'
        )

    @staticmethod
    def nslots(n, most):
        """Slots a run of n items takes: up to `most` squares; beyond that, two squares and +n."""
        return n if n <= most else 3

    def run(self, items, x_right, cy, most, step=-20):
        """A run of squares, the last centred at x_right (the first, when step is positive), each `step` from
        the one before: up to `most` squares, or two squares and +n."""
        k = self.nslots(len(items), most)
        xs = (
            [x_right + step * (k - 1 - j) for j in range(k)]
            if step < 0
            else [x_right + step * j for j in range(k)]
        )
        shown, rest = (items, []) if len(items) <= most else (items[:2], items[2:])
        out = "".join(self.square(it, x, cy) for it, x in zip(shown, xs, strict=False))
        return out + (self.more(xs[-1], cy, rest) if rest else "")

    # -- the board's slots (On the map)
    def under(self, ui=None):
        ui = ui or {}
        mm = self.mm
        s = '<g class="pm-ai-under">'
        for g in mm.groups if mm.band else []:
            gx, gw, _ = mm.cells[g["id"]]
            ids = " ".join(i["id"] for i in self.by_group.get(g["id"], []) + self.all)
            if ids:
                on = " is-ai-on is-ai-peek" if ui.get("tint") in (g["id"], "all") else ""
                s += (
                    f'<rect class="pm-ai pm-ai-band-hit{on}" data-group="{g["id"]}" data-ai="{ids}" x="{num(gx)}" '
                    f'y="{BAND_TOP}" width="{num(gw)}" height="{BAND_BOT - BAND_TOP}"/>'
                )
        for n in mm.nodes:
            its = self.by_node.get(n.id)
            if its:
                c = ui.get("halo", {}).get(n.id, "")
                s += (
                    f'<g class="pm-ai pm-ai-node{(" " + c) if c else ""}" data-node="{n.id}" data-ai="{" ".join(i["id"] for i in its)}">'
                    f'<rect class="pm-ai-halo" x="{num(n.x - 4)}" y="{num(n.y - 4)}" width="{CW + 8}" height="{CH + 8}" rx="6"/></g>'
                )
        return s + "</g>"

    def over(self, ui=None):
        ui = ui or {}
        mm = self.mm
        s = '<g class="pm-ai-over">'
        for n in mm.nodes:
            its = self.by_node.get(n.id)
            if not its:
                continue
            c = ui.get("marks", {}).get(n.id, "")
            s += (
                f'<g class="pm-ai pm-ai-marks{(" " + c) if c else ""}" data-node="{n.id}" data-ai="{" ".join(i["id"] for i in its)}">'
                + self.run(its, n.x + CW, n.y + CH + 5, 3, -21)
                + "</g>"
            )
        for g in mm.groups if mm.band else []:
            its = self.by_group.get(g["id"])
            if not its:
                continue
            gx, gw, _ = mm.cells[g["id"]]
            ids = " ".join(i["id"] for i in its)
            c = ui.get("view", {}).get(g["id"], "")
            s += (
                f'<g class="pm-ai pm-ai-view{(" " + c) if c else ""}" data-group="{g["id"]}" data-ai="{ids}">'
                f'<rect class="pm-ai-rail" data-ai="{ids}" x="{num(gx + 6)}" y="40" width="{num(gw - 12)}" height="2"/>'
                + self.run(its, gx + gw - 14, 26, 2)
                + "</g>"
            )
        if self.all:
            ids = " ".join(i["id"] for i in self.all)
            x0, x1 = GUT + 6, mm.W - 6
            c = ui.get("all", "")
            s += (
                f'<g class="pm-ai pm-ai-all{(" " + c) if c else ""}" data-ai="{ids}"><path class="pm-ai-rail" data-ai="{ids}" '
                f'd="M {num(x0)} 14 L {num(x0)} 8 L {num(x1)} 8 L {num(x1)} 14"/></g>'
            )
        for n in mm.nodes:
            its = self.by_node.get(n.id)
            if not its:
                continue
            lab = f"{n.id} {n.d['title']}: " + "; ".join(
                f"{i['id']} {i['title']} ({AI_WORD[i['origin']].lower()})" for i in its
            )
            s += (
                f'<rect class="pm-ai pm-ai-hit" data-node="{n.id}" data-ai="{" ".join(i["id"] for i in its)}" data-tip="{n.id}" '
                f'tabindex="0" role="button" aria-label="{esc(lab)}" x="{num(n.x - 4)}" y="{num(n.y - 4)}" '
                f'width="{CW + 8}" height="{CH + 8}" rx="6"/>'
            )
        return s + "</g>"

    def gutter_over(self, ui=None):
        if not self.all:
            return ""
        ui = ui or {}
        k = self.nslots(len(self.all), 3)
        ids = " ".join(i["id"] for i in self.all)
        c = ui.get("all", "")
        return (
            f'<g class="pm-slot-over pm-ai-over"><g class="pm-ai pm-ai-all{(" " + c) if c else ""}" data-ai="{ids}">'
            + self.run(self.all, 22, 26, 3, 20)
            + f'<text class="pm-ai-all-text" x="{num(14 + 20 * k + 6)}" y="30">ALL VIEWS</text></g></g>'
        )

    def tip_lines(self):
        out = {}
        for nid, its in self.by_node.items():
            s = "".join(
                f'<span class="pm-ai-tip-line"><span class="pm-ai-mark is-{i["origin"]}" aria-hidden="true">{i["id"][3:]}</span>'
                f"<span><b>{i['id']}</b> {esc(i['title'])} · {'Named' if i['origin'] == 'named' else 'Suggested'}</span></span>"
                for i in its
            )
            out[nid] = (
                f'<span class="pm-ai-tip">{s}<span class="pm-ai-tip-foot">Click to highlight it on the map</span></span>'
            )
        return out

    def data(self):
        mm = self.mm
        members = {g["id"]: [n.id for n in mm.nodes if n.d.get("group") == g["id"]] for g in mm.groups}
        return {
            "items": {
                i["id"]: {"nodes": i.get("nodes", []), "groups": i.get("groups", [])} for i in self.items
            },
            "members": members,
            "tips": self.tip_lines(),
        }

    def picks(self, pinned=None):
        """On the map: one square per item, in List order; pressing one highlights it on the board."""
        if not self.items:
            return ""
        b = "".join(
            f'<button type="button" class="pm-ai-pick is-{i["origin"]}" data-ai="{i["id"]}" aria-pressed="{str(i["id"] == pinned).lower()}" '
            f'title="{esc(i["id"] + " " + i["title"])}"><span class="pm-ai-mark is-{i["origin"]}" aria-hidden="true">{i["id"][3:]}</span>'
            f'<span class="pm-ai-pick-id">{i["id"]}</span></button>'
            for i in self.order
        )
        return f'<div class="pm-ai-picks" role="group" aria-label="Highlight an AI opportunity on the map">{b}</div>'

    def slots(self, F, ui=None, off=False, pinned=None):
        """The board's slots on an AI page: the map view's head (the toggle, the highlight squares, the system key
        and the legend), the layer's data in the toolbar, and the board marks."""
        mm = self.mm
        if self.items:
            tools = fill(
                F["toggle"], pressed=str(not off).lower(), state="Off" if off else "On"
            ) + self.picks(pinned)
            legend_end = fill(F["legend-end"], client=esc(mm.meta["client"]))
        else:
            tools, legend_end = F["toggle-none"], ""
        toolbar = f'<script type="application/json" class="pm-ai-data">{jdump(self.data())}</script>'
        _, _, legend = board_template()
        key = system_key(mm.m.get("systems", []), mm) if mm.m.get("systems") else ""
        head = (
            f'<div class="pm-map-head"><div class="pm-map-tools"><div class="pm-map-row">{tools}</div>{key}</div>'
            f"{fill(legend, {'legend-end': legend_end})}</div>"
        )
        return {
            "toolbar": toolbar,
            "legend-end": legend_end,
            "board-head": head,
            "board-under": self.under(ui),
            "board-over": self.over(ui),
            "board-over:gutter": self.gutter_over(ui),
        }

    # -- the headline summary
    def summary(self):
        mm, items = self.mm, self.items
        steps = sum(1 for n in mm.nodes if not n.dec)
        if not items:
            return (
                '<p class="pm-ai-summary"><span class="pm-ai-summary-in"><span><b>No AI opportunities</b> yet</span>'
                f"<span>touches <b>0</b> of <b>{steps}</b> steps</span></span></p>"
            )
        named = sum(1 for i in items if i["origin"] == "named")
        sug = len(items) - named
        touched = len({nid for i in items for nid in i.get("nodes", [])})
        views = sum(1 for i in items if isinstance(i.get("groups"), list) and i["groups"])
        segs = [f"<b>{len(items)}</b> AI {'opportunity' if len(items) == 1 else 'opportunities'}"]
        if named:
            segs.append(
                f'<i class="pm-ai-sum-sq is-named" aria-hidden="true"></i><b>{named}</b> named by {esc(mm.meta["client"])}'
            )
        if sug:
            segs.append(
                f'<i class="pm-ai-sum-sq" aria-hidden="true"></i><b>{sug}</b> {"our suggestion" if sug == 1 else "our suggestions"}'
            )
        segs.append(f"touches <b>{touched}</b> of <b>{steps}</b> steps")
        if views:
            segs.append(f"<b>{views}</b> across a whole view")
        if self.all:
            segs.append(f"<b>{len(self.all)}</b> across all views")
        return (
            '<p class="pm-ai-summary"><span class="pm-ai-summary-in">'
            + "".join(f"<span>{x}</span>" for x in segs)
            + "</span></p>"
        )

    # -- the List
    def evidence_html(self, it):
        """The evidence of a row: a grounded citation's quote (or its first record's text) over a Grounded line
        with the speaker or web domain; an inferred one's basis over an Inferred line. Markers, not addresses."""
        idx = self.mm.idx
        out = ""
        for c, es in self.pairs[it["id"]]:
            t = ctype(c)
            if t == "grounded":
                e = es[0]
                h = idx.src[c["source"]]["h"]
                text = c.get("quote") or e["recs"][0]["text"]
                extra = ""
                if h["kind"] == "transcript" and e["recs"][0].get("context"):
                    extra = f" · {esc(e['recs'][0]['context'])}"
                elif h["kind"] == "web" and h.get("url"):
                    extra = f" · {esc(domain(h['url']))}"
                out += (
                    f'<blockquote class="pm-ai-cite is-quote">“{esc(text)}”</blockquote>'
                    f'<span class="pm-prov"><span class="pm-prov-grounded"><b>Grounded</b>{extra}{mks([e])}</span></span>'
                )
            elif t == "inferred":
                out += (
                    f'<p class="pm-ai-cite is-inferred"><strong>Basis:</strong> {esc(c["reading"])}</p>'
                    f'<span class="pm-prov"><span class="pm-prov-inferred"><b>Inferred</b> · from{mks(es)}</span></span>'
                )
        return out

    def agentic_html(self, a, open_=False):
        if not a:
            return ""
        mm = self.mm
        li = ""
        for i, step in enumerate(a["steps"]):
            li += f'<li><span class="n">{i + 1}</span><span>{esc(step)}</span></li>'
            for d in a["decides"]:
                if d["after"] == i + 1:
                    li += (
                        f'<li class="is-person"><span class="d" aria-hidden="true"></span><span><b>Person decides</b> · '
                        f"{esc(d['who'])} {esc(d['what'])}</span></li>"
                    )
        nd = len(a["decides"])
        meta = f"{plural(len(a['steps']), 'step')} · {nd} {'place' if nd == 1 else 'places'} a person decides · {plural(len(a['systems']), 'system')}"
        syss = "".join(
            f'<span class="pm-ai-sys">{icon_svg(mm.systems[sid]["icon"])}{esc(mm.systems[sid]["label"])}</span>'
            for sid in a["systems"]
        )
        return (
            f'<details class="pm-ai-agentic"{" open" if open_ else ""}><summary><span class="pm-ai-ag-title">Agentic version</span>'
            f'<span class="pm-ai-ag-meta">{meta}</span></summary><dl class="pm-ai-ag">'
            f"<div><dt>Trigger</dt><dd>{esc(a['trigger'])}</dd></div>"
            f'<div><dt>Steps</dt><dd><ol class="pm-ai-flow">{li}</ol></dd></div>'
            f"<div><dt>Systems</dt><dd>{syss}</dd></div>"
            f"<div><dt>Logging</dt><dd>{esc(a['logging'])}</dd></div></dl></details>"
        )

    def row_html(self, it, state="", open_=False):
        mm, pre = self.mm, self.mm.pre
        chips = ""
        for nid in it.get("nodes", []):
            chips += f'<a class="pm-ai-step" href="#{pre}{nid}" data-node="{nid}"><b>{nid}</b>{esc(mm.N[nid].d["title"])}</a>'
        g = it.get("groups", [])
        if g == "all":
            chips += (
                f'<a class="pm-ai-step is-scope" href="#{pre}board" data-scope="all"><b>All views</b></a>'
            )
        else:
            for gid in g:
                gl = mm.groups[mm.group_ix[gid]]["label"]
                chips += f'<a class="pm-ai-step is-scope" href="#{pre}{gid}" data-group="{gid}"><b>{gid}</b>{esc(gl)} · whole view</a>'
        where_word = "Steps it touches" if it.get("nodes") else "Where it applies"
        cls = f"pm-ai-item is-{it['origin']}" + (f" {state}" if state else "")
        return (
            f'<li class="{cls}" data-ai="{it["id"]}" id="{pre}{it["id"]}">'
            f'<span class="pm-ai-mark is-{it["origin"]}" aria-hidden="true">{it["id"][3:]}</span><div class="pm-ai-body">'
            f'<div class="pm-ai-head"><h3 class="pm-ai-title"><span class="pm-ai-id">{it["id"]}</span> {esc(it["title"])}</h3>'
            f'<span class="pm-ai-origin is-{it["origin"]}">{AI_WORD[it["origin"]]}</span>'
            f'<button class="pm-ai-show" type="button" data-ai="{it["id"]}" aria-pressed="false">Show on map</button></div>'
            f'<div class="pm-ai-cols"><div><span class="pm-ai-label">What it would do</span><p class="pm-ai-does">{esc(it["does"])}</p>'
            f'<span class="pm-ai-label">{where_word}</span><div class="pm-ai-steps">{chips}</div></div>'
            f'<div><span class="pm-ai-label">Evidence</span>{self.evidence_html(it)}</div></div>'
            f"{self.agentic_html(it.get('agentic'), open_)}</div></li>"
        )

    def card_html(self, F, states=None, opened=()):
        states = states or {}
        if not self.items:
            return fill(F["card-empty"], pre=self.mm.pre)
        rows = "".join(self.row_html(it, states.get(it["id"], ""), it["id"] in opened) for it in self.order)
        named = sum(1 for i in self.items if i["origin"] == "named")
        count = plural(len(self.items), "item") + (
            " · named by the client first" if named and named < len(self.items) else ""
        )
        return fill(F["card"], pre=self.mm.pre, count=count, rows=rows)

    # -- the page: the view switch, then the List and the Flow panels (the board section is the third)
    def views_html(self, F):
        pre = self.mm.pre
        tabs = "".join(
            f'<button type="button" role="tab" class="pm-view-tab" id="{pre}tab-{v}" data-view="{v}" '
            f'aria-controls="{pre}{"board" if v == "map" else "ai-" + v}" aria-selected="{str(v == "list").lower()}"'
            f"{'' if v == 'list' else ' tabindex=' + chr(34) + '-1' + chr(34)}>{label}</button>"
            for v, label in VIEWS
        )
        nav = f'<nav class="pm-views" role="tablist" aria-label="Views">{tabs}</nav>'
        lst = (
            f'<section class="pm-view" id="{pre}ai-list" data-view-panel="list" role="tabpanel" aria-labelledby="{pre}tab-list">'
            f"{self.card_html(F)}</section>"
        )
        flow = (
            f'<section class="pm-view" id="{pre}ai-flow" data-view-panel="flow" role="tabpanel" aria-labelledby="{pre}tab-flow" data-off>'
            f"{FlowView(self).html()}</section>"
        )
        return nav + lst + flow

    def panel_attrs(self):
        pre = self.mm.pre
        return f' data-view-panel="map" role="tabpanel" aria-labelledby="{pre}tab-map" data-off'


# ------------------------------------------------------------------ the Flow view
# The steps in one horizontal line in flow order (the AI README section 3). The main path is the longest run of
# forward edges, read left to right on the line. Every other step sits on a row above it, in the cell whose lines
# cross no step and no label, and cross each other least; when no cell is clear, a column opens for the step.
# Lines are the map's own edges, each drawn once: along a row; straight up or down between the line and the step
# above; up from the line and along a row; along a row and down into the line; along a row to the gap beside the
# target's column, then up or down; else through the channel between the line and the first row, on tracks 12
# apart. Lines that leave one side of a step share one trunk and lines that enter one side share one stem, as on
# the board. A line through a step or a label fails the build (build-6); two lines that cross, or run closer than
# 12 units, are a warning that names both. Under the line, the AI lane. On a phone, the same order as a list.

FP, FM = 132, 28  # column pitch and side margin
FR = 14  # a step's circle radius; a decision is a square of side 1.3 * FR turned 45°
FD = FR * 0.65 * 2**0.5  # a decision's half diagonal
FROW = 96  # pitch of the rows above the line: a step and its label over it
FTRACK = 12  # pitch of the channel's tracks, and of two stems side by side
FMAXROW = 8
FLAB = FP - 22  # a title's widest measure
KIND_COST = {"row": 0, "vert": 0, "up": 1, "down": 1, "gap": 2, "ch": 3}


def flow_who(n):
    """The second line of a step in the Flow: its owner, or what it is."""
    return "Decision" if n.dec else (n.d.get("owner") or "no owner")


def seg_in_box(x1, y1, x2, y2, b, pad=0.5):
    """Does the axis-aligned segment run through the box (x0, y0, x1, y1), shrunk by pad?"""
    return (
        min(x1, x2) < b[2] - pad
        and max(x1, x2) > b[0] + pad
        and min(y1, y2) < b[3] - pad
        and max(y1, y2) > b[1] + pad
    )


def steps_words(steps, decs):
    if steps and decs:
        return f"{plural(steps, 'step')} and {plural(decs, 'decision')}"
    return plural(decs, "decision") if decs else plural(steps, "step")


class FlowView:
    """The Flow of an AI page, computed from the base map's nodes and edges and the layer's items."""

    def __init__(self, am):
        self.am, self.mm = am, am.mm
        mm = self.mm
        nodes, self.E = mm.nodes, mm.edges
        self.ix = ix = {n.id: n.i for n in nodes}
        preds = {n.id: [] for n in nodes}
        succs = {n.id: [] for n in nodes}
        for e in self.E:
            if ix[e["to"]] > ix[e["from"]]:
                preds[e["to"]].append(e["from"])
                succs[e["from"]].append(e["to"])
        best = {}
        for n in nodes:  # the longest path ending at each node; ties keep the earlier-listed predecessor
            cand = [(best[p][0] + 1, -ix[p], p) for p in preds[n.id]]
            if cand:
                L, _, p = max(cand)
                best[n.id] = (L, best[p][1] + [n.id])
            else:
                best[n.id] = (1, [n.id])
        end = max(nodes, key=lambda n: (best[n.id][0], n.i)).id
        self.main = best[end][1]
        at = {nid: i for i, nid in enumerate(self.main)}
        steps = [n.id for n in nodes if not n.dec]
        self.num = {
            nid: i + 1 for i, nid in enumerate(steps)
        }  # a step's number in the circle: its place in the list
        used = sorted({n.col for n in nodes})
        squeeze = {c: i for i, c in enumerate(used)}
        board = {n.id: squeeze[n.col] for n in nodes}
        self.col, self.row, self.cell = {}, {}, {}
        c = -1
        for nid in self.main:  # the line keeps the board's columns, closed up, and always moves right
            c = max(board[nid], c + 1)
            self.col[nid], self.row[nid] = c, 0
            self.cell[(c, 0)] = nid
        self.ncols = max([c] + list(board.values())) + 1
        self.kind = {}
        for k, e in enumerate(self.E):
            if e["from"] in at and e["to"] in at:
                self.kind[k] = "row" if at[e["to"]] == at[e["from"]] + 1 else "ch"
        self.links = {n.id: [] for n in nodes}
        for k, e in enumerate(self.E):
            self.links[e["from"]].append(k)
            self.links[e["to"]].append(k)
        self.ai = set(am.by_node)
        for n in nodes:
            if n.id not in at:
                self.place(n.id, preds[n.id], succs[n.id], board[n.id])
        self.improve((preds, succs, board))
        self.nrows = max(self.row.values())
        self.W = FM * 2 + FP * self.ncols
        self.geometry()

    # -- placement, in grid units: x is a column (a gap between columns is c ± 0.5), y a row (the channel is 0.5)
    def segs(self, kind, a, b):
        ca, ra, cb, rb = self.col[a], self.row[a], self.col[b], self.row[b]
        if kind in ("row", "vert"):
            return [(ca, ra, cb, rb)]
        if kind == "up":
            return [(ca, ra, ca, rb), (ca, rb, cb, rb)]
        if kind == "down":
            return [(ca, ra, cb, ra), (cb, ra, cb, rb)]
        if kind == "ch":
            return [(ca, ra, ca, 0.5), (ca, 0.5, cb, 0.5), (cb, 0.5, cb, rb)]
        g = cb - 0.5 if kind == "gapl" else cb + 0.5
        return [(ca, ra, g, ra), (g, ra, g, rb), (g, rb, cb, rb)]

    def kinds_for(self, a, b):
        ca, ra, cb, rb = self.col[a], self.row[a], self.col[b], self.row[b]
        out = []
        if ca == cb and (ra == 0) != (rb == 0):
            out.append("vert")
        elif ra == 0 and rb > 0:
            out.append("up")
        elif rb == 0 and ra > 0:
            out.append("down")
        elif ra == rb:
            out.append("row")
        else:
            out += ["gapl", "gapr"]
        return out + (["ch"] if ca != cb else [])

    def kcost(self, kind, a, b):
        if kind in ("gapl", "gapr"):  # a gap between the two columns is an L; a gap beyond the target is a U
            g = self.col[b] + (-0.5 if kind == "gapl" else 0.5)
            return KIND_COST["gap"] + (
                0 if min(self.col[a], self.col[b]) < g < max(self.col[a], self.col[b]) else 1
            )
        return KIND_COST[kind]

    def clear(self, sg, a, b):
        """No stretch passes a step other than its own two, and none runs through a step's label (the part of a
        column between a step's row and the row above)."""
        for x1, y1, x2, y2 in sg:
            if y1 == y2:
                if y1 == 0.5:
                    continue
                lo, hi = min(x1, x2), max(x1, x2)
                for c in range(int(lo + 0.5), int(hi) + 1):
                    if lo <= c <= hi and self.cell.get((c, y1)) not in (None, a, b):
                        return False
            elif x1 == int(x1):
                lo, hi = min(y1, y2), max(y1, y2)
                for r in range(FMAXROW + 1):
                    nid = self.cell.get((int(x1), r))
                    if nid is None:
                        continue
                    if nid not in (a, b) and lo <= r <= hi:
                        return False
                    if r and hi > r and lo < r + 1:
                        return False
        return True

    @staticmethod
    def put(H, V, s, k, add=True):
        x1, y1, x2, y2 = s
        lst, item = (
            (H.setdefault(y1, []), (min(x1, x2), max(x1, x2), k))
            if y1 == y2
            else (V.setdefault(x1, []), (min(y1, y2), max(y1, y2), k))
        )
        if add:
            lst.append(item)
        else:
            lst.remove(item)

    def grid(self):
        H, V = {}, {}
        for k, kind in self.kind.items():
            for s in self.segs(kind, self.E[k]["from"], self.E[k]["to"]):
                self.put(H, V, s, k)
        return H, V

    def shares(self, k, k2):
        """Two lines from one step (a trunk) or into one step (a stem) may meet."""
        a, b = self.E[k], self.E[k2]
        return a["from"] == b["from"] or a["to"] == b["to"]

    def pins(self, a, b):
        """A channel line's two stems in grid units: (x, "bot" for a step on the line or "top" for one above),
        each set a little toward the way its line heads, as ports() orders them."""
        out = []
        for u, v in ((a, b), (b, a)):
            d = (self.col[v] > self.col[u]) - (self.col[v] < self.col[u])
            out.append((self.col[u] + 0.2 * d, "bot" if self.row[u] == 0 else "top"))
        return out

    @staticmethod
    def lower(P, Q):
        """Channel line P must run lower than Q: a stem rising from the line inside Q's span, or one of Q's stems
        dropping from a row inside P's span."""
        lo, hi = min(x for x, _ in Q), max(x for x, _ in Q)
        plo, phi = min(x for x, _ in P), max(x for x, _ in P)
        return any(w == "bot" and lo < x < hi for x, w in P) or any(
            w == "top" and plo < x < phi for x, w in Q
        )

    def forced(self, P, Q):
        """Two channel lines that each must run lower than the other cross on any tracks, whichever way stems
        sharing a column are ordered."""
        for d in (1e-3, -1e-3):
            p, q = [(x + d, w) for x, w in P], [(x - d, w) for x, w in Q]
            if not (self.lower(p, q) and self.lower(q, p)):
                return False
        return True

    def conflicts(self, sg, k, H, V, kind=None):
        """10 for each crossing with a line already drawn, in the channel too; 40 for a stretch run along another
        line (8 in a gap between columns, 3 on a step's own top or bottom, where stems stand apart)."""
        cost = 0
        if kind == "ch":
            e = self.E[k]
            P = self.pins(e["from"], e["to"])
            for k2, kind2 in self.kind.items():
                if kind2 == "ch" and k2 != k and not self.shares(k, k2):
                    f = self.E[k2]
                    cost += 10 if self.forced(P, self.pins(f["from"], f["to"])) else 0
        for x1, y1, x2, y2 in sg:
            if y1 == y2:
                lo, hi = min(x1, x2), max(x1, x2)
                for x, vs in V.items():
                    if lo < x < hi:
                        cost += sum(10 for v1, v2, k2 in vs if v1 < y1 < v2 and not self.shares(k, k2))
                if y1 != 0.5:
                    cost += sum(
                        40
                        for h1, h2, k2 in H.get(y1, ())
                        if min(hi, h2) > max(lo, h1) and not self.shares(k, k2)
                    )
            else:
                lo, hi = min(y1, y2), max(y1, y2)
                for y, hs in H.items():
                    if lo < y < hi:
                        cost += sum(10 for h1, h2, k2 in hs if h1 < x1 < h2 and not self.shares(k, k2))
                for v1, v2, k2 in V.get(x1, ()):
                    if min(hi, v2) > max(lo, v1) and not self.shares(k, k2):
                        e, f = self.E[k], self.E[k2]
                        cost += (
                            8 if x1 != int(x1) else 3 if {e["from"], e["to"]} & {f["from"], f["to"]} else 40
                        )
        return cost

    def blocked(self, c, r, H, V):
        """A line already drawn passes the cell, or runs through the label a step there would have."""
        if any(x1 <= c <= x2 for x1, x2, _ in H.get(r, ())):
            return True
        return any(y1 <= r <= y2 or (y2 > r and y1 < r + 1) for y1, y2, _ in V.get(c, ()))

    def link_cost(self, nid, H, V, hard):
        total, kinds, added = 0, {}, []
        ok_all = True
        for k in self.links[nid]:
            e = self.E[k]
            a, b = e["from"], e["to"]
            if (b if a == nid else a) not in self.row or k in kinds or k in self.kind:
                continue
            best = None
            for kind in self.kinds_for(a, b):
                sg = self.segs(kind, a, b)
                ok = self.clear(sg, a, b)
                if not ok and hard:
                    continue
                c = self.kcost(kind, a, b) + self.conflicts(sg, k, H, V, kind) + (0 if ok else 1000)
                if best is None or c < best[0]:
                    best = (c, kind, sg)
            if best is None:
                ok_all = False
                break
            total += best[0]
            kinds[k] = best[1]
            for s in best[2]:
                self.put(H, V, s, k)
                added.append((s, k))
        for s, k in added:
            self.put(H, V, s, k, add=False)
        return (total, kinds) if ok_all else None

    def best_cell(self, nid, prefs, lo, cells, H, V, hard=True):
        """The cheapest of the cells (c, r) for the step: its lines' cost, 2 a row up, 1 a column from its first
        choices, 40 a column left of the step before it (a last resort: its line would run backwards), and 5 when
        another step with AI items is in the column (their squares would share a place in the AI lane)."""
        best = None
        for c, r in cells:
            if (c, r) in self.cell or r < 1:
                continue
            pen = 0
            if self.blocked(c, r, H, V):
                if hard:
                    continue
                pen = 1000
            self.col[nid], self.row[nid] = c, r
            self.cell[(c, r)] = nid
            got = self.link_cost(nid, H, V, hard)
            del self.cell[(c, r)]
            if got is None:
                continue
            d = min(abs(c - p) for p in prefs)
            cost = got[0] + pen + 2 * (r - 1) + d + (40 * (lo - c) if c < lo else 0)
            if nid in self.ai and any(self.cell.get((c, x)) in self.ai for x in range(FMAXROW + 1)):
                cost += 5
            key = (cost, r, d, c)
            if best is None or key < best[0]:
                best = (key, c, r, got[1])
        self.col.pop(nid, None)
        self.row.pop(nid, None)
        return best

    @staticmethod
    def cells(cols):
        return [(c, r) for c in cols for r in range(1, FMAXROW + 1)]

    def shift(self, p, d):
        """Open (d = 1) or close (d = -1) the column p."""
        for nid, c in list(self.col.items()):
            if c >= p + (1 if d < 0 else 0):
                self.col[nid] = c + d
        self.cell = {(self.col[n], self.row[n]): n for n in self.col}
        self.ncols += d

    def choices(self, preds, succs, board):
        """A step's first choices of column: just above the step it branches from, else one column after the step
        before it, else its board column; and the column of the step before it (lo)."""
        mp = [self.col[p] for p in preds if self.row.get(p) == 0]
        op = [self.col[p] for p in preds if self.row.get(p, 0) > 0]
        ms = [self.col[s] for s in succs if self.row.get(s) == 0]
        lo = max([c + 1 for c in op] + mp + [0])
        hi = max(lo, min([board] + ms))
        prefs = []
        for c in ([max(mp)] if mp else []) + ([max(op) + 1] if op else []) + [board]:
            c = min(max(c, lo), hi)
            if c not in prefs:
                prefs.append(c)
        return prefs, lo, hi

    def place(self, nid, preds, succs, board):
        """The cheapest clear cell near the first choices; a new column at the first choice, costing 8 more, is
        weighed against it; a cell further away comes last."""
        prefs, lo, hi = self.choices(preds, succs, board)
        H, V = self.grid()
        near = self.cells(
            c for c in range(self.ncols) if lo <= c <= hi + 2
        )  # never left of the step before it
        best, opened = self.best_cell(nid, prefs, lo, near, H, V), None
        if best is None or best[0][0] >= 10:  # a new column for the step
            for p in sorted(range(lo, min(hi + 1, self.ncols) + 1), key=lambda c: (abs(c - prefs[0]), c))[:3]:
                self.shift(p, 1)
                got = self.best_cell(nid, [p], p, self.cells([p]), *self.grid())
                self.shift(p, -1)
                if got and (best is None or got[0][0] + 8 < best[0][0]):
                    best, opened = got, p
        if best is None:
            best = self.best_cell(nid, prefs, lo, self.cells(range(self.ncols)), H, V)
        if best is None:  # none is clear: the least bad, which check() reports
            best = self.best_cell(nid, prefs, lo, self.cells(range(self.ncols)), H, V, hard=False)
        if opened is not None:
            self.shift(opened, 1)
        _, c, r, kinds = best
        self.col[nid], self.row[nid] = c, r
        self.cell[(c, r)] = nid
        self.kind.update(kinds)

    def lift(self, nid):
        own = {k: self.kind.pop(k) for k in self.links[nid] if k in self.kind}
        c, r = self.col.pop(nid), self.row.pop(nid)
        del self.cell[(c, r)]
        return c, r, own

    def drop(self, nid, c, r, kinds):
        self.col[nid], self.row[nid] = c, r
        self.cell[(c, r)] = nid
        self.kind.update(kinds)

    def cost_at(self, nid, cells, ctx):
        """The cheapest of the cells for the lifted step nid, as things stand."""
        prefs, lo, _ = self.choices(*(x[nid] for x in ctx))
        return self.best_cell(nid, prefs, lo, cells, *self.grid())

    def around(self, nid, ctx):
        _, lo, hi = self.choices(*(x[nid] for x in ctx))
        return self.cells(range(lo, min(self.ncols, hi + 3)))

    def improve(self, ctx):
        """Steps are placed in listing order, so a step cannot see the lines of steps placed after it. Three passes
        then move each step off the line to its cheapest cell nearby, now that all its lines are known; a step
        whose lines still cross tries the cell of a neighbour, which moves to its own cheapest cell. Each line is
        then routed again, and columns left empty close up."""
        for _ in range(3):
            for n in self.mm.nodes:
                nid = n.id
                if self.row[nid] == 0:
                    continue
                c0, r0, own = self.lift(nid)
                cur = self.cost_at(nid, [(c0, r0)], ctx)
                best = self.cost_at(nid, self.around(nid, ctx), ctx)
                if best and (cur is None or best[0][0] < cur[0][0]):
                    cur = best
                if cur:
                    self.drop(nid, cur[1], cur[2], cur[3])
                else:
                    self.drop(nid, c0, r0, own)
                if cur is None or cur[0][0] >= 10:
                    self.displace(nid, ctx)
        for k in sorted(self.kind):
            e = self.E[k]
            a, b = e["from"], e["to"]
            if self.row[a] == 0 and self.row[b] == 0:
                continue
            old = self.kind.pop(k)
            H, V = self.grid()
            opts = [
                (self.kcost(kind, a, b) + self.conflicts(self.segs(kind, a, b), k, H, V, kind), i, kind)
                for i, kind in enumerate(self.kinds_for(a, b))
                if self.clear(self.segs(kind, a, b), a, b)
            ]
            self.kind[k] = min(opts)[2] if opts else old
        for c in range(self.ncols - 1, -1, -1):
            if all(x != c for x in self.col.values()):
                self.shift(c, -1)

    def displace(self, nid, ctx):
        c0, r0, own = self.lift(nid)
        cn = self.cost_at(nid, [(c0, r0)], ctx)
        self.drop(nid, c0, r0, cn[3] if cn else own)
        old_n = cn[0][0] if cn else 1e6
        best = None
        for c, r in self.around(nid, ctx):
            m = self.cell.get((c, r))
            if not m or m == nid:
                continue
            _, _, own_m = self.lift(m)
            cm = self.cost_at(m, [(c, r)], ctx)
            self.drop(m, c, r, cm[3] if cm else own_m)
            old = old_n + (cm[0][0] if cm else 1e6)
            _, _, keep_n = self.lift(nid)
            _, _, keep_m = self.lift(m)
            got_n = self.cost_at(nid, [(c, r)], ctx)
            if got_n:
                self.drop(nid, c, r, got_n[3])
                got_m = self.cost_at(m, self.around(m, ctx), ctx)
                self.lift(nid)
                if (
                    got_m
                    and got_n[0][0] + got_m[0][0] < old - 1
                    and (best is None or got_n[0][0] + got_m[0][0] - old < best[0])
                ):
                    best = (got_n[0][0] + got_m[0][0] - old, m, (c, r, got_n[3]), got_m[1:])
            self.drop(nid, c0, r0, keep_n)
            self.drop(m, c, r, keep_m)
        if best:
            _, m, (c, r, kn), (cm, rm, km) = best
            self.lift(nid)
            self.lift(m)
            self.drop(nid, c, r, kn)
            self.drop(m, cm, rm, km)

    # -- geometry, in units
    def geometry(self):
        self.ports()
        self.tracks()
        self.gutters()
        self.layout_y()
        self.text()
        self.paths = [self.path(k) for k in range(len(self.E))]
        self.branches()
        self.check()

    def X(self, x):
        return FM + FP / 2 + FP * x

    def ny(self, nid):
        return self.y_row[self.row[nid]]

    def side(self, nid):
        return FD if self.mm.N[nid].dec else FR

    def rim(self, nid, dx):
        """How far above or below its centre a stem dx off the centre meets a step's outline."""
        if self.mm.N[nid].dec:
            return max(FD - abs(dx), 1.0)
        return max(FR * FR - dx * dx, 1.0) ** 0.5

    def ports(self):
        """The stems in each column's part of the channel: on the top of the step on the line and the bottom of the
        lowest step above it. Lines that leave a step heading the same way share one stem, and so do lines that
        enter it from the same side; stems stand 12 apart, in the order (order()) that leaves the fewest crossings.
        A line straight between the two steps keeps the centre."""
        self.pinx, self.unit, self.full = {}, {}, {}
        uid = 0
        for c in range(self.ncols):
            M = self.cell.get((c, 0))
            U = next((self.cell[(c, r)] for r in range(1, FMAXROW + 1) if (c, r) in self.cell), None)
            groups, vert = {}, None
            for k in sorted(self.kind):
                kind, e = self.kind[k], self.E[k]
                for nid, d in ((e["from"], "out"), (e["to"], "in")):
                    if nid is None:
                        continue
                    if nid == M and (kind in ("ch", "vert") or (kind, d) in (("up", "out"), ("down", "in"))):
                        groups.setdefault((M, d), []).append(k)
                    elif nid == U and kind in ("ch", "vert"):
                        groups.setdefault((U, d), []).append(k)
                if kind == "vert" and self.col[e["from"]] == c:
                    vert = k
            units = []
            # one stem for the lines that head left, one for those heading right; a feedback line never shares a
            # stem (or so a track) with a forward line, so dashes never run over a solid line
            for (nid, _d), ks in groups.items():
                side = {}
                for k in ks:
                    e = self.E[k]
                    other = e["to"] if e["from"] == nid else e["from"]
                    fb = self.ix[e["to"]] < self.ix[e["from"]]
                    side.setdefault(((self.col[other] > c) - (self.col[other] < c), fb), []).append(k)
                for fb in (
                    False,
                    True,
                ):  # a straight line shares the stem of the lines heading right, else left
                    if (0, fb) in side:
                        to = 1 if (1, fb) in side or (-1, fb) not in side else -1
                        side.setdefault((to, fb), []).extend(side.pop((0, fb)))
                units += [
                    {"ks": sorted(v), "mem": [(k, nid) for k in sorted(v)], "anchor": False}
                    for _, v in sorted(side.items())
                ]
            if vert is not None:
                um = next(u for u in units if (vert, M) in u["mem"])
                uu = next(u for u in units if (vert, U) in u["mem"])
                if um["ks"] == [vert] or uu["ks"] == [vert]:
                    um["mem"] += uu["mem"]
                    um["ks"] = sorted(set(um["ks"] + uu["ks"]))
                    units.remove(uu)
                else:
                    uu["ks"].remove(vert)
                    uu["mem"].remove((vert, U))
                    um["mem"].append((vert, U))
                um["anchor"] = True
            units = self.order(units, c)
            pos = self.positions(units)
            for u, p in zip(units, pos, strict=True):
                uid += 1
                self.full[uid] = any(self.kind[k] in ("vert", "up", "down") for k in u["ks"])
                for k, nid in u["mem"]:
                    self.pinx[(k, nid)] = p
                    self.unit[(k, nid)] = uid

    def positions(self, units):
        """Stem offsets, 12 apart, the straight line's at the centre; squeezed to ±12 so each meets its step."""
        n = len(units)
        v = next((i for i, u in enumerate(units) if u["anchor"]), None)
        pos = [(i - v) * FTRACK if v is not None else (i - (n - 1) / 2) * FTRACK for i in range(n)]
        far = max([abs(p) for p in pos] + [12])
        return [p * 12 / far for p in pos]

    def order(self, units, c):
        """The left-to-right order of a column's stems that leaves the fewest crossings in the channel: no line
        through a stem that runs the whole channel, and no two lines that each need the lower track; ties keep
        the stems in the order their lines head."""
        x0 = self.X(c)

        def heading(u):
            dx = []
            for k, nid in u["mem"]:
                e = self.E[k]
                other = e["to"] if e["from"] == nid else e["from"]
                dx.append(0 if self.kind[k] == "vert" else self.X(self.col[other]) - x0)
            return sum(dx) / len(dx)

        units.sort(key=lambda u: (heading(u), min(u["ks"])))
        if len(units) < 2:
            return units
        best = None
        for perm in itertools.permutations(range(len(units))):
            us = [units[i] for i in perm]
            pos = self.positions(us)
            nets, trunks = [], []
            for u, p in zip(us, pos, strict=True):
                full = any(self.kind[k] in ("vert", "up", "down") for k in u["ks"])
                if full:
                    trunks.append(x0 + p)
                pins = {}
                for k, nid in u["mem"]:
                    if self.kind[k] == "ch":
                        e = self.E[k]
                        o = e["to"] if e["from"] == nid else e["from"]
                        pins[x0 + p] = ("bot" if self.row[nid] == 0 else "top", full)
                        pins.setdefault(self.X(self.col[o]), ("bot" if self.row[o] == 0 else "top", False))
                if pins:
                    nets.append(pins)

            def lower(P, Q):  # P must run lower than Q
                return any(
                    not f and min(Q) + 0.5 < x < max(Q) - 0.5 and w == "bot" for x, (w, f) in P.items()
                ) or any(not f and min(P) + 0.5 < x < max(P) - 0.5 and w == "top" for x, (w, f) in Q.items())

            cost = sum(10 for P in nets for x in trunks if x not in P and min(P) + 0.5 < x < max(P) - 0.5)
            cost += sum(10 for i, P in enumerate(nets) for Q in nets[i + 1 :] if lower(P, Q) and lower(Q, P))
            v = next((j for j, u in enumerate(us) if u["anchor"]), None)
            reach = max(abs(i - v) for i in range(len(us))) if v is not None else (len(us) - 1) / 2
            cost += 3 if reach * FTRACK > 12 else 0  # squeezed closer than 12
            key = (
                cost,
                sum(1 for i in range(len(perm)) for j in range(i + 1, len(perm)) if perm[i] > perm[j]),
            )
            if best is None or key < best[0]:
                best = (key, us)
        return best[1]

    def tracks(self):
        """Lines through the channel. Lines that share a stem share a track (a trunk with branches, or branches into
        a stem). A line whose stem rises from the line inside another's span takes a lower track, and one whose
        stem drops from a row inside it a higher one, so neither crosses the other; tracks are 12 apart."""
        chs = sorted(k for k, kind in self.kind.items() if kind == "ch")
        nets, seen = [], set()
        for end in ("from", "to"):
            by = {}
            for k in chs:
                if k not in seen:
                    by.setdefault(self.unit.get((k, self.E[k][end]), (k, end)), []).append(k)
            for ks in sorted(by.values()):
                if len(ks) > 1:
                    nets.append(ks)
                    seen.update(ks)
        nets += [[k] for k in chs if k not in seen]
        info = []
        for ks in nets:
            pins = {}
            for k in ks:
                for nid in (self.E[k]["from"], self.E[k]["to"]):
                    x = self.X(self.col[nid]) + self.pinx.get((k, nid), 0)
                    pins[x] = (
                        "bot" if self.row[nid] == 0 else "top",
                        self.full.get(self.unit.get((k, nid)), False),
                    )
            info.append({"ks": ks, "pins": pins, "lo": min(pins), "hi": max(pins)})
        n = len(info)
        below = {i: set() for i in range(n)}  # below[i]: the nets that must run lower than net i
        for i, P in enumerate(info):
            for j, Q in enumerate(info):
                if i != j:
                    for x, (where, full) in P["pins"].items():
                        if not full and Q["lo"] + 0.5 < x < Q["hi"] - 0.5:
                            (below[j] if where == "bot" else below[i]).add(j if where == "top" else i)
        for i in range(n):
            below[i].discard(i)
        order, done = [], set()

        def span(i):
            return (info[i]["hi"] - info[i]["lo"], info[i]["lo"], i)

        while len(order) < n:
            ready = [i for i in range(n) if i not in done and not (below[i] - done)]
            if (
                not ready
            ):  # lines that must cross: break the cycle at the net with the fewest constraints left
                ready = [
                    min(
                        (i for i in range(n) if i not in done),
                        key=lambda i: (len(below[i] - done),) + span(i),
                    )
                ]
            i = min(ready, key=span)
            order.append(i)
            done.add(i)
        rows, self.track = [], {}
        for i in order:
            P = info[i]
            t = max(
                [self.track[info[j]["ks"][0]] + 1 for j in below[i] if info[j]["ks"][0] in self.track] + [0]
            )
            while True:
                while len(rows) <= t:
                    rows.append([])
                if all(P["lo"] > Q["hi"] + FTRACK or P["hi"] < Q["lo"] - FTRACK for Q in rows[t]):
                    break
                t += 1
            rows[t].append(P)
            for k in P["ks"]:
                self.track[k] = t
        self.ntracks = len(rows)

    def gutters(self):
        """Lines that turn in the gap beside a column: lines from one side of a step share one stem, and so do lines
        into one side, but a feedback line never shares with a forward one; others whose stretches would meet in
        the gap stand 12 apart."""
        self.gx = {}
        by_g = {}
        for k in sorted(self.kind):
            if self.kind[k] in ("gapl", "gapr"):
                b = self.E[k]["to"]
                by_g.setdefault(self.col[b] + (-0.5 if self.kind[k] == "gapl" else 0.5), []).append(k)
        for g, ks in sorted(by_g.items()):
            nets, seen = [], set()
            for end in ("from", "to"):
                by = {}
                for k in ks:
                    if k not in seen:
                        fb = self.ix[self.E[k]["to"]] < self.ix[self.E[k]["from"]]
                        by.setdefault((self.E[k][end], fb), []).append(k)
                for grp in sorted(by.values()):
                    if len(grp) > 1:
                        nets.append(grp)
                        seen.update(grp)
            nets += [[k] for k in ks if k not in seen]
            spans = []
            for net in nets:
                rs = [self.row[self.E[k][end]] for k in net for end in ("from", "to")]
                spans.append((min(rs), max(rs), net))
            colour = []
            lanes = []
            for lo, hi, net in sorted(spans, key=lambda s: (s[0], s[1], s[2])):
                j = next(
                    (j for j, track in enumerate(lanes) if all(hi < a or lo > b for a, b in track)), None
                )
                if j is None:
                    lanes.append([])
                    j = len(lanes) - 1
                lanes[j].append((lo, hi))
                colour.append((j, net))
            m = len(lanes)
            for j, net in colour:
                for k in net:
                    self.gx[k] = self.X(g) + (j - (m - 1) / 2) * FTRACK

    def layout_y(self):
        """Vertical positions: the stage brackets, the rows above (each a label over a step), the channel, the
        line and its labels."""
        self.y_stage = 22
        lab = 3 * 14 + 16  # up to three title lines and the id line
        top = 44 + lab + FR
        self.y_row = {r: top + FROW * (self.nrows - r) for r in range(1, self.nrows + 1)}
        ch_top = (self.y_row[1] + FR) if self.nrows else 44
        self.y_main = ch_top + 24 + FTRACK * max(self.ntracks - 1, 0) + FR
        self.y_row[0] = self.y_main
        self.y_lab = self.y_main + FR + 16
        self.h = self.y_lab + lab + 6

    def track_y(self, t):
        return self.y_main - FR - 12 - FTRACK * t

    def text(self):
        """Each step's title (up to three lines, the marker after the last), its id line and its badges, with the
        box each takes."""
        mm = self.mm
        self.lab, self.boxes = {}, []
        gaps = [(gx, self.ny(self.E[k]["from"]), self.ny(self.E[k]["to"])) for k, gx in self.gx.items()]
        for n in mm.nodes:
            x, y = self.X(self.col[n.id]), self.ny(n.id)
            # how far the label may reach either side: 4 units short of the next column, and 6 short of a line
            # turning in the gap beside it
            reach = FP / 2 - 4
            if self.row[n.id]:
                for gx, ya, yb in gaps:
                    if min(ya, yb) < y - FR and max(ya, yb) > y - 80:
                        reach = min(reach, abs(gx - x) - 6)
            e = mm.point(n.id)
            mw = tw(str(e["n"]), 9, True) + 2 if e else 0
            lines, _ = wrap_bal(n.d["title"], 11.5, True, min(FLAB, 2 * reach), 3)
            if (
                tw(lines[-1], 11.5, True) / 2 + mw > reach
            ):  # the marker would reach too far: narrow the measure
                narrow, cut = wrap_bal(n.d["title"], 11.5, True, 2 * (reach - mw), 3)
                if not cut:
                    lines = narrow
            sub = fit(f"{n.id} · {flow_who(n)}", 10, False, 2 * reach)
            if self.row[n.id] == 0:
                y0 = self.y_lab
                ys = y0 + 14 * len(lines) - 1
            else:
                ys = y - FR - 11
                y0 = ys - 13 - 14 * (len(lines) - 1)
            boxes = [
                (x - tw(ln, 11.5, True) / 2, y0 + 14 * i - 10, x + tw(ln, 11.5, True) / 2, y0 + 14 * i + 3)
                for i, ln in enumerate(lines)
            ]
            sw = tw(sub, 10)
            boxes.append((x - sw / 2, ys - 8, x + sw / 2, ys + 2.5))
            if e:
                mx = x + tw(lines[-1], 11.5, True) / 2 + 2
                boxes.append(
                    (
                        mx - 1,
                        y0 + 14 * (len(lines) - 1) - 4.4 - 8,
                        mx + mw,
                        y0 + 14 * (len(lines) - 1) - 4.4 + 1,
                    )
                )
            # badges at the top right, clear of any stem on the step's top
            right = max([p for (k, nid), p in self.pinx.items() if nid == n.id and self.row[nid] == 0] + [0])
            bx0 = x + max(FR + 2, right + 9) if right > 0 else x + FR + 2
            badges = []
            for j, b in enumerate(mm.badge[n.id][:3]):
                bx, by = bx0 + 15 * j, y - FR - 1
                badges.append((b, bx, by))
                boxes.append((bx - 6.5, by - 6.5, bx + 6.5, by + 6.5))
            self.lab[n.id] = (lines, y0, sub, ys, e, badges)
            self.boxes += [(n.id, b) for b in boxes]

    def path(self, k):
        e = self.E[k]
        a, b, kind = e["from"], e["to"], self.kind[k]
        xa, ya, xb, yb = self.X(self.col[a]), self.ny(a), self.X(self.col[b]), self.ny(b)
        tip = 1  # the gap before an arrow's tip
        if kind == "row":
            s = 1 if xb > xa else -1
            # a line back between the same two steps runs 4 below, the forward one 4 above: never one on the other
            two = any(
                self.kind.get(j) == "row" and (f["from"], f["to"]) == (b, a) for j, f in enumerate(self.E)
            )
            dy = (4 if self.ix[b] < self.ix[a] else -4) if two else 0
            pts = [(xa + s * self.rim(a, dy), ya + dy), (xb - s * (self.rim(b, dy) + tip), yb + dy)]
        elif kind == "vert":
            x = xa + self.pinx[(k, a)]
            dn = 1 if yb > ya else -1
            pts = [(x, ya + dn * self.rim(a, x - xa)), (x, yb - dn * (self.rim(b, x - xb) + tip))]
        elif kind == "up":
            x = xa + self.pinx[(k, a)]
            s = 1 if xb > x else -1
            pts = [(x, ya - self.rim(a, x - xa)), (x, yb), (xb - s * (self.side(b) + tip), yb)]
        elif kind == "down":
            x = xb + self.pinx[(k, b)]
            s = 1 if x > xa else -1
            pts = [(xa + s * self.side(a), ya), (x, ya), (x, yb - self.rim(b, x - xb) - tip)]
        elif kind == "ch":
            ty = self.track_y(self.track[k])
            pa, pb = xa + self.pinx.get((k, a), 0), xb + self.pinx.get((k, b), 0)
            sa = ya - self.rim(a, pa - xa) if self.row[a] == 0 else ya + self.rim(a, pa - xa)
            sb = yb - self.rim(b, pb - xb) - tip if self.row[b] == 0 else yb + self.rim(b, pb - xb) + tip
            pts = [(pa, sa), (pa, ty), (pb, ty), (pb, sb)]
        else:
            gx = self.gx[k]
            sa, sb = (1 if gx > xa else -1), (1 if xb > gx else -1)

            def beside(
                nid, x
            ):  # a forward line in a gap on the same side of the step: a feedback line keeps 4 below
                return self.ix[b] < self.ix[a] and any(
                    j != k
                    and self.kind.get(j) in ("gapl", "gapr")
                    and self.ix[f["to"]] > self.ix[f["from"]]
                    and nid in (f["from"], f["to"])
                    and (self.gx[j] > x) == (gx > x)
                    for j, f in enumerate(self.E)
                )

            da, db = (4 if beside(a, xa) else 0), (4 if beside(b, xb) else 0)
            pts = [
                (xa + sa * self.rim(a, da), ya + da),
                (gx, ya + da),
                (gx, yb + db),
                (xb - sb * (self.rim(b, db) + tip), yb + db),
            ]
        return {
            "e": e,
            "k": k,
            "a": a,
            "b": b,
            "kind": kind,
            "fb": self.ix[b] < self.ix[a],
            "pts": simplify(pts),
        }

    def free(self, box, extra=()):
        if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for _, b in self.boxes):
            return False
        if any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in extra):
            return False
        for n in self.mm.nodes:
            x, y, r = self.X(self.col[n.id]), self.ny(n.id), self.side(n.id) + 2
            if box[0] < x + r and x - r < box[2] and box[1] < y + r and y - r < box[3]:
                return False
        return not any(
            seg_in_box(x1, y1, x2, y2, box, 0)
            for p in self.paths
            for (x1, y1), (x2, y2) in itertools.pairwise(p["pts"])
        )

    def branches(self):
        """A branch label beside the first stretch of its line where it meets nothing: near the start, then half,
        a quarter and three quarters of the way, above or below a level stretch, right or left of an upright one;
        then the next stretches."""
        self.blabels, placed = {}, []
        for p in self.paths:
            e = p["e"]
            if e.get("kind") != "conditional" or not e.get("label"):
                continue
            label = e["label"]
            w = tw(label, 10, True)
            cands = []
            for (x0, y0), (x1, y1) in itertools.pairwise(p["pts"]):
                if y0 == y1:
                    s = 1 if x1 > x0 else -1
                    for bx in [x0 + 8 if s > 0 else x0 - 8 - w] + [
                        x0 + (x1 - x0) * f - w / 2 for f in (0.5, 0.25, 0.75)
                    ]:
                        cands += [(bx, y0 - 5), (bx, y0 + 13)]
                else:
                    s = 1 if y1 > y0 else -1
                    for by in [y0 + s * 12 + (8 if s > 0 else 0)] + [
                        y0 + (y1 - y0) * f + 3.5 for f in (0.5, 0.25, 0.75)
                    ]:
                        cands += [(x0 + 5, by), (x0 - 5 - w, by)]
            for lx, ly in cands:
                box = (lx - 2, ly - 9, lx + w + 2, ly + 2.5)
                if self.free(box, placed):
                    break
            else:
                lx, ly = cands[0]
                box = (lx - 2, ly - 9, lx + w + 2, ly + 2.5)
                warn(
                    f"build-6 {self.mm.where} (the Flow): the branch label “{label}” of {p['a']} -> {p['b']} has no free place beside its line"
                )
            placed.append(box)
            self.blabels[p["k"]] = (lx, ly, label, box)

    def check(self):
        """build-6 for the Flow: no line through a step or a label (an error); two lines that cross, or run side by
        side closer than 12 units, are a warning naming both."""
        mm = self.mm
        segs = [
            (x1, y1, x2, y2, p) for p in self.paths for (x1, y1), (x2, y2) in itertools.pairwise(p["pts"])
        ]

        def name(p):
            return f"{p['a']} -> {p['b']}"

        errors, cross, close = [], [], []
        for x1, y1, x2, y2, p in segs:
            for n in mm.nodes:
                if n.id in (p["a"], p["b"]):
                    continue
                cx, cy, r = self.X(self.col[n.id]), self.ny(n.id), self.side(n.id) + 1.5
                qx, qy = min(max(cx, min(x1, x2)), max(x1, x2)), min(max(cy, min(y1, y2)), max(y1, y2))
                if (qx - cx) ** 2 + (qy - cy) ** 2 < r * r:
                    errors.append(f"the line {name(p)} crosses the step {n.id}")
            for nid, box in self.boxes:
                if seg_in_box(x1, y1, x2, y2, box):
                    errors.append(f"the line {name(p)} crosses the label of {nid}")
            for _, _, label, box in self.blabels.values():
                if seg_in_box(x1, y1, x2, y2, box, 1):
                    warn(
                        f"build-6 {mm.where} (the Flow): the line {name(p)} runs over the branch label “{label}”"
                    )
        for i, s in enumerate(segs):
            for t in segs[i + 1 :]:
                p, q = s[4], t[4]
                if p is q or p["a"] == q["a"] or p["b"] == q["b"] or (p["a"], p["b"]) == (q["b"], q["a"]):
                    continue
                hs, ht = s[1] == s[3], t[1] == t[3]
                if hs != ht:
                    h, v = (s, t) if hs else (t, s)
                    if (
                        min(h[0], h[2]) + 0.5 < v[0] < max(h[0], h[2]) - 0.5
                        and min(v[1], v[3]) + 0.5 < h[1] < max(v[1], v[3]) - 0.5
                    ):
                        cross.append(f"{name(p)} and {name(q)}")
                else:
                    o = 0 if hs else 1  # the axis the two stretches run along
                    gap = abs(s[1 - o] - t[1 - o])
                    run = min(max(s[o], s[o + 2]), max(t[o], t[o + 2])) - max(
                        min(s[o], s[o + 2]), min(t[o], t[o + 2])
                    )
                    if run > 4 and gap < FTRACK - 0.5:
                        close.append(f"{name(p)} and {name(q)}")
        if errors:
            raise DataError(
                "\n".join(
                    f"build-6 {mm.where} (the Flow): {m} -> set col on a step to open a column, or "
                    f"reorder the nodes"
                    for m in dict.fromkeys(errors)
                )
            )
        for e in self.E:  # a forward line reads left to right
            if self.ix[e["to"]] > self.ix[e["from"]] and self.col[e["to"]] < self.col[e["from"]]:
                warn(
                    f"build-6 {mm.where} (the Flow): {e['to']} sits left of {e['from']}, the step before it "
                    f"-> set col on {e['to']} so it sits at or right of {e['from']}"
                )
        for c in dict.fromkeys(cross):
            warn(f"build-6 {mm.where} (the Flow): the lines {c} cross")
        for c in dict.fromkeys(close):
            warn(f"build-6 {mm.where} (the Flow): the lines {c} run side by side closer than {FTRACK} units")

    # -- drawing
    def node_svg(self, n):
        x, y = self.X(self.col[n.id]), self.ny(n.id)
        st = n.state
        if n.dec:
            h = FR * 0.65
            shape = (
                f'<rect class="pm-fl-dec is-{st}" x="{num(x - h)}" y="{num(y - h)}" width="{num(2 * h)}" height="{num(2 * h)}" '
                f'rx="1.5" transform="rotate(45 {num(x)} {num(y)})"/>'
            )
        else:
            shape = (
                f'<circle class="pm-fl-step is-{st}" cx="{num(x)}" cy="{num(y)}" r="{FR}"/>'
                f'<text class="pm-fl-num" x="{num(x)}" y="{num(y + 3.4)}">{self.num[n.id]:02d}</text>'
            )
        badges = ""
        for (kind, i, cid, _t), bx, by in self.lab[n.id][5]:
            word = "Gap" if kind == "gap" else "Clarification"
            badges += (
                f'<a class="pm-fl-badge-link" href="#{self.mm.pre}{cid}" aria-label="{word} {i}"><g class="pm-fl-badge is-{kind}">'
                f'<circle cx="{num(bx)}" cy="{num(by)}" r="6.5"/><text x="{num(bx)}" y="{num(by + 3)}">{i}</text></g></a>'
            )
        return (
            f'<g class="pm-fl-node is-{st}" id="{self.mm.pre}fl-{n.id}" data-node="{n.id}"><title>{esc(n.id + " " + n.d["title"])}</title>'
            f"{shape}{badges}</g>"
        )

    def label_svg(self, n):
        """Title with the marker after it, then the id with the owner: under a step on the line, over a step above."""
        x = self.X(self.col[n.id])
        lines, y0, sub, ys, e, _ = self.lab[n.id]
        s = text_lines("pm-fl-title", x, y0, lines, 14)
        s += title_marker(e, lines, x, y0, 14, 11.5)
        return (
            s + f'<text class="pm-fl-sub" x="{num(x)}" y="{num(ys)}" text-anchor="middle">{esc(sub)}</text>'
        )

    def edge_svg(self, p):
        pts = p["pts"]
        cls = "pm-fl-line" + (" is-feedback" if p["fb"] else "")
        s = (
            f'<g class="pm-fl-edge" data-from="{p["a"]}" data-to="{p["b"]}"><path class="{cls}" d="{path_d(pts)}"/>'
            f"{arrow(pts[-2], pts[-1]).replace('pm-arrow', 'pm-fl-arrow')}"
        )
        if p["k"] in self.blabels:
            lx, ly, label, _ = self.blabels[p["k"]]
            s += f'<text class="pm-fl-branch" x="{num(lx)}" y="{num(ly)}">{esc(label)}</text>'
        return s + "</g>"

    def stages_svg(self):
        mm = self.mm
        if not mm.band:
            return ""
        spans = []
        for g in mm.groups:
            xs = [
                self.X(self.col[n.id])
                for n in mm.nodes
                if n.d.get("group") == g["id"] and self.row[n.id] == 0
            ] or [self.X(self.col[n.id]) for n in mm.nodes if n.d.get("group") == g["id"]]
            spans.append([g, min(xs) - FP / 2 + 6, max(xs) + FP / 2 - 6])
        for i in range(1, len(spans)):  # neighbours never overlap: meet half way
            if spans[i][1] < spans[i - 1][2] + 12:
                mid = (spans[i][1] + spans[i - 1][2]) / 2
                spans[i - 1][2], spans[i][1] = mid - 6, mid + 6
        s = ""
        for g, x0, x1 in spans:
            if x1 - x0 < 24:
                continue
            label = fit(f"{g['id']} {g['label']}", 11, True, x1 - x0 - 4)
            s += (
                f'<g class="pm-fl-stage"><text x="{num(x0)}" y="{self.y_stage}">{esc(label)}</text>'
                f'<path d="M {num(x0)} {self.y_stage + 13} V {self.y_stage + 7} H {num(x1)} V {self.y_stage + 13}"/></g>'
            )
        return s

    def lane_items(self):
        """The AI lane's tracks: (item, x0, x1, its squares as (x, step number to print or None), caption words).
        Items on steps read left to right like a staircase; whole-view items follow, then all-views items. A
        square under a step off the line prints that step's number when another step in its column has AI items,
        so it never reads as the line's step."""
        mm, am = self.mm, self.am
        out = []
        for it in am.items:
            g = it.get("groups", [])
            if g == "all":
                out.append((2, FM, it, FM + 8, self.W - FM, [(FM + 8, None)], "every step"))
                continue
            ids = list(it.get("nodes", [])) + [n.id for n in mm.nodes if n.d.get("group") in g and not n.dec]
            sq = {}
            for nid in ids:
                shared = any(m != nid and m in am.by_node and self.col[m] == self.col[nid] for m in self.col)
                tag = self.num[nid] if self.row[nid] and shared and not g else None
                sq.setdefault(self.X(self.col[nid]), tag)
            xs = sorted(sq.items())
            word = (
                ("whole view: " + ", ".join(mm.groups[mm.group_ix[gid]]["label"] for gid in g)) if g else ""
            )
            out.append((1 if g else 0, xs[0][0], it, xs[0][0], xs[-1][0], xs, word))
        out.sort(key=lambda t: (t[0], t[1], t[2]["id"]))
        return [t[2:] for t in out]

    def ai_svg(self, y0):
        """One track per item, packed: a track shares a row with earlier ones when its caption and bar fit beside
        theirs. A row with a step number under a square is 10 units taller."""
        s = f'<text class="pm-fl-ai-h" x="{FM}" y="{num(y0)}">AI OPPORTUNITIES · UNDER THE STEPS THEY TOUCH</text>'
        rows, tall = (
            [],
            [],
        )  # per row: the x where the row is next free; whether a square in it prints a number
        placed = []
        for it, x0, x1, xs, word in self.lane_items():
            cap = f"{it['id']} {it['title']}"
            tail = f" · {'named by the client' if it['origin'] == 'named' else 'our suggestion'}" + (
                f" · {word}" if word else ""
            )
            w = tw(cap, 11, True) + tw(tail, 11)
            lx = x0 - SQ / 2 if x0 - SQ / 2 + w <= self.W - FM else max(FM, x1 + SQ / 2 - w)
            lo, hi = min(lx, x0 - SQ / 2), max(lx + w, x1 + SQ / 2)
            r = next((i for i, end in enumerate(rows) if end + 24 <= lo), None)
            if r is None:
                rows.append(hi)
                tall.append(False)
                r = len(rows) - 1
            else:
                rows[r] = hi
            tall[r] = tall[r] or any(t for _, t in xs)
            placed.append((it, x0, x1, xs, cap, tail, lx, r))
        top = [y0 + 22 + sum(52 if t else 42 for t in tall[:r]) for r in range(len(rows) + 1)]
        for it, x0, x1, xs, cap, tail, lx, r in placed:
            y = top[r]
            s += (
                f'<g class="pm-ai-fl-track is-{it["origin"]}" data-ai="{it["id"]}">'
                f'<a href="#{self.mm.pre}{it["id"]}" class="pm-ai-fl-cap"><text x="{num(lx)}" y="{num(y + 13)}"><tspan class="pm-ai-fl-id">{esc(cap)}</tspan>'
                f'<tspan class="pm-ai-fl-tail">{esc(tail)}</tspan></text></a>'
            )
            by = y + 28
            if x1 > x0:
                s += f'<rect class="pm-ai-fl-bar" x="{num(x0)}" y="{num(by - 1)}" width="{num(x1 - x0)}" height="2"/>'
            for x, tag in xs:
                s += self.am.square(it, x, by)
                if tag:
                    s += f'<text class="pm-ai-fl-at" x="{num(x)}" y="{num(by + 19)}">step {tag:02d}</text>'
            s += "</g>"
        return s, top[-1]

    def html(self):
        mm, am = self.mm, self.am
        body = self.stages_svg()
        body += "".join(self.edge_svg(p) for p in self.paths)
        body += "".join(self.node_svg(n) for n in mm.nodes)
        body += "".join(self.label_svg(n) for n in mm.nodes)
        ai, H = self.ai_svg(self.h + 6) if am.items else ("", self.h)
        H += 4
        svg = (
            f'<svg class="pm-fl-svg" viewBox="0 0 {num(self.W)} {num(H)}" width="{num(self.W)}" height="{num(H)}" role="img" '
            f'aria-label="{esc(mm.meta["title"])}: the steps in flow order, with the AI opportunities under the steps they touch">'
            f"{body}{ai}</svg>"
        )
        on = [mm.N[nid] for nid in self.main]
        off = [n for n in mm.nodes if self.row[n.id]]

        def words(ns):
            return steps_words(sum(1 for n in ns if not n.dec), sum(1 for n in ns if n.dec))

        count = (
            f"{words(on)} on the line"
            + (f" · {words(off)} off it, above" if off else "")
            + (
                f" · {plural(len(am.items), 'AI opportunity', 'AI opportunities')} under the steps they touch"
                if am.items
                else ""
            )
        )
        legend = (
            '<div class="pm-fl-legend" aria-label="Key">'
            '<span><i class="pm-fl-k-step"></i>Step</span><span><i class="pm-fl-k-dec"></i>Decision</span>'
            '<span><i class="pm-fl-k-flow"></i>Flow</span><span><i class="pm-fl-k-feed"></i>Feedback</span>'
            '<span><i class="pm-fl-k-dash"></i>Gap step or inferred</span>'
            '<span><i class="pm-ai-sw pm-ai-sw-named"></i>AI named by the client</span><span><i class="pm-ai-sw pm-ai-sw-suggested"></i>AI suggested by us</span>'
            '<span><i class="pm-sw-gap pm-fl-k-c"></i>Gap</span><span><i class="pm-sw-clar pm-fl-k-c"></i>Clarification</span>'
            '<span><i class="pm-fl-k-cp">3</i>Citation point</span></div>'
        )
        return (
            f'<article class="pm-ev-card pm-fl-card"><h2>Along the flow<span class="pm-ai-count">{count}</span></h2>'
            f'<div class="pm-fl-scroll" tabindex="0" aria-label="The flow, scrolls sideways">{svg}</div>{legend}{self.phone_html()}</article>'
        )

    # -- the phone: the same order as a vertical list
    def phone_html(self):
        """The line's steps in order; each step off the line hangs under the step it comes from: its first step on
        the line, else nested under its first step off the line, with the label of the branch that leads to it."""
        mm, am = self.mm, self.am
        pre = mm.pre
        on = set(self.main)
        parent, kids = {}, {nid: [] for nid in self.ix}
        rest = [n.id for n in mm.nodes if n.id not in on]
        for back in (False, True):  # forward edges first; a step only a loop leads to comes after
            moved = True
            while moved:
                moved = False
                for nid in rest:
                    ins = [
                        e for e in self.E if e["to"] == nid and (back or self.ix[e["from"]] < self.ix[nid])
                    ]
                    e = next((e for e in ins if e["from"] in on), None) or next(
                        (e for e in ins if e["from"] in parent), None
                    )
                    if nid not in parent and e:
                        parent[nid] = (e["from"], e.get("label") if e.get("kind") == "conditional" else None)
                        moved = True
        for nid in rest:  # a step nothing leads to: under the last step on the line before its column
            if nid not in parent:
                a = max(
                    (m for m in self.main if self.col[m] <= self.col[nid]),
                    key=lambda m: self.col[m],
                    default=self.main[0],
                )
                parent[nid] = (a, None)
        for nid in rest:
            kids[parent[nid][0]].append(nid)

        def row(nid, depth):
            n = mm.N[nid]
            e = mm.point(nid)
            badges = "".join(
                f'<a class="pm-fl-pb is-{k}" href="#{pre}{cid}" aria-label="{"Gap" if k == "gap" else "Clarification"} {i}">{i}</a>'
                for k, i, cid, _t in mm.badge[nid]
            )
            sq = "".join(
                f'<span class="pm-ai-mark is-{i["origin"]}" title="{esc(i["id"] + " " + i["title"])}">{i["id"][3:]}</span>'
                for i in am.by_node.get(nid, [])
            )
            label = parent.get(nid, (None, None))[1]
            lab = f'<span class="pm-fl-pl">{esc(label) + " →" if label else ""}</span>' if depth else ""
            shape = "is-dec" if n.dec else "is-step"
            numtxt = "" if n.dec else f"{self.num[nid]:02d}"
            cls = (
                "pm-fl-pi"
                + (" is-branch" if depth else "")
                + (f" is-d{min(depth, 3)}" if depth > 1 else "")
                + f" is-{n.state}"
            )
            s = (
                f'<li class="{cls}">{lab}<span class="pm-fl-ps {shape}" aria-hidden="true">{numtxt}</span>'
                f'<span class="pm-fl-pt"><b>{esc(n.d["title"])}</b>{mks([e]) if e else ""}{badges}<small>{esc(nid)} · {esc(flow_who(n))}</small></span>'
                f'<span class="pm-fl-psq">{sq}</span></li>'
            )
            return s + "".join(row(c, depth + 1) for c in kids[nid])

        out, group = "", None
        for nid in self.main:
            g = mm.N[nid].d.get("group")
            if mm.band and g != group:
                group = g
                gd = mm.groups[mm.group_ix[g]]
                views = "".join(
                    f'<span class="pm-ai-mark is-{i["origin"]}" title="{esc(i["id"] + " " + i["title"])}">{i["id"][3:]}</span>'
                    for i in am.by_group.get(g, [])
                )
                out += f'<li class="pm-fl-pg">{esc(gd["id"])} · {esc(gd["label"])}<span class="pm-fl-psq">{views}</span></li>'
            out += row(nid, 0)
        alls = "".join(
            f'<p class="pm-fl-pall"><span class="pm-ai-mark is-{i["origin"]}" aria-hidden="true">{i["id"][3:]}</span>'
            f"<span><b>{i['id']}</b> {esc(i['title'])} · every step</span></p>"
            for i in am.all
        )
        return f'<div class="pm-fl-phone">{alls}<ol class="pm-fl-plist">{out}</ol></div>'


# ------------------------------------------------------------------ page builds


def load_json(path, what):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise DataError(f"{what} does not exist: {path}") from None
    except ValueError as e:
        raise DataError(f"{what} is not valid JSON: {e}") from e


def load_rules():
    try:
        return json.loads(RULES_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CannotRun(f"cannot read {RULES_JSON}: {e}") from e


def build_page(ws, section, name):
    rules = load_rules()
    idx = Index(ws, rules)
    if section == "process-map":
        m = load_json(ws / "process-map" / f"{name}.json", f"process-map/{name}.json")
        mm = MapModel(m, idx, f"process-map/{name}.json")
        return render_page(mm, None)
    if section == "process-map-ai-opportunity":
        layer = load_json(
            ws / "process-map-ai-opportunity" / f"{name}.json", f"process-map-ai-opportunity/{name}.json"
        )
        base = layer.get("base", "")
        m = load_json(ws / "process-map" / f"{base}.json", f"the base map process-map/{base}.json")
        mm = MapModel(m, idx, f"process-map/{base}.json")
        am = AiModel(layer, mm, f"process-map-ai-opportunity/{name}.json")
        return render_page(mm, am)
    raise CannotRun(f"unknown section {section!r}: process-map or process-map-ai-opportunity")


def page_texts(mm, am):
    meta = mm.meta
    kicker, title = meta["kicker"], meta["title"]
    subtitle = mm.fill_counts(meta["subtitle"]) if meta.get("subtitle") else ""
    date = meta["date"]
    if am:
        lm = am.layer["meta"]
        kicker = lm.get("kicker", kicker)
        title = lm["title"]
        subtitle = lm.get("subtitle", subtitle)
        date = lm.get("date", date)
    return kicker, title, subtitle, date


def board_label(mm):
    return f"{mm.meta['title']}: swimlane board, {plural(len(mm.lanes), 'lane')}, {plural(mm.counts()['steps'], 'step')}"


AI_KEY = (
    '<aside class="pm-ai-key" aria-label="Key"><span><i class="pm-ai-sw pm-ai-sw-named" aria-hidden="true"></i>Named by the client</span>'
    '<span><i class="pm-ai-sw pm-ai-sw-suggested" aria-hidden="true"></i>Our suggestion</span>'
    '<span><i class="pm-sw-cp" aria-hidden="true">3</i>Citation point</span></aside>'
)


def render_page(mm, am, ui=None, ai_ui=None, off=False, pinned=None):
    """A process-map page (header with legend, board, gaps and clarifications, citation points), or an AI page:
    the same page led by the AI opportunities, with the List, the Flow and the board On the map as three views."""
    tpl, shell_tpl, legend = board_template()
    kicker, title, subtitle, date = page_texts(mm, am)
    parts = board_parts(mm, ui)
    if am:
        F = fills()
        slots = am.slots(F, ai_ui, off, pinned)
        slots.update({"style": F["style"], "script": F["script"], "views": am.views_html(F)})
        shell = shell_html(
            shell_tpl, mm, parts, board_label(mm), zoom="auto", slots=slots, panel=am.panel_attrs()
        )
        header = header_html(mm.meta, [], kicker, title, subtitle) + am.summary()
        aside = AI_KEY
    else:
        slots = {}
        shell = shell_html(shell_tpl, mm, parts, board_label(mm), zoom="auto")
        header = header_html(mm.meta, mm.m.get("systems", []), kicker, title, subtitle, mm)
        aside = fill(legend)
    return fill(
        tpl,
        slots,
        shell=shell,
        title=esc(title),
        pre=mm.pre,
        aside=aside,
        evidence=gaps_html(mm) + clar_html(mm),
        citations=cp_html(mm.reg, mm.links),
        footer=footer_html(mm.meta, date),
        header=header,
    )


# ------------------------------------------------------------------ specimens (--specimen)
# Both specimen.html files are built from the workspace's own files (examples/). A state the examples
# lack is drawn from a generated variant of them, marked "generated". Element states are crops of real
# boards drawn by the functions above; interaction states call the real overlay code.

SP_LINKS = "../../examples/out/"  # a specimen's citation links reach the example workspace's computed pages
SP_CSS = """<style id="sp-style">
/* specimen chrome (sp-*): not part of the system */
.sp-page{padding:32px 28px 72px}
.sp-wrap{max-width:1384px;margin:0 auto}
.sp-eyebrow{margin:0;color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
.sp-head h1{margin:6px 0 8px;font-size:30px;font-weight:600;line-height:1.15}
.sp-lede{margin:0;max-width:80ch;color:var(--muted);font-size:14px;line-height:1.5}
.sp-toc{display:flex;flex-wrap:wrap;gap:6px;margin:20px 0 0;padding:12px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.sp-toc a{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 9px;border:1px solid var(--line);border-radius:var(--r);background:var(--paper);color:var(--ink);font-size:12px;text-decoration:none;white-space:nowrap}
.sp-toc a span{color:var(--muted);font-size:11px}
.sp-sec{margin-top:52px}
.sp-sec-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px;margin:0 0 4px}
.sp-n{color:var(--muted);font-size:12px;font-weight:700}
.sp-sec-h h2{margin:0;font-size:21px;font-weight:600;line-height:1.2}
.sp-sec-h code{color:var(--muted);font-size:11.5px}
.sp-sub{margin:0 0 16px;max-width:90ch;color:var(--muted);font-size:13.5px;line-height:1.5}
.sp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(var(--min,260px),100%),1fr));gap:16px;align-items:start}
.sp-fig{display:flex;flex-direction:column;min-width:0;margin:0;border:1px solid var(--line);border-radius:var(--r);background:var(--paper)}
.sp-fig.is-wide{grid-column:1/-1}
.sp-stage{display:flex;align-items:center;justify-content:center;min-height:96px;padding:18px 16px;background:var(--bg);border-bottom:1px solid var(--line);overflow:auto}
.sp-stage.is-block{display:block}
.sp-stage > svg{display:block;max-width:100%;height:auto}
.sp-cap{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;padding:10px 14px 12px;color:var(--muted);font-size:12px;line-height:1.45}
.sp-state{display:inline-flex;align-items:center;height:18px;padding:0 6px;border-radius:var(--r);background:var(--lane-0);color:var(--flow);font-size:11px;font-weight:700}
.sp-gen{display:inline-flex;align-items:center;height:18px;padding:0 6px;border:1px dashed var(--line-strong);border-radius:var(--r);color:var(--muted);font-size:10.5px;font-weight:700;letter-spacing:.03em;text-transform:uppercase}
.sp-narrow{width:360px;max-width:100%}
.sp-narrow .pm-footer{flex-direction:column}
.sp-phone{width:390px;max-width:100%;padding:12px;border:1px dashed var(--line-strong);background:var(--bg)}
.sp-example{border:1px solid var(--line);border-radius:var(--r);background:var(--bg)}
.sp-example .pm-page{padding:24px 24px 22px}
.sp-mock{width:100%}
.sp-tipbox{max-width:300px}
.sp-tipbox.is-cp{max-width:380px}
.sp-show{display:block!important}
.sp-print{width:744px;max-width:100%;padding:12px;border:1px dashed var(--line-strong);background:#fff}
.sp-print .pm-fl-scroll{overflow:visible;margin:0;padding:0}
.sp-print .pm-fl-svg{width:100%;height:auto}
.sp-print .pm-fl-phone{display:none!important}
.sp-print .pm-fl-scroll,.sp-print .pm-fl-legend{display:block!important}
.sp-print .pm-fl-legend{display:flex!important}
@media (max-width:700px){.sp-page{padding:20px 16px 48px}.sp-example .pm-page{padding:16px 12px}}
</style>"""

SP_JS = """<script id="sp-script">
/* specimen only: freeze interaction states with the real page functions */
(function(){
function run(){
  document.querySelectorAll('[data-sp-act]').forEach(function(root){
    var api = root.pmAiApi; if (!api) return;
    var a = root.getAttribute('data-sp-act').split(':');
    if (a[0] === 'pin'){ api.view('map'); api.pin(a[1]); }
    if (a[0] === 'off') api.setLayer(false);
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function(){ setTimeout(run, 0); });
else setTimeout(run, 0);
})();
</script>"""


def sp_fig(states, body, note="", wide=False, block=False, gen=False):
    tags = "".join(f'<span class="sp-state">{esc(s)}</span>' for s in states)
    g = '<span class="sp-gen">generated</span>' if gen else ""
    n = f"<span>{note}</span>" if note else ""
    return (
        f'<figure class="sp-fig{" is-wide" if wide else ""}"><div class="sp-stage{" is-block" if block else ""}">{body}</div>'
        f'<figcaption class="sp-cap">{tags}{g}{n}</figcaption></figure>'
    )


def sp_section(sid, n, title, sub, figs, min_w="260px"):
    return (
        f'<section class="sp-sec" id="{sid}"><div class="sp-sec-h"><span class="sp-n">{n:02d}</span><h2>{esc(title)}</h2>'
        f'<code>#{sid}</code></div><p class="sp-sub">{sub}</p><div class="sp-grid" style="--min:{min_w}">{"".join(figs)}</div></section>'
    )


def sp_page(title, eyebrow, lede, sections, ai=False):
    st, sc = board_style_script()
    F = fills() if ai else None
    toc = "".join(
        f'<a href="#{sid}"><span>{i + 1:02d}</span>{esc(t)}</a>' for i, (sid, t) in enumerate(sections["toc"])
    )
    head = (
        f'<header class="sp-head"><p class="sp-eyebrow">{esc(eyebrow)}</p><h1>{esc(title)}</h1>'
        f'<p class="sp-lede">{lede}</p><nav class="sp-toc" aria-label="Sections">{toc}</nav></header>'
    )
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n{st}\n{F['style'] if ai else ''}\n{SP_CSS}\n</head>\n<body>\n"
        f'<main class="sp-page"><div class="sp-wrap">{head}{"".join(sections["body"])}</div></main>\n'
        f"{sc}\n{F['script'] if ai else ''}\n{SP_JS}\n</body>\n</html>\n"
    )


def sp_main(page):
    """The body of a built page, for embedding: the content of its <main>."""
    return re.search(r'<main class="pm-page">.*?</main>', page, re.S).group(0)


def crop(mm, box, ui=None, am=None, ai_ui=None, cls="pm-board", gutter=False, label="Specimen"):
    """A crop of a board as one SVG: everything drawn in draw order, shown through a viewBox."""
    p = board_parts(mm, ui)
    under = am.under(ai_ui) if am else ""
    over = am.over(ai_ui) if am else ""
    gut = (p["gutter"] + (am.gutter_over(ai_ui) if am else "")) if gutter else ""
    body = gut + p["lanes"] + p["band"] + under + p["edges"] + p["nodes"] + p["pills"] + over
    body = body.replace(' tabindex="0"', "")
    x, y, w, h = box
    return (
        f'<svg class="{cls}" viewBox="{num(x)} {num(y)} {num(w)} {num(h)}" width="{num(w)}" height="{num(h)}" '
        f'role="img" aria-label="{esc(label)}">{body}</svg>'
    )


def node_box(mm, nid, below=26):
    n = mm.N[nid]
    return (n.x - 18, n.y - 20, CW + 36, CH + 20 + below)


def variant(m, **changes):
    v = json.loads(json.dumps(m))
    v.update(changes)
    return v


def first(folder, ws):
    files = sorted((ws / folder).glob("*.json"))
    if not files:
        raise DataError(f"{ws}/{folder}/ holds no .json file for the specimen")
    return files[0]


def pm_specimen(ws, idx, base_path):
    m = load_json(base_path, base_path.name)
    where = f"process-map/{base_path.name}"

    def mk(mv, pre):
        return MapModel(mv, idx, where, pre, SP_LINKS)

    ex = mk(m, "ex-")
    steps = [n for n in m["nodes"] if n.get("kind", "step") == "step"]
    decs = [n for n in m["nodes"] if n.get("kind") == "decision"]
    grounded = next(n for n in steps if n["state"] == "grounded" and n.get("owner") and n.get("systems"))
    inferred = next((n for n in steps if n["state"] == "inferred"), None)
    gapn = next((n for n in steps if n["state"] == "gap"), None)
    noowner = next((n for n in steps if not n.get("owner")), None)
    gcite = grounded["cite"]
    sys_ids = [s["id"] for s in m.get("systems", [])]
    lane0, lane1 = m["lanes"][0]["id"], m["lanes"][-1]["id"]
    sections, toc = [], []

    def add(sid, title, sub, figs, min_w="260px"):
        toc.append((sid, title))
        sections.append(sp_section(sid, len(toc), title, sub, figs, min_w))

    # the example, whole
    sections.append(
        f'<section class="sp-sec" id="pm-example"><div class="sp-sec-h"><span class="sp-n">00</span><h2>The example map</h2>'
        f'<code>#pm-example</code></div><p class="sp-sub">examples/{esc(where)}, built as a page. Every element below is drawn by the same code.</p>'
        f'<div class="sp-example">{sp_main(render_page(ex, None))}</div></section>'
    )

    # a variant holding one node per node state the sections need
    extra_sys = [
        {"id": "shared-drive", "label": "Shared drive", "icon": "shared-drive", "cite": gcite[:1]},
        {"id": "request-form", "label": "Request form", "icon": "document", "cite": gcite[:1]},
    ]
    long_title = "Reconcile every request with its tracker records"[:48]
    vn = [
        dict(grounded, id="NOD-01"),
        dict(
            inferred or grounded,
            id="NOD-02",
            state="inferred",
            owner="Team A",
            cite=(inferred or {}).get("cite")
            or [{"type": "inferred", "reading": "Team A completes it again", "from": gcite[:1]}],
        ),
        dict(gapn or grounded, id="NOD-03", state="gap"),
        {k: v for k, v in grounded.items() if k not in ("owner", "systems")}
        | {"id": "NOD-04", "title": (noowner or grounded)["title"]},
        dict(grounded, id="NOD-05", title=long_title, systems=sys_ids[:1]),
        dict(grounded, id="NOD-06", systems=(sys_ids + ["shared-drive", "request-form"])[:4]),
        dict(grounded, id="NOD-07", systems=sys_ids[:2]),
        dict(grounded, id="NOD-08", systems=sys_ids[:1]),
        dict(
            inferred or grounded,
            id="NOD-09",
            state="inferred",
            owner="Team B",
            title="Check the request",
            systems=[],
            cite=[
                {
                    "type": "inferred",
                    "reading": "Team B rechecks each submission against the list",
                    "from": gcite[:1],
                }
            ],
        ),
    ]
    for d in vn:
        d.pop("group", None)
        d.pop("col", None)
        d["lane"] = lane0
    dq = (
        decs[0]
        if decs
        else {
            "id": "DEC-01",
            "title": "Request complete?",
            "kind": "decision",
            "state": "grounded",
            "cite": gcite[:1],
        }
    )
    vd = [
        dict(dq, id="DEC-01"),
        dict(
            dq,
            id="DEC-02",
            state="inferred",
            cite=[{"type": "inferred", "reading": "Team B checks the limit first", "from": gcite[:1]}],
        ),
        dict(dq, id="DEC-03", state="gap"),
        dict(dq, id="DEC-04"),
        dict(dq, id="DEC-05", title="Over the approval limit?"),
    ]
    for d in vd:
        d.pop("group", None)
        d["lane"] = lane1
    clar0 = (
        m.get("clarifications")
        or [
            {
                "title": "Who confirms this step?",
                "shows": "The step is listed.",
                "ask": "Who does it?",
                "cite": gcite[:1],
            }
        ]
    )[0]
    gap0 = (
        m.get("gaps") or [{"title": "No owner is named", "text": "The step has no owner.", "cite": gcite[:1]}]
    )[0]
    vm = variant(
        m,
        systems=m.get("systems", []) + extra_sys,
        groups=[],
        edges=[],
        nodes=vn + vd,
        gaps=[dict(gap0, id="GAP-01", nodes=["NOD-03", "DEC-03"])],
        clarifications=[
            dict(clar0, id=f"P0{i}", nodes=nodes)
            for i, nodes in (
                (1, ["NOD-08", "DEC-04", "NOD-03"]),
                (2, ["NOD-08"]),
                (3, ["NOD-08"]),
                (4, ["NOD-08"]),
            )
        ],
    )
    vm["lanes"] = [lane for lane in m["lanes"] if lane["id"] in (lane0, lane1)]

    def nfig(states, nid, ui="", note="", gen=True):
        v = mk(vm, f"n{len(states)}{nid.lower()}{ui}-")
        return sp_fig(
            states,
            crop(v, node_box(v, nid, 20), ui={nid: ui} if ui else None, label=f"{nid}, {', '.join(states)}"),
            note,
            gen=gen,
        )

    def bfig(states, state, note=""):
        """A decision whose second branch leaves its bottom vertex: its id and marker sit right of the line."""
        cite = (
            gcite[:1]
            if state == "grounded"
            else [
                {"type": "inferred", "reading": "Team B checks the limit before approval", "from": gcite[:1]}
            ]
        )
        d = {
            "id": "DEC-06",
            "title": dq["title"],
            "kind": "decision",
            "state": state,
            "lane": lane0,
            "cite": cite,
        }
        ys = dict(grounded, id="YES-01", lane=lane0, title="Approve request", systems=[])
        no = dict(grounded, id="NOD-10", lane=lane1, title="Return request", systems=[])
        for x in (ys, no):
            x.pop("group", None)
            x.pop("col", None)
            x.pop("owner", None)
        bv = mk(
            variant(
                m,
                groups=[],
                nodes=[d, ys, no],
                gaps=[],
                clarifications=[],
                lanes=[lane for lane in m["lanes"] if lane["id"] in (lane0, lane1)],
                edges=[
                    {"from": "DEC-06", "to": "YES-01", "kind": "conditional", "label": "Yes"},
                    {"from": "DEC-06", "to": "NOD-10", "kind": "conditional", "label": "No"},
                ],
            ),
            f"b{state[0]}-",
        )
        n = bv.N["DEC-06"]
        return sp_fig(
            states,
            crop(bv, (n.x - 18, n.y - 20, PITCH + 16, CH + 40), label=f"DEC-06, {', '.join(states)}"),
            note,
            gen=True,
        )

    # 01 header
    meta = m["meta"]

    def hx(mt, mv=m):
        return f'<div class="pm-head-main" style="width:100%">{header_html(mt, mv.get("systems", []), mt["kicker"], mt["title"], ex.fill_counts(mt.get("subtitle", "")), ex)}</div>'

    add(
        "pm-header",
        "Page header",
        "Kicker with the flag chips, title, subtitle with its {count:…} tokens filled, and the system key. The title wraps and is never cut.",
        [
            sp_fig(["full"], hx(meta), block=True, wide=True, gen=False),
            sp_fig(
                ["minimal"],
                hx(
                    {
                        "kicker": meta["kicker"],
                        "title": meta["title"],
                        "client": meta["client"],
                        "date": meta["date"],
                    },
                    variant(m, systems=[]),
                ),
                block=True,
                wide=True,
                gen=True,
            ),
            sp_fig(
                ["long title"],
                hx(
                    dict(
                        meta,
                        title="Request handling from the first email to the recorded outcome, with every return to Team A"[
                            :90
                        ],
                    )
                ),
                block=True,
                wide=True,
                gen=True,
            ),
        ],
        "100%",
    )
    # 02 key
    add(
        "pm-key",
        "System key",
        "One item per system, in file order, with its icon and its citation marker. With no systems the row is left out.",
        [
            sp_fig(["systems"], hx(meta), block=True, gen=False),
            sp_fig(
                ["omitted when there are none"],
                hx(dict(meta, subtitle=""), variant(m, systems=[])),
                block=True,
                gen=True,
            ),
        ],
        "420px",
    )
    # 03 legend
    legend = fill(board_template()[2])
    add(
        "pm-legend",
        "Legend",
        "Template text, always complete: lines, then node states and the citation point, then marks. Two columns under 640px.",
        [
            sp_fig(
                ["3 × 3 on desktop"], f'<div style="width:392px;max-width:100%">{legend}</div>', gen=False
            ),
            sp_fig(
                ["2 columns under 640px"],
                f'<div style="width:300px;max-width:100%">{legend.replace("pm-legend", "pm-legend is-2col", 1)}</div>',
                gen=False,
            ),
        ],
        "420px",
    )
    # 04 lanes
    lanes = [
        dict(m["lanes"][0]),
        {"id": "shared", "label": "Shared services and finance review team"},
        {"id": "team-x", "label": m["lanes"][-1]["label"]},
        {"id": "team-c", "label": "Procurement and supplier finance team", "cite": gcite[:1]},
    ]
    ln = [
        dict(grounded, id="LAN-01", lane=lanes[0]["id"]),
        dict(grounded, id="LAN-02", lane="shared", owner="Team B"),
        dict(grounded, id="LAN-03", lane="team-x"),
        dict(grounded, id="LAN-04", lane="team-x", title="Log request"),
    ]
    for d in ln:
        d.pop("group", None)
    lv = mk(
        variant(
            m,
            lanes=lanes,
            groups=[],
            nodes=ln,
            edges=[{"from": "LAN-01", "to": "LAN-03"}, {"from": "LAN-01", "to": "LAN-04"}],
            gaps=[],
            clarifications=[],
        ),
        "lane-",
    )
    add(
        "pm-lane",
        "Lane and gutter",
        "Lanes in alternating fills; the gutter holds the role and its note. A lane grows a 144-unit row for each step stacked in a column, and an empty lane shrinks to 56.",
        [
            sp_fig(
                ["alternating fills", "long name", "stacked rows", "empty"],
                crop(lv, (0, 0, min(lv.W, 560), lv.H), gutter=True, label="Lanes"),
                wide=True,
                gen=True,
                note="Second lane: a 39-character role wraps to three lines. Third: two steps in one column. Fourth: no steps, and a long role still gets three lines.",
            ),
        ],
    )
    # 05 band
    bands = [dict(g) for g in m.get("groups", [])] or [
        {"id": "G01", "label": "Intake"},
        {"id": "G02", "label": "Review and approval"},
    ]
    bt = mk(m, "band-")
    one = [dict(n, group=bands[0]["id"] if i == 0 else bands[-1]["id"]) for i, n in enumerate(m["nodes"])]
    gl = variant(m, groups=[dict(bands[0], label="Review, approval, record"), bands[-1]], nodes=one)
    bl = mk(gl, "bandl-")
    first_g = bands[0]["id"]
    bw = min(bt.W, 760)
    add(
        "pm-band",
        "Group band",
        "Drawn with two or more groups: one cell per view, its id and label, and the derived step count. The label is cut to leave room for the AI layer's squares.",
        [
            sp_fig(
                ["drawn with two or more groups"],
                crop(bt, (GUT, 0, bw - GUT, 52), label="Band"),
                wide=True,
                gen=False,
            ),
            sp_fig(
                [f"targeted (#{first_g})"],
                crop(mk(m, "bandt-"), (GUT, 0, bw - GUT, 52), ui={"group": first_g}, label="Band, targeted"),
                wide=True,
                gen=False,
            ),
            sp_fig(
                ["long label (cut with …)"],
                crop(bl, (GUT, 0, min(bl.W, 760) - GUT, 52), label="Band, long label"),
                wide=True,
                gen=True,
                note="A one-column view: its label stops 70 units short of the cell's end, where a view's AI squares go.",
            ),
        ],
    )
    # 06 node card
    add(
        "pm-node",
        "Node card",
        "A 156 × 104 card: the title with its one citation marker, the owner, a gap step's tag, and the step id. Nothing else: every address and reading is in Citation points. Focus is a 2px ink ring 8 units out, so it never reads as an AI halo.",
        [
            nfig(["grounded", "with owner"], "NOD-01", gen=False),
            nfig(["inferred"], "NOD-02", gen=False),
            nfig(["gap"], "NOD-03", gen=False),
            nfig(["without owner"], "NOD-04", gen=False),
            nfig(["long title (3 lines, then …)"], "NOD-05"),
            nfig(["several systems"], "NOD-06"),
            nfig(
                ["inferred", "with owner"],
                "NOD-09",
                note="The reading is printed in Citation points and the tooltip, never on the card.",
            ),
            nfig(["hover"], "NOD-01", "hover"),
            nfig(["keyboard focus"], "NOD-01", "focus"),
            nfig(["targeted"], "NOD-01", "target"),
        ],
        "236px",
    )
    # 07 badges
    add(
        "pm-badge",
        "Badges",
        "Gap badges are filled orange, clarification badges a dashed ring; the number is the card's list position and links to it. After three comes +n.",
        [
            nfig(["gap"], "NOD-03", gen=False),
            nfig(["clarification"], "NOD-07"),
            nfig(["+n after three"], "NOD-08"),
        ],
        "236px",
    )
    # 08 system icons
    add(
        "pm-sys",
        "System icon",
        "The node's systems on its top-right corner: one, two, then +n.",
        [
            nfig(["1"], "NOD-05"),
            nfig(["2"], "NOD-07"),
            nfig(["+n"], "NOD-06"),
        ],
        "236px",
    )
    # 09 decisions
    add(
        "pm-decision",
        "Decision diamond",
        "A 60.2 square turned 45°. The question sits inside on at most two lines; the id and the marker sit under the bottom vertex, or right of a branch that leaves it.",
        [
            nfig(["grounded"], "DEC-01", gen=not decs),
            nfig(["inferred (dashed grey)"], "DEC-02"),
            nfig(["gap (dashed orange)"], "DEC-03"),
            nfig(["with a clarification"], "DEC-04"),
            nfig(["long question (2 lines)"], "DEC-05", note="A 24-character question, uncut."),
            bfig(["grounded", "a branch leaves the bottom vertex"], "grounded"),
            bfig(
                ["inferred", "a branch leaves the bottom vertex"],
                "inferred",
                note="Its reading is printed in Citation points.",
            ),
        ],
        "236px",
    )
    # 10 edges
    e_hover = (m["edges"][0]["from"], m["edges"][0]["to"]) if m.get("edges") else None
    add(
        "pm-edge",
        "Edges",
        "Flow lines are solid; an edge to an earlier node is feedback, dashed. A branch label sits in a pill on its line's longest free stretch.",
        [
            sp_fig(
                ["flow", "branch with its label pill", "feedback (dashed)"],
                crop(
                    mk(m, "edge-"),
                    (GUT, ex.lanes_top, ex.W - GUT, ex.lanes_bottom - ex.lanes_top),
                    label="Edges",
                ),
                wide=True,
                gen=False,
            ),
            sp_fig(
                ["hover"],
                crop(
                    mk(m, "edgeh-"),
                    (GUT, ex.lanes_top, PITCH * min(ex.ncols, 3) + 4, ex.lanes_bottom - ex.lanes_top),
                    ui={"edges": {e_hover}} if e_hover else None,
                    label="Edge hover",
                ),
                note=f"{e_hover[0]} → {e_hover[1]} hovered." if e_hover else "",
                wide=True,
                gen=False,
            ),
        ],
    )
    # 11 shell
    shell_tpl = board_template()[1]

    def shell(pre, zoom, phone=False):
        v = mk(m, pre)
        s = shell_html(shell_tpl, v, board_parts(v), board_label(v), zoom=zoom)
        return f'<div class="sp-phone">{s}</div>' if phone else s

    add(
        "pm-shell",
        "Board shell",
        "Fit scales the board to the page; 100% draws it 1:1 with a sticky gutter and drag to pan. Under 700px the gutter is redrawn compact and Fit keeps the board 860 wide inside its own scroll.",
        [
            sp_fig(["Fit"], shell("sf-", "fit"), wide=True, block=True, gen=False),
            sp_fig(
                ["100% (sticky gutter, drag to pan)"], shell("s1-", "100"), wide=True, block=True, gen=False
            ),
            sp_fig(["phone (compact gutter)"], shell("sp-", "fit", True), wide=True, gen=False),
        ],
    )
    # 12 tooltip
    tv = mk(vm, "tip-")
    dec_id = "DEC-01"
    add(
        "pm-tip",
        "Tooltip",
        "One tooltip, on hover or keyboard focus. It only repeats printed facts: id and group, the full title, lane, owner, systems, an inferred reading, marks and the step's citation points. A marker's tooltip is one line: the address and the first words of the verbatim text.",
        [
            sp_fig(
                ["step"],
                f'<div class="pm-tip is-static sp-tipbox">{ex.tip(ex.N[grounded["id"]])}</div>',
                gen=False,
            ),
            sp_fig(
                ["decision"],
                f'<div class="pm-tip is-static sp-tipbox">{tv.tip(tv.N[dec_id])}</div>',
                gen=not decs,
            ),
            sp_fig(
                ["truncated title"], f'<div class="pm-tip is-static sp-tipbox">{tv.tip(tv.N["NOD-05"])}</div>'
            ),
            sp_fig(
                ["citation marker"],
                f'<div class="pm-tip is-static is-cp sp-tipbox">{cp_tip(ex.reg.order[0])}</div>',
                gen=False,
                note="Hover or focus a marker: one line.",
            ),
        ],
        "300px",
    )
    # 13, 14 cards
    gid = (m.get("gaps") or [{}])[0].get("id")
    cid = (m.get("clarifications") or [{}])[0].get("id")
    add(
        "pm-gaps",
        "Gaps card",
        "One item per gap, numbered as its badges: title, text with citation markers, the steps, and the provenance line: each needle searched for, then Grounded, each with its markers.",
        [
            sp_fig(["list"], gaps_html(mk(m, "g1-")), block=True, gen=False),
            sp_fig(["targeted item"], gaps_html(mk(m, "g2-"), target=gid), block=True, gen=False),
        ],
        "360px",
    )
    add(
        "pm-clar",
        "Clarifications card",
        "One item per question: what the sources show, what to confirm and with whom, the steps, and the provenance line with its markers.",
        [
            sp_fig(["list"], clar_html(mk(m, "c1-")), block=True, gen=False),
            sp_fig(["targeted item"], clar_html(mk(m, "c2-"), target=cid), block=True, gen=False),
        ],
        "360px",
    )
    # 15 citation points
    st = mk(m, "s2-")
    absent = next((e for e in st.reg.order if e["kind"] == "absent"), None)
    span = next((e for e in st.reg.order if e["kind"] == "span"), None)
    add(
        "pm-cp",
        "Citation points section",
        "Every citation point the page uses, numbered as its markers: the record and locator, the verbatim text, how it is used and by which element, a link to the record in Original data received, and ↗ to the point in Citation points. Above the rows, one line per record.",
        [
            sp_fig(
                ["per point", "span point", "absent search", "inferred reading"],
                cp_html(mk(m, "s1-").reg, SP_LINKS),
                wide=True,
                block=True,
                gen=False,
            ),
            sp_fig(
                ["targeted row"],
                cp_html(
                    st.reg,
                    SP_LINKS,
                    target=(absent or span or st.reg.order[0])["anchor"],
                    only={(absent or span or st.reg.order[0])["source"]},
                ),
                wide=True,
                block=True,
                gen=False,
            ),
        ],
    )
    mm_ = mk(m, "mk-")
    g0 = mm_.gap_html[0] if mm_.gap_html else None
    add(
        "pm-marker",
        "Citation marker",
        "One quiet numeral per cited element, linked to its row in Citation points: after a card's title, after a decision's id, after a system or a lane, and in place of each [SRC locator] bracket in card prose.",
        [
            sp_fig(
                ["on a card"],
                crop(mm_, node_box(mm_, grounded["id"], 20), label="Marker on a card"),
                gen=False,
            ),
            sp_fig(
                ["in prose"],
                f'<p style="margin:0;max-width:60ch;font-size:12.5px;line-height:1.45;color:var(--muted)">{g0[3]}</p>'
                if g0
                else "",
                block=True,
                gen=False,
            ),
            sp_fig(["in a provenance line"], g0[4] if g0 else "", block=True, gen=False),
            sp_fig(
                ["hover", "focus (one-line tooltip)"],
                crop(mm_, node_box(mm_, grounded["id"], 20), label="Marker hovered").replace(
                    '<a class="cp-mk"', '<a class="cp-mk is-hover is-focus"', 1
                )
                + f'<div class="pm-tip is-static is-cp sp-tipbox" style="margin-top:8px">{cp_tip(mm_.point(grounded["id"]))}</div>',
                block=True,
                gen=False,
                note="Hover or keyboard focus: the numeral turns orange and underlines (focus adds a 1.5px ink ring), and one line names the record, the locator and the first words of the verbatim text.",
            ),
        ],
        "300px",
    )
    # 16 footer
    add(
        "pm-footer",
        "Footer",
        "Left: meta.footer. Right: the confidential and draft clauses when they apply, then the date.",
        [
            sp_fig(["flags"], footer_html(meta, meta["date"]), block=True, gen=False),
            sp_fig(["no flags"], footer_html(dict(meta, flags=[]), meta["date"]), block=True, gen=True),
            sp_fig(
                ["phone (the sides stack)"],
                f'<div class="sp-narrow">{footer_html(meta, meta["date"])}</div>',
                gen=False,
            ),
        ],
        "420px",
    )
    # 17 empty states
    en = [
        dict(grounded, id="EMP-01", lane=lane0, group="G01"),
        dict(grounded, id="EMP-02", lane=lane0, group="G01", title="Log request"),
    ]
    for d in en:
        d.pop("systems", None)
    em = variant(
        m,
        meta={k: v for k, v in meta.items() if k != "flags"}
        | {"subtitle": "{count:steps} steps across {count:groups} view."},
        systems=[],
        lanes=[m["lanes"][0], {"id": "team-c", "label": "Team C", "cite": gcite[:1]}],
        groups=[{"id": "G01", "label": "Intake"}],
        nodes=en,
        edges=[{"from": "EMP-01", "to": "EMP-02"}],
        gaps=[dict(m["gaps"][0], nodes=["EMP-02"])],
        clarifications=[dict(m["clarifications"][0], nodes=["EMP-01"])],
    )
    add(
        "pm-empty",
        "Empty states",
        "A map with an empty lane, no systems, no flags and one group (so no band). Gaps and clarifications are "
        "required, so their cards are never empty.",
        [
            sp_fig(
                [
                    "lane with no steps",
                    "no systems",
                    "no flags",
                    "0 or 1 group (no band)",
                ],
                f'<div class="sp-example">{sp_main(render_page(mk(em, "e-"), None))}</div>',
                wide=True,
                block=True,
                gen=True,
            ),
        ],
    )
    return sp_page(
        "Process map: every element",
        "design-system/process-map · specimen",
        "Built from <code>examples/</code> by <code>build_map.py --specimen</code>. Each section is an element of the README's table, at its anchor; "
        'a state the examples lack is drawn from a generated variant of them, marked <span class="sp-gen">generated</span>.',
        {"toc": toc, "body": sections},
    )


def ai_specimen(ws, idx, base_path, layer_path):
    layer = load_json(layer_path, layer_path.name)
    m = load_json(ws / "process-map" / f"{layer['base']}.json", f"process-map/{layer['base']}.json")
    where = f"process-map/{layer['base']}.json"
    lwhere = f"process-map-ai-opportunity/{layer_path.name}"
    F = fills()

    def mk(lv, pre, mv=None):
        mm = MapModel(mv or m, idx, where, pre, SP_LINKS)
        return mm, AiModel(lv, mm, lwhere)

    items = layer["ai"]
    by = {i["id"]: i for i in items}
    named = next((i for i in items if i["origin"] == "named" and i.get("nodes")), None)
    sugg = next((i for i in items if i["origin"] == "suggested" and i.get("nodes")), None)
    viewi = next((i for i in items if isinstance(i.get("groups"), list) and i["groups"]), None)
    alli = next((i for i in items if i.get("groups") == "all"), None)
    agi = next((i for i in items if i.get("agentic")), None)
    noag = next((i for i in items if not i.get("agentic")), None)
    sections, toc = [], []

    def add(sid, title, sub, figs, min_w="260px"):
        toc.append((sid, title))
        sections.append(sp_section(sid, len(toc), title, sub, figs, min_w))

    def page_with(lv, pre, act=None, mv=None):
        mm, am = mk(lv, pre, mv)
        body = sp_main(render_page(mm, am))
        if act:
            body = body.replace("data-pm-board ", f'data-pm-board data-sp-act="{act}" ', 1)
        return body

    sections.append(
        f'<section class="sp-sec" id="ai-example"><div class="sp-sec-h"><span class="sp-n">00</span><h2>The example page</h2>'
        f'<code>#ai-example</code></div><p class="sp-sub">examples/{esc(lwhere)} over examples/{esc(where)}, built as a page. '
        f"It opens on the List; switch to the Flow and On the map. Show on map highlights an item on the board; Esc releases it.</p>"
        f'<div class="sp-example">{page_with(layer, "ex-")}</div></section>'
    )

    # variant: four items on one step, for +n
    nid = (named or sugg)["nodes"][0]
    four = [dict(i, nodes=[nid], groups=[]) | {"id": f"AI-0{k + 1}"} for k, i in enumerate((items * 4)[:4])]
    for i in four:
        i.pop("agentic", None)
    v4 = dict(layer, ai=four)
    mm, am = mk(layer, "x-")
    n_named = named["nodes"][0] if named else nid
    n_sugg = sugg["nodes"][0] if sugg else nid

    def ncrop(lv, nid, pre, cls="pm-board has-ai", ui=None, ai_ui=None, label="AI marks"):
        a, b = mk(lv, pre)
        return crop(a, node_box(a, nid, 30), ui=ui, am=b, ai_ui=ai_ui, cls=cls, label=label)

    kicker, title, subtitle, _ = page_texts(mm, am)
    emm, eam = mk(dict(layer, ai=[]), "z-")
    add(
        "ai-header",
        "Header and summary",
        "The layer's kicker, title and subtitle replace the base's; flags and client are inherited. The summary is computed: a zero segment is left out, and decisions are not steps. The key on the right is the page's only legend until On the map.",
        [
            sp_fig(
                ["standard"],
                f'<div class="pm-head-main" style="width:100%">{header_html(mm.meta, [], kicker, title, subtitle)}{am.summary()}</div>',
                block=True,
                wide=True,
                gen=False,
            ),
            sp_fig(["empty"], eam.summary(), block=True, wide=True, gen=True),
            sp_fig(["key"], AI_KEY, gen=False),
        ],
    )
    nav = am.views_html(F).split("</nav>", 1)[0] + "</nav>"

    def tab(v, extra=""):
        n = nav.replace('aria-selected="true"', 'aria-selected="false"')
        return re.sub(f'(data-view="{v}" [^>]*?)aria-selected="false"', r'\1aria-selected="true"', n).replace(
            f'class="pm-view-tab" id="x-tab-{v}"', f'class="pm-view-tab{extra}" id="x-tab-{v}"'
        )

    add(
        "ai-views",
        "View switch",
        "List, Flow, On the map: one quiet tab row under the header. Every load opens on the List; the arrow keys move along the row. A link to something in another view opens that view first; print shows all three.",
        [
            sp_fig(["List (default)"], tab("list"), block=True, wide=True, gen=False),
            sp_fig(["Flow"], tab("flow"), block=True, wide=True, gen=False),
            sp_fig(["On the map"], tab("map"), block=True, wide=True, gen=False),
            sp_fig(
                ["focus-visible"],
                tab("list").replace(
                    'class="pm-view-tab" id="x-tab-flow"', 'class="pm-view-tab is-focus" id="x-tab-flow"'
                ),
                block=True,
                wide=True,
                gen=False,
                note="Keyboard focus on Flow while the List is shown: a 2px ink outline.",
            ),
        ],
    )
    add(
        "ai-list",
        "List",
        "The page's default view: one row per item, named by the client first, then our suggestions, each by id.",
        [
            sp_fig(["list"], mk(layer, "c1-")[1].card_html(F), block=True, wide=True, gen=False),
            sp_fig(["empty"], eam.card_html(F), block=True, wide=True, gen=True),
        ],
    )
    rid = (named or items[0])["id"]

    def row(state, pre, it=None):
        a, b = mk(layer, pre)
        return f'<article class="pm-ev-card pm-ai-card sp-mock"><ol class="pm-ai-list">{b.row_html(it or by[rid], state)}</ol></article>'

    add(
        "ai-row",
        "List row",
        "Square, id and title, the origin tag, Show on map, what it would do, the steps it touches (or where it applies), the evidence, and the agentic version.",
        [
            sp_fig(["default"], row("", "r1-"), block=True, wide=True, gen=False),
            sp_fig(["targeted"], row("is-target", "r2-"), block=True, wide=True, gen=False),
        ],
    )

    def ev(it, pre):
        a, b = mk(dict(layer, ai=[it]), pre)
        return f'<div class="sp-mock">{b.evidence_html(it)}</div>'

    gq = next((i for i in items if any(ctype(c) == "grounded" and c.get("quote") for c in i["cite"])), None)
    gn = next(
        (i for i in items if any(ctype(c) == "grounded" and not c.get("quote") for c in i["cite"])), None
    )
    inf = next((i for i in items if any(ctype(c) == "inferred" for c in i["cite"])), None)
    gq_it = (
        dict(gq, cite=[c for c in gq["cite"] if ctype(c) == "grounded" and c.get("quote")]) if gq else None
    )
    gn_it = (
        dict(gn, cite=[c for c in gn["cite"] if ctype(c) == "grounded" and not c.get("quote")])
        if gn
        else dict(gq, cite=[{k: v for k, v in c.items() if k != "quote"} for c in gq_it["cite"]])
    )
    inf_it = dict(inf, cite=[c for c in inf["cite"] if ctype(c) == "inferred"])
    add(
        "ai-evidence",
        "Evidence",
        "A grounded citation shows its quote, or else its first record's text, then Grounded with the speaker or the web domain and its marker. An inferred one shows its basis, then Inferred · from and its markers.",
        [
            sp_fig(["grounded quote"], ev(gq_it, "e1-"), block=True, gen=False),
            sp_fig(["grounded without a quote"], ev(gn_it, "e2-"), block=True, gen=not gn),
            sp_fig(["inferred"], ev(inf_it, "e3-"), block=True, gen=False),
        ],
        "320px",
    )

    def agr(it, pre, open_=False):
        a, b = mk(layer, pre)
        return f'<div class="sp-mock">{b.agentic_html(it.get("agentic"), open_)}</div>'

    add(
        "ai-agentic",
        "Agentic version",
        "Folded by default; a numbered spine of steps with each place a person decides, then systems with the base icons, then logging. No orange inside. Print opens every block.",
        [
            sp_fig(["folded"], agr(agi, "g1-"), block=True, wide=True, gen=False),
            sp_fig(["open", "print (open)"], agr(agi, "g2-", True), block=True, wide=True, gen=False),
            sp_fig(
                ["absent"],
                row("", "g3-", noag or dict(by[rid], agentic=None)),
                block=True,
                wide=True,
                gen=not noag,
                note="The row ends after its evidence.",
            ),
        ],
    )
    add(
        "ai-flow",
        "Flow",
        "The steps in one line in flow order, branches on the rows above, only the map's own edges; under the line, the AI lane. On a phone, the same order as a vertical list.",
        [
            sp_fig(["desktop"], FlowView(mk(layer, "f1-")[1]).html(), block=True, wide=True, gen=False),
            sp_fig(
                ["phone (vertical list)"],
                f'<div class="sp-phone">{FlowView(mk(layer, "f2-")[1]).phone_html().replace("pm-fl-phone", "pm-fl-phone sp-show")}</div>',
                gen=False,
            ),
            sp_fig(
                ["print (scaled to the page)"],
                f'<div class="sp-print">{FlowView(mk(layer, "f4-")[1]).html()}</div>',
                wide=True,
                gen=False,
                note="Print scales the Flow to the page width and leaves out the phone list.",
            ),
        ],
    )
    add(
        "ai-lane",
        "AI lane",
        "One track per item, packed: a square under each step it touches, joined by a thin bar; a whole-view item has a square under each step of its view, an all-views item one bar along the line. The caption links to the List row.",
        [
            sp_fig(
                ["on a step", "on several steps (bar)", "a whole view", "every step"],
                f'<div class="sp-mock" style="overflow:auto">{_lane_only(mk(layer, "f3-")[1])}</div>',
                block=True,
                wide=True,
                gen=False,
            ),
        ],
    )
    add(
        "ai-halo",
        "Halo",
        "On the map: one halo per marked step, under the node, 4 units outside its border; never dashed.",
        [
            sp_fig(["default"], ncrop(layer, n_sugg, "h1-"), gen=False),
            sp_fig(
                ["thick (focus, hover)"],
                ncrop(layer, n_sugg, "h2-", ai_ui={"halo": {n_sugg: "is-ai-hover"}}),
                gen=False,
            ),
            sp_fig(
                ["faded"],
                ncrop(layer, n_sugg, "h3-", cls="pm-board has-ai is-ai-focus"),
                gen=False,
                note="Another item is highlighted.",
            ),
            sp_fig(["hidden (layer off)"], ncrop(layer, n_sugg, "h4-", cls="pm-board"), gen=False),
            sp_fig(
                ["peek (layer off, item highlighted)"],
                ncrop(
                    layer,
                    n_sugg,
                    "h5-",
                    cls="pm-board",
                    ai_ui={"halo": {n_sugg: "is-ai-peek"}, "marks": {n_sugg: "is-ai-peek"}},
                ),
                gen=False,
            ),
        ],
        "236px",
    )
    add(
        "ai-square",
        "Node square",
        "Squares hang from the bottom-right corner, right of the centre line. Filled: named by the client. Outlined: our suggestion. The digits are the item id's.",
        [
            sp_fig(["named (filled)"], ncrop(layer, n_named, "q1-"), gen=not named),
            sp_fig(["suggested (outlined)"], ncrop(layer, n_sugg, "q2-"), gen=not sugg),
            sp_fig(["faded"], ncrop(layer, n_named, "q3-", cls="pm-board has-ai is-ai-focus"), gen=False),
            sp_fig(["hidden"], ncrop(layer, n_named, "q4-", cls="pm-board"), gen=False),
            sp_fig(
                ["peek"],
                ncrop(
                    layer,
                    n_named,
                    "q5-",
                    cls="pm-board",
                    ai_ui={"halo": {n_named: "is-ai-peek"}, "marks": {n_named: "is-ai-peek"}},
                ),
                gen=False,
            ),
            sp_fig(
                ["+n"], ncrop(v4, nid, "q6-"), gen=True, note="Four items on one step: two squares, then +2."
            ),
        ],
        "236px",
    )

    def bcrop(lv, pre, cls="pm-board has-ai", ai_ui=None, gutter=False, label="Band"):
        a, b = mk(lv, pre)
        x0 = 0 if gutter else GUT
        return crop(a, (x0, 0, a.W - x0, 52), am=b, ai_ui=ai_ui, cls=cls, gutter=gutter, label=label)

    vg = viewi["groups"][0] if viewi else m["groups"][1]["id"]
    vlayer = dict(
        layer,
        ai=[
            viewi
            or {
                "id": "AI-01",
                "title": "Check requests on arrival",
                "origin": "suggested",
                "does": "Checks each request.",
                "groups": [vg],
                "cite": (sugg or items[0])["cite"],
            }
        ],
    )
    add(
        "ai-view",
        "View underline",
        "A view item marks its group cell: a 2-unit underline at y 41 and its squares at the cell's right end.",
        [
            sp_fig(["default"], bcrop(vlayer, "v1-"), wide=True, gen=not viewi),
            sp_fig(
                ["on (band cell tinted)"],
                bcrop(vlayer, "v2-", ai_ui={"tint": vg, "view": {vg: "is-ai-on"}}),
                wide=True,
                gen=not viewi,
            ),
            sp_fig(["hidden"], bcrop(vlayer, "v3-", cls="pm-board"), wide=True, gen=not viewi),
            sp_fig(
                ["peek"],
                bcrop(vlayer, "v4-", cls="pm-board", ai_ui={"tint": vg, "view": {vg: "is-ai-peek"}}),
                wide=True,
                gen=not viewi,
            ),
        ],
    )
    alayer = dict(
        layer,
        ai=[
            alli
            or {
                "id": "AI-01",
                "title": "Keep one history",
                "origin": "suggested",
                "does": "Keeps one history.",
                "groups": "all",
                "cite": (sugg or items[0])["cite"],
            }
        ],
    )
    add(
        "ai-all",
        "All-views bracket",
        "An all-views item is drawn once: a bracket along the band's top edge, and ALL VIEWS with its squares in the gutter's band cell.",
        [
            sp_fig(["default"], bcrop(alayer, "a1-", gutter=True), wide=True, gen=not alli),
            sp_fig(
                ["on (every band cell tinted, nothing fades)"],
                bcrop(alayer, "a2-", gutter=True, ai_ui={"tint": "all", "all": "is-ai-on"}),
                wide=True,
                gen=not alli,
            ),
            sp_fig(["hidden"], bcrop(alayer, "a3-", gutter=True, cls="pm-board"), wide=True, gen=not alli),
            sp_fig(
                ["peek"],
                bcrop(alayer, "a4-", gutter=True, cls="pm-board", ai_ui={"tint": "all", "all": "is-ai-peek"}),
                wide=True,
                gen=not alli,
            ),
        ],
    )
    legend = board_template()[2]
    lg_on = fill(legend, {"legend-end": fill(F["legend-end"], client=esc(m["meta"]["client"]))})
    add(
        "ai-legend",
        "Legend block",
        "On the map, appended to the base legend. It fades to 40% with the layer off, and is left out when the layer has no items.",
        [
            sp_fig(["on"], f'<div style="width:392px;max-width:100%">{lg_on}</div>', gen=False),
            sp_fig(
                ["off"],
                f'<div style="width:392px;max-width:100%">{lg_on.replace("pm-legend", "pm-legend is-ai-off", 1)}</div>',
                gen=False,
            ),
            sp_fig(
                ["left out when ai is empty"],
                f'<div style="width:392px;max-width:100%">{fill(legend)}</div>',
                gen=True,
            ),
        ],
        "420px",
    )

    def tog(pressed, state, extra=""):
        return fill(F["toggle"], pressed=pressed, state=state).replace(
            'class="pm-ai-toggle"', f'class="pm-ai-toggle{extra}"'
        )

    add(
        "ai-toggle",
        "Toggle",
        "On the map, on at every load and not remembered. Off hides the marks; the view's legend block fades.",
        [
            sp_fig(["on"], tog("true", "On"), gen=False),
            sp_fig(["off"], tog("false", "Off"), gen=False),
            sp_fig(["hover"], tog("true", "On", " is-hover"), gen=False),
            sp_fig(["focus-visible"], tog("true", "On", " is-focus"), gen=False),
            sp_fig(["None when ai is empty"], F["toggle-none"], gen=True),
        ],
        "200px",
    )
    pid = (sugg or items[0])["id"]

    def preview(iid):
        a, b = mk(layer, "pv-")
        ns = by[iid].get("nodes") or [a.nodes[0].id]
        n0 = a.N[ns[0]]
        hit = {nid: "is-ai-hit is-ai-peek" for nid in ns}
        return crop(
            a,
            (n0.x - 18, n0.y - 20, CW + 36 + PITCH, CH + 50),
            ui={nid: "ai-hit" for nid in ns},
            am=b,
            ai_ui={"halo": hit, "marks": hit},
            cls="pm-board has-ai is-ai-focus",
            label=f"{iid} previewed",
        )

    add(
        "ai-pick",
        "Highlight squares",
        "On the map, one square per item in List order. Pressing one highlights its item on the board and pressing it again releases it; hovering previews.",
        [
            sp_fig(["none pressed (default)"], am.picks(), block=True, gen=False),
            sp_fig(["pressed"], am.picks(pid), block=True, gen=False),
            sp_fig(
                ["hover (preview)"],
                am.picks().replace(
                    f'class="pm-ai-pick is-{by[pid]["origin"]}" data-ai="{pid}"',
                    f'class="pm-ai-pick is-{by[pid]["origin"]} is-hover" data-ai="{pid}"',
                )
                + f'<div style="margin-top:12px">{preview(pid)}</div>',
                block=True,
                gen=False,
                note=f"Hovering {pid} previews it on the board: its steps stay and the rest steps back, without pressing it.",
            ),
        ],
        "420px",
    )
    add(
        "ai-empty",
        "Empty state",
        "ai: [] gives the List one dashed row, an empty AI lane in the Flow, and on the map the base board, the toggle reading None and no legend block.",
        [
            sp_fig(["ai: []"], page_with(dict(layer, ai=[]), "em-"), block=True, wide=True, gen=True),
        ],
    )
    tm, ta = mk(layer, "t-")
    add(
        "ai-tip",
        "Tooltip lines",
        "Through the tooltip-lines hook: one line per item on the step, then “Click to highlight it on the map”. There is one tooltip.",
        [
            sp_fig(
                ["a step with items"],
                f'<div class="pm-tip is-static sp-tipbox">{tm.tip(tm.N[n_sugg])}{ta.tip_lines()[n_sugg]}</div>',
                gen=False,
            ),
        ],
        "300px",
    )
    add(
        "ai-link",
        "Highlighting",
        "Frozen here with the real page code: Show on map (or a highlight square, or a click on a marked step) opens On the map with the item lit and the rest of the board stepped back; Esc releases it.",
        [
            sp_fig(
                ["item highlighted"],
                page_with(layer, "l1-", f"pin:{pid}"),
                block=True,
                wide=True,
                gen=False,
                note=f"{pid} highlighted.",
            ),
        ],
    )
    return sp_page(
        "AI opportunities: every element",
        "design-system/process-map-ai-opportunity · specimen",
        "Built from <code>examples/</code> by <code>design-system/process-map/build_map.py --specimen</code>. Each section is an element of the README's table, at its anchor; "
        'a state the examples lack is drawn from a generated variant of them, marked <span class="sp-gen">generated</span>.',
        {"toc": toc, "body": sections},
        ai=True,
    )


def _lane_only(am):
    """The Flow's AI lane alone, as its own svg (the AI lane specimen)."""
    fv = FlowView(am)
    lane, h = fv.ai_svg(14)
    return f'<svg class="pm-fl-svg" viewBox="0 0 {num(fv.W)} {num(h + 4)}" width="{num(fv.W)}" height="{num(h + 4)}" role="img" aria-label="AI lane">{lane}</svg>'


def build_specimens(ws):
    rules = load_rules()
    idx = Index(ws, rules)
    base = first("process-map", ws)
    layer = first("process-map-ai-opportunity", ws)
    pm = pm_specimen(ws, idx, base)
    ai = ai_specimen(ws, idx, base, layer)
    write(HERE / "specimen.html", pm)
    write(AI_DIR / "specimen.html", ai)
    WARNINGS.clear()  # the generated variants cut text on purpose ("long title", "long question")


# ------------------------------------------------------------------ CLI


def write(path, text):
    path = pathlib.Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    except OSError as e:
        raise CannotRun(f"cannot write {path}: {e.strerror or e}") from e


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] == "--specimen":
            if len(argv) != 2:
                raise CannotRun("usage: build_map.py --specimen <ws>")
            build_specimens(pathlib.Path(argv[1]))
        else:
            if len(argv) != 4:
                raise CannotRun("usage: build_map.py <ws> <section> <name> <out.html> | --specimen <ws>")
            ws, section, name, out = argv
            write(out, build_page(pathlib.Path(ws), section, name))
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        print(
            f"ERROR a map or record file is malformed ({type(e).__name__}: {e}) -> run bs.py check",
            file=sys.stderr,
        )
        return 1
    except DataError as e:
        for w in WARNINGS:
            print(f"WARN {w}", file=sys.stderr)
        print(f"ERROR {e}", file=sys.stderr)
        return 1
    except CannotRun as e:
        print(f"ERROR cannot run: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"ERROR cannot run: {e}", file=sys.stderr)
        return 2
    for w in WARNINGS:
        print(f"WARN {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

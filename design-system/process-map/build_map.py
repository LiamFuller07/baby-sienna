#!/usr/bin/env python3
"""build_map.py: one self-contained page from a map JSON plus its records, for both map sections.

  python3 design-system/process-map/build_map.py <ws> process-map <name> <out.html>
  python3 design-system/process-map/build_map.py <ws> process-map-ai-opportunity <name> <out.html>
  python3 design-system/process-map/build_map.py --specimen <ws>

The second form builds the base map named by the layer, then fills the board's slots from
design-system/process-map-ai-opportunity/fills.html. --specimen builds both gitignored specimen.html
files from <ws> (examples/), adding a generated variant for each state the examples lack.

Everything the READMEs call derived is computed here: columns, rows, coordinates and routes (README
section 2), badge numbers, detail lines, group meta, lane notes, {count:...} tokens, provenance lines,
the Sources card, the tooltips and the footer. The build fails on build-6 (a line crossing a card, or a
branch pill with no free stretch of its width plus 16). Same inputs, same bytes: no timestamps, no
random ids, and no build meta (bs.py adds that).

Standard library only. Exit codes: 0 ok, 1 data error, 2 cannot run.
"""
import html
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
_CH = (' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~'
       '’‘“”…·–—×→←↔▾■□¶éèàüöäçñ€£§°•')
_W400 = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
         556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
         500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469,
         556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
         278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 222, 222, 333, 333, 1000, 333, 556, 1000, 584,
         1000, 1000, 1000, 502, 604, 604, 537, 556, 556, 556, 556, 556, 556, 500, 556, 556, 556, 556, 400, 350]
_W700 = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
         556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278,
         556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584,
         556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556,
         333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 278, 278, 500, 500, 1000, 333, 556, 1000, 584,
         1000, 1000, 1000, 502, 604, 604, 556, 556, 556, 556, 611, 611, 556, 556, 611, 556, 556, 556, 400, 350]
_WIDTH = {False: dict(zip(_CH, _W400)), True: dict(zip(_CH, _W700))}
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
        rest = " ".join(lines[max_lines - 1:])
        lines = lines[:max_lines - 1] + [fit(rest + " …", size, bold, max_w).replace(" …", "…")]
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
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def fill(tpl, **kw):
    for k, v in kw.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    left = re.findall(r"\{\{[a-z-]+\}\}", tpl)
    if left:
        raise CannotRun(f"template placeholders left unfilled: {', '.join(sorted(set(left)))}")
    return tpl


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
                raise DataError(f"records/{p.name} is not valid JSON: {e}")
            kind = d.get("kind")
            if kind not in self.kinds:
                raise DataError(f"records/{p.name} has an unknown kind {kind!r}")
            recs = []
            for i, r in enumerate(d.get("records", [])):
                recs.append({"locator": r["locator"], "text": r["text"], "context": r.get("context"),
                             "key": self.unit_key(kind, r["locator"]), "i": i})
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


# ------------------------------------------------------------------ the Sources register

class Register:
    """Every record address the page uses, with the elements that use it (build-1, build-4)."""

    def __init__(self, idx, pre):
        self.idx, self.pre, self.entries = idx, pre, {}

    def add(self, ref, used):
        a = address(ref)
        e = self.entries.get(a)
        if not e:
            recs = self.idx.resolve(ref)
            e = self.entries[a] = {"kind": "rec" if len(recs) == 1 and ref.get("locator") else "span",
                                   "source": ref["source"], "loc": ref.get("locator") or "", "recs": recs,
                                   "address": a, "anchor": self.pre + anchor(a), "used": []}
        if used not in e["used"]:
            e["used"].append(used)
        return e

    def add_absent(self, ref, needle, used):
        a = address(ref)
        key = f"{a}\u0000{needle}"
        e = self.entries.get(key)
        if not e:
            recs = self.idx.resolve(ref)
            partial = self.idx.src[ref["source"]]["h"].get("coverage") != "complete"
            e = self.entries[key] = {"kind": "absent", "source": ref["source"], "loc": ref.get("locator") or "",
                                     "recs": recs, "address": a, "needle": needle, "partial": partial,
                                     "anchor": self.pre + anchor(a) + "-not-" + slug(needle), "used": []}
        if used not in e["used"]:
            e["used"].append(used)
        return e

    def cites(self, cites, used):
        """Register an element's citations; returns them with their entries, in order."""
        out = []
        for c in cites or []:
            t = ctype(c)
            if t == "grounded":
                out.append((c, [self.add(c, used)]))
            elif t == "inferred":
                out.append((c, [self.add(f, used) for f in c["from"]]))
            elif t == "absent":
                out.append((c, [self.add_absent(s, c["needle"], used) for s in c["in"]]))
        return out


def addr_link(e, text=None):
    return f'<a href="#{e["anchor"]}">{esc(text or e["address"])}</a>'


def prov_html(pairs, cls="pm-prov"):
    """FORMATS 2.6: one Gap clause, one Grounded clause, one Inferred clause per reading; each its own colour."""
    gaps = [(c, es) for c, es in pairs if ctype(c) == "absent"]
    grounded = [es[0] for c, es in pairs if ctype(c) == "grounded"]
    inferred = [(c, es) for c, es in pairs if ctype(c) == "inferred"]
    parts = []
    if gaps:
        bits, partial = [], False
        for c, es in gaps:
            for e in es:
                bits.append(f'not in {addr_link(e)}: “{esc(c["needle"])}”')
                partial = partial or e["partial"]
        tag = '<span class="pm-tag">Provisional</span>' if partial else ""
        parts.append(f'<span class="pm-prov-gap"><b>Gap</b> · {" · ".join(bits)}{tag}</span>')
    if grounded:
        parts.append(f'<span class="pm-prov-grounded"><b>Grounded</b> · {", ".join(addr_link(e) for e in grounded)}</span>')
    for c, es in inferred:
        parts.append(f'<span class="pm-prov-inferred"><b>Inferred</b> · {esc(c["reading"])} · from '
                     f'{", ".join(addr_link(e) for e in es)}</span>')
    return f'<span class="{cls}">{"".join(parts)}</span>' if parts else ""


# ------------------------------------------------------------------ prose with [SRC locator] markers

BRACKET = re.compile(r"(?<!\\)\[([^\[\]]+)\]")
BRACKET_PART = re.compile(r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)(?:\s+(.+))?$")


def marker_refs(text):
    refs = []
    for m in BRACKET.finditer(text):
        for part in m.group(1).split(";"):
            pm = BRACKET_PART.match(part.strip())
            if pm:
                refs.append({"source": pm.group(1), "locator": pm.group(2).strip()} if pm.group(2) else {"source": pm.group(1)})
    return refs


def prose_html(text, reg, used):
    """Claim prose: escaped, with each marker printed in place and linked to its Sources entry."""
    out, pos = [], 0
    for m in BRACKET.finditer(text):
        out.append(esc(text[pos:m.start()]))
        links = []
        for part in m.group(1).split(";"):
            pm = BRACKET_PART.match(part.strip())
            if not pm or pm.group(1) not in reg.idx.src:
                raise DataError(f"[{m.group(1)}] is not a citation (run bs.py check)")
            ref = {"source": pm.group(1), "locator": pm.group(2).strip()} if pm.group(2) else {"source": pm.group(1)}
            links.append(addr_link(reg.add(ref, used)))
        out.append(f'<cite class="pm-cite">[{"; ".join(links)}]</cite>')
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out).replace("\\[", "[").replace("\\]", "]")


# ------------------------------------------------------------------ geometry

GUT, X0, PITCH, CW, CH, ROW, EMPTY = 150, 166, 188, 156, 104, 144, 56
HALF = 60.2 * 2 ** 0.5 / 2          # half diagonal of the decision square: 42.57
BAND_TOP, BAND_BOT, LANES_BAND, LANES_PLAIN = 8, 44, 52, 18
MAX_COLUMNS = 14
LABEL_RESERVE = 70                   # right end of a band cell kept for a view's squares (AI section 2)
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
            return self.y + eps < y1 < self.y + CH - eps and min(x1, x2) < self.x + CW - eps and max(x1, x2) > self.x + eps
        return self.x + eps < x1 < self.x + CW - eps and min(y1, y2) < self.y + CH - eps and max(y1, y2) > self.y + eps


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

    def __init__(self, m, idx, where, pre=""):
        self.m, self.idx, self.where, self.pre = m, idx, where, pre
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
        self.lane_ix = {l["id"]: i for i, l in enumerate(self.lanes)}
        self.group_ix = {g["id"]: i for i, g in enumerate(self.groups)}
        for n in self.nodes:
            if n.d["lane"] not in self.lane_ix:
                raise DataError(f"{where}: {n.id} names lane {n.d['lane']!r}, which is not in lanes[] (map-1)")
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
                    raise DataError(f"{self.where}: {n.id} has col {n.d['col']}, left of its derived column {c} (map-10)")
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
            raise DataError(f"{self.where}: the board needs {start} columns, more than {MAX_COLUMNS} (map-10): split the map")
        rows, seen = {}, {}
        for n in nodes:
            k = (n.d["lane"], col[n.id])
            rows[n.id] = seen.get(k, 0)
            seen[k] = rows[n.id] + 1
        self.lane_rows = {l["id"]: 0 for l in self.lanes}
        for n in nodes:
            self.lane_rows[n.d["lane"]] = max(self.lane_rows[n.d["lane"]], rows[n.id] + 1)
        y = LANES_BAND if self.band else LANES_PLAIN
        self.lanes_top = y
        self.lane_geo = {}
        for l in self.lanes:
            h = ROW * self.lane_rows[l["id"]] or EMPTY
            self.lane_geo[l["id"]] = (y, h)
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

    def badge_pos(self, n, i):
        if n.dec:
            return (n.cx - 22 - 24 * i, n.cy - HALF + 6)
        return (n.x + 24 * i, n.y)

    def marks(self):
        """Every badge, system icon and chip on the board, as boxes (x0, y0, x1, y1), for pill placement."""
        out = []
        for n in self.nodes:
            b = self.badge[n.id]
            for i in range(min(len(b), 3)):
                x, y = self.badge_pos(n, i)
                out.append((x - 11, y - 11, x + 11, y + 11))
            if len(b) > 3:
                x, y = self.badge_pos(n, 3)
                out.append((x - 14, y - 8, x + 14, y + 8))
            sy = n.d.get("systems", [])
            for i in range(min(len(sy), 2)):
                out.append((n.x + CW - 24 * i - 11, n.y - 11, n.x + CW - 24 * i + 11, n.y + 11))
            if len(sy) > 2:
                out.append((n.x + CW - 64, n.y - 8, n.x + CW - 36, n.y + 8))
            if n.dec:
                out.append((n.cx - 70, n.cy + HALF, n.cx + 90, n.cy + HALF + 26))
        return out

    # -- routing (README section 2, the case table) and build-6
    def clear_route(self, points):
        return not any(n.crosses(a, b) for a, b in zip(points, points[1:]) for n in self.nodes)

    def free_pill(self, points, width, placed):
        """Longest horizontal stretch clear of cards, badges, detail text and earlier labels."""
        best = None
        for a, b in zip(points, points[1:]):
            if a[1] != b[1]:
                continue
            y, lo, hi = a[1], min(a[0], b[0]), max(a[0], b[0])
            blocked = []
            for n in self.nodes:
                if n.dec and abs(y - n.cy) < HALF + 9:
                    blocked.append((n.cx - HALF, n.cx + HALF))
                elif not n.dec and n.y - 9 < y < n.y + CH + 9:
                    blocked.append((n.x, n.x + CW))
            for bx0, by0, bx1, by1 in self.marks() + placed:
                if by0 - 9 < y < by1 + 9:
                    blocked.append((bx0, bx1))
            free = [(lo, hi)]
            for c0, c1 in sorted(blocked):
                free = [(x, z) for f0, f1 in free for x, z in
                        ([(f0, f1)] if c1 <= f0 or c0 >= f1 else
                         ([(f0, c0)] if c0 > f0 else []) + ([(c1, f1)] if c1 < f1 else []))]
            for f0, f1 in free:
                if f1 - f0 >= width + 16 and (best is None or f1 - f0 > best[2] - best[1]):
                    best = (y, f0, f1)
        return best

    def detour(self, source, target, width=0, placed=None):
        """Deterministic orthogonal fallback through column gaps and row channels.

        Endpoints keep their identity and direction. Never change graph edges or
        relax collision checks just to get a page to build.
        """
        placed = placed or []
        channels = sorted({max(self.lanes_top + 4, min(self.H - 12, y))
                           for n in self.nodes for y in (n.y - 24, n.y - 12, n.y + CH + 12, n.y + CH + 24)})
        choices = []
        for sp in ('R', 'L'):
            a = source.port(sp)
            sx = source.x + CW + 16 if sp == 'R' else source.x - 12
            for tp in ('L', 'R'):
                end = target.port(tp)
                tx = target.x - 12 if tp == 'L' else target.x + CW + 16
                for y in channels:
                    pts = simplify([a, (sx, a[1]), (sx, y), (tx, y), (tx, end[1]), end])
                    if not self.clear_route(pts):
                        continue
                    pill = self.free_pill(pts, width, placed) if width else None
                    if width and pill is None:
                        continue
                    cost = sum(abs(b[0]-a[0]) + abs(b[1]-a[1]) for a,b in zip(pts,pts[1:]))
                    cost += (16 if sp == 'L' else 0) + (16 if tp == 'R' else 0)
                    choices.append((cost, sp, tp, y, pts, pill))
        if not choices:
            return None
        best = min(choices, key=lambda c: c[:4])
        return best[4], best[5]

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
                    p = next((q for q in (want, "B" if want == "T" else "T", "R") if q not in used_ports[s.id]), "R")
                used_ports[s.id].add(p)
                port[id(e)] = p
        errors = []
        self.routes = []
        for k, e in enumerate(self.edges):
            s, t = self.N[e["from"]], self.N[e["to"]]
            if s is t:
                raise DataError(f"{self.where}#/edges/{k}: {s.id} -> {t.id} is a self-loop (map-5)")
            feedback = ix[t.id] < ix[s.id]
            if feedback:
                ch = s.cy - 52 - 10
                end = t.port("T") if t.cy >= s.cy else t.port("B")
                pts = [s.port("T"), (s.cx, ch), (t.cx, ch), end]
            else:
                p = port.get(id(e), "R")
                gx = t.x - 16
                tl = t.port("L")
                if p == "R":
                    a = s.port("R")
                    pts = [a, tl] if abs(t.cy - s.cy) < 0.01 else [a, (gx, a[1]), (gx, t.cy), tl]
                else:
                    v = s.port(p)
                    if abs(t.cy - s.cy) > 0.01:
                        pts = [v, (s.cx, t.cy), tl]
                    else:
                        ch = s.cy - 62 if p == "T" else s.cy + 52 + 16
                        pts = [v, (s.cx, ch), (gx, ch), (gx, t.cy), tl]
            pts = simplify(pts)
            name = f"{self.where}#/edges/{k} ({s.id} -> {t.id})"
            if not self.clear_route(pts):
                alternative = self.detour(s, t)
                if alternative:
                    pts = alternative[0]
            for a, b in zip(pts, pts[1:]):
                for n in self.nodes:
                    if n.crosses(a, b):
                        errors.append(f"build-6 {name}: the line crosses {n.id} -> set col on a node to open a column, or reorder the nodes")
                        break
                else:
                    continue
                break
            self.routes.append({"e": e, "k": k, "pts": pts, "feedback": feedback, "pill": None})
        # pills: centred on the longest free horizontal stretch
        marks = self.marks()
        placed = []
        for r in self.routes:
            e = r["e"]
            if e.get("kind") != "conditional" or not e.get("label"):
                continue
            label = e["label"]
            w = tw(label, 11, True) + 14
            best = None
            for a, b in zip(r["pts"], r["pts"][1:]):
                if a[1] != b[1]:
                    continue
                y, lo, hi = a[1], min(a[0], b[0]), max(a[0], b[0])
                blocked = []
                for n in self.nodes:
                    if n.dec:
                        if abs(y - n.cy) < HALF + 9:
                            blocked.append((n.cx - HALF, n.cx + HALF))
                    elif n.y - 9 < y < n.y + CH + 9:
                        blocked.append((n.x, n.x + CW))
                for (bx0, by0, bx1, by1) in marks + placed:
                    if by0 - 9 < y < by1 + 9:
                        blocked.append((bx0, bx1))
                free = [(lo, hi)]
                for (c0, c1) in sorted(blocked):
                    nxt = []
                    for (f0, f1) in free:
                        if c1 <= f0 or c0 >= f1:
                            nxt.append((f0, f1))
                            continue
                        if c0 > f0:
                            nxt.append((f0, c0))
                        if c1 < f1:
                            nxt.append((c1, f1))
                    free = nxt
                for (f0, f1) in free:
                    if best is None or f1 - f0 > best[2] - best[1]:
                        best = (y, f0, f1)
            name = f"{self.where}#/edges/{r['k']} ({e['from']} -> {e['to']}, “{label}”)"
            if best is None or best[2] - best[1] < w + 16:
                alternative = self.detour(self.N[e['from']], self.N[e['to']], w, placed)
                if alternative:
                    r['pts'], best = alternative
            if best is None or best[2] - best[1] < w + 16:
                have = 0 if best is None else best[2] - best[1]
                errors.append(f"build-6 {name}: the pill needs a free stretch of {num(w + 16)} units and has {num(have)} "
                              f"-> shorten the label, or set col on its target to open a column")
                continue
            px = (best[1] + best[2]) / 2
            r["pill"] = (px, best[0], w, label)
            placed.append((px - w / 2, best[0] - 9, px + w / 2, best[0] + 9))
        if errors:
            raise DataError("\n".join(errors))

    # -- derived text: counts, notes, detail lines, provenance, tooltips, cards, sources
    def counts(self):
        return {"steps": sum(1 for n in self.nodes if not n.dec), "decisions": sum(1 for n in self.nodes if n.dec),
                "groups": len(self.groups), "gaps": len(self.gaps), "clarifications": len(self.clars),
                "systems": len(self.systems)}

    def fill_counts(self, text):
        c = self.counts()
        def one(m):
            if m.group(1) not in c:
                raise DataError(f"{self.where}#/meta/subtitle: {{count:{m.group(1)}}} is not a count selector (prose-5)")
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
        self.used = {}
        # file order: systems, lanes, nodes, gaps, clarifications (the AI layer adds its items after)
        for s in self.m.get("systems", []):
            reg.cites(s["cite"], (s["label"], None))
        for l in self.lanes:
            reg.cites(l.get("cite"), (l["label"], None))
        self.npairs = {}
        for n in self.nodes:
            self.npairs[n.id] = reg.cites(n.d["cite"], (n.id, pre + n.id))
        self.gap_html = []
        for i, g in enumerate(self.gaps):
            u = (g["id"], pre + g["id"])
            text = prose_html(g["text"], reg, u)
            title = prose_html(g["title"], reg, u)
            pairs = reg.cites(g["cite"], u)
            self.gap_html.append((g, i + 1, title, text, prov_html(pairs)))
        self.clar_html = []
        for i, c in enumerate(self.clars):
            u = (c["id"], pre + c["id"])
            title, shows, ask = (prose_html(c[k], reg, u) for k in ("title", "shows", "ask"))
            pairs = reg.cites(c["cite"], u)
            self.clar_html.append((c, i + 1, title, shows, ask, prov_html(pairs)))

    def detail(self, n):
        """The derived detail line: (prefix, linked entry or None, suffix), or an inferred reading."""
        pairs = self.npairs[n.id]
        grounded = [es[0] for c, es in pairs if ctype(c) == "grounded"]
        if n.state == "inferred" or not grounded:
            inf = next((c for c, es in pairs if ctype(c) == "inferred"), None)
            return ("inferred", f"Inferred · {inf['reading']}" if inf else n.id)
        more = f" +{len(grounded) - 1}" if len(grounded) > 1 else ""
        return ("grounded", f"{n.id} · ", grounded[0], more)

    def tip(self, n):
        g = self.groups[self.group_ix[n.d["group"]]] if self.groups else None
        head = f"{n.id} · {g['id']} {g['label']}" if g else n.id
        rows = [("Lane", self.lanes[self.lane_ix[n.d["lane"]]]["label"])]
        if n.d.get("owner"):
            rows.append(("Owner", n.d["owner"]))
        if n.d.get("systems"):
            rows.append(("Systems", ", ".join(self.systems[s]["label"] for s in n.d["systems"])))
        s = f'<span class="pm-tip-id">{esc(head)}</span><span class="pm-tip-title">{esc(n.d["title"])}</span>'
        s += "".join(f'<span class="pm-tip-row"><b>{k}:</b> {esc(v)}</span>' for k, v in rows)
        for kind, i, _id, title in self.badge[n.id]:
            word = "Gap" if kind == "gap" else "To confirm"
            s += (f'<span class="pm-tip-mark"><span class="pm-tip-mk is-{kind}">{i}</span>'
                  f'<span>{word}: {esc(title)}</span></span>')
        return s + prov_html(self.npairs[n.id])


# ------------------------------------------------------------------ SVG rendering of the base board

def text_lines(cls, x, y, lines, lead, anchor_mid=True):
    a = ' text-anchor="middle"' if anchor_mid else ""
    sp = "".join(f'<tspan x="{num(x)}" dy="{lead if i else 0}">{esc(t)}</tspan>' for i, t in enumerate(lines))
    return f'<text class="{cls}" x="{num(x)}" y="{num(y)}"{a}>{sp}</text>'


def chip(cx, cy, label):
    w = tw(label, 9.5, True) + 10
    return (f'<g class="pm-more"><rect class="pm-more-bg" x="{num(cx - w / 2)}" y="{num(cy - 8)}" width="{num(w)}" '
            f'height="16" rx="8"/><text class="pm-more-text" x="{num(cx)}" y="{num(cy + 3.5)}">{esc(label)}</text></g>')


def badge_svg(mm, kind, i, cid, x, y):
    word = "Gap" if kind == "gap" else "Clarification"
    return (f'<a class="pm-badge-link" href="#{mm.pre}{cid}" aria-label="{word} {i}"><g class="pm-badge pm-badge-{kind}">'
            f'<circle class="pm-badge-ring" cx="{num(x)}" cy="{num(y)}" r="11"/>'
            f'<text class="pm-badge-num" x="{num(x)}" y="{num(y + 4)}">{i}</text></g></a>')


def sys_svg(mm, sid, cx, cy):
    s = mm.systems[sid]
    return (f'<g class="pm-sys"><circle class="pm-sys-bg" cx="{num(cx)}" cy="{num(cy)}" r="11"/>'
            f'<g class="pm-ic" transform="translate({num(cx - 6.5)},{num(cy - 6.5)}) scale(0.81)">{ICONS[s["icon"]]}</g></g>')


def node_svg(mm, n, ui=""):
    x, y, cx = n.x, n.y, n.cx
    cls = f"pm-node is-{n.state}" + (f" is-{ui}" if ui else "")
    lab = esc(f"{n.id} {n.d['title']}")
    s = (f'<g class="{cls}" id="{mm.pre}{n.id}" data-node="{n.id}" data-tip="{n.id}" tabindex="0" role="group" aria-label="{lab}">'
         f'<rect class="pm-focus-ring" x="{num(x - 8)}" y="{num(y - 8)}" width="{CW + 16}" height="{CH + 16}" rx="4"/>'
         f'<rect class="pm-node-rect is-{n.state}" x="{num(x)}" y="{num(y)}" width="{CW}" height="{CH}" rx="2"/>')
    title, cut = wrap_bal(n.d["title"], 12, True, CW - 24, 3)
    if cut:
        warn(f"build-6 {mm.where}: the title of {n.id} is cut with … on its card")
    low = []
    if n.d.get("owner"):
        low.append(("owner", fit(n.d["owner"], 9.5, True, CW - 12)))
    det = mm.detail(n)
    if det[0] == "inferred":
        lines, c2 = wrap_bal(det[1], 9.5, False, CW - 12, 2)
        if c2:
            warn(f"build-6 {mm.where}: the reading on {n.id} is cut with … on its card")
        low += [("inf", t) for t in lines]
    else:
        low.append(("detail", det))
    ys = [70, 83, 96][-len(low):] if len(low) == 3 else ([70, 83] if len(low) == 2 else [83])
    if n.state == "gap" and len(low) == 3:
        ys = [57, 70, 83]
    if not low and n.state != "gap":
        ty = y + CH / 2 - (len(title) - 1) * 6.5 + 4
    else:
        ty = y + 24
    s += text_lines("pm-node-title", cx, ty, title, 13)
    for (k, v), dy in zip(low, ys):
        yy = y + dy
        if k == "owner":
            s += f'<text class="pm-node-owner" x="{num(cx)}" y="{num(yy)}" text-anchor="middle">{esc(v)}</text>'
        elif k == "inf":
            s += f'<text class="pm-node-detail" x="{num(cx)}" y="{num(yy)}" text-anchor="middle">{esc(v)}</text>'
        else:
            s += detail_svg(mm, n, v, cx, yy, CW - 12)
    if n.state == "gap":
        s += f'<text class="pm-node-tag" x="{num(cx)}" y="{num(y + 96)}" text-anchor="middle">Needs confirmation</text>'
    b = mm.badge[n.id]
    for i, (kind, k, cid, _t) in enumerate(b[:3]):
        bx, by = mm.badge_pos(n, i)
        s += badge_svg(mm, kind, k, cid, bx, by)
    if len(b) > 3:
        s += chip(x + 72 + 4, y, f"+{len(b) - 3}")
    sy = n.d.get("systems", [])
    for i, sid in enumerate(sy[:2]):
        s += sys_svg(mm, sid, x + CW - 24 * i, y)
    if len(sy) > 2:
        s += chip(x + CW - 52, y, f"+{len(sy) - 2}")
    return s + "</g>"


def detail_svg(mm, n, det, cx, yy, max_w, anchor_mid=True):
    _, prefix, e, more = det
    full = prefix + e["address"] + more
    a = ' text-anchor="middle"' if anchor_mid else ""
    if tw(full, 9.5) > max_w:
        warn(f"build-6 {mm.where}: the detail line of {n.id} is cut with …")
        return f'<text class="pm-node-detail" x="{num(cx)}" y="{num(yy)}"{a}>{esc(fit(full, 9.5, False, max_w))}</text>'
    return (f'<text class="pm-node-detail" x="{num(cx)}" y="{num(yy)}"{a}>{esc(prefix)}<a class="pm-node-link" '
            f'href="#{e["anchor"]}"><tspan class="pm-node-cite">{esc(e["address"])}</tspan></a>{esc(more)}</text>')


def decision_svg(mm, n, ui=""):
    cx, cy = n.cx, n.cy
    cls = f"pm-decision-group is-{n.state}" + (f" is-{ui}" if ui else "")
    rot = f'transform="rotate(45 {num(cx)} {num(cy)})"'
    a = 30.1
    s = (f'<g class="{cls}" id="{mm.pre}{n.id}" data-node="{n.id}" data-tip="{n.id}" tabindex="0" role="group" '
         f'aria-label="{esc(n.id + " " + n.d["title"])}">'
         f'<rect class="pm-focus-ring" x="{num(cx - a - 6)}" y="{num(cy - a - 6)}" width="{num(2 * a + 12)}" height="{num(2 * a + 12)}" rx="4" {rot}/>'
         f'<rect class="pm-decision is-{n.state}" x="{num(cx - a)}" y="{num(cy - a)}" width="60.2" height="60.2" rx="2" {rot}/>')
    lines, cut = wrap_bal(n.d["title"], 11, True, 64, 2)
    if cut:
        warn(f"build-6 {mm.where}: the question of {n.id} is cut with … in its diamond")
    y0 = cy - 2 if len(lines) > 1 else cy + 4
    s += text_lines("pm-decision-label", cx, y0, lines, 12)
    det = mm.detail(n)
    yy = cy + HALF + 12
    bottom_used = any(r["pts"][0] == (round(cx, 2), round(cy + HALF, 2)) for r in mm.routes if r["e"]["from"] == n.id)
    if det[0] == "inferred":
        lines, c2 = wrap(det[1], 9.5, False, 168, 2)
        if c2:
            warn(f"build-6 {mm.where}: the reading on {n.id} is cut with …")
        if bottom_used:
            s += text_lines("pm-node-detail", cx + 6, yy, lines, 11, anchor_mid=False)
        else:
            s += text_lines("pm-node-detail", cx, yy, lines, 11)
    elif bottom_used:   # a branch leaves the bottom vertex: id, then address, right of the line
        _, prefix, e, more = det
        addr = e["address"] + more
        if tw(addr, 9.5) > 82:
            warn(f"build-6 {mm.where}: the detail line of {n.id} is cut with …")
            link = esc(fit(addr, 9.5, False, 82))
        else:
            link = (f'<a class="pm-node-link" href="#{e["anchor"]}"><tspan class="pm-node-cite">{esc(e["address"])}</tspan></a>{esc(more)}')
        s += (f'<text class="pm-node-detail" x="{num(cx + 6)}" y="{num(yy)}">{esc(n.id)}'
              f'<tspan x="{num(cx + 6)}" dy="11">{link}</tspan></text>')
    else:
        s += detail_svg(mm, n, det, cx, yy, 168)
    b = mm.badge[n.id]
    for i, (kind, k, cid, _t) in enumerate(b[:3]):
        bx, by = mm.badge_pos(n, i)
        s += badge_svg(mm, kind, k, cid, bx, by)
    if len(b) > 3:
        bx, by = mm.badge_pos(n, 3)
        s += chip(bx - 2, by, f"+{len(b) - 3}")
    return s + "</g>"


def path_d(pts):
    return "M " + " L ".join(f"{num(x)} {num(y)}" for x, y in pts)


def arrow(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = (dx * dx + dy * dy) ** 0.5 or 1
    ux, uy = dx / ln, dy / ln
    bx, by = b[0] - ux * 5, b[1] - uy * 5
    px, py = -uy * 3.4, ux * 3.4
    return (f'<polygon class="pm-arrow" points="{num(b[0])},{num(b[1])} {num(bx + px)},{num(by + py)} '
            f'{num(bx - px)},{num(by - py)}"/>')


def edges_svg(mm, ui=None):
    s = ""
    for r in mm.routes:
        e, d = r["e"], path_d(r["pts"])
        cls = "pm-feed" if r["feedback"] else "pm-flow"
        kind = ("is-feedback " if r["feedback"] else "") + ("is-branch" if e.get("kind") == "conditional" else "is-flow")
        extra = " is-hover" if ui and (e["from"], e["to"]) in ui else ""
        s += (f'<g class="pm-edge {kind.strip()}{extra}" data-from="{e["from"]}" data-to="{e["to"]}">'
              f'<path class="pm-hit" d="{d}"/><path class="{cls}" d="{d}"/>{arrow(r["pts"][-2], r["pts"][-1])}</g>')
    return s


def pills_svg(mm):
    s = ""
    for r in mm.routes:
        if not r["pill"]:
            continue
        px, py, w, label = r["pill"]
        s += (f'<g class="pm-pill-g"><rect class="pm-pill" x="{num(px - w / 2)}" y="{num(py - 9)}" width="{num(w)}" height="18" rx="9"/>'
              f'<text class="pm-pill-text" x="{num(px)}" y="{num(py + 3.8)}">{esc(label)}</text></g>')
    return s


def lane_label_svg(label, y, h, note, lx=14, max_w=128):
    lines, cut = wrap(label, 15, True, max_w, 3 if h > EMPTY else 2)
    lh = 17
    block = (len(lines) - 1) * lh + (16 if note else 0)
    ty = y + h / 2 - block / 2 + 5
    s = f'<g class="pm-lane-head">' + text_lines("pm-lane-label", lx, ty, lines, lh, anchor_mid=False)
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
    for i, l in enumerate(mm.lanes):
        y, h = mm.lane_geo[l["id"]]
        members = [n for n in mm.nodes if n.d["lane"] == l["id"]]
        note = mm.note(members) if members else ""
        gut += f'<rect class="pm-lane-{i % 2}" y="{num(y)}" width="{GUT}" height="{num(h)}"/>'
        lbl, cut = lane_label_svg(l["label"], y, h, note)
        if cut:
            warn(f"build-6 {mm.where}: the lane label {l['label']!r} is cut with …")
        gut += lbl
        lanes += f'<rect class="pm-lane-{i % 2}" x="{GUT}" y="{num(y)}" width="{num(W - GUT)}" height="{num(h)}"/>'
        if not members:
            lanes += f'<text class="pm-lane-empty" x="{GUT + 16}" y="{num(y + h / 2 + 4)}">No steps in this lane</text>'
        lane_data.append([l["label"], y, h, note])
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
            band += (f'<g class="pm-group{tcls}" id="{mm.pre}{g["id"]}" data-group="{g["id"]}">'
                     f'<rect class="pm-band-cell" x="{num(gx)}" y="{BAND_TOP}" width="{num(gw)}" height="{BAND_BOT - BAND_TOP}"/>')
            if gi:
                band += f'<line class="pm-band-sep" x1="{num(x0)}" y1="14" x2="{num(x0)}" y2="34"/>'
            band += (f'<text x="{num(gx + 8)}" y="23"><tspan class="pm-band-id">{esc(g["id"])}</tspan>'
                     f'<tspan class="pm-band-label" dx="6">{esc(label)}</tspan></text>'
                     f'<text class="pm-band-meta" x="{num(gx + 8)}" y="35.5">{esc(mm.note(members))}</text></g>')
        band += f'<line class="pm-band-line" x1="{GUT}" y1="{BAND_BOT}" x2="{num(W)}" y2="{BAND_BOT}"/></g>'
    nodes = ""
    for n in mm.nodes:
        if not n.dec:
            nodes += node_svg(mm, n, ui.get(n.id, ""))
    for n in mm.nodes:
        if n.dec:
            nodes += decision_svg(mm, n, ui.get(n.id, ""))
    data = {"w": round(W, 2), "h": round(H, 2), "lanes": lane_data,
            "tips": {n.id: mm.tip(n) for n in mm.nodes}}
    return {"gutter": gut, "lanes": lanes, "band": band, "edges": edges_svg(mm, ui.get("edges")),
            "nodes": nodes, "pills": pills_svg(mm), "data": data}


# ------------------------------------------------------------------ HTML around the board

def header_html(meta, systems, kicker, title, subtitle):
    flags = meta.get("flags", [])
    chips = "".join(f'<span class="pm-flag{" is-confidential" if f == "confidential" else ""}">'
                    f'{"Confidential" if f == "confidential" else "Draft"}</span>' for f in flags)
    flags_html = f'<div class="pm-flags">{chips}</div>' if chips else ""
    s = f'<div class="pm-kicker-row"><p class="pm-kicker">{esc(kicker)}</p>{flags_html}</div><h1>{esc(title)}</h1>'
    if subtitle:
        s += f'<p class="pm-subtitle">{esc(subtitle)}</p>'
    syss = systems
    if syss:
        s += ('<ul class="pm-key" aria-label="Systems">' + "".join(
            f'<li>{icon_svg(x["icon"])}{esc(x["label"])}</li>' for x in syss) + "</ul>")
    return s


def gaps_html(mm, target=None):
    pre = mm.pre
    if not mm.gap_html:
        body = ('<p class="pm-ev-empty"><span class="pm-ev-empty-mk" aria-hidden="true">0</span><span>'
                '<strong>No gaps on this map.</strong>Every step has at least one source.</span></p>')
    else:
        body = '<ol class="pm-ev-list pm-ev-gaps">'
        for g, i, title, text, prov in mm.gap_html:
            t = ' class="is-target"' if target == g["id"] else ""
            steps = ", ".join(f'<a href="#{pre}{x}">{x}</a>' for x in g["nodes"])
            body += (f'<li id="{pre}{g["id"]}" data-n="{i}"{t}><strong>{title}</strong>{text}'
                     f'<span class="pm-ev-steps">Steps: {steps}</span>{prov}</li>')
        body += "</ol>"
    return f'<article class="pm-ev-card" id="{pre}gaps"><h2>Gaps</h2>{body}</article>'


def clar_html(mm, target=None):
    pre = mm.pre
    if not mm.clar_html:
        body = ('<p class="pm-ev-empty"><span class="pm-ev-empty-mk" aria-hidden="true">0</span><span>'
                '<strong>Nothing to confirm on this map.</strong></span></p>')
    else:
        body = '<ol class="pm-ev-list pm-ev-clar">'
        for c, i, title, shows, ask, prov in mm.clar_html:
            t = ' class="is-target"' if target == c["id"] else ""
            steps = ", ".join(f'<a href="#{pre}{x}">{x}</a>' for x in c["nodes"])
            body += (f'<li id="{pre}{c["id"]}" data-n="{i}"{t}><strong>{title}</strong>'
                     f'<span class="pm-ev-row"><b>What the sources show:</b> {shows}</span>'
                     f'<span class="pm-ev-row"><b>To confirm:</b> {ask}</span>'
                     f'<span class="pm-ev-steps">Steps: {steps}</span>{prov}</li>')
        body += "</ol>"
    return f'<article class="pm-ev-card" id="{pre}clarifications"><h2>Clarifications needed</h2>{body}</article>'


def rec_line(r):
    ctx = f' · {esc(r["context"])}' if r.get("context") else ""
    return f'<b>{esc(r["locator"])}</b>{ctx} · <q>{esc(r["text"])}</q>'


def sources_html(reg, target=None, only=None):
    """FORMATS 2.6: grouped by source in id order; entries in reading order; Used by names each element."""
    idx = reg.idx
    by_src = {}
    for e in reg.entries.values():
        by_src.setdefault(e["source"], []).append(e)
    out = ""
    for sid in sorted(by_src):
        if only and sid not in only:
            continue
        h = idx.src[sid]["h"]
        bits = [esc(h["title"])]
        if h.get("detail"):
            bits.append(esc(h["detail"]))
        bits.append(esc(idx.label(sid)))
        if h["kind"] == "web" and h.get("url"):
            bits.append(esc(domain(h["url"])))
        bits.append(f'captured {pdate(h["captured"])}')
        items = sorted(by_src[sid], key=lambda e: (e["recs"][0]["i"] if e["loc"] else -1, e["kind"] == "absent",
                                                   e["kind"] == "span", e["address"], e.get("needle", "")))
        rows = ""
        for e in items:
            t = ' class="is-target"' if target == e["anchor"] else ""
            loc = e["loc"] or "Whole source"
            if e["kind"] == "absent":
                state = "PROVISIONAL" if e["partial"] else "PROVEN"
                body = f'<span class="pm-src-absent">Searched for “{esc(e["needle"])}”: not found · {state}</span>'
            elif e["kind"] == "rec":
                r = e["recs"][0]
                body = (f'{esc(r["context"])} · ' if r.get("context") else "") + f'<q>{esc(r["text"])}</q>'
            else:
                recs = e["recs"]
                lis = "".join(f"<li>{rec_line(r)}</li>" for r in recs[:10])
                remaining = ''.join(f'<li>{rec_line(r)}</li>' for r in recs[10:])
                more = (f'<li><details><summary>{len(recs) - 10} more records</summary>'
                        f'<ul>{remaining}</ul></details></li>') if remaining else ""
                body = f'{plural(len(recs), "record")}<ul class="pm-src-recs">{lis}{more}</ul>'
            used = ", ".join(f'<a href="#{href}">{esc(name)}</a>' if href else esc(name) for name, href in e["used"])
            rows += (f'<li id="{e["anchor"]}"{t}><span class="pm-src-loc">{esc(loc)}</span>'
                     f'<span class="pm-src-body">{body}</span><span class="pm-src-used">Used by {used}</span></li>')
        out += (f'<div class="pm-src" id="{reg.pre}src-{slug(sid)}"><p class="pm-src-head"><b>{esc(sid)}</b> · '
                f'{" · ".join(bits)}</p><ol class="pm-src-list">{rows}</ol></div>')
    return f'<article class="pm-ev-card pm-ev-wide" id="{reg.pre}sources"><h2>Sources</h2>{out}</article>'


def footer_html(meta, date):
    left = meta.get("footer") or "Source · process map"
    right = []
    if "confidential" in meta.get("flags", []):
        right.append(f'Contains {meta["client"]} confidential information')
    if "draft" in meta.get("flags", []):
        right.append("Draft")
    right.append(pdate(date))
    return f'<footer class="pm-footer"><span>{esc(left)}</span><span>{esc(" · ".join(right))}</span></footer>'


# ------------------------------------------------------------------ templates

def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as e:
        raise CannotRun(f"cannot read {path}: {e}")


def board_template():
    t = read(BOARD_HTML)
    t = re.sub(r"^<!doctype html>\n<!--.*?-->\n", "<!doctype html>\n", t, count=1, flags=re.S)
    m = re.search(r"<!--bs:shell-->\n(.*?)<!--/bs:shell-->\n", t, re.S)
    if not m:
        raise CannotRun("board.html has no <!--bs:shell--> block")
    return t, m.group(1)


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


SLOTS = ("style", "legend-end", "toolbar", "board-over:gutter", "board-under", "board-over", "evidence-start", "script")


def fill_slots(t, slots):
    for k in SLOTS:
        t = t.replace(f"<!--slot:{k}-->", slots.get(k, ""))
    return t


def shell_html(shell_tpl, mm, parts, label, zoom="fit", slots=None):
    s = fill(shell_tpl, pre=mm.pre, label=esc(label), fit=str(zoom != "100").lower(), full=str(zoom == "100").lower(),
             zoom=zoom, h=num(mm.H), cw=num(mm.W - GUT), gutter=parts["gutter"], lanes=parts["lanes"],
             band=parts["band"], edges=parts["edges"], nodes=parts["nodes"], pills=parts["pills"], data=jdump(parts["data"]))
    return fill_slots(s, slots or {})


# ------------------------------------------------------------------ the AI layer (fills the slots)

AI_WORD = {"named": "Named by the client", "suggested": "Our suggestion"}
SQ = 16


class AiModel:
    def __init__(self, layer, mm, where):
        self.layer, self.mm, self.where = layer, mm, where
        self.items = layer.get("ai", [])
        self.by_node, self.by_group, self.all = {}, {}, []
        for it in self.items:
            for nid in it.get("nodes", []):
                n = mm.N.get(nid)
                if not n or n.dec:
                    raise DataError(f"{where}: {it['id']} lists {nid!r}, which is not a step of the base (ai-2)")
                self.by_node.setdefault(nid, []).append(it)
            g = it.get("groups", [])
            if g == "all":
                self.all.append(it)
            else:
                for gid in g:
                    if gid not in mm.group_ix or not mm.band:
                        raise DataError(f"{where}: {it['id']} lists view {gid!r}, which is not a group of a base with two or more groups (ai-2)")
                    self.by_group.setdefault(gid, []).append(it)
        if self.all and not mm.band:
            raise DataError(f"{where}: an all-views item needs a base with two or more groups (ai-2)")
        reg = mm.reg
        self.pairs = {it["id"]: reg.cites(it["cite"], (it["id"], mm.pre + it["id"])) for it in self.items}

    # -- squares
    def square(self, it, cx, cy, extra=""):
        h = SQ / 2
        return (f'<g class="pm-ai-sq is-{it["origin"]}" data-ai="{it["id"]}"{extra}><title>{esc(it["id"] + " " + it["title"] + " · " + AI_WORD[it["origin"]])}</title>'
                f'<rect x="{num(cx - h)}" y="{num(cy - h)}" width="{SQ}" height="{SQ}" rx="2"/>'
                f'<text x="{num(cx)}" y="{num(cy + 3.3)}">{it["id"][3:]}</text></g>')

    def more(self, cx, cy, rest):
        h = SQ / 2
        ids = " ".join(i["id"] for i in rest)
        return (f'<g class="pm-ai-more" data-ai="{ids}"><title>{len(rest)} more AI items: {esc(ids)}</title>'
                f'<rect x="{num(cx - h)}" y="{num(cy - h)}" width="{SQ}" height="{SQ}" rx="2"/>'
                f'<text x="{num(cx)}" y="{num(cy + 3.2)}">+{len(rest)}</text></g>')

    def run(self, items, xs, cy):
        """Squares at the given centres (left to right); with more than len(xs) items, the last becomes +n."""
        k = len(xs)
        if len(items) <= k:
            xs = xs[k - len(items):]
            return "".join(self.square(it, x, cy) for it, x in zip(items, xs))
        shown = items[:k - 1]
        return "".join(self.square(it, x, cy) for it, x in zip(shown, xs)) + self.more(xs[-1], cy, items[k - 1:])

    # -- slots
    def under(self, ui=None):
        ui = ui or {}
        mm = self.mm
        s = '<g class="pm-ai-under">'
        for g in mm.groups if mm.band else []:
            gx, gw, _ = mm.cells[g["id"]]
            ids = " ".join(i["id"] for i in self.by_group.get(g["id"], []) + self.all)
            if ids:
                on = " is-ai-on" if ui.get("tint") in (g["id"], "all") else ""
                s += (f'<rect class="pm-ai pm-ai-band-hit{on}" data-group="{g["id"]}" data-ai="{ids}" x="{num(gx)}" '
                      f'y="{BAND_TOP}" width="{num(gw)}" height="{BAND_BOT - BAND_TOP}"/>')
        for n in mm.nodes:
            its = self.by_node.get(n.id)
            if its:
                c = ui.get("halo", {}).get(n.id, "")
                s += (f'<g class="pm-ai pm-ai-node{(" " + c) if c else ""}" data-node="{n.id}" data-ai="{" ".join(i["id"] for i in its)}">'
                      f'<rect class="pm-ai-halo" x="{num(n.x - 4)}" y="{num(n.y - 4)}" width="{CW + 8}" height="{CH + 8}" rx="6"/></g>')
        return s + "</g>"

    def over(self, ui=None):
        ui = ui or {}
        mm = self.mm
        s = '<g class="pm-ai-over">'
        for n in mm.nodes:
            its = self.by_node.get(n.id)
            if not its:
                continue
            k = min(len(its), 3)
            xs = [n.x + CW - 21 * (k - 1 - j) for j in range(k)]
            c = ui.get("marks", {}).get(n.id, "")
            s += (f'<g class="pm-ai pm-ai-marks{(" " + c) if c else ""}" data-node="{n.id}" data-ai="{" ".join(i["id"] for i in its)}">'
                  + self.run(its, xs, n.y + CH + 5) + "</g>")
        for g in mm.groups if mm.band else []:
            its = self.by_group.get(g["id"])
            if not its:
                continue
            gx, gw, _ = mm.cells[g["id"]]
            k = min(len(its), 3)
            xs = [gx + gw - 14 - 20 * (k - 1 - j) for j in range(k)]
            ids = " ".join(i["id"] for i in its)
            c = ui.get("view", {}).get(g["id"], "")
            s += (f'<g class="pm-ai pm-ai-view{(" " + c) if c else ""}" data-group="{g["id"]}" data-ai="{ids}">'
                  f'<rect class="pm-ai-rail" data-ai="{ids}" x="{num(gx + 6)}" y="40" width="{num(gw - 12)}" height="2"/>'
                  + self.run(its, xs, 26) + "</g>")
        if self.all:
            ids = " ".join(i["id"] for i in self.all)
            x0, x1 = GUT + 6, mm.W - 6
            c = ui.get("all", "")
            s += (f'<g class="pm-ai pm-ai-all{(" " + c) if c else ""}" data-ai="{ids}"><path class="pm-ai-rail" data-ai="{ids}" '
                  f'd="M {num(x0)} 14 L {num(x0)} 8 L {num(x1)} 8 L {num(x1)} 14"/></g>')
        for n in mm.nodes:
            its = self.by_node.get(n.id)
            if not its:
                continue
            lab = f"{n.id} {n.d['title']}: " + "; ".join(f"{i['id']} {i['title']} ({AI_WORD[i['origin']].lower()})" for i in its)
            s += (f'<rect class="pm-ai pm-ai-hit" data-node="{n.id}" data-ai="{" ".join(i["id"] for i in its)}" data-tip="{n.id}" '
                  f'tabindex="0" role="button" aria-label="{esc(lab)}" x="{num(n.x - 4)}" y="{num(n.y - 4)}" '
                  f'width="{CW + 8}" height="{CH + 8}" rx="6"/>')
        return s + "</g>"

    def gutter_over(self, ui=None):
        if not self.all:
            return ""
        ui = ui or {}
        k = min(len(self.all), 3)
        xs = [22 + 20 * j for j in range(k)]
        ids = " ".join(i["id"] for i in self.all)
        c = ui.get("all", "")
        return (f'<g class="pm-slot-over pm-ai-over"><g class="pm-ai pm-ai-all{(" " + c) if c else ""}" data-ai="{ids}">'
                + self.run(self.all, xs, 26)
                + f'<text class="pm-ai-all-text" x="{num(14 + 20 * k + 6)}" y="30">ALL VIEWS</text></g></g>')

    def summary(self, off=False):
        mm, items = self.mm, self.items
        steps = sum(1 for n in mm.nodes if not n.dec)
        if not items:
            return ('<p class="pm-ai-summary" aria-live="polite"><span class="pm-ai-summary-in"><span><b>No AI opportunities</b> yet</span>'
                    f'<span>touches <b>0</b> of <b>{steps}</b> steps</span></span></p>')
        named = sum(1 for i in items if i["origin"] == "named")
        sug = len(items) - named
        touched = len({nid for i in items for nid in i.get("nodes", [])})
        views = sum(1 for i in items if isinstance(i.get("groups"), list) and i["groups"])
        alls = len(self.all)
        segs = [f'<b>{len(items)}</b> AI {"opportunity" if len(items) == 1 else "opportunities"}']
        if named:
            segs.append(f'<i class="pm-ai-sum-sq is-named" aria-hidden="true"></i><b>{named}</b> named by the client')
        if sug:
            segs.append(f'<i class="pm-ai-sum-sq" aria-hidden="true"></i><b>{sug}</b> {"our suggestion" if sug == 1 else "our suggestions"}')
        segs.append(f'touches <b>{touched}</b> of <b>{steps}</b> steps')
        if views:
            segs.append(f'<b>{views}</b> across a whole view')
        if alls:
            segs.append(f'<b>{alls}</b> across all views')
        cls = " is-off" if off else ""
        return (f'<p class="pm-ai-summary{cls}" aria-live="polite"><span class="pm-ai-summary-in">'
                + "".join(f"<span>{x}</span>" for x in segs)
                + '<span class="pm-ai-sum-off">hidden on the board</span></span></p>')

    def tip_lines(self):
        out = {}
        for nid, its in self.by_node.items():
            s = "".join(f'<span class="pm-ai-tip-line"><span class="pm-ai-mark is-{i["origin"]}" aria-hidden="true">{i["id"][3:]}</span>'
                        f'<span><b>{i["id"]}</b> {esc(i["title"])} · {"Named" if i["origin"] == "named" else "Suggested"}</span></span>'
                        for i in its)
            out[nid] = f'<span class="pm-ai-tip">{s}<span class="pm-ai-tip-foot">Click to open the card</span></span>'
        return out

    def data(self):
        mm = self.mm
        members = {g["id"]: [n.id for n in mm.nodes if n.d.get("group") == g["id"]] for g in mm.groups}
        return {"items": {i["id"]: {"nodes": i.get("nodes", []), "groups": i.get("groups", [])} for i in self.items},
                "members": members, "tips": self.tip_lines()}

    # -- the card
    def evidence_html(self, it):
        idx = self.mm.idx
        out = ""
        for c, es in self.pairs[it["id"]]:
            t = ctype(c)
            if t == "grounded":
                e = es[0]
                h = idx.src[c["source"]]["h"]
                quote = c.get("quote") or e["recs"][0]["text"]
                extra = ""
                if h["kind"] == "transcript" and e["recs"][0].get("context"):
                    extra = f' · {esc(e["recs"][0]["context"])}'
                elif h["kind"] == "web" and h.get("url"):
                    extra = f' · {esc(domain(h["url"]))}'
                out += (f'<blockquote class="pm-ai-cite is-quote">“{esc(quote)}”</blockquote>'
                        f'<span class="pm-prov"><span class="pm-prov-grounded"><b>Grounded</b> · {addr_link(e)}{extra}</span></span>')
            elif t == "inferred":
                out += (f'<p class="pm-ai-cite is-inferred"><strong>Basis:</strong> {esc(c["reading"])}</p>'
                        f'<span class="pm-prov"><span class="pm-prov-inferred"><b>Inferred</b> · from '
                        f'{", ".join(addr_link(e) for e in es)}</span></span>')
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
                    li += (f'<li class="is-person"><span class="d" aria-hidden="true"></span><span><b>Person decides</b> · '
                           f'{esc(d["who"])} {esc(d["what"])}</span></li>')
        nd = len(a["decides"])
        meta = f'{plural(len(a["steps"]), "step")} · {nd} {"place" if nd == 1 else "places"} a person decides · {plural(len(a["systems"]), "system")}'
        syss = ""
        for sid in a["systems"]:
            s = mm.systems.get(sid)
            if not s:
                raise DataError(f"{self.where}: an agentic version names system {sid!r}, which is not in the base (ai-4)")
            syss += f'<span class="pm-ai-sys">{icon_svg(s["icon"])}{esc(s["label"])}</span>'
        return (f'<details class="pm-ai-agentic"{" open" if open_ else ""}><summary><span class="pm-ai-ag-title">Agentic version</span>'
                f'<span class="pm-ai-ag-meta">{meta}</span></summary><dl class="pm-ai-ag">'
                f'<div><dt>Trigger</dt><dd>{esc(a["trigger"])}</dd></div>'
                f'<div><dt>Steps</dt><dd><ol class="pm-ai-flow">{li}</ol></dd></div>'
                f'<div><dt>Systems</dt><dd>{syss}</dd></div>'
                f'<div><dt>Logging</dt><dd>{esc(a["logging"])}</dd></div></dl></details>')

    def row_html(self, it, state="", open_=False):
        mm, pre = self.mm, self.mm.pre
        chips = ""
        for nid in it.get("nodes", []):
            chips += f'<a class="pm-ai-step" href="#{pre}{nid}" data-node="{nid}"><b>{nid}</b>{esc(mm.N[nid].d["title"])}</a>'
        g = it.get("groups", [])
        if g == "all":
            chips += f'<a class="pm-ai-step is-scope" href="#{pre}board" data-scope="all"><b>All views</b></a>'
        else:
            for gid in g:
                gl = mm.groups[mm.group_ix[gid]]["label"]
                chips += f'<a class="pm-ai-step is-scope" href="#{pre}{gid}" data-group="{gid}"><b>{gid}</b>{esc(gl)} · whole view</a>'
        where_word = "Steps it touches" if it.get("nodes") else "Where it applies"
        cls = f"pm-ai-item is-{it['origin']}" + (f" {state}" if state else "")
        return (f'<li class="{cls}" data-ai="{it["id"]}" id="{pre}{it["id"]}">'
                f'<span class="pm-ai-mark is-{it["origin"]}" aria-hidden="true">{it["id"][3:]}</span><div class="pm-ai-body">'
                f'<div class="pm-ai-head"><h3 class="pm-ai-title"><span class="pm-ai-id">{it["id"]}</span> {esc(it["title"])}</h3>'
                f'<span class="pm-ai-origin is-{it["origin"]}">{AI_WORD[it["origin"]]}</span>'
                f'<button class="pm-ai-show" type="button" data-ai="{it["id"]}">Show on map</button></div>'
                f'<div class="pm-ai-cols"><div><span class="pm-ai-label">What it would do</span><p class="pm-ai-does">{esc(it["does"])}</p>'
                f'<span class="pm-ai-label">{where_word}</span><div class="pm-ai-steps">{chips}</div></div>'
                f'<div><span class="pm-ai-label">Evidence</span>{self.evidence_html(it)}</div></div>'
                f'{self.agentic_html(it.get("agentic"), open_)}</div></li>')

    def card_html(self, F, states=None, opened=()):
        states = states or {}
        if not self.items:
            return fill(F["card-empty"], pre=self.mm.pre)
        rows = "".join(self.row_html(it, states.get(it["id"], ""), it["id"] in opened) for it in self.items)
        count = f'{plural(len(self.items), "item")} · hover a row to see it on the map'
        return fill(F["card"], pre=self.mm.pre, count=count, rows=rows)

    def slots(self, F, ui=None, off=False):
        if self.items:
            toolbar = fill(F["toggle"], pressed=str(not off).lower(), state="Off" if off else "On") + self.summary(off)
            legend = fill(F["legend-end"], client=esc(self.mm.meta["client"]))
        else:
            toolbar = F["toggle-none"] + self.summary()
            legend = ""
        toolbar += f'<script type="application/json" class="pm-ai-data">{jdump(self.data())}</script>'
        return {"toolbar": toolbar, "legend-end": legend, "board-under": self.under(ui), "board-over": self.over(ui),
                "board-over:gutter": self.gutter_over(ui)}


# ------------------------------------------------------------------ page builds

def load_json(path, what):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        raise DataError(f"{what} does not exist: {path}")
    except ValueError as e:
        raise DataError(f"{what} is not valid JSON: {e}")


def load_rules():
    try:
        return json.loads(RULES_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CannotRun(f"cannot read {RULES_JSON}: {e}")


def build_page(ws, section, name):
    rules = load_rules()
    idx = Index(ws, rules)
    if section == "process-map":
        m = load_json(ws / "process-map" / f"{name}.json", f"process-map/{name}.json")
        mm = MapModel(m, idx, f"process-map/{name}.json")
        return render_page(mm, None)
    if section == "process-map-ai-opportunity":
        layer = load_json(ws / "process-map-ai-opportunity" / f"{name}.json", f"process-map-ai-opportunity/{name}.json")
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


def render_page(mm, am, ui=None, ai_ui=None):
    tpl, shell_tpl = board_template()
    kicker, title, subtitle, date = page_texts(mm, am)
    parts = board_parts(mm, ui)
    slots = {}
    if am:
        F = fills()
        slots = am.slots(F, ai_ui)
        slots["style"] = F["style"]
        slots["script"] = F["script"]
        slots["evidence-start"] = am.card_html(F)
    shell = shell_html(shell_tpl, mm, parts, board_label(mm), slots=slots)
    connections = ""
    for i, edge in enumerate(mm.edges, 1):
        label = f'{edge["from"]} → {edge["to"]}'
        pairs = mm.reg.cites(edge.get("cite", []), (label, mm.pre + f"connection-{i}"))
        if pairs:
            connections += f'<li id="{mm.pre}connection-{i}"><b>{esc(label)}</b>{prov_html(pairs)}</li>'
    connection_card = ('<article class="pm-ev-card"><h2>Connection evidence</h2><ol class="pm-ev-list">'
                       + connections + '</ol></article>') if connections else ""
    evidence = sources_html(mm.reg) + connection_card + gaps_html(mm) + clar_html(mm)
    page = tpl.replace("<!--bs:shell-->\n" + shell_tpl + "<!--/bs:shell-->\n", shell)
    page = fill(page, title=esc(title), pre=mm.pre, header=header_html(mm.meta, mm.m.get("systems", []), kicker, title, subtitle),
                evidence=evidence, footer=footer_html(mm.meta, date))
    return fill_slots(page, slots)


# ------------------------------------------------------------------ specimens (--specimen)
# Both specimen.html files are built from the workspace's own files (examples/). A state the examples
# lack is drawn from a generated variant of them, marked "generated". Element states are crops of real
# boards drawn by the functions above; interaction states call the real overlay code.

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
@media (max-width:700px){.sp-page{padding:20px 16px 48px}.sp-example .pm-page{padding:16px 12px}}
</style>"""

SP_JS = """<script id="sp-script">
/* specimen only: freeze interaction states with the real overlay functions */
(function(){
function run(){
  document.querySelectorAll('[data-sp-act]').forEach(function(root){
    var api = root.pmAiApi; if (!api) return;
    var a = root.getAttribute('data-sp-act').split(':');
    if (a[0] === 'focus') api.focus(a[1]);
    if (a[0] === 'pin') api.pin(a[1]);
    if (a[0] === 'node'){ api.nodeHover(a[1], true); api.link(a[2].split(','), true); }
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
    return (f'<figure class="sp-fig{" is-wide" if wide else ""}"><div class="sp-stage{" is-block" if block else ""}">{body}</div>'
            f'<figcaption class="sp-cap">{tags}{g}{n}</figcaption></figure>')


def sp_section(sid, n, title, sub, figs, min_w="260px"):
    return (f'<section class="sp-sec" id="{sid}"><div class="sp-sec-h"><span class="sp-n">{n:02d}</span><h2>{esc(title)}</h2>'
            f'<code>#{sid}</code></div><p class="sp-sub">{sub}</p><div class="sp-grid" style="--min:{min_w}">{"".join(figs)}</div></section>')


def sp_page(title, eyebrow, lede, sections, ai=False):
    st, sc = board_style_script()
    F = fills() if ai else None
    toc = "".join(f'<a href="#{sid}"><span>{i + 1:02d}</span>{esc(t)}</a>' for i, (sid, t) in enumerate(sections["toc"]))
    head = (f'<header class="sp-head"><p class="sp-eyebrow">{esc(eyebrow)}</p><h1>{esc(title)}</h1>'
            f'<p class="sp-lede">{lede}</p><nav class="sp-toc" aria-label="Sections">{toc}</nav></header>')
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            f"<title>{esc(title)}</title>\n{st}\n{F['style'] if ai else ''}\n{SP_CSS}\n</head>\n<body>\n"
            f'<main class="sp-page"><div class="sp-wrap">{head}{"".join(sections["body"])}</div></main>\n'
            f"{sc}\n{F['script'] if ai else ''}\n{SP_JS}\n</body>\n</html>\n")


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
    return (f'<svg class="{cls}" viewBox="{num(x)} {num(y)} {num(w)} {num(h)}" width="{num(w)}" height="{num(h)}" '
            f'role="img" aria-label="{esc(label)}">{body}</svg>')


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
        return MapModel(mv, idx, where, pre)
    ex = mk(m, "ex-")
    N = {n["id"]: n for n in m["nodes"]}
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
    sections.append(f'<section class="sp-sec" id="pm-example"><div class="sp-sec-h"><span class="sp-n">00</span><h2>The example map</h2>'
                    f'<code>#pm-example</code></div><p class="sp-sub">examples/{esc(where)}, built as a page. Every element below is drawn by the same code.</p>'
                    f'<div class="sp-example">{sp_main(render_page(ex, None))}</div></section>')

    # a variant holding one node per node state the sections need
    extra_sys = [{"id": "shared-drive", "label": "Shared drive", "icon": "shared-drive", "cite": gcite[:1]},
                 {"id": "request-form", "label": "Request form", "icon": "document", "cite": gcite[:1]}]
    long_title = "Reconcile every request with its tracker records"[:48]
    vn = [
        dict(grounded, id="NOD-01"),
        dict(inferred or grounded, id="NOD-02", state="inferred", owner="Team A",
             cite=(inferred or {}).get("cite") or [{"type": "inferred", "reading": "Team A completes it again", "from": gcite[:1]}]),
        dict(gapn or grounded, id="NOD-03", state="gap"),
        {k: v for k, v in grounded.items() if k not in ("owner", "systems")} | {"id": "NOD-04", "title": (noowner or grounded)["title"]},
        dict(grounded, id="NOD-05", title=long_title, systems=sys_ids[:1]),
        dict(grounded, id="NOD-06", systems=(sys_ids + ["shared-drive", "request-form"])[:4]),
        dict(grounded, id="NOD-07", systems=sys_ids[:2]),
        dict(grounded, id="NOD-08", systems=sys_ids[:1]),
    ]
    for d in vn:
        d.pop("group", None)
        d.pop("col", None)
        d["lane"] = lane0
    dq = decs[0] if decs else {"id": "DEC-01", "title": "Request complete?", "kind": "decision", "state": "grounded", "cite": gcite[:1]}
    vd = [dict(dq, id="DEC-01"), dict(dq, id="DEC-02", state="inferred", cite=[{"type": "inferred", "reading": "Team B checks the limit first", "from": gcite[:1]}]),
          dict(dq, id="DEC-03", state="gap"), dict(dq, id="DEC-04"), dict(dq, id="DEC-05", title="Over the approval limit?")]
    for d in vd:
        d.pop("group", None)
        d["lane"] = lane1
    clar0 = (m.get("clarifications") or [{"title": "Who confirms this step?", "shows": "The step is listed.", "ask": "Who does it?", "cite": gcite[:1]}])[0]
    gap0 = (m.get("gaps") or [{"title": "No owner is named", "text": "The step has no owner.", "cite": gcite[:1]}])[0]
    vm = variant(m, systems=m.get("systems", []) + extra_sys, groups=[], edges=[], nodes=vn + vd,
                 gaps=[dict(gap0, id="GAP-01", nodes=["NOD-03", "DEC-03"])],
                 clarifications=[dict(clar0, id=f"P0{i}", nodes=nodes) for i, nodes in
                                 ((1, ["NOD-08", "DEC-04", "NOD-03"]), (2, ["NOD-08"]), (3, ["NOD-08"]), (4, ["NOD-08"]))])
    vm["lanes"] = [l for l in m["lanes"] if l["id"] in (lane0, lane1)]

    def nfig(states, nid, ui="", note="", gen=True):
        v = mk(vm, f"n{len(states)}{nid.lower()}{ui}-")
        return sp_fig(states, crop(v, node_box(v, nid, 30 if v.N[nid].dec else 26), ui={nid: ui} if ui else None,
                                   label=f"{nid}, {', '.join(states)}"), note, gen=gen)

    # 01 header
    meta = m["meta"]
    hx = lambda mt, mv=m: f'<div class="pm-head-main" style="width:100%">{header_html(mt, mv.get("systems", []), mt["kicker"], mt["title"], ex.fill_counts(mt.get("subtitle", "")))}</div>'
    add("pm-header", "Page header", "Kicker with the flag chips, title, subtitle with its {count:…} tokens filled, and the system key. The title wraps and is never cut.", [
        sp_fig(["full"], hx(meta), block=True, wide=True, gen=False),
        sp_fig(["minimal"], hx({"kicker": meta["kicker"], "title": meta["title"], "client": meta["client"], "date": meta["date"]}, variant(m, systems=[])), block=True, wide=True, gen=True),
        sp_fig(["long title"], hx(dict(meta, title="Request handling from the first email to the recorded outcome, with every return to Team A"[:90])), block=True, wide=True, gen=True),
    ], "100%")
    # 02 key
    add("pm-key", "System key", "One item per system, in file order, with its icon. With no systems the row is left out.", [
        sp_fig(["systems"], hx(meta), block=True, gen=False),
        sp_fig(["omitted when there are none"], hx(dict(meta, subtitle=""), variant(m, systems=[])), block=True, gen=True),
    ], "420px")
    # 03 legend
    tpl, _ = board_template()
    legend = re.search(r'<aside class="pm-legend".*?</aside>', tpl, re.S).group(0).replace("<!--slot:legend-end-->", "")
    add("pm-legend", "Legend", "Template text, always complete: lines, then node states, then marks. Two columns under 640px.", [
        sp_fig(["3 × 3 on desktop"], f'<div style="width:392px;max-width:100%">{legend}</div>', gen=False),
        sp_fig(["2 columns under 640px"], f'<div style="width:300px;max-width:100%">{legend.replace("pm-legend", "pm-legend is-2col", 1)}</div>', gen=False),
    ], "420px")
    # 04 lanes
    lanes = [dict(m["lanes"][0]), {"id": "shared", "label": "Shared services and finance review team"},
             {"id": "team-x", "label": m["lanes"][-1]["label"]}, {"id": "team-c", "label": "Team C", "cite": gcite[:1]}]
    ln = [dict(grounded, id="LAN-01", lane=lanes[0]["id"]), dict(grounded, id="LAN-02", lane="shared", owner="Team B"),
          dict(grounded, id="LAN-03", lane="team-x"), dict(grounded, id="LAN-04", lane="team-x", title="Log request")]
    for d in ln:
        d.pop("group", None)
    lv = mk(variant(m, lanes=lanes, groups=[], nodes=ln, edges=[{"from": "LAN-01", "to": "LAN-03"}, {"from": "LAN-01", "to": "LAN-04"}],
                    gaps=[], clarifications=[]), "lane-")
    add("pm-lane", "Lane and gutter", "Lanes in alternating fills; the gutter holds the role and its note. A lane grows a 144-unit row for each step stacked in a column, and an empty lane shrinks to 56.", [
        sp_fig(["alternating fills", "long name", "stacked rows", "empty"], crop(lv, (0, 0, min(lv.W, 560), lv.H), gutter=True, label="Lanes"), wide=True, gen=True,
               note="Second lane: a 39-character role wraps to three lines. Third: two steps in one column. Fourth: no steps."),
    ])
    # 05 band
    bands = [dict(g) for g in m.get("groups", [])] or [{"id": "G01", "label": "Intake"}, {"id": "G02", "label": "Review and approval"}]
    bt = mk(m, "band-")
    one = [dict(n, group=bands[0]["id"] if i == 0 else bands[-1]["id"]) for i, n in enumerate(m["nodes"])]
    gl = variant(m, groups=[dict(bands[0], label="Review, approval, record"), bands[-1]], nodes=one)
    bl = mk(gl, "bandl-")
    first_g = bands[0]["id"]
    bw = min(bt.W, 760)
    add("pm-band", "Group band", "Drawn with two or more groups: one cell per view, its id and label, and the derived step count. The label is cut to leave room for the AI layer's squares.", [
        sp_fig(["drawn with two or more groups"], crop(bt, (GUT, 0, bw - GUT, 52), label="Band"), wide=True, gen=False),
        sp_fig([f"targeted (#{first_g})"], crop(mk(m, "bandt-"), (GUT, 0, bw - GUT, 52), ui={"group": first_g}, label="Band, targeted"), wide=True, gen=False),
        sp_fig(["long label (cut with …)"], crop(bl, (GUT, 0, min(bl.W, 760) - GUT, 52), label="Band, long label"), wide=True, gen=True,
               note="A one-column view: its label stops 70 units short of the cell's end, where a view's AI squares go."),
    ])
    # 06 node card
    add("pm-node", "Node card", "A 156 × 104 card: title, owner line, the derived detail line, and the gap tag. Focus is a 2px ink ring 8 units out, so it never reads as an AI halo.", [
        nfig(["grounded", "with owner"], "NOD-01", gen=False), nfig(["inferred"], "NOD-02", gen=False), nfig(["gap"], "NOD-03", gen=False),
        nfig(["without owner"], "NOD-04", gen=False), nfig(["long title (3 lines, then …)"], "NOD-05"), nfig(["several systems"], "NOD-06"),
        nfig(["hover"], "NOD-01", "hover"), nfig(["keyboard focus"], "NOD-01", "focus"), nfig(["targeted"], "NOD-01", "target"),
    ], "236px")
    # 07 badges
    add("pm-badge", "Badges", "Gap badges are filled orange, clarification badges a dashed ring; the number is the card's list position and links to it. After three comes +n.", [
        nfig(["gap"], "NOD-03", gen=False), nfig(["clarification"], "NOD-07"), nfig(["+n after three"], "NOD-08"),
    ], "236px")
    # 08 system icons
    add("pm-sys", "System icon", "The node's systems on its top-right corner: one, two, then +n.", [
        nfig(["1"], "NOD-05"), nfig(["2"], "NOD-07"), nfig(["+n"], "NOD-06"),
    ], "236px")
    # 09 decisions
    add("pm-decision", "Decision diamond", "A 60.2 square turned 45°. The question sits inside on at most two lines; the detail line sits under the bottom vertex.", [
        nfig(["grounded"], "DEC-01", gen=not decs), nfig(["inferred (dashed grey)"], "DEC-02"), nfig(["gap (dashed orange)"], "DEC-03"),
        nfig(["with a clarification"], "DEC-04"), nfig(["long question (2 lines)"], "DEC-05"),
    ], "236px")
    # 10 edges
    e_hover = (m["edges"][0]["from"], m["edges"][0]["to"]) if m.get("edges") else None
    add("pm-edge", "Edges", "Flow lines are solid; an edge to an earlier node is feedback, dashed. A branch label sits in a pill on its line's longest free stretch.", [
        sp_fig(["flow", "branch with its label pill", "feedback (dashed)"], crop(mk(m, "edge-"), (GUT, ex.lanes_top, ex.W - GUT, ex.lanes_bottom - ex.lanes_top), label="Edges"), wide=True, gen=False),
        sp_fig(["hover"], crop(mk(m, "edgeh-"), (GUT, ex.lanes_top, PITCH * min(ex.ncols, 3) + 4, ex.lanes_bottom - ex.lanes_top), ui={"edges": {e_hover}} if e_hover else None, label="Edge hover"),
               note=f"{e_hover[0]} → {e_hover[1]} hovered." if e_hover else "", wide=True, gen=False),
    ])
    # 11 shell
    _, shell_tpl = board_template()
    def shell(pre, zoom, phone=False):
        v = mk(m, pre)
        s = shell_html(shell_tpl, v, board_parts(v), board_label(v), zoom=zoom)
        return f'<div class="sp-phone">{s}</div>' if phone else s
    add("pm-shell", "Board shell", "Fit scales the board to the page; 100% draws it 1:1 with a sticky gutter and drag to pan. Under 700px the gutter is redrawn compact and Fit keeps the board 860 wide inside its own scroll.", [
        sp_fig(["Fit"], shell("sf-", "fit"), wide=True, block=True, gen=False),
        sp_fig(["100% (sticky gutter, drag to pan)"], shell("s1-", "100"), wide=True, block=True, gen=False),
        sp_fig(["phone (compact gutter)"], shell("sp-", "fit", True), wide=True, gen=False),
    ])
    # 12 tooltip
    tv = mk(vm, "tip-")
    dec_id = "DEC-01"
    add("pm-tip", "Tooltip", "One tooltip, on hover or keyboard focus. It only repeats printed facts: id and group, the full title, lane, owner, systems, marks and the provenance line.", [
        sp_fig(["step"], f'<div class="pm-tip is-static sp-tipbox">{ex.tip(ex.N[grounded["id"]])}</div>', gen=False),
        sp_fig(["decision"], f'<div class="pm-tip is-static sp-tipbox">{tv.tip(tv.N[dec_id])}</div>', gen=not decs),
        sp_fig(["truncated title"], f'<div class="pm-tip is-static sp-tipbox">{tv.tip(tv.N["NOD-05"])}</div>'),
    ], "300px")
    # 13, 14 cards
    empty = mk(variant(m, gaps=[], clarifications=[]), "empty-")
    gid = (m.get("gaps") or [{}])[0].get("id")
    cid = (m.get("clarifications") or [{}])[0].get("id")
    add("pm-gaps", "Gaps card", "One item per gap, numbered as its badges: title, text with markers, the steps, and the provenance line with its absent searches.", [
        sp_fig(["list"], gaps_html(mk(m, "g1-")), block=True, gen=False),
        sp_fig(["targeted item"], gaps_html(mk(m, "g2-"), target=gid), block=True, gen=False),
        sp_fig(["empty"], gaps_html(empty), block=True, gen=True),
    ], "360px")
    add("pm-clar", "Clarifications card", "One item per question: what the sources show, what to confirm and with whom, the steps, and the provenance line.", [
        sp_fig(["list"], clar_html(mk(m, "c1-")), block=True, gen=False),
        sp_fig(["targeted item"], clar_html(mk(m, "c2-"), target=cid), block=True, gen=False),
        sp_fig(["empty"], clar_html(empty), block=True, gen=True),
    ], "360px")
    # 15 sources
    st = mk(m, "s2-")
    absent = next((e for e in st.reg.entries.values() if e["kind"] == "absent"), None)
    add("pm-sources", "Sources card", "Every record the page uses, by source: a record entry, a span entry with its records, and an absent search with its verdict. “Used by” names each element.", [
        sp_fig(["per source", "span entry", "absent search"], sources_html(mk(m, "s1-").reg), wide=True, block=True, gen=False),
        sp_fig(["targeted entry"], sources_html(st.reg, target=absent["anchor"] if absent else None, only={absent["source"]} if absent else None),
               wide=True, block=True, gen=False),
    ])
    # 16 footer
    add("pm-footer", "Footer", "Left: meta.footer. Right: the confidential and draft clauses when they apply, then the date.", [
        sp_fig(["flags"], footer_html(meta, meta["date"]), block=True, gen=False),
        sp_fig(["no flags"], footer_html(dict(meta, flags=[]), meta["date"]), block=True, gen=True),
        sp_fig(["phone (the sides stack)"], f'<div class="sp-narrow">{footer_html(meta, meta["date"])}</div>', gen=False),
    ], "420px")
    # 17 empty states
    en = [dict(grounded, id="EMP-01", lane=lane0, group="G01"), dict(grounded, id="EMP-02", lane=lane0, group="G01", title="Log request")]
    for d in en:
        d.pop("systems", None)
    em = variant(m, meta={k: v for k, v in meta.items() if k != "flags"} | {"subtitle": "{count:steps} steps across {count:groups} view."},
                 systems=[], lanes=[m["lanes"][0], {"id": "team-c", "label": "Team C", "cite": gcite[:1]}],
                 groups=[{"id": "G01", "label": "Intake"}], nodes=en, edges=[{"from": "EMP-01", "to": "EMP-02"}], gaps=[], clarifications=[])
    add("pm-empty", "Empty states", "A map with an empty lane, no gaps, no clarifications, no systems, no flags and one group (so no band).", [
        sp_fig(["lane with no steps", "no gaps", "no clarifications", "no systems", "no flags", "0 or 1 group (no band)"],
               f'<div class="sp-example">{sp_main(render_page(mk(em, "e-"), None))}</div>', wide=True, block=True, gen=True),
    ])
    return sp_page("Process map: every element", "design-system/process-map · specimen",
                   "Built from <code>examples/</code> by <code>build_map.py --specimen</code>. Each section is an element of the README's table, at its anchor; "
                   "a state the examples lack is drawn from a generated variant of them, marked <span class=\"sp-gen\">generated</span>.",
                   {"toc": toc, "body": sections})


def ai_specimen(ws, idx, base_path, layer_path):
    layer = load_json(layer_path, layer_path.name)
    m = load_json(ws / "process-map" / f"{layer['base']}.json", f"process-map/{layer['base']}.json")
    where = f"process-map/{layer['base']}.json"
    lwhere = f"process-map-ai-opportunity/{layer_path.name}"
    F = fills()

    def mk(lv, pre, mv=None):
        mm = MapModel(mv or m, idx, where, pre)
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

    ex_body = page_with(layer, "ex-")
    sections.append(f'<section class="sp-sec" id="ai-example"><div class="sp-sec-h"><span class="sp-n">00</span><h2>The example layer</h2>'
                    f'<code>#ai-example</code></div><p class="sp-sub">examples/{esc(lwhere)} over examples/{esc(where)}, built as a page. '
                    f'Toggle the layer, hover a card row or a marked step, click to pin, Esc to unpin.</p><div class="sp-example">{ex_body}</div></section>')

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

    meta = layer["meta"]
    kicker, title, subtitle, _ = page_texts(mm, am)
    add("ai-header", "Header text", "The layer's kicker, title and subtitle replace the base's; flags, systems, client and footer are inherited.", [
        sp_fig(["—"], f'<div class="pm-head-main" style="width:100%">{header_html(mm.meta, m.get("systems", []), kicker, title, subtitle)}</div>', block=True, wide=True, gen=False)])
    add("ai-halo", "Halo", "One halo per marked step, under the node, 4 units outside its border; never dashed.", [
        sp_fig(["default"], ncrop(layer, n_sugg, "h1-"), gen=False),
        sp_fig(["thick (focus, hover)"], ncrop(layer, n_sugg, "h2-", ai_ui={"halo": {n_sugg: "is-ai-hover"}}), gen=False),
        sp_fig(["faded"], ncrop(layer, n_sugg, "h3-", cls="pm-board has-ai is-ai-focus"), gen=False, note="Another row is in focus."),
        sp_fig(["hidden (layer off)"], ncrop(layer, n_sugg, "h4-", cls="pm-board"), gen=False),
        sp_fig(["peek (layer off, item hovered)"], ncrop(layer, n_sugg, "h5-", cls="pm-board", ai_ui={"halo": {n_sugg: "is-ai-peek"}, "marks": {n_sugg: "is-ai-peek"}}), gen=False),
    ], "236px")
    add("ai-square", "Node square", "Squares hang from the bottom-right corner, right of the centre line. Filled: named by the client. Outlined: our suggestion. The digits are the item id's.", [
        sp_fig(["named (filled)"], ncrop(layer, n_named, "q1-"), gen=not named),
        sp_fig(["suggested (outlined)"], ncrop(layer, n_sugg, "q2-"), gen=not sugg),
        sp_fig(["faded"], ncrop(layer, n_named, "q3-", cls="pm-board has-ai is-ai-focus"), gen=False),
        sp_fig(["hidden"], ncrop(layer, n_named, "q4-", cls="pm-board"), gen=False),
        sp_fig(["peek"], ncrop(layer, n_named, "q5-", cls="pm-board", ai_ui={"halo": {n_named: "is-ai-peek"}, "marks": {n_named: "is-ai-peek"}}), gen=False),
        sp_fig(["+n"], ncrop(v4, nid, "q6-"), gen=True, note="Four items on one step: two squares, then +2."),
    ], "236px")

    def bcrop(lv, pre, cls="pm-board has-ai", ai_ui=None, gutter=False, label="Band"):
        a, b = mk(lv, pre)
        x0 = 0 if gutter else GUT
        return crop(a, (x0, 0, a.W - x0, 52), am=b, ai_ui=ai_ui, cls=cls, gutter=gutter, label=label)
    vg = viewi["groups"][0] if viewi else None
    vlayer = layer if viewi else dict(layer, ai=[{"id": "AI-01", "title": "Check requests on arrival", "origin": "suggested", "does": "Checks each request.",
                                                  "groups": [m["groups"][1]["id"]], "cite": (sugg or items[0])["cite"]}])
    vg = vg or m["groups"][1]["id"]
    vlayer = dict(vlayer, ai=[viewi or vlayer["ai"][0]])
    add("ai-view", "View underline", "A view item marks its group cell: a 2-unit underline at y 41 and its squares at the cell's right end.", [
        sp_fig(["default"], bcrop(vlayer, "v1-"), wide=True, gen=not viewi),
        sp_fig(["on (band cell tinted)"], bcrop(vlayer, "v2-", ai_ui={"tint": vg, "view": {vg: "is-ai-on"}}), wide=True, gen=not viewi),
        sp_fig(["hidden"], bcrop(vlayer, "v3-", cls="pm-board"), wide=True, gen=not viewi),
        sp_fig(["peek"], bcrop(vlayer, "v4-", cls="pm-board", ai_ui={"view": {vg: "is-ai-peek"}}), wide=True, gen=not viewi),
    ])
    alayer = layer if alli else dict(layer, ai=[{"id": "AI-01", "title": "Keep one history", "origin": "suggested", "does": "Keeps one history.",
                                                 "groups": "all", "cite": (sugg or items[0])["cite"]}])
    alayer = dict(alayer, ai=[alli or alayer["ai"][0]])
    add("ai-all", "All-views bracket", "An all-views item is drawn once: a bracket along the band's top edge, and ALL VIEWS with its squares in the gutter's band cell.", [
        sp_fig(["default"], bcrop(alayer, "a1-", gutter=True), wide=True, gen=not alli),
        sp_fig(["on (every band cell tinted, nothing fades)"], bcrop(alayer, "a2-", gutter=True, ai_ui={"tint": "all", "all": "is-ai-on"}), wide=True, gen=not alli),
        sp_fig(["hidden"], bcrop(alayer, "a3-", gutter=True, cls="pm-board"), wide=True, gen=not alli),
        sp_fig(["peek"], bcrop(alayer, "a4-", gutter=True, cls="pm-board", ai_ui={"all": "is-ai-peek"}), wide=True, gen=not alli),
    ])
    tpl, _ = board_template()
    legend = re.search(r'<aside class="pm-legend".*?</aside>', tpl, re.S).group(0)
    lg_on = legend.replace("<!--slot:legend-end-->", fill(F["legend-end"], client=esc(m["meta"]["client"])))
    add("ai-legend", "Legend block", "Appended to the base legend. It fades to 40% with the layer off, and is left out when the layer has no items.", [
        sp_fig(["on"], f'<div style="width:392px;max-width:100%">{lg_on}</div>', gen=False),
        sp_fig(["off"], f'<div style="width:392px;max-width:100%">{lg_on.replace("pm-legend", "pm-legend is-ai-off", 1)}</div>', gen=False),
        sp_fig(["left out when ai is empty"], f'<div style="width:392px;max-width:100%">{legend.replace("<!--slot:legend-end-->", "")}</div>', gen=True),
    ], "420px")
    tog = lambda pressed, state, extra="": fill(F["toggle"], pressed=pressed, state=state).replace('class="pm-ai-toggle"', f'class="pm-ai-toggle{extra}"')
    add("ai-toggle", "Toggle", "On at every load and not remembered. Off hides the marks; the cards, summary and legend stay.", [
        sp_fig(["on"], tog("true", "On"), gen=False), sp_fig(["off"], tog("false", "Off"), gen=False),
        sp_fig(["hover"], tog("true", "On", " is-hover"), gen=False), sp_fig(["focus-visible"], tog("true", "On", " is-focus"), gen=False),
        sp_fig(["None when ai is empty"], F["toggle-none"], gen=True),
    ], "200px")
    emm, eam = mk(dict(layer, ai=[]), "z-")
    add("ai-summary", "Summary strip", "Computed from the layer: a zero segment is left out, and decisions are not steps.", [
        sp_fig(["standard"], am.summary(), block=True, wide=True, gen=False),
        sp_fig(["off"], am.summary(off=True), block=True, wide=True, gen=False),
        sp_fig(["empty"], eam.summary(), block=True, wide=True, gen=True),
    ])
    add("ai-card", "AI card", "First in the evidence grid: one row per item, by id.", [
        sp_fig(["list"], mk(layer, "c1-")[1].card_html(F), block=True, wide=True, gen=False),
        sp_fig(["empty"], eam.card_html(F), block=True, wide=True, gen=True),
    ])
    rid = (named or items[0])["id"]
    def row(state, pre):
        a, b = mk(layer, pre)
        return f'<article class="pm-ev-card pm-ai-card sp-mock"><ol class="pm-ai-list">{b.row_html(by[rid], state)}</ol></article>'
    add("ai-row", "Card row", "Square, id and title, origin chip, Show on map, what it would do, its targets and its evidence.", [
        sp_fig(["default"], row("", "r1-"), block=True, wide=True, gen=False),
        sp_fig(["active"], row("is-ai-active", "r2-"), block=True, wide=True, gen=False),
        sp_fig(["linked (its step hovered)"], row("is-ai-linked", "r3-"), block=True, wide=True, gen=False),
        sp_fig(["pinned"], row("is-ai-pinned", "r4-"), block=True, wide=True, gen=False),
    ])
    # evidence: grounded with quote, grounded without, inferred
    def ev(it, pre):
        a, b = mk(dict(layer, ai=[it]), pre)
        return f'<div class="sp-mock">{b.evidence_html(it)}</div>'
    gq = next((i for i in items if any(ctype(c) == "grounded" and c.get("quote") for c in i["cite"])), None)
    gn = next((i for i in items if any(ctype(c) == "grounded" and not c.get("quote") for c in i["cite"])), None)
    inf = next((i for i in items if any(ctype(c) == "inferred" for c in i["cite"])), None)
    gq_it = dict(gq, cite=[c for c in gq["cite"] if ctype(c) == "grounded" and c.get("quote")]) if gq else None
    gn_it = (dict(gn, cite=[c for c in gn["cite"] if ctype(c) == "grounded" and not c.get("quote")]) if gn
             else dict(gq, cite=[{k: v for k, v in c.items() if k != "quote"} for c in gq_it["cite"]]))
    inf_it = dict(inf, cite=[c for c in inf["cite"] if ctype(c) == "inferred"])
    add("ai-evidence", "Evidence", "A grounded citation shows its quote, or else its first record's text, then the address with the speaker or the web domain. An inferred one shows its basis and where it was read from.", [
        sp_fig(["grounded quote"], ev(gq_it, "e1-"), block=True, gen=False),
        sp_fig(["grounded without a quote"], ev(gn_it, "e2-"), block=True, gen=not gn),
        sp_fig(["inferred"], ev(inf_it, "e3-"), block=True, gen=False),
    ], "320px")
    def agr(it, pre, open_=False):
        a, b = mk(layer, pre)
        return f'<div class="sp-mock">{b.agentic_html(it.get("agentic"), open_)}</div>'
    add("ai-agentic", "Agentic version", "Folded by default; a numbered spine of steps with each place a person decides, then systems with the base icons, then logging. No orange inside. Print opens every block.", [
        sp_fig(["folded"], agr(agi, "g1-"), block=True, wide=True, gen=False),
        sp_fig(["open", "print (open)"], agr(agi, "g2-", True), block=True, wide=True, gen=False),
        sp_fig(["absent"], row("", "g3-").replace(by[rid]["id"], by[rid]["id"]) if not by[rid].get("agentic") else
               f'<article class="pm-ev-card pm-ai-card sp-mock"><ol class="pm-ai-list">{mk(layer, "g4-")[1].row_html(noag or by[rid])}</ol></article>',
               block=True, wide=True, gen=False, note="The row ends after its evidence."),
    ])
    add("ai-empty", "Empty state", "ai: [] draws the base board, the toggle reads None, the legend block is left out, and the card holds one dashed row.", [
        sp_fig(["ai: []"], page_with(dict(layer, ai=[]), "em-"), block=True, wide=True, gen=True),
    ])
    tm, ta = mk(layer, "t-")
    add("ai-tip", "Tooltip lines", "Through the tooltip-lines hook: one line per item on the step, then “Click to open the card”. There is one tooltip.", [
        sp_fig(["a step with items"], f'<div class="pm-tip is-static sp-tipbox">{tm.tip(tm.N[n_sugg])}{ta.tip_lines()[n_sugg]}</div>', gen=False),
    ], "300px")
    link_id = (sugg or items[0])["id"]
    hover_ids = ",".join(i["id"] for i in am.by_node.get(n_sugg, []))
    add("ai-link", "Linking", "Live in the example above. Frozen here with the real overlay code: a row lights its steps and fades the rest; a step lights its rows; a click pins; Esc unpins.", [
        sp_fig(["card to board"], page_with(layer, "l1-", f"focus:{link_id}"), block=True, wide=True, gen=False, note=f"{link_id} hovered in the card."),
        sp_fig(["board to card"], page_with(layer, "l2-", f"node:{n_sugg}:{hover_ids}"), block=True, wide=True, gen=False, note=f"{n_sugg} hovered on the board."),
        sp_fig(["click pins", "Esc unpins"], page_with(layer, "l3-", f"pin:{link_id}"), block=True, wide=True, gen=False,
               note=f"{link_id} pinned with Show on map; Esc releases it."),
    ])
    return sp_page("AI layer: every element", "design-system/process-map-ai-opportunity · specimen",
                   "Built from <code>examples/</code> by <code>design-system/process-map/build_map.py --specimen</code>. Each section is an element of the README's table, at its anchor; "
                   "a state the examples lack is drawn from a generated variant of them, marked <span class=\"sp-gen\">generated</span>.",
                   {"toc": toc, "body": sections}, ai=True)


def build_specimens(ws):
    rules = load_rules()
    idx = Index(ws, rules)
    base = first("process-map", ws)
    layer = first("process-map-ai-opportunity", ws)
    pm = pm_specimen(ws, idx, base)
    ai = ai_specimen(ws, idx, base, layer)
    write(HERE / "specimen.html", pm)
    write(AI_DIR / "specimen.html", ai)
    WARNINGS.clear()   # the generated variants cut text on purpose ("long title", "long question")


# ------------------------------------------------------------------ CLI

def write(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


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
        print(f"ERROR a map or record file is malformed ({type(e).__name__}: {e}) -> run bs.py check", file=sys.stderr)
        return 1
    except DataError as e:
        for w in WARNINGS:
            print(f"WARN {w}", file=sys.stderr)
        print(f"ERROR {e}", file=sys.stderr)
        return 1
    except CannotRun as e:
        print(f"ERROR cannot run: {e}", file=sys.stderr)
        return 2
    for w in WARNINGS:
        print(f"WARN {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

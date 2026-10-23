#!/usr/bin/env python3
"""build_citations.py: the Citation points page of one workspace, out/citation-points.html.

    python3 design-system/citation-points/build_citations.py <ws> <out.html>

One row per citation point the workspace's pages use. A point is a record address as a citation writes it
(WB1 Steps row 2), or an absent search of one address for one needle. A row shows the address, the verbatim records
it resolves to, and what uses it: the kind of citation (Grounded, Inferred from, Absent search) and the elements,
each linked to the page that shows it. Rows are grouped by record file, with a header per file that links to its row
in Original data received. A row's id is its point's anchor (formats/FORMATS.md section 2.6): the anchor every page's
Citation points section links to.

Everything is computed from records/ and the section files, and nobody authors any of it:
  - process-map/<name>.json: systems, lanes, nodes, gaps and clarifications (their cite arrays, and the [ ] markers
    in card prose), shown on out/process-map/<name>.html. A system's software is shown on out/data-received.html;
  - process-map-ai-opportunity/<name>.json: each AI item, on out/process-map-ai-opportunity/<name>.html;
  - document/<name>.md: its [ ] brackets and Grounded, Inferred and Gap lines, under the heading they sit in, on
    out/document/<name>.html. The document type's own parser (design-system/document/build_doc.py) reads it;
  - inventory/<name>.json: each module, on out/data-received.html.
The locator grammars come from formats/citation-types.json, and the page's required elements from template.json.

Standard library only. Deterministic: no timestamps, no random ids, every list sorted. The page holds no inputs/
path, no absolute path and no hash.

Exit codes: 0 the page is written. 1 a section or record file cannot be read, or a required element is not
fulfilled (the page is still written, and each missing element is printed with what fulfils it). 2 cannot run.
"""

import html
import importlib.util
import json
import pathlib
import re
import sys
import unicodedata

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TEMPLATE = HERE / "template.html"
ELEMENTS = HERE / "template.json"
CITATION_TYPES = ROOT / "formats" / "citation-types.json"
MAP_SCHEMA = ROOT / "design-system" / "process-map" / "process-map.schema.json"
BUILD_DOC = ROOT / "design-system" / "document" / "build_doc.py"

SHOWN = 6  # records of a span shown before the rest fold away
USE = {"grounded": "Grounded", "inferred": "Inferred from", "absent": "Absent search"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
RECEIVED = {
    "key": "data-received",
    "name": "",
    "kind": "data received",
    "file": "data-received.html",
    "section": "#citation-points",
    "rank": 3,
}


class CannotRun(Exception):
    pass


class DataError(Exception):
    pass


# ------------------------------------------------------------------ small helpers


def h(s):
    return html.escape(str(s), quote=True)


def anchor(address):
    """FORMATS.md section 2.6: src- plus the address in lower case, ¶ written para, other runs written -."""
    return "src-" + re.sub(r"[^a-z0-9]+", "-", address.lower().replace("¶", "para")).strip("-")


def needle_slug(s):
    """An absent search's anchor adds -not- and this slug of its needle, as every page writes it."""
    return re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", s).lower()).strip("-") or "x"


def received_slug(s):
    """The slug Original data received gives its software and module rows (sw-, mod-)."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def pdate(iso):
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def natural(s):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.casefold()) for t in re.split(r"(\d+)", s) if t]


def is_str(v):
    return isinstance(v, str) and v != ""


def objs(v):
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def read_json(p, what):
    try:
        return json.loads(p.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise DataError(f"{what} cannot be read ({e.__class__.__name__}): run bs.py check") from e


def ws_label(ws):
    """The client's name as the maps' meta.client gives it, when they agree; else the workspace folder's name
    (data-received README section 1)."""
    clients = set()
    for p in sorted((ws / "process-map").glob("*.json")):
        try:
            c = json.loads(p.read_text(encoding="utf-8")).get("meta", {}).get("client")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(c, str) and c.strip():
            clients.add(c.strip())
    if len(clients) == 1:
        return clients.pop()
    return (
        " ".join(w[:1].upper() + w[1:] for w in re.split(r"[-_\s]+", ws.resolve().name) if w) or "Workspace"
    )


# ------------------------------------------------------------------ records and resolution (FORMATS.md section 1)


class Records:
    """Every records/<ID>.json, and resolution by containment in the locator grammars of citation-types.json."""

    def __init__(self, ws, kinds):
        self.kinds = kinds
        self.unit_re = {k: re.compile(v["record"]) for k, v in kinds.items()}
        self.span_re = {k: {n: re.compile(r) for n, r in v["spans"].items()} for k, v in kinds.items()}
        self.src = {}
        d = ws / "records"
        for p in sorted(d.glob("*.json")) if d.is_dir() else []:
            r = read_json(p, f"records/{p.name}")
            if not (
                isinstance(r, dict)
                and is_str(r.get("id"))
                and r.get("kind") in kinds
                and isinstance(r.get("records"), list)
            ):
                raise DataError(f"records/{p.name} is not a record file: run bs.py check")
            recs = [
                {
                    "locator": x["locator"],
                    "text": x["text"],
                    "context": x.get("context"),
                    "i": i,
                    "key": self.key(r["kind"], x["locator"]),
                }
                for i, x in enumerate(objs(r["records"]))
                if is_str(x.get("locator")) and is_str(x.get("text"))
            ]
            self.src[r["id"]] = {"head": r, "recs": recs}

    @staticmethod
    def _col(s):
        n = 0
        for ch in s:
            n = n * 26 + ord(ch) - 64
        return n

    @staticmethod
    def _ms(hh, mm, ss, frac=None):
        return ((int(hh) * 60 + int(mm)) * 60 + int(ss)) * 1000 + (int(frac) if frac else 0)

    def key(self, kind, loc):
        m = self.unit_re[kind].match(loc)
        if not m:
            return None
        g = m.groups()
        if kind == "sheet":
            return (g[0], int(g[2]), self._col(g[1]))
        if kind in ("document", "web"):
            return (int(g[0]) if g[0] else 0, int(g[1]))
        return self._ms(*g)

    def pred(self, kind, loc):
        k = self.key(kind, loc)
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
                    pg = int(g[0])
                    return lambda x: x[0] == pg
                pg, a, b = (int(g[0]) if g[0] else 0), int(g[1]), int(g[2])
                return lambda x: x[0] == pg and a <= x[1] <= b
            a, b = self._ms(*g[:4]), self._ms(*g[4:]) + (0 if g[7] else 999)
            return lambda x: a <= x <= b
        return None

    def resolve(self, sid, loc):
        """The records an address reaches, [] when none, None when there is no record file."""
        s = self.src.get(sid)
        if s is None:
            return None
        if loc is None:
            return list(s["recs"])
        p = self.pred(s["head"]["kind"], loc)
        return [r for r in s["recs"] if p and r["key"] is not None and p(r["key"])]


# ------------------------------------------------------------------ the points and what uses them


class Points:
    """Every citation point, keyed as the pages key them: an address, or an address and a needle."""

    def __init__(self, records):
        self.records, self.by = records, {}

    def add(self, ref, kind, use, needle=None):
        if not (isinstance(ref, dict) and is_str(ref.get("source"))):
            return
        sid, loc = ref["source"], ref.get("locator") if is_str(ref.get("locator")) else None
        address = f"{sid} {loc}" if loc else sid
        p = self.by.get((address, needle))
        if p is None:
            got = self.records.resolve(sid, loc)
            p = self.by[(address, needle)] = {
                "source": sid,
                "locator": loc,
                "address": address,
                "needle": needle,
                "recs": got or [],
                "anchor": anchor(address) + ("" if needle is None else "-not-" + needle_slug(needle)),
                "uses": [],
            }
        u = (use[0]["key"], kind, use[1], use[2])
        if u not in p["uses"]:
            p["uses"].append(u)

    def cites(self, cites, use):
        """One element's cite array: grounded, inferred (its from) and absent (its in, with its needle)."""
        for c in objs(cites):
            t = c.get("type", "grounded")
            if t == "grounded":
                self.add(c, "grounded", use)
            elif t == "inferred":
                for f in objs(c.get("from")):
                    self.add(f, "inferred", use)
            elif t == "absent" and is_str(c.get("needle")):
                for s in objs(c.get("in")):
                    self.add(s, "absent", use, c["needle"])


def section_paths(ws, sec, ext, name_re):
    d = ws / sec
    ps = sorted(d.iterdir()) if d.is_dir() else []
    return [
        p
        for p in ps
        if not p.name.startswith(".") and p.suffix == ext and name_re.match(p.stem) and p.is_file()
    ]


def page(sec, name, kind, rank, title=None):
    """A page that uses points, named by its title (else its file name)."""
    return {
        "key": f"{sec}/{name}",
        "name": title if isinstance(title, str) and title.strip() else name,
        "kind": kind,
        "file": f"{sec}/{name}.html",
        "section": "#citation-points",
        "rank": rank,
    }


def bracket_refs(text, bracket, part, ids):
    """The citations of [ ] markers in card prose: a bracket that names a record file. Escaped brackets are text."""
    for m in bracket.finditer(re.sub(r"\\[\[\]]", "", text)):
        refs = []
        for p in m.group(1).split(";"):
            f = part.match(p.strip())
            if not f:
                refs = []
                break
            refs.append({"source": f.group(1), **({"locator": f.group(2).strip()} if f.group(2) else {})})
        if any(r["source"] in ids for r in refs):
            yield from refs


def load_doc_parser():
    """The document type's own parser, so that this page reads a document as its page is built."""
    if not BUILD_DOC.is_file():
        raise CannotRun("design-system/document/build_doc.py is missing")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("build_doc", BUILD_DOC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def document_uses(path, pg, pts, rules, bd):
    """A document's citations, each used by the heading it sits under (linked by the heading's own id), or by its
    title and lead. Provenance lines read as formats/citation-types.json › documentLines writes them."""
    lines = rules["documentLines"]
    part = re.compile(lines["bracketPart"])
    prov = {w: re.compile(lines[w]) for w in ("Grounded", "Inferred", "Gap")}
    ids = sorted(pts.records.src)
    try:
        text = path.read_bytes().decode("utf-8")
        lines = list(enumerate(text.splitlines(), start=1))
        end = next((k for k, (_, ln) in enumerate(lines) if k and ln.strip() == "---"), 0)
        if (
            lines and lines[0][1].strip() == "---"
        ):  # the mode line is bs.py's, never the builder's (FORMATS.md section 4)
            lines = [
                x for k, x in enumerate(lines) if not (0 < k < end and re.match(r"^mode\s*:", x[1], re.I))
            ]
        meta, body = bd.front_matter(lines)
        if meta.get("title"):
            pg["name"] = meta["title"]
        blocks = bd.parse_blocks(body)
    except (OSError, ValueError, bd.BuildError) as e:
        raise DataError(f"document/{path.name} cannot be parsed ({e}): run bs.py check") from e
    doc = bd.Doc({i: {"name": i, "note": ""} for i in ids}, path.parent, True)

    def refs_of(s):
        out = []
        for p in s.split(";"):
            p = p.strip()
            if p.startswith("[") and p.endswith("]"):
                p = p[1:-1].strip()
            f = part.match(p)
            if not f:
                return []
            out.append({"source": f.group(1), **({"locator": f.group(2).strip()} if f.group(2) else {})})
        return out

    def scan(t, el):
        t = re.sub(r"(`+)(.+?)\1", " ", t)
        t = re.sub(r"<!--.*?-->", "", t)
        t = re.sub(r"\\([\\`*\[\]_#+.!|-])", " ", t)
        t = re.sub(r"\[([^\[\]]+)\]\(([^)\s]+)\)", " ", t)
        for m in re.finditer(r"\[([^\[\]]+)\]", t):
            for sid, loc in doc.parse_bracket(m.group(1)) or []:
                pts.add({"source": sid, **({"locator": loc} if loc else {})}, "grounded", (pg, el[0], el[1]))

    def line(t, el):
        t = re.sub(r"<!--.*?-->", "", t).strip()
        for word, rx in prov.items():
            m = rx.match(t) if t.startswith(word + " · ") else None
            if m and word == "Grounded":
                for r in refs_of(m.group(1)):
                    pts.add(r, "grounded", (pg, el[0], el[1]))
            elif m and word == "Inferred":
                for r in refs_of(m.group(2)):
                    pts.add(r, "inferred", (pg, el[0], el[1]))
            elif m:
                for r in refs_of(m.group(1)):
                    pts.add(r, "absent", (pg, el[0], el[1]), m.group(2))
            if m:
                return
        scan(t, el)

    def walk(bs, el, examples=False):
        for b in bs:
            k = b[0]
            if k == "h" and not examples:
                el = (
                    re.sub(r"\*\*|`|\s*\[[^\]]*\]", "", b[2]).strip() or "Heading",
                    f"{pg['file']}#{doc.slug(b[2])}",
                )
                scan(b[2], el)
            elif k in ("h", "quote"):
                scan(b[2] if k == "h" else b[1], el)
            elif k == "p":
                (scan if examples else line)(b[1], el)  # an :::examples text is never a provenance line
            elif k in ("ul", "ol"):
                for t in [x for item, kids in b[1] for x in [item] + bd.kid_texts(kids)]:
                    scan(t, el)
            elif k == "table":
                for c in b[1] + [c for row in b[3] for c in row]:
                    scan(c, el)
            elif k == "sep":
                scan(b[1], el)
            elif k == "dir":
                if b[2]:
                    scan(b[2], el)
                walk(bd.parse_blocks(b[3]), el, examples=b[1] == "examples")

    i, intro = 0, ("Title and lead", pg["file"])
    if blocks and blocks[0][0] == "h" and blocks[0][1] == 1:
        scan(blocks[0][2], intro)
        i = 1
        while i < len(blocks) and blocks[i][0] == "quote" and i <= 2:
            scan(blocks[i][1], intro)
            i += 1
    walk(blocks[i:], intro)


def collect(ws, rules, records, bd):
    """Every point and its uses, in page order: maps, AI layers, documents, then inventory files."""
    try:
        name_re = re.compile(
            json.loads(MAP_SCHEMA.read_text(encoding="utf-8"))["$defs"]["sectionFile"]["pattern"]
        )
    except (OSError, ValueError, KeyError) as e:
        raise CannotRun(
            f"design-system/process-map/process-map.schema.json gives no sectionFile pattern ({e})"
        ) from e
    lines = rules["documentLines"]
    bracket, part = re.compile(lines["bracket"]), re.compile(lines["bracketPart"])
    ids = set(records.src)
    pts, pages = Points(records), {RECEIVED["key"]: RECEIVED}
    for p in section_paths(ws, "process-map", ".json", name_re):
        d = read_json(p, f"process-map/{p.name}")
        d = d if isinstance(d, dict) else {}
        title = (d.get("meta") or {}).get("title") if isinstance(d.get("meta"), dict) else None
        pg = pages.setdefault(f"process-map/{p.stem}", page("process-map", p.stem, "map", 0, title))
        for s in objs(d.get("systems")):
            if is_str(s.get("id")):
                pts.cites(s.get("cite"), (pg, s.get("label") or s["id"], f"{pg['file']}#sys-{s['id']}"))
            sw = s.get("software")
            if isinstance(sw, dict) and is_str(sw.get("name")):
                pts.cites(
                    sw.get("cite"),
                    (RECEIVED, sw["name"], f"{RECEIVED['file']}#sw-{received_slug(sw['name']) or 'x'}"),
                )
        for ln in objs(d.get("lanes")):
            if is_str(ln.get("id")):
                pts.cites(ln.get("cite"), (pg, ln.get("label") or ln["id"], f"{pg['file']}#lane-{ln['id']}"))
        for key, prose in (
            ("nodes", ()),
            ("gaps", ("title", "text")),
            ("clarifications", ("title", "shows", "ask")),
        ):
            for i, el in enumerate(objs(d.get(key))):
                if not is_str(el.get("id")):
                    continue
                shown = {"gaps": f"Gap {i + 1}", "clarifications": f"Clarification {i + 1}"}.get(
                    key, el["id"]
                )
                use = (pg, shown, f"{pg['file']}#{el['id']}")  # named as the page shows it
                pts.cites(el.get("cite"), use)
                for f in prose:
                    for r in bracket_refs(el[f], bracket, part, ids) if is_str(el.get(f)) else []:
                        pts.add(r, "grounded", use)
    for p in section_paths(ws, "process-map-ai-opportunity", ".json", name_re):
        d = read_json(p, f"process-map-ai-opportunity/{p.name}")
        meta = d.get("meta") if isinstance(d, dict) and isinstance(d.get("meta"), dict) else {}
        pg = pages.setdefault(
            f"process-map-ai-opportunity/{p.stem}",
            page("process-map-ai-opportunity", p.stem, "AI", 1, meta.get("title")),
        )
        for it in objs(d.get("ai") if isinstance(d, dict) else None):
            if is_str(it.get("id")):
                pts.cites(it.get("cite"), (pg, it["id"], f"{pg['file']}#{it['id']}"))
    for p in section_paths(ws, "document", ".md", name_re):
        pg = pages.setdefault(f"document/{p.stem}", page("document", p.stem, "document", 2))
        document_uses(p, pg, pts, rules, bd)
    seen = set()
    for p in section_paths(ws, "inventory", ".json", name_re):
        d = read_json(p, f"inventory/{p.name}")
        for mo in objs(d.get("modules") if isinstance(d, dict) else None):
            if not (is_str(mo.get("id")) and is_str(mo.get("title"))):
                continue
            a = "mod-" + received_slug(mo["id"])  # as Original data received names its module rows
            while a in seen:
                a += "-" + received_slug(p.stem)
            seen.add(a)
            pts.cites(mo.get("cite"), (RECEIVED, mo["title"].split(" · ")[0], f"{RECEIVED['file']}#{a}"))
    return pts, pages


# ------------------------------------------------------------------ the page


def verbatim(p):
    """The records a point resolves to, verbatim: one record, a span's records, or what an absent search searched."""
    if not p["recs"]:
        return '<p class="miss">Resolves to no record. <code>bs.py check</code> names the fix.</p>'
    if p["needle"] is not None:
        state = "Provisional" if p["coverage"] != "complete" else "Proven"
        return (
            f'<p class="vb ab">Searched {plural(len(p["recs"]), "record")} for <q>{h(p["needle"])}</q>: '
            f'not found <span class="st">· {state}</span></p>'
        )

    def rec(r, sub):
        ctx = f'<span class="ctx">{h(r["context"])}</span>' if r.get("context") else ""
        return (
            f'<code class="sub">{h(r["locator"])}</code><span>{ctx}<q>{h(r["text"])}</q></span>'
            if sub
            else ctx + f"<q>{h(r['text'])}</q>"
        )

    if len(p["recs"]) == 1 and p["locator"] == p["recs"][0]["locator"]:
        return f'<p class="vb">{rec(p["recs"][0], False)}</p>'
    lis = [f"<li>{rec(r, True)}</li>" for r in p["recs"]]
    more = ""
    if len(lis) > SHOWN + 1:
        more = (
            f'<details class="more"><summary>{len(lis) - SHOWN} more records</summary>'
            f'<ul class="vl">{"".join(lis[SHOWN:])}</ul></details>'
        )
        lis = lis[:SHOWN]
    return f'<ul class="vl">{"".join(lis)}</ul>{more}'


def used_by(p, pages):
    """One line per kind and page: the kind (said once), the elements, each linked to itself, and the page, linked
    to its own Citation points section. Pages in toolkit order: maps, AI layers, documents, Original data received."""
    keys = sorted({u[0] for u in p["uses"]}, key=lambda k: (pages[k]["rank"], natural(k)))
    out, last = [], None
    for kind in ("grounded", "inferred", "absent"):
        for key in keys:
            els = [(lb, hr) for k, kd, lb, hr in p["uses"] if k == key and kd == kind]
            if not els:
                continue
            pg = pages[key]
            name = f"{h(pg['name'])} · {h(pg['kind'])}" if pg["name"] else h(pg["kind"])
            links = ", ".join(f'<a href="{h(hr)}">{h(lb)}</a>' for lb, hr in els)
            out.append(
                f'<li class="use"><span class="k">{USE[kind] if kind != last else ""}</span><span class="els">{links}'
                f' <a class="pg" href="{h(pg["file"] + pg["section"])}">{name}</a></span></li>'
            )
            last = kind
    return f'<ul class="ub">{"".join(out)}</ul>'


def point_row(p, pages):
    where = h(p["address"]) if p["locator"] or p["needle"] is None else f"{h(p['source'])} · whole source"
    return (
        f'<li class="pt" id="{h(p["anchor"])}"><span class="pt-a"><code class="loc">{where}</code></span>'
        f'<div class="pt-v">{verbatim(p)}</div>{used_by(p, pages)}</li>'
    )


def unused_row(sid, r):
    ctx = f'<span class="ctx">{h(r["context"])}</span>' if r.get("context") else ""
    return (
        f'<li class="ur"><span class="pt-a"><code class="loc">{h(sid)} {h(r["locator"])}</code></span>'
        f'<div class="pt-v"><p class="vb">{ctx}<q>{h(r["text"])}</q></p></div><span class="ub mut">Not cited</span></li>'
    )


def group(sid, src, pts, kinds, pages):
    head = src["head"]
    mine = sorted(
        (p for p in pts if p["source"] == sid),
        key=lambda p: (
            not p["recs"],
            p["needle"] is not None,
            p["recs"][0]["i"] if p["recs"] else 0,
            -len(p["recs"]),
            natural(p["address"]),
            natural(p["needle"] or ""),
        ),
    )
    used = {r["i"] for p in mine if p["needle"] is None for r in p["recs"]}
    unused = [r for r in src["recs"] if r["i"] not in used]
    meta = [kinds[head["kind"]]["label"]]
    if is_str(head.get("captured")) and re.match(r"^\d{4}-\d{2}-\d{2}$", head["captured"]):
        meta.append("captured " + pdate(head["captured"]))
    m = re.match(r"^https?://([^/:?#]+)", head.get("url") or "")
    if m:
        meta.append(m.group(1)[4:] if m.group(1).startswith("www.") else m.group(1))
    if head.get("legacy") is True:
        meta.append("Legacy")
    detail = f'<span class="gh-d">{h(head["detail"])}</span>' if is_str(head.get("detail")) else ""
    count = (
        f"{plural(len(mine), 'point')} · {len(src['recs']) - len(unused)} of {plural(len(src['recs']), 'record')} cited"
        if mine
        else "Not cited by any page"
    )
    rows = (
        "".join(point_row(p, pages) for p in mine)
        or '<li class="pt-none">No page cites this record file.</li>'
    )
    urs = (
        "".join(unused_row(sid, r) for r in unused)
        or '<li class="pt-none">Every record of this file is cited.</li>'
    )
    return (
        f'<section class="grp" id="{anchor(sid)}" aria-labelledby="{anchor(sid)}-h">'
        f'<header class="gh"><h2 class="gh-id" id="{anchor(sid)}-h"><a href="data-received.html#{h(sid)}" '
        f'title="Open {h(sid)} in Original data received">{h(sid)}</a></h2>'
        f'<div class="gh-t"><b>{h(head.get("title") or sid)}</b><span class="gh-m">{h(" · ".join(meta))}</span>{detail}</div>'
        f'<div class="gh-n">{count}</div></header>'
        f'<ol class="pts">{rows}</ol><ol class="urs">{urs}</ol></section>'
    )


def fill(tpl, slots):
    """One pass over the template, so text inserted into one slot is never read as another slot."""
    for k in slots:
        if "{{" + k + "}}" not in tpl:
            raise CannotRun(f"design-system/citation-points/template.html has no {{{{{k}}}}} slot")
    return re.sub(r"\{\{([a-z]+)\}\}", lambda m: slots.get(m.group(1), m.group(0)), tpl)


def render(ws, records, pts, pages, kinds):
    points = list(pts.by.values())
    for p in points:
        src = records.src.get(p["source"])
        p["coverage"] = src["head"].get("coverage") if src else None
    sids = sorted(records.src, key=natural)
    lines = sum(len(s["recs"]) for s in records.src.values())
    cited_lines = sum(
        len({r["i"] for p in points if p["source"] == sid and p["needle"] is None for r in p["recs"]})
        for sid in sids
    )
    used_files = len({p["source"] for p in points if p["source"] in records.src})
    elements = len({(u[0], u[3]) for p in points for u in p["uses"]})
    used_pages = len({u[0] for p in points for u in p["uses"]})
    lede = (
        f"{plural(len(points), 'citation point')} in {used_files} of {plural(len(sids), 'record file')} · "
        f"{cited_lines} of {plural(lines, 'record')} cited · used by {plural(elements, 'element')} on {plural(used_pages, 'page')}"
    )
    toc = "".join(
        f'<li><a href="#{anchor(sid)}"><span class="toc-t">{h(sid)}</span>'
        f'<span class="toc-c">{sum(1 for p in points if p["source"] == sid)}</span></a></li>'
        for sid in sids
    )
    orphans = sorted({p["source"] for p in points} - set(records.src), key=natural)
    body = "".join(group(sid, records.src[sid], points, kinds, pages) for sid in sids)
    if orphans:  # a citation of a record file the workspace does not have: shown, never dropped
        body += (
            '<section class="grp" id="src-missing"><header class="gh"><h2 class="gh-id warn">Missing</h2>'
            '<div class="gh-t"><b>Cited, but no record file</b></div><div class="gh-n"></div></header><ol class="pts">'
            + "".join(point_row(p, pages) for p in points if p["source"] in orphans)
            + "</ol></section>"
        )
    label = ws_label(ws)
    example = next((p["anchor"] for p in points), "src-wb1-steps-row-2")
    foot = (
        f"Computed from records/ and the section files of {label}; never authored. A row's id is its point's anchor, "
        f"the one every page's Citation points section links to, for example citation-points.html#{example}. "
        "A record file's id opens its row in Original data received."
    )
    return fill(
        TEMPLATE.read_text(encoding="utf-8"),
        {
            "title": h(f"{label} · citation points"),
            "lede": h(lede),
            "toc": toc,
            "body": body,
            "foot": h(foot),
            "total": str(len(points)),
            "unused": str(lines - cited_lines),
        },
    ), points


def required():
    t = json.loads(ELEMENTS.read_text(encoding="utf-8"))
    return [(e["id"], e["title"], e["fulfilled_by"]) for e in t["elements"] if e.get("required")]


def main(argv):
    if len(argv) != 2 or argv[0].startswith("-"):
        print(
            "usage: python3 design-system/citation-points/build_citations.py <ws> <out.html>", file=sys.stderr
        )
        return 2
    ws, out = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    try:
        if not (ws / "inputs").is_dir():
            raise CannotRun("the workspace has no inputs/ folder")
        for p in (TEMPLATE, ELEMENTS, CITATION_TYPES):
            if not p.is_file():
                raise CannotRun(f"{p.relative_to(ROOT).as_posix()} is missing")
        rules = json.loads(CITATION_TYPES.read_text(encoding="utf-8"))
        need = required()
        bd = load_doc_parser()
        records = Records(ws, rules["kinds"])
        pts, pages = collect(ws, rules, records, bd)
        doc, points = render(ws, records, pts, pages, rules["kinds"])
    except CannotRun as e:
        print(f"cannot run: {e}", file=sys.stderr)
        return 2
    except DataError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(doc.encode("utf-8"))
    except OSError as e:
        print(f"cannot run: the page cannot be written ({e.strerror})", file=sys.stderr)
        return 2
    fulfilled = {
        "points": bool(points),
        "resolves": all(p["recs"] for p in points),
        "used-by": all(p["uses"] for p in points),
    }
    unknown = [eid for eid, _t, _by in need if eid not in fulfilled]
    if unknown:
        print(
            f"cannot run: template.json requires {', '.join(unknown)}, which build_citations.py does not check",
            file=sys.stderr,
        )
        return 2
    missing = [(t, by) for eid, t, by in need if not fulfilled[eid]]
    print(
        f"{plural(len(points), 'citation point')} from {plural(len({p['source'] for p in points}), 'record file')}"
    )
    print(f"{len(need) - len(missing)} of {len(need)} required elements fulfilled")
    for t, by in missing:
        print(f"missing  {t}  -> {by}")
    for p in points:
        if not p["recs"]:
            print(f"         {p['address']} resolves to no record")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

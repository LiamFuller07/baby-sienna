#!/usr/bin/env python3
"""build_received.py: the Original data received page of one workspace, and its deliverable, the systems inventory.

    python3 design-system/data-received/build_received.py <ws> <out.html>               out/data-received.html
    python3 design-system/data-received/build_received.py --inventory <ws> <out.html>   out/systems-inventory.html

Original data received has two views over one Citation points section:
  - Overview: Folders of data, Systems identified, Software used, Modules likely to be used;
  - Folder view: one full-width table of inputs/, grouped and searchable. Its rows are where every citation on the
    other pages lands (#<RECORD ID>).
The systems inventory is the client-ready page of the last three Overview sections, with its own Citation points.

Everything on both pages is computed, and nobody authors any of it. It comes from:
  - inputs/ (every file and folder, hidden ones skipped);
  - records/*.json (headers, records and sha256);
  - the section files (process-map/, process-map-ai-opportunity/, document/) and inventory/ (the modules).
Kinds and locator grammars come from formats/citation-types.json, and the required elements of each page from
template.json beside this file.

bs.py builds Original data received even when check fails, so invalid workspace data never stops this builder. A
record file it cannot use becomes an Error row, a section file it cannot read is skipped, and a citation that does
not resolve is shown as such.

Standard library only. Deterministic: no timestamps, no file dates, no random ids, every list sorted. The data-received
page holds no absolute path and no full hash (a hash is cut to 8 hex characters); the systems inventory holds no
inputs/ path at all.

Exit codes: 0 the page is written. 1 a required element of the page (template.json) is not fulfilled: the page is
still written, and each missing element is printed with the file and field that fulfils it. 2 cannot run (no inputs/
folder, a toolkit file missing or unreadable, the page cannot be written).
"""

import datetime
import hashlib
import html
import json
import pathlib
import re
import sys
import unicodedata
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FILES = {
    "template": HERE / "template.html",
    "inventory": HERE / "inventory.html",
    "css": HERE / "overview.css",
    "js": HERE / "overview.js",
    "elements": HERE / "template.json",
}
CITATION_TYPES = ROOT / "formats" / "citation-types.json"

# the folders whose files cite records, with their labels (the Used by column)
SECTIONS = [
    ("process-map", "Process map", ".json"),
    ("process-map-ai-opportunity", "AI opportunities", ".json"),
    ("document", "Document", ".md"),
    ("inventory", "Inventory", ".json"),
]
SECTION_FILE = re.compile(
    r"^[a-z0-9][a-z0-9-]{1,47}$"
)  # process-map.schema.json › sectionFile, as bs.py reads it
SOURCE_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")  # citation.schema.json › sourceId
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SHORT = 8  # hex characters of a hash the page holds
STEPS_SHOWN = 3  # step chips shown before "+n"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CATEGORY = {
    "spreadsheet app": "Spreadsheet app",
    "ticketing tool": "Ticketing tool",
    "ERP suite": "ERP suite",
    "email client": "Email client",
    "document store": "Document store",
    "database": "Database",
    "web app": "Web app",
    "other": "Other",
}


def cannot_run(msg):
    print(f"cannot run: {msg}", file=sys.stderr)
    sys.exit(2)


# ------------------------------------------------------------------ small helpers


def text(s):
    """A name or string as the page may hold it: a file name that is not UTF-8 (Python keeps its bytes as lone
    surrogates) and a lone surrogate from a JSON escape both become U+FFFD."""
    return s.encode("utf-8", "surrogateescape").decode("utf-8", "replace") if isinstance(s, str) else s


def is_str(v):
    return isinstance(v, str) and v != ""


def h(s):
    return html.escape(text(str(s)), quote=True)


def real_date(s):
    if not (isinstance(s, str) and DATE.match(s)):
        return False
    try:
        datetime.date(int(s[:4]), int(s[5:7]), int(s[8:]))
        return True
    except ValueError:
        return False


def pdate(s):
    return f"{int(s[8:])} {MONTHS[int(s[5:7]) - 1]} {s[:4]}"


def prange(a, b):
    if a == b:
        return pdate(a)
    if a[:7] == b[:7]:
        return f"{int(a[8:])}–{pdate(b)}"
    if a[:4] == b[:4]:
        return f"{int(a[8:])} {MONTHS[int(a[5:7]) - 1]} – {pdate(b)}"
    return f"{pdate(a)} – {pdate(b)}"


def psize(b):
    if b is None:
        return "—"
    if b < 1000:
        return f"{b} B"
    v, unit = (b / 1000, "KB") if b < 1e6 else (b / 1e6, "MB")
    return (f"{v:.1f}" if v < 10 else str(round(v))) + " " + unit


def plural(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", text(s).lower()).strip("-")


def anchor(address):
    """FORMATS.md section 2.6: src- plus the address in lower case, ¶ written para, other runs written -."""
    return "src-" + re.sub(r"[^a-z0-9]+", "-", address.lower().replace("¶", "para")).strip("-")


def natural(s):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.casefold()) for t in re.split(r"(\d+)", s) if t]


FOLD = {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "\u00a0": " "}


def fold_ci(s):
    s = "".join(FOLD.get(c, c) for c in unicodedata.normalize("NFKC", s))
    return re.sub(r"\s+", " ", s).strip().casefold()


def inputs_path(v):
    """A record's `file` when it is a clean path inside inputs/ (the only paths the page prints), else None."""
    if not isinstance(v, str) or "\\" in v or "\0" in v:
        return None
    parts = v.split("/")
    if len(parts) < 2 or parts[0] != "inputs" or any(p in ("", ".", "..") for p in parts[1:]):
        return None
    return v


def read_json(p):
    try:
        return json.loads(p.read_bytes().decode("utf-8"))
    except (OSError, ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
        return None


def section_paths(ws, sec, ext):
    d = ws / sec
    try:
        ps = sorted(d.iterdir()) if d.is_dir() else []
    except OSError:
        return []
    return [
        p
        for p in ps
        if not p.name.startswith(".") and p.suffix == ext and SECTION_FILE.match(p.stem) and p.is_file()
    ]


# ------------------------------------------------------------------ the workspace's name, never its absolute path


def ws_path(ws):
    """The workspace as bs.py is given it from the toolkit folder (examples, work/client-a); a workspace outside
    the toolkit is named by its folder alone."""
    r = ws.resolve()
    try:
        rel = r.relative_to(ROOT.resolve()).as_posix()
        return text(rel if rel != "." else r.name)
    except ValueError:
        return text(r.name)


def ws_label(ws, maps):
    """The client's name as the maps' meta.client gives it, when they agree; else the workspace folder's name."""
    clients = {m["client"] for _, m in maps if m["client"]}
    if len(clients) == 1:
        return clients.pop()
    return (
        text(" ".join(w[:1].upper() + w[1:] for w in re.split(r"[-_\s]+", ws.resolve().name) if w))
        or "Workspace"
    )


# ------------------------------------------------------------------ records


def units(kind, recs):
    """What a record file holds, in the units a reader gives (FORMATS.md section 1)."""
    n, locs = len(recs), [r["locator"] for r in recs]
    if kind == "sheet":
        return [
            {"n": len({loc.rsplit("!", 1)[0] for loc in locs if "!" in loc}), "of": "sheet"},
            {"n": n, "of": "cell"},
        ]
    if kind in ("document", "web"):
        pages = {m.group(1) for loc in locs for m in [re.match(r"p(\d+)\s", loc)] if m}
        return ([{"n": len(pages), "of": "page"}] if pages else []) + [{"n": n, "of": "paragraph"}]
    if kind == "transcript":
        return [{"n": n, "of": "turn"}]
    return [{"n": n, "of": "record"}]


def load_record(p, kinds):
    """One records/<ID>.json, every field type-checked before use. Returns {id, path, sha, kind, view, valid, why,
    recordFile, lines}: `path` is its clean inputs/ path or None, `sha` its full recorded sha256 or None, `view` the
    header the page holds, `lines` its well-formed records (for resolving citations), `valid` whether every field
    the page reads is well formed, and `why` the Error problem when it is not (unreadable: no JSON object; outside:
    no file inside inputs/; malformed: any other field)."""
    stem, name = text(p.stem), f"records/{text(p.name)}"
    rec = read_json(p)
    rid = stem if SOURCE_ID.match(stem) else None
    if not isinstance(rec, dict):
        return {
            "id": rid,
            "path": None,
            "sha": None,
            "kind": None,
            "view": {"id": rid} if rid else None,
            "valid": False,
            "why": "unreadable",
            "recordFile": name,
            "lines": [],
        }
    if isinstance(rec.get("id"), str) and SOURCE_ID.match(rec["id"]):
        rid = rec["id"]
    kind = rec.get("kind") if isinstance(rec.get("kind"), str) and rec.get("kind") in kinds else None
    raw = rec.get("records")
    good = (
        [
            {k: text(r[k]) for k in ("locator", "text", "context") if is_str(r.get(k))}
            for r in raw
            if isinstance(r, dict) and is_str(r.get("locator")) and is_str(r.get("text"))
        ]
        if isinstance(raw, list)
        else []
    )
    sha = rec.get("sha256") if isinstance(rec.get("sha256"), str) and HEX64.match(rec["sha256"]) else None
    path = text(inputs_path(rec.get("file")))
    ok = {
        "id": rid is not None and rec.get("id") == rid,
        "title": is_str(rec.get("title")),
        "kind": kind is not None,
        "captured": real_date(rec.get("captured")),
        "file": path is not None,
        "sha256": sha is not None,
        "coverage": rec.get("coverage") in ("complete", "partial"),
        "records": isinstance(raw, list) and len(raw) > 0 and len(good) == len(raw),
        "detail": "detail" not in rec or is_str(rec["detail"]),
        "url": "url" not in rec or is_str(rec["url"]),
    }
    # the header in FORMATS.md order, each field only when it is well formed; the hash cut to 8 characters
    view = {
        "id": rid,
        "title": text(rec.get("title")) if ok["title"] else None,
        "kind": kind,
        "captured": rec["captured"] if ok["captured"] else None,
        "detail": text(rec.get("detail")) if ok["detail"] else None,
        "url": text(rec.get("url")) if ok["url"] else None,
        "legacy": True if rec.get("legacy") is True else None,
        "file": path,
        "sha256": sha[:SHORT] if sha else None,
        "coverage": rec["coverage"] if ok["coverage"] else None,
    }
    view = {k: v for k, v in view.items() if v is not None}
    view["recordCount"] = len(good)
    view["units"] = units(kind, good)
    valid = all(ok.values())
    return {
        "id": rid,
        "path": path,
        "sha": sha,
        "kind": kind,
        "view": view,
        "valid": valid,
        "recordFile": name,
        "why": "outside" if path is None else None if valid else "malformed",
        "lines": good,
    }


def load_records(ws, kinds):
    """Every records/*.json, in file-name order."""
    d = ws / "records"
    try:
        ps = sorted(d.iterdir()) if d.is_dir() else []
    except OSError:
        ps = []
    return [
        load_record(p, kinds)
        for p in ps
        if not p.name.startswith(".") and p.is_file() and p.suffix == ".json"
    ]


class Resolver:
    """Resolution by containment (FORMATS.md section 1): a locator or span to the records it holds, [] when it
    reaches none. The locator grammars are citation-types.json's; it never raises on bad data."""

    def __init__(self, recs, kinds):
        self.src = {}
        self.unit_re, self.span_re = {}, {}
        for k, v in kinds.items():
            try:
                self.unit_re[k] = re.compile(v["record"])
                self.span_re[k] = {n: re.compile(r) for n, r in v.get("spans", {}).items()}
            except (re.error, TypeError, KeyError, AttributeError):
                pass
        for r in recs:
            if r["id"] and r["kind"] in self.unit_re and r["id"] not in self.src:
                self.src[r["id"]] = (
                    r,
                    [dict(ln, key=self.key(r["kind"], ln["locator"])) for ln in r["lines"]],
                )

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
        """(record view or None, [records])."""
        got = self.src.get(sid)
        if not got:
            return None, []
        r, lines = got
        if loc is None:
            return r["view"], list(lines)
        try:
            p = self.pred(r["kind"], loc)
        except (ValueError, TypeError, IndexError):
            p = None
        return r["view"], [ln for ln in lines if p and ln["key"] is not None and p(ln["key"])]


# ------------------------------------------------------------------ citations: "used by"


def citation_counter(rules, ids):
    lines = rules["documentLines"]
    bracket, part = re.compile(lines["bracket"]), re.compile(lines["bracketPart"])
    prov = {w: re.compile(lines[w]) for w in ("Grounded", "Inferred", "Gap")}
    link = re.compile(r"\[([^\[\]]+)\]\(([^)\s]+)\)")

    def refs_of(t):
        """Source ids in 'SRC locator; SRC locator', or None when it is not that form."""
        out = []
        for p in t.split(";"):
            p = p.strip()
            if p.startswith("[") and p.endswith("]"):
                p = p[1:-1].strip()
            m = part.match(p)
            if not m:
                return None
            out.append(m.group(1))
        return out

    def brackets(t, c):
        """Every citation bracket in prose: a bracket that names a record file."""
        body = re.sub(r"\\[\[\]]", "", t)
        for m in bracket.finditer(body):
            srcs = refs_of(m.group(1))
            if srcs and any(s in ids for s in srcs):
                c.update(s for s in srcs if s in ids)

    def src(r):
        return r.get("source") if isinstance(r, dict) and isinstance(r.get("source"), str) else None

    def cite(entry, c):
        if not isinstance(entry, dict):
            return
        t = entry.get("type")
        if t in ("inferred", "absent"):
            refs = entry.get("from" if t == "inferred" else "in")
            for r in refs if isinstance(refs, list) else []:
                if src(r) in ids:
                    c[src(r)] += 1
        elif src(entry) in ids:
            c[src(entry)] += 1

    def json_file(data):
        """Maps, AI layers and inventory files: every entry of every cite array (a system's software included),
        plus the [ ] markers in a map's gap and clarification prose."""
        c = Counter()
        todo = [data]
        while todo:  # a stack, not recursion: a deeply nested file cannot overflow it
            o = todo.pop()
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "cite" and isinstance(v, list):
                        for e in v:
                            cite(e, c)
                    else:
                        todo.append(v)
            elif isinstance(o, list):
                todo.extend(o)
        if isinstance(data, dict):
            for key, fields in (("gaps", ("title", "text")), ("clarifications", ("title", "shows", "ask"))):
                cards = data.get(key)
                for card in cards if isinstance(cards, list) else []:
                    for f in fields:
                        if isinstance(card, dict) and isinstance(card.get(f), str):
                            brackets(card[f], c)
        return c

    def document(t):
        """Every source in a [ ] bracket, and every address on a Grounded, Inferred or Gap line. Front matter,
        fenced code, HTML comments, code spans, escaped brackets and link targets cite nothing."""
        c = Counter()
        lines_ = t.replace("\r\n", "\n").split("\n")
        if lines_ and lines_[0].strip() == "---":
            for i in range(1, len(lines_)):
                if lines_[i].strip() == "---":
                    lines_ = lines_[i + 1 :]
                    break
        body = re.sub(r"<!--.*?-->", "", "\n".join(lines_), flags=re.S)
        blocks, cur, fence = [], [], None
        for line in body.split("\n"):
            m = re.match(r"^\s*(`{3,}|~{3,})", line)
            if fence:
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                    fence = None
                continue
            if m:
                fence = m.group(1)
                blocks.append(cur)
                cur = []
                continue
            if line.strip():
                cur.append(line.strip())
            else:
                blocks.append(cur)
                cur = []
        blocks.append(cur)
        for b in blocks:
            if not b:
                continue
            t = " ".join(b)
            word = next((w for w in prov if t.startswith(w + " · ")), None)
            if word:
                m = prov[word].match(t)
                srcs = refs_of(m.group(2 if word == "Inferred" else 1)) if m else None
                c.update(s for s in srcs or [] if s in ids)
                continue
            t = re.sub(r"(`+)(.+?)\1", " ", t)
            t = link.sub(lambda m: m.group(1), t)
            brackets(t, c)
        return c

    return json_file, document


def used_by(ws, rules, ids):
    """{record id: [use]} over every section file and inventory file, in section order and then by name. A file
    that cannot be read (not UTF-8, not JSON: an author mid-edit) is skipped; bs.py check reports it."""
    json_file, document = citation_counter(rules, ids)
    out = {i: [] for i in ids}
    for sec, _, ext in SECTIONS:
        for p in section_paths(ws, sec, ext):
            try:
                body = p.read_bytes().decode("utf-8")
                c = document(body) if ext == ".md" else json_file(json.loads(body))
            except (OSError, ValueError, RecursionError):
                continue
            for sid, n in sorted(c.items()):
                out[sid].append({"section": sec, "name": p.stem, "citations": n})
    return out


# ------------------------------------------------------------------ the Folder view: one row per input


def kind_from_ext(kinds, ext):
    for k, v in kinds.items():
        if ext in v["read"]:
            return k
    for k, v in kinds.items():
        if ext in v["unchecked"]:
            return k
    return None


def walk_inputs(ws):
    """(folders, [(display path, Path)]) under inputs/, hidden entries and everything under them skipped."""
    inputs = ws / "inputs"
    folders, files = ["inputs"], []
    stack = [inputs]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for p in entries:
            if p.name.startswith("."):
                continue
            rel = text(p.relative_to(ws).as_posix())
            if p.is_dir() and not p.is_symlink():
                folders.append(rel)
                stack.append(p)
            elif p.is_file():
                files.append((rel, p))
    return sorted(folders), sorted(files, key=lambda x: x[0])


def folder_rows(ws, rules, recs):
    """The Folder view's facts: (folders, files). Status is decided the way bs.py check and status decide it."""
    kinds = rules["kinds"]
    containers = set(rules.get("containers", []))
    ids = {r["id"] for r in recs if r["id"]}
    uses = used_by(ws, rules, ids)
    named = {}
    for r in recs:  # rec-6 forbids two records naming one file: the first one wins
        if r["path"] and r["path"] not in named:
            named[r["path"]] = r
    by_sha = {}
    for r in recs:
        if r["sha"] and r["sha"] not in by_sha:
            by_sha[r["sha"]] = r

    def with_record(f, r):
        f.update(
            kindFrom="record",
            kind=r["kind"],
            record=r["view"],
            usedBy=uses.get(r["id"], []) if r["id"] else [],
        )
        if r["view"] and r["view"].get("captured"):
            f["captured"] = r["view"]["captured"]

    folders, paths = walk_inputs(ws)
    files, listed = [], set()
    for rel, p in paths:
        ext = p.suffix.lower()
        try:
            data = p.read_bytes()
            size, now = len(data), hashlib.sha256(data).hexdigest()
        except OSError:
            size, now = None, None
        f = {
            "file": rel,
            "bytes": size,
            "sha256": now[:SHORT] if now else None,
            "status": None,
            "kind": None,
            "kindFrom": "extension",
            "captured": None,
            "record": None,
            "usedBy": [],
        }
        listed.add(rel)
        r = named.get(rel)
        if r:
            with_record(f, r)
            if not r["kind"]:
                f.update(kind=kind_from_ext(kinds, ext), kindFrom="extension")
            k = kinds[r["kind"]] if r["kind"] else None
            if not r["valid"]:
                f.update(status="error", problem="malformed")  # bs.py check names the field
            elif now is None:
                f.update(status="error", problem="missing")  # rec-2: it cannot be read
            elif now != r["sha"]:
                f.update(status="error", problem="edited")  # rec-2
            elif ext in k["read"]:
                f["status"] = "converted"
            elif ext in k["unchecked"]:
                f["status"] = "unchecked"  # rec-5: a person compares it
            else:
                f.update(status="error", problem="kind")  # rec-5: the kind cannot take this extension
        else:
            f["kind"] = kind_from_ext(kinds, ext)
            if ext in containers:
                f.update(status="not-converted", convertWith="unpack")  # ws-1: a container is unpacked first
            elif now and now in by_sha:
                o = by_sha[now]  # ws-1 warning
                f.update(status="duplicate", duplicateOf={"file": o["path"], "id": o["id"]})
            else:
                k = f["kind"]
                f.update(
                    status="not-converted",  # ws-1
                    convertWith="bs.py" if k and ext in kinds[k]["read"] else "converter agent",
                )
        files.append(f)

    for r in recs:
        f = {
            "file": r["path"],
            "bytes": None,
            "sha256": None,
            "status": "error",
            "kind": None,
            "kindFrom": "record",
            "captured": None,
            "record": None,
            "usedBy": [],
        }
        if r["path"] and named[r["path"]] is r:
            if r["path"] in listed:
                continue  # its input's row, above
            f["problem"] = "malformed" if not r["valid"] else "missing"  # rec-2
        else:
            # no file inside inputs/, or a file another record names (rec-6): a row of its own, labelled by its
            # record file and never by the path it names
            f.update(
                file=None,
                recordFile=r["recordFile"],
                problem=r["why"] if r["why"] in ("unreadable", "outside") else "named-twice",
            )
        with_record(f, r)
        files.append(f)
    files.sort(key=lambda f: (f["file"] is None, f["file"] or f.get("recordFile") or ""))
    return folders, files


# ------------------------------------------------------------------ the Overview: maps, software, modules


def objs(v):
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def cites_of(v):
    """The well-formed citations of a cite array: grounded {source, locator?} and inferred {reading, from}."""
    out = []
    for c in objs(v):
        t = c.get("type", "grounded")
        if t == "grounded" and is_str(c.get("source")):
            out.append(
                {
                    "type": "grounded",
                    "refs": [
                        {
                            "source": c["source"],
                            "locator": c.get("locator") if is_str(c.get("locator")) else None,
                        }
                    ],
                }
            )
        elif t == "inferred" and is_str(c.get("reading")):
            refs = [
                {"source": r["source"], "locator": r.get("locator") if is_str(r.get("locator")) else None}
                for r in objs(c.get("from"))
                if is_str(r.get("source"))
            ]
            if refs:
                out.append({"type": "inferred", "reading": text(c["reading"]), "refs": refs})
    return out


def load_maps(ws):
    """[(name, map)] for every map that parses, with the arrays the Overview reads made safe to walk. The largest map
    comes first (most nodes, then name): it leads the system order, the team order and each system's role."""
    out = []
    for p in section_paths(ws, "process-map", ".json"):
        d = read_json(p)
        if not isinstance(d, dict):
            continue
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        lanes = [
            lane for lane in objs(d.get("lanes")) if is_str(lane.get("id")) and is_str(lane.get("label"))
        ]
        nodes = [n for n in objs(d.get("nodes")) if is_str(n.get("id"))]
        systems = [s for s in objs(d.get("systems")) if is_str(s.get("id")) and is_str(s.get("label"))]
        out.append(
            (
                p.stem,
                {
                    "title": text(meta.get("title")) if is_str(meta.get("title")) else p.stem,
                    "client": text(meta.get("client")) if is_str(meta.get("client")) else None,
                    "date": meta.get("date") if real_date(meta.get("date")) else None,
                    "lanes": lanes,
                    "nodes": nodes,
                    "systems": systems,
                },
            )
        )
    return sorted(out, key=lambda x: (-len(x[1]["nodes"]), x[0]))


def load_inventories(ws):
    out = []
    for p in section_paths(ws, "inventory", ".json"):
        d = read_json(p)
        if isinstance(d, dict):
            out.append(
                (
                    p.stem,
                    {
                        "map": d.get("map") if is_str(d.get("map")) else None,
                        "mode": d.get("mode", "suggested"),
                        "modules": [
                            m
                            for m in objs(d.get("modules"))
                            if is_str(m.get("id")) and is_str(m.get("title"))
                        ],
                    },
                )
            )
    return out


class Points:
    """The citation points of one page: one per address as written (WB1 Steps row 2), numbered in the order the
    page first shows them, each with the records it resolves to and the elements that use it."""

    def __init__(self, res):
        self.res, self.by, self.order = res, {}, []

    def add(self, ref, user, kind="grounded"):
        a = f"{ref['source']} {ref['locator']}" if ref["locator"] else ref["source"]
        p = self.by.get(a)
        if p is None:
            view, recs = self.res.resolve(ref["source"], ref["locator"])
            p = {
                "n": len(self.order) + 1,
                "address": a,
                "source": ref["source"],
                "locator": ref["locator"],
                "anchor": anchor(a),
                "record": view,
                "recs": recs,
                "users": [],
            }
            self.by[a] = p
            self.order.append(p)
        use = (user[0], user[1], kind)
        if use not in p["users"]:
            p["users"].append(use)
        return p


def first_words(s, n=8):
    w = s.split()
    return " ".join(w[:n]) + ("…" if len(w) > n else "")


def marker(p):
    """One numbered marker, the look of every template (the map's cp-mk): it links to its row in Citation points
    and names its address on hover."""
    r = p["recs"][0] if p["recs"] else None
    tip = f"{p['address']} · “{first_words(r['text'])}”" if r else f"{p['address']} · resolves to no record"
    return f'<a class="cp-mk" href="#{p["anchor"]}" data-tip="{h(tip)}" aria-label="Citation {p["n"]}: {h(p["address"])}">{p["n"]}</a>'


def markers(ps):
    """Several markers as one superscript, ³ or ³,⁷, each number once."""
    seen = []
    for p in ps:
        if p not in seen:
            seen.append(p)
    return f'<sup class="cp-mks">{",".join(marker(p) for p in seen)}</sup>'


def evidence(cites, pts, user):
    """The provenance line (FORMATS.md section 2.6) with numbered markers: one Grounded clause, then one Inferred
    clause per reading."""
    g = [ref for c in cites if c["type"] == "grounded" for ref in c["refs"]]
    out = []
    if g:
        out.append(
            '<span class="pv pv-g"><b>Grounded</b>' + markers([pts.add(ref, user) for ref in g]) + "</span>"
        )
    for c in cites:
        if c["type"] == "inferred":
            out.append(
                f'<span class="pv pv-i"><b>Inferred</b> · {h(c["reading"])}'
                + markers([pts.add(ref, user, "inferred") for ref in c["refs"]])
                + "</span>"
            )
    return f'<p class="prov">{"".join(out)}</p>' if out else ""


ICON = {
    "sheet": '<rect x="2" y="2.8" width="12" height="10.4" rx="1.2"/><path d="M2 6.2 H14 M2 9.8 H14 M6.2 6.2 V13.2 M10 6.2 V13.2"/>',
    "document": '<path d="M3.8 1.8 H9.6 L12.6 4.9 V14.2 H3.8 z"/><path d="M9.6 1.8 V4.9 H12.6"/><path d="M5.7 8.2 H10.7 M5.7 10.8 H10.7"/>',
    "transcript": '<path d="M2.2 3.6c0-.7.5-1.2 1.2-1.2h9.2c.7 0 1.2.5 1.2 1.2v6.1c0 .7-.5 1.2-1.2 1.2H7.3L4.6 13.4v-2.5H3.4c-.7 0-1.2-.5-1.2-1.2z"/><path d="M5 5.5h6M5 7.9h3.8"/>',
    "web": '<circle cx="8" cy="8" r="6.1"/><path d="M1.9 8h12.2"/><path d="M8 1.9c1.7 1.6 2.5 3.7 2.5 6.1S9.7 12.5 8 14.1C6.3 12.5 5.5 10.4 5.5 8S6.3 3.5 8 1.9z"/>',
    "folder": '<path d="M1.8 5 c0-.7.5-1.2 1.2-1.2 h2.9 l1.4 1.7 h5.7 c.7 0 1.2.5 1.2 1.2 v5.6 c0 .7-.5 1.2-1.2 1.2 H3 c-.7 0-1.2-.5-1.2-1.2 z"/>',
    "folder-open": '<path d="M1.8 11.6V5c0-.7.5-1.2 1.2-1.2h2.9l1.4 1.7h4.5c.7 0 1.2.5 1.2 1.2v.8"/><path d="M1.8 11.6l1.6-3.9c.2-.5.6-.8 1.1-.8h9.3l-1.7 4.6c-.2.5-.6.8-1.1.8H3c-.7 0-1.2-.5-1.2-.7z"/>',
    "archive": '<path d="M2.6 5.6h10.8v7.6H2.6z"/><path d="M1.8 2.8h12.4v2.8H1.8z"/><path d="M6.4 8.2h3.2"/>',
    "chev": '<path d="M6 3.8 10.2 8 6 12.2"/>',
    # the system icons of process-map.schema.json
    "spreadsheet": '<rect x="2" y="2.8" width="12" height="10.4" rx="1.2"/><path d="M2 6.2 H14 M2 9.8 H14 M6.2 6.2 V13.2 M10 6.2 V13.2"/>',
    "database": '<ellipse cx="8" cy="4" rx="5.2" ry="1.9"/><path d="M2.8 4v8c0 1 2.3 1.9 5.2 1.9s5.2-.9 5.2-1.9V4M2.8 8c0 1 2.3 1.9 5.2 1.9s5.2-.9 5.2-1.9"/>',
    "email": '<rect x="2" y="3.4" width="12" height="9.2" rx="1.2"/><path d="M2.5 4.2 8 8.4l5.5-4.2"/>',
    "shared-drive": '<path d="M1.8 5 c0-.7.5-1.2 1.2-1.2 h2.9 l1.4 1.7 h5.7 c.7 0 1.2.5 1.2 1.2 v5.6 c0 .7-.5 1.2-1.2 1.2 H3 c-.7 0-1.2-.5-1.2-1.2 z"/>',
    "web-app": '<rect x="2" y="2.8" width="12" height="10.4" rx="1.2"/><path d="M2 5.8h12"/>',
}


def ic(name):
    return f'<svg class="ic" viewBox="0 0 16 16" aria-hidden="true" focusable="false">{ICON.get(name, ICON["document"])}</svg>'


def overview(ws, rules, recs, folders, files, client):
    """The Overview's model and HTML: {sections: {id: html}, counts, points, fulfilled}. `client` is the systems
    inventory: links to Original data received go to its page rather than to this one."""
    res = Resolver(recs, rules["kinds"])
    pts = Points(res)
    maps, invs = load_maps(ws), load_inventories(ws)
    mapnames = {n for n, _ in maps}

    # ---- systems: one row per system label across the maps, in map order; teams in the maps' lane order
    systems, sys_by, team_ix = [], {}, {}
    for _name, m in maps:
        for lane in m["lanes"]:
            team_ix.setdefault(text(lane["label"]), len(team_ix))
    for name, m in maps:
        lane_ix = {lane["id"]: i for i, lane in enumerate(m["lanes"])}
        lane_lb = {lane["id"]: text(lane["label"]) for lane in m["lanes"]}
        for s in m["systems"]:
            key = fold_ci(s["label"])
            sy = sys_by.get(key)
            if sy is None:
                sy = {
                    "label": text(s["label"]),
                    "icon": s.get("icon") if s.get("icon") in ICON else "web-app",
                    "role": None,
                    "cites": [],
                    "steps": [],
                    "teams": [],
                    "software": [],
                    "anchor": "sys-" + (slug(s["label"]) or "x"),
                }
                sys_by[key] = sy
                systems.append(sy)
            if not sy["role"] and is_str(s.get("role")):
                sy["role"] = text(s["role"])
            sy["cites"] += cites_of(s.get("cite"))
            steps = [
                n
                for n in m["nodes"]
                if n.get("kind", "step") == "step" and s["id"] in (n.get("systems") or [])
            ]
            sy["steps"] += [
                {
                    "map": name,
                    "id": n["id"],
                    "title": text(n.get("title")) if is_str(n.get("title")) else "",
                    "inferred": n.get("state") == "inferred",
                    "maptitle": m["title"],
                }
                for n in steps
            ]
            for lid in {n.get("lane") for n in steps if n.get("lane") in lane_ix}:
                if lane_lb[lid] not in sy["teams"]:
                    sy["teams"].append(lane_lb[lid])
            sy["teams"].sort(key=team_ix.get)
            sw = s.get("software")
            if isinstance(sw, dict) and is_str(sw.get("name")):
                sy["software"].append(
                    (
                        text(sw["name"]),
                        sw.get("category") if sw.get("category") in CATEGORY else "other",
                        cites_of(sw.get("cite")),
                    )
                )
    # ---- software: one row per name, sorted by name
    software, sw_by = [], {}
    for sy in systems:
        for nm, cat, cs in sy["software"]:
            sw = sw_by.get(nm)
            if sw is None:
                sw = {
                    "name": nm,
                    "category": cat,
                    "cites": [],
                    "powers": [],
                    "anchor": "sw-" + (slug(nm) or "x"),
                }
                sw_by[nm] = sw
                software.append(sw)
            sw["cites"] += cs
            if sy not in sw["powers"]:
                sw["powers"].append(sy)
    software.sort(key=lambda s: natural(s["name"]))
    for sw in software:
        recs_g = [
            r
            for c in sw["cites"]
            if c["type"] == "grounded"
            for ref in c["refs"]
            for r in res.resolve(ref["source"], ref["locator"])[1]
        ]
        sw["named"] = any(fold_ci(sw["name"]) in fold_ci(r["text"]) for r in recs_g)
    # ---- modules: inventory files in name order, modules in file order
    modules, seen = [], set()
    node_of = {(name, n["id"]): (n, m["title"]) for name, m in maps for n in m["nodes"]}
    for iname, inv in invs:
        for mo in inv["modules"]:
            a = "mod-" + slug(mo["id"])
            while a in seen:
                a += "-" + slug(iname)
            seen.add(a)
            steps = []
            for nid in [x for x in mo.get("steps") or [] if is_str(x)]:
                n, mt = node_of.get((inv["map"], nid), (None, None))
                steps.append(
                    {
                        "map": inv["map"] if inv["map"] in mapnames else None,
                        "id": nid,
                        "title": text(n.get("title")) if n and is_str(n.get("title")) else "",
                        "inferred": bool(n) and n.get("state") == "inferred",
                        "maptitle": mt or "",
                    }
                )
            modules.append(
                {
                    "id": text(mo["id"]),
                    "title": text(mo["title"]),
                    "anchor": a,
                    "software": text(mo.get("software")) if is_str(mo.get("software")) else "",
                    "mode": inv["mode"],
                    "likelihood": "observed"
                    if inv["mode"] == "observed"
                    else mo.get("likelihood")
                    if inv["mode"] == "observed" or mo.get("likelihood") in ("likely", "possible")
                    else "possible",
                    "steps": steps,
                    "cites": cites_of(mo.get("cite")),
                }
            )

    rd = "data-received.html" if client else ""  # where a file's row is: this page, or Original data received

    def chips(steps):
        if not steps:
            return '<span class="mut">—</span>'
        out = []
        for i, st in enumerate(steps):
            tip = " · ".join(x for x in (st["title"], st["maptitle"]) if x)
            cls = "step" + (" inferred" if st["inferred"] else "")
            hid = " hidden" if i >= STEPS_SHOWN else ""
            if st["map"]:
                out.append(
                    f'<a class="{cls}" href="process-map/{h(st["map"])}.html#{h(st["id"])}" data-tip="{h(tip)}"{hid}>{h(st["id"])}</a>'
                )
            else:
                out.append(
                    f'<span class="{cls}" data-tip="{h(tip or "not in a map")}"{hid}>{h(st["id"])}</span>'
                )
        more = len(steps) - STEPS_SHOWN
        if more > 0:
            out.append(f'<button type="button" class="more" aria-expanded="false">+{more}</button>')
        return f'<span class="steps"><span class="steps-n">{len(steps)}</span>{"".join(out)}</span>'

    def head(n, sid, title, desc, aside="", mark=""):
        return (
            f'<header class="sh"><div><span class="sh-n">{n}</span><h2 id="{sid}-h">{mark}{h(title)}</h2>'
            f'<p class="sh-d">{desc}</p></div><div class="sh-a">{aside}</div></header>'
        )

    def empty(msg):
        return f'<p class="none">{msg}</p>'

    sec = {}
    # ---- 01 Folders of data
    if not client:
        sec["folders"] = folders_html(folders, files, rules)
    # ---- Systems identified
    used_steps = {(st["map"], st["id"]) for sy in systems for st in sy["steps"]}
    rows = []
    for sy in systems:
        user = (sy["label"], "#" + sy["anchor"])
        lead = f'<p class="lead">{h(sy["role"])}</p>' if sy["role"] else ""
        rows.append(
            f'<tr id="{sy["anchor"]}"><td class="main"><span class="nm">{ic(sy["icon"])}<span class="nm-t">{h(sy["label"])}</span></span></td>'
            f'<td data-label="Teams">{h(", ".join(sy["teams"])) or "<span class=mut>—</span>"}</td>'
            f'<td data-label="Evidence">{lead}{evidence(sy["cites"], pts, user)}</td>'
            f'<td data-label="Steps">{chips(sy["steps"])}</td></tr>'
        )
    n_sys = len(systems)
    body = (
        table(["System", "Teams", "Role and evidence", "Steps"], rows)
        if rows
        else empty(
            "No systems yet. They come from <code>systems[]</code> of a map in <code>process-map/</code>."
        )
    )
    aside = f"{plural(n_sys, 'system')} · used by {plural(len(used_steps), 'step')}" if rows else ""
    sec["systems"] = (
        head(
            "02" if not client else "01",
            "systems",
            "Systems identified",
            "The systems the process maps name, the steps that use them and the teams on those steps.",
            aside,
        )
        + body
    )
    # ---- Software used
    rows = []
    for sw in software:
        user = (sw["name"], "#" + sw["anchor"])
        status = (
            "Named in the sources"
            if sw["named"]
            else "Inferred"
            if any(c["type"] == "inferred" for c in sw["cites"])
            else '<span class="warn">Not named in its records</span>'
        )
        powers = "".join(
            f'<li>{ic(sy["icon"])}<a href="#{sy["anchor"]}">{h(sy["label"])}</a></li>' for sy in sw["powers"]
        )
        rows.append(
            f'<tr id="{sw["anchor"]}"><td class="main"><span class="nm"><span class="nm-t">{h(sw["name"])}</span></span></td>'
            f'<td data-label="Category">{h(CATEGORY[sw["category"]])}</td>'
            f'<td data-label="Evidence"><p class="lead{" strong" if sw["named"] else ""}">{status}</p>{evidence(sw["cites"], pts, user)}</td>'
            f'<td data-label="Powers"><ul class="sys-list">{powers}</ul></td></tr>'
        )
    n_named = sum(1 for s in software if s["named"])
    body = (
        table(
            ["Software", 'Category <span class="th-n">our label</span>', "Status and evidence", "Powers"],
            rows,
        )
        if rows
        else empty(
            "No software yet. Give a system its <code>software</code> in a map: name, category and citation."
        )
    )
    n_inf = sum(1 for s in software if not s["named"] and any(c["type"] == "inferred" for c in s["cites"]))
    aside = (
        (
            f"{plural(len(software), 'product')} · {n_named or 'none'} named in the sources"
            + (f" · {n_inf} inferred" if n_inf else "")
        )
        if rows
        else ""
    )
    sec["software"] = (
        head(
            "03" if not client else "02",
            "software",
            "Software used",
            "The products behind those systems, as the sources name them or as we read them. Categories are our own labels.",
            aside,
        )
        + body
    )
    # Current-state entries never acquire a suggested likelihood.
    observed = sum(m["mode"] == "observed" for m in modules)
    suggested = len(modules) - observed
    modules_title = (
        "Documented modules and capabilities"
        if observed and not suggested
        else "Modules and capabilities: observed and suggested"
        if observed
        else "Modules likely to be used"
    )
    modules_note = (
        "Modules and capabilities described in the cited sources. Observed means source-reported use, not a live system verification."
        if observed and not suggested
        else "Observed entries describe source-reported use; likely or possible entries are our suggestions."
        if observed
        else "Modules of that software the process would likely rely on. Each is our suggestion, read from the records it cites."
    )
    rows = []
    for mo in modules:
        short = mo["title"].split(" · ")[0]
        user = (short, "#" + mo["anchor"])
        sw = sw_by.get(mo["software"])
        swh = f'<a href="#{sw["anchor"]}">{h(mo["software"])}</a>' if sw else h(mo["software"]) or "—"
        rows.append(
            f'<tr id="{mo["anchor"]}"><td class="main"><span class="nm"><i class="sq{" is-observed" if mo["mode"] == "observed" else ""}" aria-hidden="true"></i><span class="nm-t">{h(mo["title"])}</span></span></td>'
            f'<td data-label="Software">{swh}</td>'
            f'<td data-label="Reading"><p class="lead{" strong" if mo["likelihood"] == "likely" else ""}">{"Observed in supplied sources" if mo["mode"] == "observed" else mo["likelihood"].capitalize()}</p>{evidence(mo["cites"], pts, user)}</td>'
            f'<td data-label="Steps">{chips(mo["steps"])}</td></tr>'
        )
    lk = Counter(m["likelihood"] for m in modules)
    body = (
        table(
            [
                "Module",
                "Software",
                "Evidence status" if observed else "Likelihood and reading",
                "Related steps" if observed else "Steps it would serve",
            ],
            rows,
        )
        if rows
        else empty(
            "No modules yet. Write <code>inventory/&lt;name&gt;.json</code>: the modules of the software that the steps would use."
        )
    )
    aside = (
        f'<span class="lg"><i class="sq{" is-observed" if observed and not suggested else ""}" aria-hidden="true"></i>{" · ".join(f"{lk[k]} {k}" for k in ("observed", "likely", "possible") if lk[k])}</span>'
        if rows
        else ""
    )
    sec["modules"] = (
        head(
            "04" if not client else "03",
            "modules",
            modules_title,
            modules_note,
            aside,
        )
        + body
    )
    counts = {
        "files": len([f for f in files if f["file"]]),
        "folders": len(folders),
        "systems": n_sys,
        "steps": len(used_steps),
        "software": len(software),
        "named": n_named,
        "modules": len(modules),
        "observed": observed,
        "suggested": suggested,
    }
    fulfilled = {
        "folders-of-data": counts["files"] > 0,
        "folder-view": counts["files"] > 0,
        "systems-identified": n_sys > 0,
        "software-used": len(software) > 0,
        "modules-likely": len(modules) > 0,
        # every cited row carries a numbered marker: each system, software and module cites, so each row has one
        "citation-points": len(pts.order) > 0 and all(x["cites"] for x in systems + software + modules),
    }
    return {
        "sec": sec,
        "modules_title": modules_title,
        "counts": counts,
        "points": points_html(pts, rd, rules["kinds"]),
        "npoints": len(pts.order),
        "fulfilled": fulfilled,
        "date": max((m["date"] for _, m in maps if m["date"]), default=None),
        "label": ws_label(ws, maps),
    }


def table(heads, rows):
    """One table of the shared page grid: a fixed first column, a fixed second, a free third, a fixed fourth."""
    th = "".join(f'<th scope="col">{x}</th>' for x in heads)
    return (
        f'<table class="t"><colgroup><col class="k1"><col class="k2"><col><col class="k4"></colgroup>'
        f"<thead><tr>{th}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def folders_html(folders, files, rules):
    """01 Folders of data: a row per folder of inputs/ with its totals, its own files under it (shown on demand),
    then the files directly in inputs/. Each file opens its row in the Folder view."""
    kinds = rules["kinds"]
    inputs = [f for f in files if f["file"]]

    def kind_label(f):
        if f.get("convertWith") == "unpack":
            return "Archive"
        return kinds[f["kind"]]["label"] if f["kind"] in kinds else "Unknown format"

    def kind_icon(f):
        return (
            "archive" if f.get("convertWith") == "unpack" else f["kind"] if f["kind"] in kinds else "document"
        )

    def totals(fs):
        conv = sum(1 for f in fs if f["status"] == "converted")
        unch = sum(1 for f in fs if f["status"] == "unchecked")
        ks = Counter(f["kind"] for f in fs if f["kind"] in kinds and f.get("convertWith") != "unpack")
        kh = "".join(
            f'<span>{ic(k)}<b>{ks[k]}</b><span class="vh"> {h(v["label"])}</span></span>'
            for k, v in kinds.items()
            if ks[k]
        )
        ds = sorted(f["captured"] for f in fs if f["captured"])
        size = sum(f["bytes"] or 0 for f in fs)
        if not fs:
            return (
                '<td class="r num c-files">0</td><td class="c-conv"><span class="mut">empty</span></td><td class="c-kinds"></td>'
                '<td class="r num c-size">—</td><td class="r num c-recv">—</td>'
            )
        return (
            f'<td class="r num c-files">{len(fs)}</td>'
            f'<td class="c-conv num">{conv} of {len(fs)}'
            + (f'<span class="cv-u">{unch} unchecked</span>' if unch else "")
            + "</td>"
            f'<td class="c-kinds"><span class="kinds">{kh}</span></td>'
            f'<td class="r num c-size">{psize(size)}</td>'
            f'<td class="r num c-recv">{prange(ds[0], ds[-1]) if ds else "—"}</td>'
        )

    def file_row(f, lvl, parent):
        name = f["file"].rsplit("/", 1)[-1]
        rid = f["record"]["id"] if f["record"] and f["record"].get("id") else None
        href = f"#{rid}" if rid else "#file-" + slug(f["file"])
        note = {
            "converted": "",
            "unchecked": "Unchecked",
            "not-converted": "Not converted yet",
            "duplicate": "Duplicate",
            "error": "Error",
        }[f["status"]]
        hidden = f' data-in="{h(parent)}" hidden' if parent else ""
        return (
            f'<tr class="file" style="--lvl:{lvl}"{hidden}><td class="c-name"><span class="fcell">{ic(kind_icon(f))}'
            f'<a class="fname" href="{h(href)}">{h(name)}</a></span></td>'
            f'<td class="r num c-files"></td><td class="c-conv">{h(rid) if rid else "<span class=mut>—</span>"}</td>'
            f'<td class="c-kinds">{h(kind_label(f))}'
            + (
                f' <span class="fk-n{" warn" if f["status"] in ("not-converted", "error") else ""}">{note}</span>'
                if note
                else ""
            )
            + "</td>"
            f'<td class="r num c-size">{psize(f["bytes"])}</td>'
            f'<td class="r num c-recv">{pdate(f["captured"]) if f["captured"] else "—"}</td></tr>'
        )

    rows = [
        f'<tr class="root"><td class="c-name"><span class="fcell">{ic("folder-open")}<span class="fname">inputs/</span></span></td>{totals(inputs)}</tr>'
    ]
    subs = sorted((d for d in folders if d != "inputs"), key=lambda d: [natural(p) for p in d.split("/")])
    for d in subs:
        lvl = d.count("/")
        within = [f for f in inputs if f["file"].startswith(d + "/")]
        own = sorted(
            (f for f in inputs if f["file"].rsplit("/", 1)[0] == d), key=lambda f: natural(f["file"])
        )
        name = d.rsplit("/", 1)[-1]
        btn = (
            f'<button type="button" class="fold" aria-expanded="false" data-dir="{h(d)}"><span class="chev">{ic("chev")}</span>'
            f'{ic("folder")}<span class="fname">{h(name)}/</span></button>'
            if own
            else f'<span class="fold-x">{ic("folder")}<span class="fname">{h(name)}/</span></span>'
        )
        rows.append(
            f'<tr class="folder" style="--lvl:{lvl}"><td class="c-name"><span class="fcell">{btn}</span></td>{totals(within)}</tr>'
        )
        rows += [file_row(f, lvl + 1, d) for f in own]
    rows += [
        file_row(f, 1, None)
        for f in sorted((f for f in inputs if f["file"].count("/") == 1), key=lambda f: natural(f["file"]))
    ]
    kh = "".join(f'<span class="lg">{ic(k)}{h(v["label"])}</span>' for k, v in kinds.items())
    head = (
        '<header class="sh"><div><span class="sh-n">01</span><h2 id="folders-h">Folders of data</h2>'
        '<p class="sh-d">Every folder of <code>inputs/</code>, as received. Open a folder to see its files; each file opens its row in the Folder view.</p></div>'
        f'<div class="sh-a">{kh}</div></header>'
    )
    th = "".join(
        f'<th scope="col"{c}>{x}</th>'
        for x, c in (
            ("Folder", ""),
            ("Files", ' class="r"'),
            ("Converted", ""),
            ("Kinds", ""),
            ("Size", ' class="r"'),
            ("Received", ' class="r"'),
        )
    )
    return (
        head
        + '<table class="t folders"><colgroup><col class="k1"><col class="kf"><col class="kc"><col><col class="ks"><col class="kr"></colgroup>'
        f"<thead><tr>{th}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


USE_WORD = {"grounded": "Grounded", "inferred": "Inferred from"}


def points_html(pts, rd, kinds):
    """The Citation points section, in the markup and look of every template (process-map README section 3.1):
    one line per record the page cites, then one row per point, numbered as its markers, with its address, its
    verbatim text, what uses it (linked to the row) and ↗ to the point on the Citation points page. Each record id
    and address opens its file's row in Original data received (rd: this page, or data-received.html)."""
    rows = pts.order
    srcs = sorted({p["source"] for p in rows}, key=natural)
    heads = ""
    for sid in srcs:
        r = next(p["record"] for p in rows if p["source"] == sid)
        if r is None:
            bits = ['<span class="cp-absent">no record file in this workspace</span>']
        else:
            bits = [h(r.get("title") or sid)] + [h(r[k]) for k in ("detail",) if r.get(k)]
            if r.get("kind") in kinds:
                bits.append(h(kinds[r["kind"]]["label"]))
            if r.get("kind") == "web" and r.get("url"):
                bits.append(h(re.sub(r"^[a-z]+://(www\.)?", "", r["url"]).split("/")[0]))
            if r.get("captured"):
                bits.append(f"captured {pdate(r['captured'])}")
        heads += (
            f'<li><a href="{rd}#{h(sid)}" title="Open {h(sid)} in Original data received">{h(sid)}</a>'
            f" · {' · '.join(bits)}</li>"
        )
    out = ""
    for p in rows:
        recs = p["recs"]
        if not recs:
            text_ = '<span class="cp-absent">resolves to no record: bs.py check names the fix</span>'
        elif len(recs) == 1 and recs[0]["locator"] == p["locator"]:
            r = recs[0]
            text_ = (f"{h(r['context'])} · " if r.get("context") else "") + f"<q>{h(r['text'])}</q>"
        else:
            text_ = " · ".join(f"<q>{h(r['text'])}</q>" for r in recs[:10])
            if len(recs) > 10:
                text_ += f" · and {len(recs) - 10} more"
            text_ = f'<span class="cp-recs">{text_}</span>'
        uses = {}
        for label, href, kind in p["users"]:
            uses.setdefault(kind, []).append(f'<a href="{h(href)}">{h(label)}</a>')
        used = "".join(
            f'<span class="cp-use"><b>{USE_WORD[k]}</b> · {", ".join(uses[k])}</span>'
            for k in USE_WORD
            if k in uses
        )
        out += (
            f'<li class="cp-row" id="{p["anchor"]}" data-n="{p["n"]}"><span class="cp-n">{p["n"]}</span>'
            f'<a class="cp-addr" href="{rd}#{h(p["source"])}" title="Open {h(p["source"])} in Original data received">'
            f'{h(p["address"])}</a><span class="cp-text">{text_}</span><span class="cp-used">{used}</span>'
            f'<a class="cp-all" href="citation-points.html#{p["anchor"]}" aria-label="Point {p["n"]} in Citation points" '
            f'title="Open in Citation points">↗</a></li>'
        )
    count = (
        f"{plural(len(rows), 'point')} from {plural(len(srcs), 'record')}"
        if rows
        else "this page cites no record yet: its sections are empty"
    )
    return (
        '<section class="cp" id="citation-points" aria-labelledby="cp-h" data-element="citation-points">'
        f'<div class="cp-head"><h2 id="cp-h">Citation points</h2><span class="cp-count">{count}</span></div>'
        + (f'<ul class="cp-srcs">{heads}</ul><ol class="cp-list">{out}</ol>' if rows else "")
        + "</section>"
    )


# ------------------------------------------------------------------ the pages


def required(page):
    """[(id, title, fulfilled_by)] of the page's required elements, from template.json."""
    t = json.loads(FILES["elements"].read_text(encoding="utf-8"))
    want = set(t["outputs"][page])
    return [
        (e["id"], e["title"], e["fulfilled_by"])
        for e in t["elements"]
        if e["id"] in want and e.get("required")
    ]


def nav(items):
    li = "".join(
        f'<li><a href="#{a}"><span class="toc-n">{n}</span><span class="toc-t">{h(t)}</span><span class="toc-c">{c}</span></a></li>'
        for n, a, t, c in items
    )
    return f'<nav class="toc" aria-label="On this page"><span class="toc-h">On this page</span><ul class="toc-l">{li}</ul></nav>'


KEY = (
    '<div class="key"><span class="key-h">Key</span><span class="key-i">'
    '<span class="lg"><span class="key-mk"><sup class="cp-mks" aria-hidden="true">3</sup></span>record line, in Citation points</span>'
    '<span class="lg"><span class="step">SUB-01</span>step on the process map</span>'
    '<span class="lg"><i class="sq" aria-hidden="true"></i>our suggestion</span>'
    '<span class="lg"><b>Grounded</b>a record says it</span>'
    '<span class="lg"><b>Inferred</b>our reading</span></span></div>'
)


def inventory_key(o):
    suggestion = '<span class="lg"><i class="sq" aria-hidden="true"></i>our suggestion</span>'
    observed = '<span class="lg"><i class="sq is-observed" aria-hidden="true"></i>observed in supplied sources</span>'
    return KEY.replace(
        suggestion,
        (observed if o["counts"]["observed"] else "") + (suggestion if o["counts"]["suggested"] else ""),
    )


def fill(tpl, slots):
    """One pass over the template, so text inserted into one slot is never read as another slot."""
    for k in slots:
        if "{{" + k + "}}" not in tpl:
            cannot_run(f"a template of design-system/data-received/ has no {{{{{k}}}}} slot")
    return re.sub(r"\{\{([a-z]+)\}\}", lambda m: slots.get(m.group(1), m.group(0)), tpl)


def module_summary(counts, inventory=False):
    parts = []
    if counts["observed"]:
        parts.append(f"{counts['observed']} observed modules/capabilities")
    if counts["suggested"]:
        ending = "likely to be used" if inventory else "we suggest"
        parts.append(f"{plural(counts['suggested'], 'module')} {ending}")
    return parts


def lede(o, files):
    c = o["counts"]
    ds = sorted(f["captured"] for f in files if f["captured"])
    parts = [plural(c["files"], "file") + (" received " + prange(ds[0], ds[-1]) if ds else "")]
    if c["systems"]:
        parts.append(f"{plural(c['systems'], 'system')} used by {plural(c['steps'], 'step')}")
    if c["software"]:
        parts.append(plural(c["software"], "software product"))
    if c["modules"]:
        parts.extend(module_summary(c))
    if c["observed"] and not c["suggested"]:
        parts.insert(0, "Systems and capabilities linked to mapped steps")
    return " · ".join(parts)


STATUS_LABEL = {
    "converted": "Converted",
    "unchecked": "Unchecked",
    "not-converted": "Not converted",
    "duplicate": "Duplicate",
    "error": "Error",
}


def static_rows(files, kinds):
    """The Folder view's rows as static HTML, grouped by folder: every row id (the record id) exists without the
    script, so every citation's link lands. The script redraws them, with its grouping and filter, when the view
    opens."""
    out, seen, cur = [], set(), None

    def folder_of(f):
        return f["file"].rsplit("/", 1)[0] if f["file"] else "inputs"

    for f in sorted(files, key=lambda f: (folder_of(f), natural(f["file"] or f["recordFile"]))):
        path, folder = f["file"] or f["recordFile"], folder_of(f)
        if folder != cur:
            cur = folder
            out.append(f'<tr class="dir"><td colspan="7"><span class="fv-nm">{h(folder)}/</span></td></tr>')
        r = f["record"] or {}
        rid = r.get("id")
        row_id = f' id="{h(rid)}"' if rid and rid not in seen else ""
        seen.add(rid)
        kind = (
            "Archive"
            if f.get("convertWith") == "unpack"
            else kinds[f["kind"]]["label"]
            if f["kind"] in kinds
            else "Unknown format"
        )
        n = sum(u.get("citations", 0) for u in f["usedBy"])
        out.append(
            f'<tr class="file"{row_id}><td><span class="fv-nm">{h(path.rsplit("/", 1)[-1])}</span></td>'
            f'<td>{h(kind)}</td><td><span class="chip {f["status"]}">{STATUS_LABEL[f["status"]]}</span></td>'
            f'<td>{h(rid or "—")}</td><td class="r num">{psize(f["bytes"])}</td>'
            f'<td class="r num">{pdate(f["captured"]) if f["captured"] else "—"}</td>'
            f'<td class="r num">{plural(n, "citation") if n else "Not cited"}</td></tr>'
        )
    return "".join(out)


def received_page(ws, rules, recs, folders, files, o):
    label = o["label"]
    c = o["counts"]
    island = {
        "workspace": {"path": ws_path(ws), "label": label},
        "kinds": [{"id": k, "label": v["label"]} for k, v in rules["kinds"].items()],
        "sections": [{"id": s, "label": lb} for s, lb, _ in SECTIONS],
        "folders": folders,
        "files": files,
    }
    blob = json.dumps(island, ensure_ascii=False, indent=1).replace("<", "\\u003c")
    ov = (
        nav(
            [
                ("01", "folders", "Folders of data", c["folders"]),
                ("02", "systems", "Systems identified", c["systems"]),
                ("03", "software", "Software used", c["software"]),
                ("04", "modules", o["modules_title"], c["modules"]),
                ("", "citation-points", "Citation points", o["npoints"]),
            ]
        )
        + inventory_key(o)
        + "".join(
            f'<section class="sec" id="{k}" aria-labelledby="{k}-h" data-element="{e}">{o["sec"][k]}</section>'
            for k, e in (
                ("folders", "folders-of-data"),
                ("systems", "systems-identified"),
                ("software", "software-used"),
                ("modules", "modules-likely"),
            )
        )
    )
    tpl = FILES["template"].read_text(encoding="utf-8")
    return fill(
        tpl,
        {
            "title": h(f"{label} · data received"),
            "css": FILES["css"].read_text(encoding="utf-8"),
            "js": FILES["js"].read_text(encoding="utf-8"),
            "lede": h(lede(o, files)),
            "overview": ov,
            "points": o["points"],
            "rows": static_rows(files, rules["kinds"]),
            "data": blob,
        },
    )


def inventory_page(ws, o):
    label = o["label"]
    c = o["counts"]
    parts = (
        ["Systems and capabilities linked to mapped steps"] if c["observed"] and not c["suggested"] else []
    )
    if c["systems"]:
        parts.append(f"{plural(c['systems'], 'system')} used by {plural(c['steps'], 'step')}")
    if c["software"]:
        parts.append(
            f"{plural(c['software'], 'software product')}, {c['named'] or 'none'} named in the sources"
        )
    if c["modules"]:
        parts.extend(module_summary(c, inventory=True))
    body = (
        nav(
            [
                ("01", "systems", "Systems identified", c["systems"]),
                ("02", "software", "Software used", c["software"]),
                ("03", "modules", o["modules_title"], c["modules"]),
                ("", "citation-points", "Citation points", o["npoints"]),
            ]
        )
        + inventory_key(o)
        + "".join(
            f'<section class="sec" id="{k}" aria-labelledby="{k}-h" data-element="{e}">{o["sec"][k]}</section>'
            for k, e in (
                ("systems", "systems-identified"),
                ("software", "software-used"),
                ("modules", "modules-likely"),
            )
        )
    )
    # a client-ready footer: no tool language and no paths
    foot = " · ".join(
        [f"{label} · systems inventory"]
        + ([pdate(o["date"])] if o["date"] else [])
        + ["sources listed in Citation points"]
    )
    tpl = FILES["inventory"].read_text(encoding="utf-8")
    return fill(
        tpl,
        {
            "title": h(f"{label} · systems inventory"),
            "css": FILES["css"].read_text(encoding="utf-8"),
            "js": FILES["js"].read_text(encoding="utf-8"),
            "lede": h(" · ".join(parts) or "No systems yet"),
            "body": body,
            "points": o["points"],
            "foot": h(foot),
        },
    )


def main(argv):
    client = "--inventory" in argv
    args = [a for a in argv if a != "--inventory"]
    if len(args) != 2 or args[0].startswith("-"):
        print(__doc__.strip().split("\n\n")[0], file=sys.stderr)
        print(
            "usage: python3 design-system/data-received/build_received.py [--inventory] <ws> <out.html>",
            file=sys.stderr,
        )
        return 2
    ws, out = pathlib.Path(args[0]), pathlib.Path(args[1])
    if not (ws / "inputs").is_dir():
        cannot_run("the workspace has no inputs/ folder")
    for _key, p in list(FILES.items()) + [("kinds", CITATION_TYPES)]:
        if not p.is_file():
            cannot_run(f"{p.relative_to(ROOT).as_posix()} is missing")
    try:
        rules = json.loads(CITATION_TYPES.read_text(encoding="utf-8"))
        kinds = rules["kinds"]
        assert isinstance(kinds, dict) and all(
            isinstance(v.get("read"), list)
            and isinstance(v.get("unchecked"), list)
            and isinstance(v.get("label"), str)
            for v in kinds.values()
        )
    except (OSError, ValueError, KeyError, AssertionError, AttributeError, TypeError):
        cannot_run("formats/citation-types.json is not the toolkit's kinds table")
    page = "out/systems-inventory.html" if client else "out/data-received.html"
    try:
        need = required(page)
    except (OSError, ValueError, KeyError, TypeError):
        cannot_run(f"design-system/data-received/template.json does not list the elements of {page}")
    try:
        recs = load_records(ws, kinds)
        folders, files = folder_rows(ws, rules, recs)
        o = overview(ws, rules, recs, folders, files, client)
        doc = inventory_page(ws, o) if client else received_page(ws, rules, recs, folders, files, o)
    except Exception as e:  # a builder bug: say where without a traceback (it holds paths)
        tb, line = e.__traceback__, "?"
        while tb:  # the deepest line of this file
            if tb.tb_frame.f_code.co_filename == __file__:
                line = tb.tb_lineno
            tb = tb.tb_next
        cannot_run(f"build_received.py failed ({e.__class__.__name__} at line {line})")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(doc.encode("utf-8", "replace"))
    except OSError as e:
        cannot_run(f"the page cannot be written ({e.strerror})")
    unknown = [eid for eid, _t, _by in need if eid not in o["fulfilled"]]
    if unknown:
        cannot_run(f"template.json requires {', '.join(unknown)}, which build_received.py does not check")
    missing = [(t, by) for eid, t, by in need if not o["fulfilled"][eid]]
    if client:
        print(
            f"{plural(o['counts']['systems'], 'system')}, {plural(o['counts']['software'], 'software product')}, "
            f"{plural(o['counts']['modules'], 'module')}, {plural(o['npoints'], 'citation point')}"
        )
    else:
        n = Counter(f["status"] for f in files)
        order = ["converted", "unchecked", "not-converted", "duplicate", "error"]
        print(
            f"{len(files)} file(s)"
            + "".join(f"{', ' if i else ': '}{n[s]} {s}" for i, s in enumerate(x for x in order if n[x]))
            + f"; {plural(o['npoints'], 'citation point')}"
        )
    print(f"{len(need) - len(missing)} of {len(need)} required elements fulfilled")
    for t, by in missing:
        print(f"missing  {t}  -> {by}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

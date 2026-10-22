#!/usr/bin/env python3
"""build_received.py <ws> <out.html>: the Original data received page of one workspace.

A calm folder view of <ws>/inputs/: one row per input with its status, and a detail pane with its record, its
units, a preview and where it is cited. Everything on the page is computed from three things and nothing else:
  - inputs/ (every file and folder, hidden ones skipped);
  - records/*.json (the record headers, their records and their sha256);
  - the section files (process-map/, process-map-ai-opportunity/, document/, proposal/), for citation counts.
Kinds and readers come from formats/citation-types.json. Nobody authors any of it.

Standard library only. Deterministic: no timestamps, no file dates, no random ids, every list sorted, so the same
workspace gives the same bytes. The page holds no absolute path and no full hash: a file's hash is printed as its
first 8 hex characters only.

Exit codes: 0 the page is written; 1 data error (a record or section file that cannot be read: bs.py check
names the fix); 2 cannot run (no inputs/ folder, a toolkit file is missing, the page cannot be written).
"""
import hashlib
import json
import pathlib
import re
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TEMPLATE = HERE / "template.html"
CITATION_TYPES = ROOT / "formats" / "citation-types.json"

SECTIONS = [("process-map", "Process map", ".json"), ("process-map-ai-opportunity", "AI layer", ".json"),
            ("document", "Document", ".md"), ("proposal", "Proposal", ".json")]
SECTION_FILE = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")   # process-map.schema.json › sectionFile, as bs.py reads it
SHORT = 8          # hex characters of a hash the page holds
PREVIEW = 4        # records shown per file


class DataError(Exception):
    pass


def cannot_run(msg):
    print(f"cannot run: {msg}", file=sys.stderr)
    sys.exit(2)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(ws, path):
    rel = path.relative_to(ws).as_posix()
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise DataError(f"{rel} is not valid UTF-8 JSON ({e.__class__.__name__}); bs.py check names the fix")


def hidden(parts):
    return any(p.startswith(".") for p in parts)


# ------------------------------------------------------------------ the workspace's name, never its absolute path

def ws_path(ws):
    """The workspace as bs.py is given it from the toolkit folder (examples, work/client-a); a workspace outside
    the toolkit is named by its folder alone."""
    r = ws.resolve()
    try:
        rel = r.relative_to(ROOT.resolve()).as_posix()
        return rel if rel != "." else r.name
    except ValueError:
        return r.name


def ws_label(ws):
    return " ".join(w[:1].upper() + w[1:] for w in re.split(r"[-_\s]+", ws.resolve().name) if w)


# ------------------------------------------------------------------ records

REQUIRED = ("id", "title", "kind", "captured", "file", "sha256", "coverage", "records")
HEADER = ("id", "title", "kind", "captured", "detail", "url", "legacy", "file", "sha256", "coverage")


def load_records(ws, kinds):
    """{id: record} for every records/<ID>.json, in id order."""
    out = {}
    d = ws / "records"
    for p in sorted(d.iterdir()) if d.is_dir() else []:
        if p.name.startswith(".") or not p.is_file() or p.suffix != ".json":
            continue
        rec = read_json(ws, p)
        rel = p.relative_to(ws).as_posix()
        if not isinstance(rec, dict) or any(k not in rec for k in REQUIRED):
            raise DataError(f"{rel} is not a record file (it needs {', '.join(REQUIRED)}); bs.py check names the fix")
        if rec["kind"] not in kinds or not isinstance(rec["records"], list) or not isinstance(rec["file"], str):
            raise DataError(f"{rel} has an unknown kind or a malformed records list; bs.py check names the fix")
        out[rec["id"]] = rec
    return out


def units(kind, recs):
    """What a record file holds, in the units a reader gives (FORMATS.md section 1)."""
    n = len(recs)
    locs = [r.get("locator", "") for r in recs if isinstance(r, dict)]
    if kind == "sheet":
        return [{"n": len({l.rsplit("!", 1)[0] for l in locs if "!" in l}), "of": "sheet"}, {"n": n, "of": "cell"}]
    if kind in ("document", "web"):
        pages = {m.group(1) for l in locs for m in [re.match(r"p(\d+)\s", l)] if m}
        return ([{"n": len(pages), "of": "page"}] if pages else []) + [{"n": n, "of": "paragraph"}]
    return [{"n": n, "of": "turn"}]


def record_view(rec):
    """The record header verbatim (its sha256 cut to 8 characters), plus the page fields."""
    v = {k: rec[k] for k in HEADER if k in rec}
    v["sha256"] = str(rec["sha256"])[:SHORT]
    v["href"] = f"../records/{rec['id']}.json"
    v["recordCount"] = len(rec["records"])
    v["units"] = units(rec["kind"], rec["records"])
    v["preview"] = [{k: r[k] for k in ("locator", "text", "context") if k in r}
                    for r in rec["records"][:PREVIEW] if isinstance(r, dict)]
    return v


# ------------------------------------------------------------------ citations: "used by"

def citation_counter(rules, ids):
    lines = rules["documentLines"]
    bracket, part = re.compile(lines["bracket"]), re.compile(lines["bracketPart"])
    prov = {w: re.compile(lines[w]) for w in ("Grounded", "Inferred", "Gap")}
    link = re.compile(r"\[([^\[\]]+)\]\(([^)\s]+)\)")

    def refs_of(text):
        """Source ids in 'SRC locator; SRC locator', or None when it is not that form."""
        out = []
        for p in text.split(";"):
            p = p.strip()
            if p.startswith("[") and p.endswith("]"):
                p = p[1:-1].strip()
            m = part.match(p)
            if not m:
                return None
            out.append(m.group(1))
        return out

    def brackets(text, c):
        """Every citation bracket in prose: a bracket that names a record file."""
        body = re.sub(r"\\[\[\]]", "", text)
        for m in bracket.finditer(body):
            srcs = refs_of(m.group(1))
            if srcs and any(s in ids for s in srcs):
                c.update(s for s in srcs if s in ids)

    def cite(entry, c):
        if not isinstance(entry, dict):
            return
        t = entry.get("type")
        if t in ("inferred", "absent"):
            for r in entry.get("from" if t == "inferred" else "in") or []:
                if isinstance(r, dict) and r.get("source") in ids:
                    c[r["source"]] += 1
        elif entry.get("source") in ids:
            c[entry["source"]] += 1

    def json_file(data):
        """Maps, AI layers and decks: every entry of every cite array, plus the [ ] markers in a map's gap and
        clarification prose."""
        c = Counter()

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "cite" and isinstance(v, list):
                        for e in v:
                            cite(e, c)
                    else:
                        walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
        if isinstance(data, dict):
            for key, fields in (("gaps", ("title", "text")), ("clarifications", ("title", "shows", "ask"))):
                for card in data.get(key) or []:
                    for f in fields:
                        if isinstance(card, dict) and isinstance(card.get(f), str):
                            brackets(card[f], c)
        return c

    def document(text):
        """Every source in a [ ] bracket, and every address on a Grounded, Inferred or Gap line. Front matter,
        fenced code, HTML comments, code spans, escaped brackets and link targets cite nothing."""
        c = Counter()
        lines_ = text.replace("\r\n", "\n").split("\n")
        if lines_ and lines_[0].strip() == "---":
            for i in range(1, len(lines_)):
                if lines_[i].strip() == "---":
                    lines_ = lines_[i + 1:]
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
    """{record id: [use]} over every section file, in section order and then by name."""
    json_file, document = citation_counter(rules, ids)
    out = {i: [] for i in ids}
    for sec, _, ext in SECTIONS:
        d = ws / sec
        for p in sorted(d.iterdir()) if d.is_dir() else []:
            if p.name.startswith(".") or not p.is_file() or p.suffix != ext or not SECTION_FILE.match(p.stem):
                continue
            if ext == ".md":
                try:
                    c = document(p.read_bytes().decode("utf-8"))
                except UnicodeDecodeError:
                    raise DataError(f"{sec}/{p.name} is not UTF-8 text; bs.py check names the fix")
            else:
                c = json_file(read_json(ws, p))
            for sid, n in sorted(c.items()):
                out[sid].append({"section": sec, "name": p.stem, "href": f"{sec}/{p.stem}.html", "citations": n})
    return out


# ------------------------------------------------------------------ status, the way bs.py decides it

def kind_from_ext(kinds, ext):
    for k, v in kinds.items():
        if ext in v["read"]:
            return k
    for k, v in kinds.items():
        if ext in v["unchecked"]:
            return k
    return None


def island(ws, rules):
    kinds = rules["kinds"]
    containers = set(rules.get("containers", []))
    inputs = ws / "inputs"
    recs = load_records(ws, kinds)
    uses = used_by(ws, rules, set(recs))
    named = {r["file"]: r for r in recs.values()}
    by_sha = {r["sha256"]: r for r in recs.values()}

    folders, paths = ["inputs"], []
    for p in sorted(inputs.rglob("*")):
        parts = p.relative_to(inputs).parts
        if hidden(parts):
            continue
        if p.is_dir():
            folders.append(p.relative_to(ws).as_posix())
        elif p.is_file():
            paths.append(p)

    files = []
    for p in paths:
        rel, ext = p.relative_to(ws).as_posix(), p.suffix.lower()
        now = sha(p)
        f = {"file": rel, "bytes": p.stat().st_size, "sha256": now[:SHORT], "status": None, "kind": None,
             "kindFrom": "extension", "captured": None, "record": None, "duplicateOf": None, "usedBy": [],
             "convertWith": None, "problem": None}
        rec = named.get(rel)
        if rec:
            k = kinds[rec["kind"]]
            f.update(kind=rec["kind"], kindFrom="record", captured=rec["captured"], record=record_view(rec),
                     usedBy=uses[rec["id"]])
            if now != rec["sha256"]:
                f.update(status="error", problem="edited")          # rec-2
            elif ext in k["read"]:
                f["status"] = "converted"
            elif ext in k["unchecked"]:
                f["status"] = "unchecked"                            # rec-5: a person compares it
            else:
                f.update(status="error", problem="kind")            # rec-5: the kind cannot take this extension
        else:
            f["kind"] = kind_from_ext(kinds, ext)
            if ext in containers:
                f.update(status="not-converted", convertWith="unpack")   # ws-1: a container is unpacked first
            elif now in by_sha:
                o = by_sha[now]
                f.update(status="duplicate", duplicateOf={"file": o["file"], "id": o["id"]})   # ws-1 warning
            else:
                k = f["kind"]
                f.update(status="not-converted",                    # ws-1
                         convertWith="bs.py" if k and ext in kinds[k]["read"] else "converter agent")
        files.append(f)

    listed = {f["file"] for f in files}
    for rec in sorted(recs.values(), key=lambda r: r["file"]):
        if rec["file"] in listed:
            continue
        files.append({"file": rec["file"], "bytes": None, "sha256": None, "status": "error", "kind": rec["kind"],
                      "kindFrom": "record", "captured": rec["captured"], "record": record_view(rec),
                      "duplicateOf": None, "usedBy": uses[rec["id"]], "convertWith": None, "problem": "missing"})
    files.sort(key=lambda f: f["file"])
    for f in files:
        for k in [k for k, v in f.items() if v is None and k in ("duplicateOf", "convertWith", "problem")]:
            del f[k]

    return {
        "workspace": {"path": ws_path(ws), "label": ws_label(ws)},
        "kinds": [{"id": k, "label": v["label"]} for k, v in kinds.items()],
        "sections": [{"id": s, "label": label} for s, label, _ in SECTIONS],
        "folders": sorted(folders),
        "files": files,
    }


def page(data):
    tpl = TEMPLATE.read_text(encoding="utf-8")
    blob = json.dumps(data, ensure_ascii=False, indent=1).replace("<", "\\u003c")
    title = f"{data['workspace']['label']} · data received"
    esc = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for slot, n in (("{{title}}", 2), ("{{data}}", 1)):
        if tpl.count(slot) != n:
            cannot_run(f"design-system/data-received/template.html holds {slot} {tpl.count(slot)} time(s), not {n}")
    return tpl.replace("{{title}}", esc).replace("{{data}}", blob)


def main(argv):
    if len(argv) != 2 or argv[0].startswith("-"):
        print(__doc__.strip().split("\n\n")[0], file=sys.stderr)
        print("usage: python3 design-system/data-received/build_received.py <ws> <out.html>", file=sys.stderr)
        return 2
    ws, out = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    if not (ws / "inputs").is_dir():
        cannot_run("the workspace has no inputs/ folder")
    for p, rel in ((TEMPLATE, "design-system/data-received/template.html"), (CITATION_TYPES, "formats/citation-types.json")):
        if not p.is_file():
            cannot_run(f"{rel} is missing")
    rules = json.loads(CITATION_TYPES.read_text(encoding="utf-8"))
    try:
        data = island(ws, rules)
    except DataError as e:
        print(f"data error: {e}", file=sys.stderr)
        return 1
    html = page(data)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(html.encode("utf-8"))
    except OSError as e:
        cannot_run(f"the page cannot be written ({e.strerror})")
    n = Counter(f["status"] for f in data["files"])
    order = ["converted", "unchecked", "not-converted", "duplicate", "error"]
    print(f"{len(data['files'])} file(s): " + ", ".join(f"{n[s]} {s}" for s in order if n[s]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

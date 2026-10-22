#!/usr/bin/env python3
"""bs.py: the one command of baby-sienna. Python 3.8+ standard library only.

    python3 bs.py status  WS [--json]                 the state of each file, the workspace state and the next step
    python3 bs.py convert WS inputs/FILE --id ID --kind KIND --title T --captured DATE
                          [--detail D] [--url U] [--partial] [--legacy]
                                                      write records/ID.json (refuses to overwrite; exit 2 when no reader)
    python3 bs.py convert --units FILE KIND           print the records a raw input converts to, and write nothing
    python3 bs.py check   WS [FILE] [--builtin]       every rule in formats/FORMATS.md section 6
    python3 bs.py check   --rules                     print the citation rules table of formats/FORMATS.md section 2.3
    python3 bs.py check   --selftest [--builtin]      break the examples one rule at a time; every break must be caught
    python3 bs.py build   WS [SECTION/NAME | data-received]
                                                      check, then the builders, then the build rules, into WS/out/
    python3 bs.py build   WS --prepare OUTDIR         write what build hands the document and proposal builders

Every whole-workspace build also builds the Original data received page, WS/out/data-received.html (formats/FORMATS.md
section 8), even when check fails; the target data-received builds it alone.

Exit codes: 0 pass (warnings are listed), 1 a rule failed, 2 cannot run. Every command exits 2 on a workspace that
git tracks, except the toolkit's own examples/.

Citation types, kinds, grammars, readers and the rules per element category come from formats/citation-types.json;
id patterns and enums come from the schemas. bs.py uses the jsonschema package when it is installed and otherwise a
built-in checker for the fixed keyword subset the schemas use (--builtin forces it). A document is parsed by the
document type's own parser (design-system/document/build_doc.py), so the checker and the builder read the same blocks.

Each finding is one line:  LEVEL  RULE  file#/json/pointer (or file:line)  message  -> fix
"""
import argparse
import csv
import datetime
import hashlib
import html
import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser

HERE = pathlib.Path(__file__).resolve().parent
SECTIONS = ["process-map", "process-map-ai-opportunity", "document", "proposal"]
WORKSPACE_DIRS = ["inputs", "records", "out"] + SECTIONS
EXTS = {"process-map": ".json", "process-map-ai-opportunity": ".json", "document": ".md", "proposal": ".json"}
AI_SECTION = "process-map-ai-opportunity"
RECEIVED = "data-received"


# ================================================================== contract: formats/ and the section schemas

def design(rel):
    """A file of the toolkit, or exit 2 when it is missing."""
    p = HERE / rel
    if not p.is_file():
        raise SystemExit(f"cannot run: {rel} is missing")
    return p


SCHEMA_FILES = ["formats/schemas/source-record.schema.json", "formats/schemas/citation.schema.json",
                "design-system/process-map/process-map.schema.json",
                "design-system/process-map-ai-opportunity/ai-layer.schema.json",
                "design-system/document/document-front-matter.schema.json",
                "design-system/proposal/proposal.schema.json"]
RULES = None   # load() fills these from formats/ and the schemas, so that --help runs on an incomplete toolkit


def load():
    """Read the contract once: citation-types.json and the six schemas, and the patterns taken from them."""
    global RULES, SCHEMAS, SOURCE_RE, FILE_RE, ID_SHAPES, COUNT_SELECTORS, AI_RX, KINDS, UNIT_RE, SPAN_RE
    global BRACKET, BRACKET_PART, DOC_LINES
    if RULES is not None:
        return
    rules = json.loads(design("formats/citation-types.json").read_text(encoding="utf-8"))
    SCHEMAS = {}
    for rel in SCHEMA_FILES:
        s = json.loads(design(rel).read_text(encoding="utf-8"))
        SCHEMAS[s["$id"]] = s
    SOURCE_RE = re.compile(defn("citation.schema.json", "sourceId")["pattern"])
    FILE_RE = re.compile(defn("process-map.schema.json", "sectionFile")["pattern"])
    shapes = {"node": defn("process-map.schema.json", "nodeId")["pattern"],
              "group": defn("process-map.schema.json", "groupId")["pattern"],
              "gap": defn("process-map.schema.json", "gapId")["pattern"],
              "clarification": defn("process-map.schema.json", "clarificationId")["pattern"],
              "AI item": defn("ai-layer.schema.json", "aiId")["pattern"]}
    ID_SHAPES = {k: re.compile(v) for k, v in shapes.items()}
    COUNT_SELECTORS = defn("process-map.schema.json", "count")["enum"]
    AI_RX = ([re.compile(rf"(?<![A-Za-z0-9]){re.escape(w)}(?![A-Za-z0-9])") for w in rules["aiTerms"]["caseSensitiveWords"]]
             + [re.compile(rf"(?<![A-Za-z0-9]){re.escape(w)}(?![A-Za-z0-9])", re.I) for w in rules["aiTerms"]["caseInsensitiveWords"]])
    KINDS = rules["kinds"]
    UNIT_RE = {k: re.compile(v["record"]) for k, v in KINDS.items()}
    SPAN_RE = {k: {n: re.compile(r) for n, r in v["spans"].items()} for k, v in KINDS.items()}
    BRACKET = re.compile(rules["documentLines"]["bracket"])
    BRACKET_PART = re.compile(rules["documentLines"]["bracketPart"])
    DOC_LINES = {k: re.compile(rules["documentLines"][k]) for k in ("Grounded", "Inferred", "Gap")}
    RULES = rules


def defn(schema_id, name):
    return SCHEMAS[schema_id]["$defs"][name]


class _DocBuilder:
    """The document type's own builder (build_doc.py), imported on first use so that its parser is the checker's
    parser. Bytecode is not written, which leaves the adopted folder untouched."""
    mod = None

    def __getattr__(self, name):
        if _DocBuilder.mod is None:
            path = design("design-system/document/build_doc.py")
            spec = importlib.util.spec_from_file_location("build_doc", path)
            mod = importlib.util.module_from_spec(spec)
            write, sys.dont_write_bytecode = sys.dont_write_bytecode, True
            try:
                spec.loader.exec_module(mod)
            finally:
                sys.dont_write_bytecode = write
            _DocBuilder.mod = mod
        return getattr(_DocBuilder.mod, name)


BD = _DocBuilder()


# ================================================================== report

class Report:
    """The findings of one check, plus what status and build read from it: the citations that resolved, per file
    (cited), each input's state (inputs), the record files with no reader (unchecked), the maps and the index."""
    def __init__(self):
        self.items, self.engine = [], ""
        self.cited, self.inputs, self.unchecked, self.maps, self.idx = {}, [], [], {}, None

    def err(self, rule, where, msg, fix=""):
        self.items.append(("ERROR", rule, where, msg, fix))

    def warn(self, rule, where, msg, fix=""):
        self.items.append(("WARN", rule, where, msg, fix))

    def errors(self):
        return [i for i in self.items if i[0] == "ERROR"]

    def rules(self):
        return {i[1] for i in self.errors()}

    def print(self, out=sys.stdout, only=None):
        for level, rule, where, msg, fix in self.items:
            if only is None or finding_file(where) == only:
                print(f"{level:5}  {rule:8}  {where}  {msg}" + (f"  -> {fix}" if fix else ""), file=out)


def finding_file(where):
    """The workspace file a finding names: 'process-map/x.json#/nodes/0' and 'document/x.md:12' name their files."""
    return re.sub(r":\d+$", "", where.split("#", 1)[0])


def ptr(*parts):
    return "/" + "/".join(str(p) for p in parts) if parts else ""


# ================================================================== JSON Schema

def jeq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


class MiniValidator:
    """The keyword subset the baby-sienna schemas use. Any other keyword stops the run (exit 2), so the
    built-in checker can never silently pass something jsonschema would fail."""
    ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "default", "examples", "$defs"}
    KEYWORDS = {"$ref", "type", "const", "enum", "pattern", "minLength", "maxLength", "minimum", "maximum",
                "items", "minItems", "maxItems", "uniqueItems", "contains", "properties", "required",
                "additionalProperties", "allOf", "anyOf", "oneOf", "not", "if", "then", "else"}

    def __init__(self, schemas):
        self.schemas = schemas

    def resolve(self, ref, base):
        file, _, frag = ref.partition("#")
        doc_id = file or base
        node = self.schemas[doc_id]
        for part in [p for p in frag.split("/") if p]:
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return node, doc_id

    def validate(self, inst, schema_id):
        out = []
        self._check(inst, self.schemas[schema_id], schema_id, (), out)
        return out

    @staticmethod
    def _type_ok(v, t):
        return {"object": isinstance(v, dict), "array": isinstance(v, list), "string": isinstance(v, str),
                "boolean": isinstance(v, bool), "null": v is None,
                "integer": isinstance(v, int) and not isinstance(v, bool),
                "number": isinstance(v, (int, float)) and not isinstance(v, bool)}[t]

    def _ok(self, inst, sch, base):
        tmp = []
        self._check(inst, sch, base, (), tmp)
        return not tmp

    def _check(self, inst, sch, base, path, out):
        if sch is True:
            return
        if sch is False:
            out.append((path, "is not allowed here"))
            return
        for k in sch:
            if k not in self.KEYWORDS and k not in self.ANNOTATIONS and not k.startswith("x-"):
                raise SystemExit(f"cannot run: schema keyword '{k}' is outside the supported subset")
        if "$ref" in sch:
            target, tbase = self.resolve(sch["$ref"], base)
            self._check(inst, target, tbase, path, out)
        if "type" in sch:
            ts = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
            if not any(self._type_ok(inst, t) for t in ts):
                out.append((path, f"should be {' or '.join(ts)}"))
                return
        if "const" in sch and not jeq(inst, sch["const"]):
            out.append((path, f"should be {json.dumps(sch['const'], ensure_ascii=False)}"))
        if "enum" in sch and not any(jeq(inst, e) for e in sch["enum"]):
            out.append((path, f"should be one of {', '.join(json.dumps(e, ensure_ascii=False) for e in sch['enum'])}"))
        if isinstance(inst, str):
            if "minLength" in sch and len(inst) < sch["minLength"]:
                out.append((path, f"is shorter than {sch['minLength']} characters"))
            if "maxLength" in sch and len(inst) > sch["maxLength"]:
                out.append((path, f"is {len(inst)} characters; the limit is {sch['maxLength']}"))
            if "pattern" in sch and not re.search(sch["pattern"], inst):
                out.append((path, f"does not match {sch['pattern']}"))
        if isinstance(inst, (int, float)) and not isinstance(inst, bool):
            if "minimum" in sch and inst < sch["minimum"]:
                out.append((path, f"is below {sch['minimum']}"))
            if "maximum" in sch and inst > sch["maximum"]:
                out.append((path, f"is above {sch['maximum']}"))
        if isinstance(inst, list):
            if "minItems" in sch and len(inst) < sch["minItems"]:
                out.append((path, f"needs at least {sch['minItems']} items"))
            if "maxItems" in sch and len(inst) > sch["maxItems"]:
                out.append((path, f"has {len(inst)} items; the limit is {sch['maxItems']}"))
            if sch.get("uniqueItems"):
                seen = []
                for v in inst:
                    if any(jeq(v, s) for s in seen):
                        out.append((path, "has duplicate items"))
                        break
                    seen.append(v)
            if "items" in sch:
                for i, v in enumerate(inst):
                    self._check(v, sch["items"], base, path + (i,), out)
            if "contains" in sch and not any(self._ok(v, sch["contains"], base) for v in inst):
                out.append((path, "holds no matching item"))
        if isinstance(inst, dict):
            for r in sch.get("required", []):
                if r not in inst:
                    out.append((path, f"is missing required field '{r}'"))
            props = sch.get("properties", {})
            for k, v in inst.items():
                if k in props:
                    self._check(v, props[k], base, path + (k,), out)
                elif "additionalProperties" in sch:
                    ap = sch["additionalProperties"]
                    if ap is False:
                        out.append((path + (k,), f"unknown field '{k}' (allowed: {', '.join(props)})"))
                    elif isinstance(ap, dict):
                        self._check(v, ap, base, path + (k,), out)
        for s in sch.get("allOf", []):
            self._check(inst, s, base, path, out)
        if "anyOf" in sch and not any(self._ok(inst, s, base) for s in sch["anyOf"]):
            out.append((path, sch.get("x-messages", {}).get("anyOf", "matches none of the allowed shapes")))
        if "oneOf" in sch:
            n = sum(1 for s in sch["oneOf"] if self._ok(inst, s, base))
            if n != 1:
                out.append((path, "matches none of the allowed shapes" if n == 0 else "matches more than one shape"))
        if "not" in sch and self._ok(inst, sch["not"], base):
            out.append((path, "matches a shape that is not allowed"))
        if "if" in sch:
            if self._ok(inst, sch["if"], base):
                if "then" in sch:
                    self._check(inst, sch["then"], base, path, out)
            elif "else" in sch:
                self._check(inst, sch["else"], base, path, out)


class SchemaSet:
    def __init__(self, builtin=False):
        load()
        self.schemas = SCHEMAS
        self.engine = "built-in subset"
        self.mini = MiniValidator(self.schemas)
        self.lib = None
        if not builtin:
            try:
                import importlib.metadata as md
                import jsonschema
                from referencing import Registry, Resource
                reg = Registry().with_resources([(k, Resource.from_contents(v)) for k, v in self.schemas.items()])
                self.lib = {k: jsonschema.Draft202012Validator(v, registry=reg) for k, v in self.schemas.items()}
                self.engine = "jsonschema " + md.version("jsonschema")
            except Exception:
                self.lib = None

    def validate(self, inst, schema_id):
        """[(path tuple, message)]"""
        if self.lib:
            return [(tuple(e.absolute_path), e.message[:300]) for e in self.lib[schema_id].iter_errors(inst)]
        return self.mini.validate(inst, schema_id)


def load_json(rep, where, path):
    """The parsed file, or None after a schema-1 finding."""
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except UnicodeDecodeError:
        rep.err("schema-1", where, "is not UTF-8 text")
    except ValueError as e:
        rep.err("schema-1", where, f"is not valid JSON: {e}")
    return None


def schema_ok(rep, where, data, schema_id, schemas, hint=None):
    errs = schemas.validate(data, schema_id)
    for p, msg in errs:
        rep.err("schema-1", where + "#" + ptr(*p), msg, hint(p, msg) if hint else "")
    return not errs


# ================================================================== text folding, AI terms

FOLD_MAP = {"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "\u00a0": " "}


def fold(s):
    s = unicodedata.normalize("NFKC", s)
    s = "".join(FOLD_MAP.get(c, c) for c in s)
    return re.sub(r"\s+", " ", s).strip()


def fold_ci(s):
    return fold(s).casefold()


def ai_terms_in(text):
    return [rx for rx in AI_RX if rx.search(text)]


# ================================================================== locators

def col_num(s):
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def col_name(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def tms(h, m, s, frac=None):
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + (int(frac) if frac else 0)


def unit_key(kind, loc):
    m = UNIT_RE[kind].match(loc)
    if not m:
        return None
    g = m.groups()
    if kind == "sheet":
        return (g[0], int(g[2]), col_num(g[1]))
    if kind in ("document", "web"):
        return (int(g[0]) if g[0] else 0, int(g[1]))
    return tms(*g)


def span_pred(kind, loc):
    """A predicate over record keys for a record locator or a span, or None when loc is neither."""
    k = unit_key(kind, loc)
    if k is not None:
        return lambda x: x == k
    for name, rx in SPAN_RE[kind].items():
        m = rx.match(loc)
        if not m:
            continue
        g = m.groups()
        if kind == "sheet":
            sh = g[0]
            if name == "range":
                c1, r1, c2, r2 = col_num(g[1]), int(g[2]), col_num(g[3]), int(g[4])
                if r1 > r2 or c1 > c2 or (r1, c1) == (r2, c2):
                    return None
                return lambda x: x[0] == sh and r1 <= x[1] <= r2 and c1 <= x[2] <= c2
            if name == "row":
                r = int(g[1])
                return lambda x: x[0] == sh and x[1] == r
            a, b = int(g[1]), int(g[2])
            if a >= b:
                return None
            return lambda x: x[0] == sh and a <= x[1] <= b
        if kind in ("document", "web"):
            if name == "page":
                p = int(g[0])
                return lambda x: x[0] == p
            p, a, b = (int(g[0]) if g[0] else 0), int(g[1]), int(g[2])
            if a >= b:
                return None
            return lambda x: x[0] == p and a <= x[1] <= b
        a = tms(*g[:4])
        b = tms(*g[4:]) + (0 if g[7] else 999)   # an end without milliseconds takes its whole second
        if a >= b:
            return None
        return lambda x: a <= x <= b
    return None


# ================================================================== readers (the core of convert, and of rec-5)

class ReadError(Exception):
    pass


def read_text(path):
    try:
        return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as e:
        raise ReadError(f"is not UTF-8 text ({e.reason} at byte {e.start})")


def norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def sheet_units(sheets):
    """sheets: [(name, {(row, col): text})] in workbook order."""
    units = []
    for name, cells in sheets:
        header = {c: t for (r, c), t in cells.items() if r == 1 and t.strip()}
        for (r, c) in sorted(cells):
            text = cells[(r, c)]
            if text.strip():
                units.append((f"{name}!{col_name(c)}{r}", text, header.get(c) if r > 1 else None))
    return units


def read_csv(path, delimiter):
    rows = list(csv.reader(io.StringIO(read_text(path)), delimiter=delimiter))
    return [(path.stem, {(r, c): v for r, row in enumerate(rows, 1) for c, v in enumerate(row, 1)})]


XL = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
DATE_FORMAT_IDS = set(range(14, 23)) | {45, 46, 47}


def xlsx_date(serial, date1904):
    v = float(serial)
    base = datetime.datetime(1904, 1, 1) if date1904 else datetime.datetime(1899, 12, 30)
    d = base + datetime.timedelta(seconds=round(v * 86400))
    t = d.strftime("%H:%M") if d.second == 0 else d.strftime("%H:%M:%S")
    if v < 1:
        return t
    return d.strftime("%Y-%m-%d") if d.hour == d.minute == d.second == 0 else d.strftime("%Y-%m-%d ") + t


def read_xlsx(path):
    """Each cell's stored value: text as stored, a number unformatted (5000), a date cell as an ISO date."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise ReadError("is not a readable .xlsx workbook")
    with z:
        try:
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
            pr = wb.find("m:workbookPr", XL)
            date1904 = pr is not None and pr.get("date1904") in ("1", "true")
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", XL):
                    ts = si.findall("m:t", XL) or [t for r in si.findall("m:r", XL) for t in r.findall("m:t", XL)]
                    shared.append("".join(t.text or "" for t in ts))
            dates = set()
            if "xl/styles.xml" in z.namelist():
                st = ET.fromstring(z.read("xl/styles.xml"))
                custom = {int(f.get("numFmtId")): f.get("formatCode", "") for f in (st.find("m:numFmts", XL) or [])}
                for i, xf in enumerate(st.find("m:cellXfs", XL) or []):
                    fid = int(xf.get("numFmtId", "0"))
                    code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", custom.get(fid, ""))
                    if fid in DATE_FORMAT_IDS or re.search(r"[dmyhs]", code, re.I):
                        dates.add(i)
            sheets = []
            for sh in wb.find("m:sheets", XL):
                target = rels[sh.get(f"{{{XL['r']}}}id")]
                target = target.lstrip("/") if target.startswith("/") else "xl/" + target
                cells = {}
                for c in ET.fromstring(z.read(target)).iter(f"{{{XL['m']}}}c"):
                    m = re.match(r"([A-Z]+)(\d+)$", c.get("r", ""))
                    if not m:
                        raise ReadError("has a cell without a reference")
                    t, v = c.get("t", "n"), c.find("m:v", XL)
                    val = v.text if v is not None else None
                    if t == "s":
                        text = shared[int(val)] if val is not None else ""
                    elif t == "inlineStr":
                        text = "".join(x.text or "" for x in c.iter(f"{{{XL['m']}}}t"))
                    elif t == "b":
                        text = "TRUE" if val == "1" else "FALSE"
                    elif val is None:
                        continue
                    elif t in ("str", "e", "d"):
                        text = val
                    else:
                        text = xlsx_date(val, date1904) if int(c.get("s", "0")) in dates else val
                    cells[(int(m.group(2)), col_num(m.group(1)))] = text
                sheets.append((sh.get("name"), cells))
            return sheets
        except (KeyError, ET.ParseError, ValueError, IndexError) as e:
            raise ReadError(f"is not a readable .xlsx workbook ({e})")


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_units(path):
    try:
        with zipfile.ZipFile(path) as z:
            body = ET.fromstring(z.read("word/document.xml")).find(f"{W}body")
    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError):
        raise ReadError("is not a readable .docx document")

    def ptext(p):
        out = []
        for el in p.iter():
            if el.tag == f"{W}t":
                out.append(el.text or "")
            elif el.tag in (f"{W}tab", f"{W}br", f"{W}cr"):
                out.append(" ")
        return norm_ws("".join(out))

    units, heading, n = [], None, 0
    for el in (body if body is not None else []):
        if el.tag == f"{W}p":
            text = ptext(el)
            if not text:
                continue
            style = el.find(f"{W}pPr/{W}pStyle")
            is_h = style is not None and re.match(r"(?i)heading|title", style.get(f"{W}val", "")) is not None
            n += 1
            units.append((f"¶{n}", text, None if is_h else heading))
            if is_h:
                heading = text
        elif el.tag == f"{W}tbl":
            for tr in el.iter(f"{W}tr"):
                cells = [" ".join(t for t in (ptext(p) for p in tc.iter(f"{W}p")) if t) for tc in tr.findall(f"{W}tc")]
                if any(cells):
                    n += 1
                    units.append((f"¶{n}", " | ".join(cells), heading))
    return units


MD_LIST = re.compile(r"^\s*([-*+]|\d+[.)])\s+")


def md_units(raw):
    """Paragraphs, headings, list items and table rows of Markdown or plain text, in reading order."""
    heading, n, units = None, 0, []
    for block in re.split(r"\n\s*\n", raw):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        items = []
        if all(l.lstrip().startswith("|") for l in lines):
            for l in lines:
                if not BD.TABLE_SEP.match(l.strip()):
                    items.append(("row", " | ".join(BD.split_row(l))))
        else:
            for l in lines:
                s = l.strip()
                if re.match(r"^#{1,6}\s", s):
                    items.append(("h", re.sub(r"^#{1,6}\s+(.*?)\s*#*\s*$", r"\1", s)))
                elif MD_LIST.match(l):
                    items.append(("li", MD_LIST.sub("", l).strip()))
                elif items and items[-1][0] in ("li", "p") and (l[:1].isspace() or items[-1][0] == "p"):
                    items[-1] = (items[-1][0], items[-1][1] + " " + re.sub(r"^>\s?", "", s))
                else:
                    items.append(("p", re.sub(r"^>\s?", "", s)))
        for kind, text in items:
            if not text.strip():
                continue
            n += 1
            units.append((f"¶{n}", text, None if kind == "h" else heading))
            if kind == "h":
                heading = text
    return units


class _HtmlUnits(HTMLParser):
    BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "dt", "dd", "caption", "figcaption", "pre"}
    SKIP = {"script", "style", "head", "title", "template", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.units, self.buf, self.tag, self.skip, self.heading, self.row, self.cell = [], None, None, 0, None, None, None

    def add(self, text, is_h):
        self.units.append((text, None if is_h else self.heading))
        if is_h:
            self.heading = text

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif self.skip:
            return
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag in self.BLOCKS and self.buf is None and self.cell is None:
            self.buf, self.tag = [], tag
        elif tag == "br":
            self.handle_data(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(norm_ws("".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.add(" | ".join(self.row), False)
            self.row = None
        elif self.buf is not None and tag == self.tag:
            text = norm_ws("".join(self.buf))
            if text:
                self.add(text, re.fullmatch(r"h[1-6]", tag) is not None)
            self.buf, self.tag = None, None

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.buf is not None:
            self.buf.append(data)


def html_units(raw):
    p = _HtmlUnits()
    p.feed(raw)
    return [(f"¶{i}", t, ctx) for i, (t, ctx) in enumerate(p.units, 1)]


TURN = re.compile(r"^(\d{2}:\d{2}:\d{2}(?:\.\d{3})?)\s+([^:]{1,60}?):\s+(.+?)\s*$")
CUE_TIME = re.compile(r"^(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s+-->")


def read_timed_txt(path):
    units = []
    for line in read_text(path).split("\n"):
        if not line.strip():
            continue
        m = TURN.match(line)
        if m:
            units.append([m.group(1), m.group(3), m.group(2)])
        elif units:
            units[-1][1] += " " + line.strip()   # a turn that wraps onto the next line
        else:
            raise ReadError("a timed transcript starts with a line 'HH:MM:SS Speaker: text'")
    return [tuple(u) for u in units]


def timed_units(cues):
    """cues: [((h, m, s, ms), speaker, text)]. A turn is located by its start second; a later turn that starts
    in a second already used keeps its milliseconds (00:00:31.400)."""
    units, used = [], set()
    for (h, m, s, ms), speaker, text in cues:
        if not text:
            continue
        loc = f"{int(h or 0):02d}:{m}:{s}"
        if loc in used:
            loc = f"{loc}.{ms}"
            if loc in used:
                raise ReadError(f"two cues start at {loc}")
        used.add(loc.split(".")[0])
        used.add(loc)
        units.append((loc, text, speaker))
    return units


def cue(lines, where):
    m = CUE_TIME.match(lines[0]) if lines else None
    if not m:
        raise ReadError(f"{where}: a cue starts with a time line '00:00:05.000 --> 00:00:07.000'")
    text = " ".join(l.strip() for l in lines[1:] if l.strip())
    speaker = None
    vm = re.match(r"^<v(?:\.[^\s>]*)?\s+([^>]+)>", text)
    if vm:
        speaker = vm.group(1).strip()
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
    if not speaker:
        sm = re.match(r"^([^:]{1,60}?):\s+(.+)$", text)
        if sm:
            speaker, text = sm.group(1).strip(), sm.group(2)
    return m.groups(), speaker, norm_ws(text)


def read_vtt(path):
    blocks = [b for b in re.split(r"\n\s*\n", read_text(path).strip()) if b.strip()]
    if not blocks or not blocks[0].startswith("WEBVTT"):
        raise ReadError("a .vtt file starts with WEBVTT")
    cues = []
    for k, b in enumerate(blocks[1:], 2):
        lines = b.split("\n")
        if lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        if not CUE_TIME.match(lines[0]):
            lines = lines[1:]   # a cue identifier
        cues.append(cue(lines, f"block {k}"))
    return timed_units(cues)


def read_srt(path):
    cues = []
    for k, b in enumerate([b for b in re.split(r"\n\s*\n", read_text(path).strip()) if b.strip()], 1):
        lines = b.split("\n")
        if re.fullmatch(r"\d+", lines[0].strip()):
            lines = lines[1:]
        cues.append(cue(lines, f"block {k}"))
    return timed_units(cues)


def extract_units(kind, path):
    """[(locator, text, context)] in reading order, or None when the kind has no reader for this extension
    (an UNCHECKED format). Raises ReadError when the file cannot be read."""
    path = pathlib.Path(path)
    ext = path.suffix.lower()
    if ext not in KINDS[kind]["read"]:
        return None
    if kind == "sheet":
        return sheet_units(read_xlsx(path) if ext in (".xlsx", ".xlsm") else read_csv(path, "\t" if ext == ".tsv" else ","))
    if kind == "transcript":
        return {".txt": read_timed_txt, ".vtt": read_vtt, ".srt": read_srt}[ext](path)
    if ext in (".html", ".htm"):
        return html_units(read_text(path))
    if ext == ".docx":
        return docx_units(path)
    return md_units(read_text(path))


# ================================================================== records

class Source:
    def __init__(self, data):
        self.id, self.header, self.kind, self.coverage = data["id"], data, data["kind"], data["coverage"]
        self.records = [{"locator": r["locator"], "text": r["text"], "context": r.get("context"),
                         "key": unit_key(self.kind, r["locator"]), "index": i, "address": f"{data['id']} {r['locator']}"}
                        for i, r in enumerate(data["records"])]


class Index:
    def __init__(self):
        self.sources = {}

    def resolve(self, ref):
        sid, loc = ref.get("source"), ref.get("locator")
        src = self.sources.get(sid)
        if not src:
            return None, f"source {sid} has no record file records/{sid}.json"
        if loc is None:
            return list(src.records), None
        pred = span_pred(src.kind, loc)
        if pred is None:
            return None, f"'{loc}' is not a {src.kind} locator (forms such as {', '.join(KINDS[src.kind]['examples'])})"
        recs = [r for r in src.records if r["key"] is not None and pred(r["key"])]
        if not recs:
            return None, f"'{sid} {loc}' resolves to no record"
        return recs, None


RECONVERT = "never edit a record file: delete it and convert the input again"


def real_date(s):
    """True when s is an ISO date, YYYY-MM-DD, that is on the calendar. The schemas check only its shape."""
    if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return False
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        return False
    return True


def check_records(ws, rep, schemas):
    idx, seen_file, seen_sha = Index(), {}, {}
    inputs = (ws / "inputs").resolve()
    for p in sorted((ws / "records").iterdir()) if (ws / "records").is_dir() else []:
        if p.name.startswith("."):
            continue
        where = f"records/{p.name}"
        if not p.is_file() or p.suffix != ".json" or not SOURCE_RE.match(p.stem):
            rep.err("ws-2", where, "records/ holds only <ID>.json record files", "move it out of the workspace")
            continue
        data = load_json(rep, where, p)
        if data is None or not schema_ok(rep, where, data, "source-record.schema.json", schemas):
            continue
        if data["id"] != p.stem:
            rep.err("rec-1", where + "#/id", f"id {data['id']} differs from the file name", f"name the file records/{data['id']}.json")
        if not real_date(data["captured"]):
            rep.err("schema-1", where + "#/captured", f"{data['captured']} is not a calendar date",
                    RECONVERT + " with a real --captured date")
        src, kind = Source(data), data["kind"]
        f = ws / data["file"]
        inside = inputs in f.resolve().parents
        if not inside:
            rep.err("rec-2", where + "#/file", f"{data['file']} is not inside inputs/")
        elif not f.is_file():
            rep.err("rec-2", where + "#/file", f"{data['file']} is not in the workspace, so nothing proves these records",
                    "restore the input from the original; a record file never exists without its input")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != data["sha256"]:
            rep.err("rec-2", where + "#/sha256", f"{data['file']} was edited after conversion",
                    "restore the original; save a new version under a new name in inputs/ and convert that")
        for key, store in (("file", seen_file), ("sha256", seen_sha)):
            if data[key] in store:
                rep.err("rec-6", where + "#/" + key, f"{key} is the same as in {store[data[key]]}: one input becomes one record file")
            store[data[key]] = where
        locs = set()
        for i, r in enumerate(src.records):
            if r["key"] is None:
                rep.err("rec-3", where + "#" + ptr("records", i, "locator"), f"'{r['locator']}' is not a {kind} record locator",
                        "forms: " + ", ".join(KINDS[kind]["examples"][:2]))
            if r["locator"] in locs:
                rep.err("rec-3", where + "#" + ptr("records", i, "locator"), f"locator '{r['locator']}' is used twice")
            locs.add(r["locator"])
        keys = [r["key"] for r in src.records if r["key"] is not None]
        if kind == "sheet":
            order = {}
            keys = [(order.setdefault(k[0], len(order)), k[1], k[2]) for k in keys]
        if kind in ("document", "web") and keys and len({k[0] == 0 for k in keys}) > 1:
            rep.err("rec-4", where, "either every record has a page (p2 ¶3) or none has (¶3)")
        for i in range(1, len(keys)):
            if keys[i] <= keys[i - 1]:
                rep.err("rec-4", where + "#" + ptr("records", i), "records are not in reading order", KINDS[kind]["order"])
                break
        if inside and f.is_file():
            check_verbatim(rep, where, data, src, f, locs)
        idx.sources[src.id] = src
    return idx


def check_verbatim(rep, where, data, src, f, locs):
    kind, ext = data["kind"], f.suffix.lower()
    k = KINDS[kind]
    if ext not in k["read"] + k["unchecked"]:
        rep.err("rec-5", where + "#/kind", f"a {ext or 'extensionless'} file cannot be a {kind} source",
                f"{kind} inputs: {', '.join(k['read'] + k['unchecked'])}")
        return
    try:
        units = extract_units(kind, f)
    except ReadError as e:
        rep.err("rec-5", where + "#/file", f"{data['file']} {e}")
        return
    if units is None:
        rep.warn("rec-5", where, f"{ext} has no reader, so the records are UNCHECKED", "a person compares them with the input")
        rep.unchecked.append((where, data["file"]))
        return
    by_loc = {u[0]: u for u in units}
    for i, r in enumerate(src.records):
        u = by_loc.get(r["locator"])
        if not u:
            rep.err("rec-5", where + "#" + ptr("records", i), f"{r['address']} is not a unit of {data['file']}", RECONVERT)
        elif u[1] != r["text"]:
            rep.err("rec-5", where + "#" + ptr("records", i, "text"), f"text is not verbatim: the input says {json.dumps(u[1], ensure_ascii=False)}", RECONVERT)
        elif u[2] != r["context"]:
            rep.err("rec-5", where + "#" + ptr("records", i, "context"), f"context should be {json.dumps(u[2], ensure_ascii=False)}", RECONVERT)
    if data["coverage"] == "complete":
        missing = [u[0] for u in units if u[0] not in locs]
        if missing:
            rep.err("rec-5", where + "#/records", f"coverage is complete but {len(missing)} unit(s) have no record: {', '.join(missing[:5])}",
                    RECONVERT + " (with --partial for an excerpt)")


# ================================================================== citations

class Ctx:
    """Where prose and citations are checked: the section, the record index, the element ids prose may name
    (None in documents and decks), whether a citation may name a whole source, and whether a Gap must be PROVEN."""
    def __init__(self, section, idx, schemas, ids=None, whole_ok=False, doc=False):
        self.section, self.idx, self.schemas, self.ids, self.whole_ok, self.doc = section, idx, schemas, ids, whole_ok, doc


class Ev:
    def __init__(self, ctype, cite, recs, refs, web):
        self.type, self.cite, self.recs, self.refs, self.web = ctype, cite, recs, refs, web


def pool(evs):
    """The records a claim may draw quotes and numbers from: never the spans of an absent search."""
    return [r for e in evs if e.type != "absent" for r in e.recs]


def eval_cites(rep, where, cites, ctx):
    evs, idx = [], ctx.idx
    for i, c in enumerate(cites or []):
        w = f"{where}/{i}"
        t = c.get("type", "grounded")
        refs = [c] if t == "grounded" else c.get("from" if t == "inferred" else "in", [])
        recs, ok = [], True
        for j, ref in enumerate(refs):
            rw = w if t == "grounded" else f"{w}/{'from' if t == 'inferred' else 'in'}/{j}"
            if "locator" not in ref and t != "absent" and not ctx.whole_ok and ref.get("source") in idx.sources:
                rep.err("cite-1", rw, f"{ref['source']} with no locator cites the whole source",
                        "name the record or span, e.g. " + ", ".join(KINDS[idx.sources[ref['source']].kind]["examples"][:2]))
                ok = False
                continue
            got, why = idx.resolve(ref)
            if why:
                rep.err("cite-1", rw, why, "cite a record that exists, or a span that holds records")
                ok = False
            else:
                recs.extend(got)
        if not ok:
            continue
        web = sum(1 for ref in refs if idx.sources[ref["source"]].kind == "web")
        ev = Ev(t, c, recs, refs, web)
        rep.cited.setdefault(finding_file(where), []).append(ev)   # what the page prints (build-1, build-4)
        if t == "grounded" and c.get("quote") and not any(fold(c["quote"]) in fold(r["text"]) for r in recs):
            rep.err("cite-2", w + "/quote", f"quote is not verbatim in {c['source']} {c.get('locator', '')}".rstrip(),
                    "copy the words exactly as the record has them")
        if t == "absent":
            needle = fold_ci(c["needle"])
            hits = [r["address"] for r in recs if needle in fold_ci(r["text"])]
            if hits:
                rep.err("cite-3", w, f"“{c['needle']}” does occur in {hits[0]}", "this is not a gap: cite that record instead")
            partial = sorted({ref["source"] for ref in refs if idx.sources[ref["source"]].coverage != "complete"})
            if partial and not hits:
                if ctx.doc:
                    rep.err("cite-3", w, f"a document's Gap line must be PROVEN, but {', '.join(partial)} has coverage partial",
                            "search a complete source, or write the point as a clarification")
                else:
                    rep.warn("cite-3", w, f"absence is PROVISIONAL: {', '.join(partial)} has coverage partial")
        if t == "inferred":
            check_prose(rep, w + "/reading", c["reading"], recs, ctx, "design")
        evs.append(ev)
    return evs


def check_category(rep, where, section, category, evs, to_confirm=False):
    rule = RULES["categories"][section][category]
    for e in evs:
        if e.type not in rule["allowed"]:
            rep.err("cite-4", where, f"{category} does not take {e.type} citations"
                    + (f" (allowed: {', '.join(rule['allowed'])})" if rule["allowed"] else " (it takes none)"))
    for group in rule["require"]:
        hits = [e for e in evs if e.type in group]
        if rule.get("quoteWithAiTerm"):
            if not any(e.cite.get("quote") and ai_terms_in(e.cite["quote"]) and not e.web for e in hits):
                rep.err("ai-3", where, "a named item needs a grounded quote, from the client's own material, that holds an AI term",
                        "quote the client's words, or make the item suggested")
            continue
        if not hits and not (rule.get("orToConfirm") and to_confirm):
            rep.err("cite-4", where, f"{category} needs at least one {' or '.join(group)} citation")
    key, nweb = f"{section}/{category}", sum(e.web for e in evs)
    if nweb and key not in RULES["web"]["allowedIn"]:
        rep.err("cite-5", where, f"{category} cannot cite web sources", "cite the client's own material")
    if key in RULES["web"]["neverAloneIn"] and evs and all(e.web == len(e.refs) for e in evs):
        rep.err("cite-5", where, "web sources are never the only evidence here")


# ================================================================== prose

LINK = re.compile(r"\[([^\[\]]+)\]\(([^)\s]+)\)")
QUOTE = re.compile(r"“([^”]*)”")
NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
COUNT_TOKEN = re.compile(r"\{count:([a-z][a-z-]*)\}")
ID_TOKEN = re.compile(r"(?<![A-Za-z0-9-])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*(?![A-Za-z0-9-])")
PLACEHOLDER = re.compile(r"\[[A-Z][A-Za-z ]*\]")


def parse_bracket(inner):
    refs = []
    for part in inner.split(";"):
        m = BRACKET_PART.match(part.strip())
        if not m:
            return None
        refs.append({"source": m.group(1)} if not m.group(2) else {"source": m.group(1), "locator": m.group(2).strip()})
    return refs


def unescaped(text):
    return re.sub(r"\\[\[\]]", "", text)


def strip_ids(rep, where, text, ctx):
    """Source ids, and element ids that resolve, carry no numbers for prose-4. In maps and layers an id-shaped token
    must name an element (prose-6); documents and decks have no elements, so their id-shaped tokens are plain text."""
    def repl(m):
        tok = m.group(0)
        if tok in ctx.idx.sources:
            return " "
        shape = next((name for name, rx in ID_SHAPES.items() if rx.match(tok)), None)
        if shape is None or ctx.ids is None:
            return tok
        if tok not in ctx.ids:
            rep.err("prose-6", where, f"{tok} reads as a {shape} id but names no element here", "name an element that exists, or reword")
        return " "
    return ID_TOKEN.sub(repl, text)


def check_prose(rep, where, text, recs, ctx, kind, brackets="none", tokens=False):
    """kind: claim | design | label | deck. brackets: 'cite' (already checked as citations), 'none', 'placeholder'.
    recs: the records the element cites (its pool for prose-3 and prose-4)."""
    body = unescaped(text)
    if brackets == "none" and re.search(r"[\[\]]", body):
        rep.err("prose-1", where, "this field holds no brackets", "move evidence into cite; write \\[ for a literal bracket")
    if brackets == "placeholder":
        for m in re.finditer(r"\[[^\[\]]*\]", body):
            if not PLACEHOLDER.fullmatch(m.group(0)):
                rep.err("prose-1", where, f"{m.group(0)} is not a placeholder", "cite through the claim's cite; placeholders read [N] or [PRICE]")
    if '"' in re.sub(r"`[^`]*`", "", body):
        rep.err("prose-2", where, "straight double quote", "quote with “…”")
    rest = body.replace("`", "")
    names = COUNT_TOKEN.findall(rest)
    if names and not tokens:
        rep.err("prose-5", where, "{count:…} tokens are only for a map's meta.subtitle")
    for t in names:
        if tokens and t not in COUNT_SELECTORS:
            rep.err("prose-5", where, f"unknown count token {{count:{t}}}", "selectors: " + ", ".join(COUNT_SELECTORS))
    if re.search(r"[{}]", COUNT_TOKEN.sub("", rest)):
        rep.err("prose-5", where, "only {count:<selector>} tokens use { }")
    rest = BRACKET.sub(" ", LINK.sub(lambda m: m.group(1), COUNT_TOKEN.sub(" ", rest)))
    texts = [fold(r["text"]) for r in recs]
    for q in QUOTE.findall(rest):
        if not any(fold(q) in t for t in texts):
            rep.err("prose-3", where, f"“{q}” is not verbatim in a record this cites", "cite the record, or reword without quote marks")
    if ctx.section == "process-map":
        for rx in ai_terms_in(rest):
            if not any(rx.search(t) for t in texts):
                rep.err("map-9", where, f"“{rx.search(rest).group(0)}” is an AI idea in a current-state map",
                        "AI ideas belong in a process-map-ai-opportunity layer; describe today's automation only when a cited record does")
    rest = strip_ids(rep, where, QUOTE.sub(" ", rest), ctx)
    have = {n for t in texts for n in NUMBER.findall(t)}
    for num in NUMBER.findall(rest):
        if num not in have:
            rep.err("prose-4", where, f"the number {num} has no source", "cite a record that holds it, quote it, or use a {count:…} token")


def markers(rep, where, text, ctx):
    """Grounded evs for the [ ] markers in map card prose (prose-1, cite-1)."""
    body = unescaped(text)
    if LINK.search(body):
        rep.err("prose-1", where, "maps hold no links")
    evs = []
    for m in BRACKET.finditer(body):
        refs = parse_bracket(m.group(1))
        if refs is None or not any(r["source"] in ctx.idx.sources for r in refs):
            rep.err("prose-1", where, f"[{m.group(1)}] is not a citation", "brackets hold 'SRC locator; SRC locator'; write \\[ for a literal bracket")
            continue
        evs.extend(eval_cites(rep, where, refs, ctx))
    return evs


# ================================================================== process map

def map_counts(data):
    nodes = data["nodes"]
    return {"steps": sum(1 for n in nodes if n.get("kind", "step") == "step"),
            "decisions": sum(1 for n in nodes if n.get("kind") == "decision"),
            "groups": len(data.get("groups", [])), "gaps": len(data.get("gaps", [])),
            "clarifications": len(data.get("clarifications", [])), "systems": len(data.get("systems", []))}


def layout(data):
    """The board columns (README 'Layout'): {node id: column from 0}, the column count, and col hints that sit left
    of their derived column. Within a group a node's column is 1 + the longest path to it over forward edges inside
    the group; groups take consecutive columns, left to right."""
    nodes, edges = data["nodes"], data.get("edges", [])
    ix = {n["id"]: i for i, n in enumerate(nodes)}
    preds = {n["id"]: [] for n in nodes}
    for e in edges:
        a, b = nodes[ix[e["from"]]], nodes[ix[e["to"]]]
        if ix[b["id"]] > ix[a["id"]] and a.get("group") == b.get("group"):
            preds[b["id"]].append(a["id"])
    local, bad = {}, []
    for n in nodes:
        c = max([local[p] + 1 for p in preds[n["id"]]], default=1)
        if "col" in n:
            if n["col"] < c:
                bad.append((n["id"], n["col"], c))
            c = max(c, n["col"])
        local[n["id"]] = c
    col, start = {}, 0
    for g in [g["id"] for g in data.get("groups", [])] or [None]:
        members = [n["id"] for n in nodes if n.get("group") == g]
        for nid in members:
            col[nid] = start + local[nid] - 1
        start += max((local[nid] for nid in members), default=0)
    return col, start, bad


MAX_COLUMNS = 14


def check_map(rep, path, data, idx, schemas):
    where = f"process-map/{path.name}"
    if not schema_ok(rep, where, data, "process-map.schema.json", schemas):
        return False
    n0 = len(rep.errors())
    lanes, groups, nodes = data["lanes"], data.get("groups", []), data["nodes"]
    edges, gaps, clars, systems = data.get("edges", []), data.get("gaps", []), data.get("clarifications", []), data.get("systems", [])
    seen = {}
    for name, arr in (("lanes", lanes), ("systems", systems), ("groups", groups), ("nodes", nodes), ("gaps", gaps), ("clarifications", clars)):
        for i, x in enumerate(arr):
            if x["id"] in seen:
                rep.err("map-1", f"{where}#/{name}/{i}/id", f"id {x['id']} is already used by {seen[x['id']]}", "every id in a map is unique")
            seen.setdefault(x["id"], f"{name}/{i}")
    lane_ids, group_ix = {l["id"] for l in lanes}, {g["id"]: i for i, g in enumerate(groups)}
    sys_ids, node_ix = {s["id"] for s in systems}, {n["id"]: i for i, n in enumerate(nodes)}
    node_by = {n["id"]: n for n in nodes}
    for i, n in enumerate(nodes):
        w = f"{where}#/nodes/{i}"
        if n["lane"] not in lane_ids:
            rep.err("map-1", w + "/lane", f"node {n['id']}: unknown lane '{n['lane']}'", "lanes: " + ", ".join(sorted(lane_ids)))
        if "group" in n and n["group"] not in group_ix:
            rep.err("map-1", w + "/group", f"node {n['id']}: unknown group '{n['group']}'")
        for s in n.get("systems", []):
            if s not in sys_ids:
                rep.err("map-1", w + "/systems", f"node {n['id']}: unknown system '{s}'")
    for i, e in enumerate(edges):
        for end in ("from", "to"):
            if e[end] not in node_ix:
                rep.err("map-1", f"{where}#/edges/{i}/{end}", f"unknown node '{e[end]}'")
    for key, arr in (("gaps", gaps), ("clarifications", clars)):
        for i, c in enumerate(arr):
            for nid in c["nodes"]:
                if nid not in node_ix:
                    rep.err("map-1", f"{where}#/{key}/{i}/nodes", f"{c['id']}: unknown node '{nid}'")
    if len(rep.errors()) > n0:
        return False
    # map-2: groups
    if groups:
        for i, n in enumerate(nodes):
            if "group" not in n:
                rep.err("map-2", f"{where}#/nodes/{i}", f"node {n['id']} names no group; when a map has groups, every node names one")
        for g in groups:
            if not any(n.get("group") == g["id"] for n in nodes):
                rep.err("map-2", f"{where}#/groups/{group_ix[g['id']]}", f"group {g['id']} holds no node")
        seq = [group_ix.get(n.get("group"), -1) for n in nodes]
        if seq != sorted(seq):
            rep.err("map-2", f"{where}#/nodes", "nodes are not listed group by group, in groups[] order", "list each group's nodes together, in flow order")
    ids = {x["id"] for arr in (groups, nodes, gaps, clars) for x in arr}
    ctx = Ctx("process-map", idx, schemas, ids)
    # citations
    lane_evs = {l["id"]: eval_cites(rep, f"{where}#/lanes/{i}/cite", l.get("cite"), ctx) for i, l in enumerate(lanes)}
    sys_evs = {s["id"]: eval_cites(rep, f"{where}#/systems/{i}/cite", s["cite"], ctx) for i, s in enumerate(systems)}
    node_evs = {n["id"]: eval_cites(rep, f"{where}#/nodes/{i}/cite", n["cite"], ctx) for i, n in enumerate(nodes)}
    card_evs = {}
    for key, arr, fields in (("gaps", gaps, ("title", "text")), ("clarifications", clars, ("title", "shows", "ask"))):
        for i, c in enumerate(arr):
            w = f"{where}#/{key}/{i}"
            evs = eval_cites(rep, w + "/cite", c["cite"], ctx)
            for f in fields:
                evs += markers(rep, f"{w}/{f}", c[f], ctx)
            card_evs[c["id"]] = evs
    every = pool([e for d in (lane_evs, sys_evs, node_evs, card_evs) for evs in d.values() for e in evs])
    # lanes (map-3)
    for i, l in enumerate(lanes):
        w, evs = f"{where}#/lanes/{i}", lane_evs[l["id"]]
        check_category(rep, w, "process-map", "lane", evs)
        if not any(n["lane"] == l["id"] for n in nodes) and not any(e.type == "grounded" for e in evs):
            rep.err("map-3", w, f"lane {l['id']} holds no step, so it needs a grounded citation for the role")
        check_prose(rep, w + "/label", l["label"], pool(evs) if evs else every, ctx, "label")
    for i, g in enumerate(groups):
        check_prose(rep, f"{where}#/groups/{i}/label", g["label"], every, ctx, "label")
    # systems (map-8)
    for i, s in enumerate(systems):
        w, evs = f"{where}#/systems/{i}", sys_evs[s["id"]]
        check_category(rep, w, "process-map", "system", evs)
        if evs and not any(fold_ci(s["label"]) in fold_ci(r["text"]) for r in pool(evs)):
            rep.err("map-8", w, f"system {s['id']}: '{s['label']}' does not occur in a record it cites", "cite the record that names the system")
        check_prose(rep, w + "/label", s["label"], pool(evs), ctx, "label")
    # nodes (map-7)
    rmax = RULES["cardReadingMax"]
    for i, n in enumerate(nodes):
        w, evs = f"{where}#/nodes/{i}", node_evs[n["id"]]
        check_category(rep, w, "process-map", "node." + n["state"], evs)
        inf = [e for e in evs if e.type == "inferred"]
        if n["state"] == "inferred" and inf and len(inf[0].cite["reading"]) > rmax:
            rep.err("map-7", w, f"node {n['id']}: the reading printed on the card is {len(inf[0].cite['reading'])} characters; the card prints at most {rmax}")
        for f in ("title", "owner"):
            if f in n:
                check_prose(rep, f"{w}/{f}", n[f], pool(evs), ctx, "label")
    # edges (map-4, map-5)
    seen_e = set()
    for i, e in enumerate(edges):
        w, kind, a = f"{where}#/edges/{i}", e.get("kind", "flow"), node_by[e["from"]]
        if e["from"] == e["to"]:
            rep.err("map-5", w, "an edge joins two different nodes")
        if (e["from"], e["to"]) in seen_e:
            rep.err("map-5", w, f"edge {e['from']} -> {e['to']} is listed twice")
        seen_e.add((e["from"], e["to"]))
        if kind == "conditional" and a.get("kind") != "decision":
            rep.err("map-4", w, f"a conditional edge leaves a decision; {e['from']} is a step")
        if kind != "conditional" and a.get("kind") == "decision":
            rep.err("map-4", w, f"an edge leaving decision {e['from']} is conditional, with its branch label")
        if "label" in e:
            check_prose(rep, w + "/label", e["label"], pool(node_evs[e["from"]]), ctx, "label")
    for d in [n for n in nodes if n.get("kind") == "decision"]:
        labels = [e["label"] for e in edges if e["from"] == d["id"] and e.get("kind") == "conditional"]
        if len(labels) < 2 or len(set(labels)) != len(labels):
            rep.err("map-4", f"{where}#/nodes/{node_ix[d['id']]}", f"decision {d['id']} needs two or more conditional branches with different labels")
    # cards (map-6)
    in_cards = {}
    for i, g in enumerate(gaps):
        for nid in g["nodes"]:
            in_cards.setdefault(nid, []).append(g["id"])
            if node_by[nid]["state"] != "gap":
                rep.err("map-6", f"{where}#/gaps/{i}/nodes", f"{g['id']} lists {nid}, which is not a gap-state step")
    for n in nodes:
        if n["state"] == "gap" and len(in_cards.get(n["id"], [])) != 1:
            rep.err("map-6", f"{where}#/nodes/{node_ix[n['id']]}", f"gap step {n['id']} is listed by {len(in_cards.get(n['id'], []))} gap cards; it needs exactly one")
    for key, arr, fields in (("gaps", gaps, ("title", "text")), ("clarifications", clars, ("title", "shows", "ask"))):
        for i, c in enumerate(arr):
            w, evs = f"{where}#/{key}/{i}", card_evs[c["id"]]
            check_category(rep, w, "process-map", "gap" if key == "gaps" else "clarification", evs)
            for f in fields:
                check_prose(rep, f"{w}/{f}", c[f], pool(evs), ctx, "claim", brackets="cite")
    # layout (map-10)
    _, ncols, bad = layout(data)
    for nid, hint, derived in bad:
        rep.err("map-10", f"{where}#/nodes/{node_ix[nid]}/col", f"node {nid}: col {hint} is left of its derived column {derived}",
                "a col hint only pushes a node right; remove it or raise it")
    if ncols > MAX_COLUMNS:
        rep.err("map-10", f"{where}#/nodes", f"the board needs {ncols} columns; it holds at most {MAX_COLUMNS}", "split the process into several maps")
    # meta
    m = data["meta"]
    if "subtitle" in m:
        check_prose(rep, f"{where}#/meta/subtitle", m["subtitle"], [], ctx, "claim", tokens=True)
    for f in ("kicker", "title", "footer"):
        if f in m:
            check_prose(rep, f"{where}#/meta/{f}", m[f], every, ctx, "label")
    return data if len(rep.errors()) == n0 else False


# ================================================================== AI layer

def check_ai(rep, path, data, idx, schemas, maps):
    where = f"process-map-ai-opportunity/{path.name}"
    if not schema_ok(rep, where, data, "ai-layer.schema.json", schemas):
        return
    base = maps.get(data["base"])
    if base is None:
        rep.err("ai-1", where + "#/base", f"base '{data['base']}' is not a map in process-map/", "name a file in process-map/ without .json")
        return
    if base is False:
        rep.err("ai-1", where + "#/base", f"base '{data['base']}' does not pass its checks, so its layer cannot be checked")
        return
    node_by = {n["id"]: n for n in base["nodes"]}
    group_ids = {g["id"] for g in base.get("groups", [])}
    sys_ids = {s["id"] for s in base.get("systems", [])}
    ids = {x["id"] for k in ("groups", "nodes", "gaps", "clarifications") for x in base.get(k, [])} | {it["id"] for it in data["ai"]}
    ctx = Ctx("process-map-ai-opportunity", idx, schemas, ids)
    aid = [it["id"] for it in data["ai"]]
    if aid != sorted(aid) or len(set(aid)) != len(aid):
        rep.err("ai-2", where + "#/ai", "items are unique and sorted by id")
    every = []
    for i, it in enumerate(data["ai"]):
        w = f"{where}#/ai/{i}"
        nodes, groups = it.get("nodes", []), it.get("groups", [])
        if not nodes and groups == []:
            rep.err("ai-2", w, f"{it['id']} touches no step and no view", "list nodes, groups, or groups: \"all\"")
        if groups == "all" and nodes:
            rep.err("ai-2", w, f"{it['id']} is across all views, so it lists no steps")
        if groups and len(group_ids) < 2:
            rep.err("ai-2", w + "/groups", f"{it['id']}: view items need a base with two or more groups (the band they mark)")
        for nid in nodes:
            if nid not in node_by:
                rep.err("ai-2", w + "/nodes", f"{it['id']}: node {nid} is not in base {data['base']}")
            elif node_by[nid].get("kind", "step") != "step":
                rep.err("ai-2", w + "/nodes", f"{it['id']}: {nid} is a decision; AI items mark steps")
            elif isinstance(groups, list) and node_by[nid].get("group") in groups:
                rep.err("ai-2", w + "/nodes", f"{it['id']}: {nid} is inside view {node_by[nid]['group']}, which the item already lists")
        for gid in (groups if isinstance(groups, list) else []):
            if gid not in group_ids:
                rep.err("ai-2", w + "/groups", f"{it['id']}: group {gid} is not in base {data['base']}")
        evs = eval_cites(rep, w + "/cite", it["cite"], ctx)
        every += pool(evs)
        check_category(rep, w, "process-map-ai-opportunity", "ai." + it["origin"], evs)
        recs = pool(evs)
        check_prose(rep, w + "/title", it["title"], recs, ctx, "design")
        check_prose(rep, w + "/does", it["does"], recs, ctx, "design")
        ag = it.get("agentic")
        if ag:
            for j, d in enumerate(ag["decides"]):
                if d["after"] > len(ag["steps"]):
                    rep.err("ai-4", f"{w}/agentic/decides/{j}/after", f"step {d['after']} does not exist (the plan has {len(ag['steps'])} steps)")
                check_prose(rep, f"{w}/agentic/decides/{j}/who", d["who"], recs, ctx, "label")
                check_prose(rep, f"{w}/agentic/decides/{j}/what", d["what"], recs, ctx, "design")
            for s in ag["systems"]:
                if s not in sys_ids:
                    rep.err("ai-4", f"{w}/agentic/systems", f"system {s} is not in base {data['base']}")
            for f in ("trigger", "logging"):
                check_prose(rep, f"{w}/agentic/{f}", ag[f], recs, ctx, "design")
            for j, s in enumerate(ag["steps"]):
                check_prose(rep, f"{w}/agentic/steps/{j}", s, recs, ctx, "design")
    for f in ("kicker", "title"):
        if f in data["meta"]:
            check_prose(rep, f"{where}#/meta/{f}", data["meta"][f], every, ctx, "label")
    if "subtitle" in data["meta"]:
        check_prose(rep, f"{where}#/meta/subtitle", data["meta"]["subtitle"], every, ctx, "design")


# ================================================================== document (parsed by build_doc.py itself)

MARK = re.compile(r"\x01(\d+)\x01")
HOLD = re.compile(r"\x00(\d+)\x00")
ABBREV = re.compile(r"(?:^|\s)(?:e\.g|i\.e|etc|vs)\.$", re.I)


class DocError(Exception):
    pass


class LineFinder:
    """Best-effort line numbers for the builder's blocks, which carry none for lists, tables and quotes."""
    def __init__(self, lines):
        self.lines, self.cur = lines, 0

    def __call__(self, text):
        probe = norm_ws(re.split(r" \| ", text)[0])[:16]
        for k in range(self.cur, len(self.lines)):
            if probe and probe in self.lines[k][1]:
                self.cur = k
                return self.lines[k][0]
        return self.lines[self.cur][0] if self.lines else 1


def doc_items(blocks, find, top=True):
    """The builder's blocks as ('claim', units) | ('prov', line, text) | ('exempt', units, examples?) | ('break',)."""
    items, i = [], 0
    if top and blocks and blocks[0][0] == "h" and blocks[0][1] == 1:
        units, i = [(find(blocks[0][2]), blocks[0][2])], 1
        while i < len(blocks) and blocks[i][0] == "quote" and i <= 2:
            units.append((find(blocks[i][1]), blocks[i][1]))
            i += 1
        items += [("exempt", units, False), ("break",)]
    for b in blocks[i:]:
        k = b[0]
        if k == "h":
            if b[1] == 1:
                raise DocError("only one # title is allowed, at the top of the document")
            items.append(("exempt", [(find(b[2]), b[2])], False))
        elif k == "p":
            items.append(("prov", b[3], b[1]) if BD.PROV.match(b[1]) else ("claim", [(b[3], b[1])]))
        elif k == "quote":
            items.append(("claim", [(find(b[1]), b[1])]))
        elif k in ("ul", "ol"):
            units = []
            for text, kids in b[1]:
                units.append((find(text), text))
                for kid in kids:
                    if kid[0] == "ul":
                        units += [(find(t), t) for t in kid[1]]
                    elif kid[0] == "p":
                        units.append((find(kid[1]), kid[1]))
            items.append(("claim", units))
        elif k == "table":
            items.append(("exempt", [(find(" | ".join(b[1])), " | ".join(b[1]))], False))
            items.append(("claim", [(find(" | ".join(r)), " | ".join(r)) for r in b[3]]))
        elif k == "dir":
            name, arg, sub = b[1], b[2], BD.parse_blocks(b[3])
            if name == "columns":
                items += [("break",)] + doc_items([x for x in sub if x[0] != "sep"], find, top=False) + [("break",)]
            else:
                units = ([(b[4], arg)] if arg else []) + exempt_texts(sub, find)
                items += [("exempt", units, name == "examples"), ("break",)]
        elif k == "sep":
            raise DocError("+++ is only used inside :::columns or :::examples")
        else:
            items.append(("break",))
    return items


def exempt_texts(blocks, find):
    out = []
    for b in blocks:
        texts = {"h": lambda: [b[2]], "p": lambda: [b[1]], "quote": lambda: [b[1]], "sep": lambda: [b[1]],
                 "ul": lambda: [t for text, kids in b[1] for t in [text] + BD.kid_texts(kids)],
                 "ol": lambda: [t for text, kids in b[1] for t in [text] + BD.kid_texts(kids)],
                 "table": lambda: [" | ".join(b[1])] + [" | ".join(r) for r in b[3]]}.get(b[0], lambda: [])()
        out += [(find(t), t) for t in texts if t]
    return out


def doc_inline(rep, w, text, idx):
    """The builder's inline rules, in its order: code spans are held (their text stays, but never cites), comments
    go, escapes are literal, links become their text, and a bracket is a citation when it names a record file.
    Returns the text with each citation bracket replaced by \\x01k\\x01, and the bracket refs."""
    holds, cites = [], []

    def hold(s):
        holds.append(s)
        return f"\x00{len(holds) - 1}\x00"

    t = re.sub(r"(`+)(.+?)\1", lambda m: hold("`" + m.group(2).strip() + "`"), text)
    t = re.sub(r"<!--.*?-->", "", t)
    t = re.sub(r"\\([\\`*\[\]_#+.!|-])", lambda m: hold("\\" + m.group(1) if m.group(1) in "[]" else m.group(1)), t)
    t = LINK.sub(lambda m: m.group(1), t)

    def br(m):
        refs = parse_bracket(m.group(1))
        if refs and any(r["source"] in idx.sources for r in refs):
            cites.append(refs)
            return f"\x01{len(cites) - 1}\x01"
        rep.err("prose-1", w, f"[{m.group(1)}] is not a citation", "brackets hold 'SRC locator; SRC locator'; write \\[ for a literal bracket")
        return hold(m.group(0))

    t = BRACKET.sub(br, t)
    return t, cites, holds


def sentences(t):
    """Split on . ? ! before white space, outside “quotes”; a bold lead-in (**Approve.**) belongs to the sentence
    after it, and a fragment with no words (a trailing bracket) joins the sentence before it."""
    lead = re.match(r"^\*\*(.+?)\*\*", t)
    if lead:
        t = re.sub(r"[.?!]", "\x02", lead.group(1)) + t[lead.end():]
    t = t.replace("**", "")
    out, cur, inq = [], "", False
    for k, ch in enumerate(t):
        cur += ch
        if ch == "“":
            inq = True
        elif ch == "”":
            inq = False
        elif ch in ".?!" and not inq and (k + 1 == len(t) or t[k + 1].isspace()) and not ABBREV.search(cur):
            out.append(cur)
            cur = ""
    if cur.strip():
        out.append(cur)
    merged = []
    for s in out:
        if merged and not re.search(r"[A-Za-z0-9]", MARK.sub("", HOLD.sub("x", s)).replace("\x02", "")):
            merged[-1] += s
        else:
            merged.append(s)
    return [s.replace("\x02", ".") for s in merged]


def restore(s, holds):
    while HOLD.search(s):
        s = HOLD.sub(lambda m: holds[int(m.group(1))], s)
    return s


def prov_line(rep, where, text, ctx):
    text = re.sub(r"<!--.*?-->", "", text).strip()
    for word, rx in DOC_LINES.items():
        if not text.startswith(word + " · "):
            continue
        m = rx.match(text)
        forms = {"Grounded": "Grounded · SRC locator; SRC locator", "Inferred": "Inferred · <reading> · from SRC locator; SRC locator",
                 "Gap": "Gap · not in SRC locator; SRC: “<needle>”"}
        refs = parse_ref_list(m.group(2 if word == "Inferred" else 1)) if m else None
        if refs is None:
            rep.err("doc-2", where, f"a {word} line reads '{forms[word]}'")
            return []
        cites = (refs if word == "Grounded" else [{"type": "inferred", "reading": m.group(1).strip(), "from": refs}] if word == "Inferred"
                 else [{"type": "absent", "needle": m.group(2), "in": refs}])
        bad = False
        for c in cites:
            for p, msg in ctx.schemas.validate(c, "citation.schema.json"):
                rep.err("doc-2", where, f"the {word} line's {'/'.join(map(str, p)) or 'citation'} {msg}", f"it reads '{forms[word]}'")
                bad = True
        return [] if bad else eval_cites(rep, where, cites, ctx)
    return []


def parse_ref_list(text):
    refs = []
    for part in text.split(";"):
        part = part.strip()
        if part.startswith("[") and part.endswith("]"):
            part = part[1:-1].strip()
        m = BRACKET_PART.match(part)
        if not m:
            return None
        refs.append({"source": m.group(1)} if not m.group(2) else {"source": m.group(1), "locator": m.group(2).strip()})
    return refs


def front_matter(rep, where, lines):
    fm, start = {}, 0
    if lines and lines[0][1].strip() == "---":
        k = 1
        while k < len(lines) and lines[k][1].strip() != "---":
            m = re.match(r"^([A-Za-z]+)\s*:\s*(.*?)\s*$", lines[k][1])
            if not m:
                rep.err("doc-1", f"{where}:{k + 1}", "front matter lines read 'key: value'")
            elif m.group(1).lower() in fm:
                rep.err("doc-1", f"{where}:{k + 1}", f"the front matter key '{m.group(1).lower()}' is written twice", "keep one")
            else:
                fm[m.group(1).lower()] = m.group(2).strip("\"'")
            k += 1
        if k >= len(lines):
            rep.err("doc-1", f"{where}:1", "front matter starts with --- but is never closed")
            return None, []
        start = k + 1
    return fm, lines[start:]


def check_document(rep, path, idx, schemas):
    where = f"document/{path.name}"
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        rep.err("doc-1", where, "is not UTF-8 text")
        return
    lines = list(enumerate(text.splitlines(), start=1))
    fm, body = front_matter(rep, where, lines)
    if fm is None:
        return
    for p, msg in schemas.validate(fm, "document-front-matter.schema.json"):
        rep.err("doc-1", f"{where}#/front-matter" + ptr(*p), msg)
    BD.WARNINGS.clear()
    find = LineFinder(body)
    try:
        items = doc_items(BD.parse_blocks(body), find)
    except (BD.BuildError, DocError) as e:
        rep.err("doc-1", where, f"build_doc.py stops: {e}")
        return
    for msg in BD.WARNINGS:
        rep.err("doc-1", where, f"build_doc.py --strict stops: {msg}")
    BD.WARNINGS.clear()
    ctx = Ctx("document", idx, schemas, doc=True)
    every, i = [], 0
    while i < len(items):
        it = items[i]
        if it[0] == "prov":
            rep.err("doc-2", f"{where}:{it[1]}", "a provenance line follows the paragraph, list or table it supports",
                    "put it straight after that block")
            i += 1
            continue
        if it[0] != "claim":
            i += 1
            continue
        j, line_evs = i + 1, []
        while j < len(items) and items[j][0] == "prov":
            line_evs += prov_line(rep, f"{where}:{items[j][1]}", items[j][2], ctx)
            j += 1
        every += pool(line_evs)
        for uln, utext in it[1]:
            w = f"{where}:{uln}"
            if BD.IMAGE.search(utext):
                rep.err("doc-1", w, "an image sits outside :::examples", "put it in an :::examples item, or use template.html")
            t, cites, holds = doc_inline(rep, w, utext, idx)
            for s in sentences(t):
                evs = [e for k in MARK.findall(s) for e in eval_cites(rep, w, cites[int(k)], ctx)]
                clean = restore(MARK.sub(" ", s), holds)
                every += pool(evs)
                if not evs and not line_evs:
                    rep.err("doc-3", w, f"no citation for “{norm_ws(clean)[:60]}”",
                            "add [SRC locator] to the sentence, put a Grounded / Inferred / Gap line after its block, or move it into a :::callout")
                    continue
                check_category(rep, w, "document", "sentence", evs + line_evs)
                check_prose(rep, w, clean, pool(evs + line_evs), ctx, "claim", brackets="cite")
        i = j
    for it in items:
        if it[0] != "exempt":
            continue
        for uln, utext in it[1]:
            w = f"{where}:{uln}"
            if BD.IMAGE.search(utext) and not it[2]:
                rep.err("doc-1", w, "an image sits outside :::examples", "put it in an :::examples item, or use template.html")
            t, cites, holds = doc_inline(rep, w, BD.IMAGE.sub(" ", utext), idx)
            for k in range(len(cites)):
                eval_cites(rep, w, cites[k], ctx)
            check_prose(rep, w, restore(MARK.sub(" ", t), holds), every, ctx, "claim", brackets="cite")


def doc_mode(text):
    """The front matter's mode: a4 (the default) or screen. bs.py passes it to build_doc.py as --a4 or --screen."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            m = re.match(r"^mode\s*:\s*(.*?)\s*$", line, re.I)
            if m:
                return m.group(1).strip("\"'")
    return "a4"


def strip_mode(text):
    """The document as build_doc.py receives it: the front matter's mode line removed."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for k in range(1, len(lines)):
            if lines[k].strip() == "---":
                break
            if re.match(r"^mode\s*:", lines[k], re.I):
                return "\n".join(lines[:k] + lines[k + 1:])
    return text


def sources_map(idx):
    """What bs.py build passes to build_doc.py --sources: every record file, in id order."""
    out = {}
    for sid in sorted(idx.sources):
        h = idx.sources[sid].header
        note = " · ".join(x for x in (h.get("detail"), domain(h.get("url"))) if x)
        out[sid] = {"name": h["title"], **({"note": note} if note else {})}
    return out


def domain(url):
    m = re.match(r"^https?://([^/:?#]+)", url or "")
    return m.group(1) if m else ""


# ================================================================== proposal

REQUIRED_SLIDES = ["cover", "situation", "focus", "deliverables", "process", "needs", "commercials"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CLAIM_FIELDS = {"points": ("heading", "text"), "stats": ("value", "label"), "evidence": ("text",)}


def print_date(iso):
    """'2026-10-22' printed as '22 Oct 2026'. check reports a date that is not on the calendar (schema-1), so
    one never reaches a page; it is returned unchanged here so that status and check never crash on it."""
    if not real_date(iso):
        return iso
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


def deck_claims(data):
    out = []
    for si, sl in enumerate(data.get("slides", []) if isinstance(data.get("slides"), list) else []):
        if not isinstance(sl, dict):
            continue
        if sl.get("type") == "situation":
            out += [(f"#/slides/{si}/points/{j}", c, "points") for j, c in enumerate(sl.get("points", []))]
            out += [(f"#/slides/{si}/stats/{j}", c, "stats") for j, c in enumerate(sl.get("stats", []))]
        if sl.get("type") == "focus":
            out += [(f"#/slides/{si}/options/{j}/evidence", o["evidence"], "evidence")
                    for j, o in enumerate(sl.get("options", [])) if isinstance(o, dict) and "evidence" in o]
    return [x for x in out if isinstance(x[1], dict)]


def register(data, idx):
    """The deck's sources[]: one row per cited source, in first-cited order, from its record header."""
    rows, seen = [], set()
    for _, c, _ in deck_claims(data):
        for ref in c.get("cite", []) if isinstance(c.get("cite"), list) else []:
            sid = ref.get("source") if isinstance(ref, dict) else None
            if sid in idx.sources and sid not in seen:
                seen.add(sid)
                h = idx.sources[sid].header
                row = {"id": sid, "title": h["title"], "kind": KINDS[h["kind"]]["deckKind"], "date": print_date(h["captured"])}
                row.update({k: h[k] for k in ("detail", "url") if k in h})
                rows.append(row)
    return rows


def with_register(data, idx):
    """The deck build_proposal.py receives: the authored deck with its register written in, after meta."""
    return {"meta": data["meta"], "sources": register(data, idx), **{k: v for k, v in data.items() if k != "meta"}}


def deck_hint(p, msg):
    if p and p[-1] == "locator" and "characters" in msg:
        return "a deck locator is at most 20 characters: cite a row (Steps row 7), a shorter span, or the whole source"
    return ""


def check_proposal(rep, path, data, idx, schemas):
    where = f"proposal/{path.name}"
    if isinstance(data, dict) and "sources" in data:
        rep.err("deck-2", where + "#/sources", "the authored deck holds no sources[]", "delete it: bs.py writes the register from the record headers")
    merged = dict(data, sources=register(data, idx)) if isinstance(data, dict) else data
    if not schema_ok(rep, where, merged, "proposal.schema.json", schemas, deck_hint):
        return
    if not real_date(data["meta"].get("date", "2000-01-01")):
        rep.err("schema-1", where + "#/meta/date", f"{data['meta']['date']} is not a calendar date", "write the date as YYYY-MM-DD")
    ctx = Ctx("proposal", idx, schemas, whole_ok=True)
    for w, c, kind in deck_claims(data):
        w = where + w
        if "cite" in c and "to_confirm" in c:
            rep.err("deck-3", w, "a claim carries cite or to_confirm, not both", "keep cite when a record supports it")
        evs = eval_cites(rep, w + "/cite", c.get("cite"), ctx)
        check_category(rep, w, "proposal", "claim", evs, to_confirm="to_confirm" in c)
        if "cite" in c:
            for f in CLAIM_FIELDS[kind]:
                check_prose(rep, f"{w}/{f}", c[f], pool(evs), ctx, "deck", brackets="placeholder")
    types = [s["type"] for s in data["slides"]]
    if types[0] != "cover":
        rep.err("deck-1", f"{where}#/slides/0", "the cover comes first")
    for t in REQUIRED_SLIDES:
        if t not in types:
            rep.err("deck-1", f"{where}#/slides", f"a {t} slide is required")
    if types.count("sources") > 1 or ("sources" in types and types[-1] != "sources"):
        rep.err("deck-1", f"{where}#/slides", "one sources slide, at the end")


# ================================================================== workspace check

def check(ws, builtin=False):
    """Every rule of FORMATS.md section 6 except the build rules, in its order: records, maps, AI layers after their
    base, then documents and decks."""
    ws = pathlib.Path(ws)
    if not (ws / "inputs").is_dir():
        raise SystemExit(f"cannot run: {ws} has no inputs/ folder, so it is not a workspace")
    schemas, rep = SchemaSet(builtin), Report()
    rep.engine = schemas.engine
    for p in sorted(ws.iterdir()):
        if not p.name.startswith(".") and (p.name not in WORKSPACE_DIRS or not p.is_dir()):
            rep.err("ws-2", p.name, "is not a workspace folder", "the folders are: " + ", ".join(WORKSPACE_DIRS))
    idx = check_records(ws, rep, schemas)
    named, shas = {}, {}
    for p in sorted((ws / "records").glob("*.json")) if (ws / "records").is_dir() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(d, dict) and isinstance(d.get("file"), str):
            named[d["file"]] = p.name
            shas[d.get("sha256")] = d["file"]
    for f in sorted((ws / "inputs").rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(ws).as_posix()
        if any(part.startswith(".") for part in f.relative_to(ws / "inputs").parts):
            rep.err("ws-2", rel, "a hidden file in inputs/ is never converted", "remove it if it is system noise; give real material a visible name")
            rep.inputs.append((rel, "HIDDEN", ""))
        elif rel in named:
            rep.inputs.append((rel, "CONVERTED", named[rel][:-5]))
            continue
        elif f.suffix.lower() in RULES["containers"]:
            rep.err("ws-1", rel, "is a container: NOT CONVERTED", f"save its members in inputs/{f.stem}/ and keep the {f.suffix} outside the workspace")
            rep.inputs.append((rel, "NOT CONVERTED", "a container: unpack it"))
        else:
            sha = hashlib.sha256(f.read_bytes()).hexdigest()
            if sha in shas:
                rep.warn("ws-1", rel, f"is a byte-identical copy of {shas[sha]}: DUPLICATE, nothing to convert")
                rep.inputs.append((rel, "DUPLICATE", shas[sha]))
            else:
                rep.err("ws-1", rel, "has no record file: NOT CONVERTED", "convert it (convert.js) into records/<ID>.json")
                rep.inputs.append((rel, "NOT CONVERTED", ""))
    maps = {}
    for sec in SECTIONS:
        d = ws / sec
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.name.startswith("."):
                continue
            if p.suffix != EXTS[sec] or not FILE_RE.match(p.stem) or not p.is_file():
                rep.err("ws-2", f"{sec}/{p.name}", f"a {sec} file is <name>{EXTS[sec]}, the name in lower case with hyphens")
                continue
            if sec == "document":
                check_document(rep, p, idx, schemas)
                continue
            data = load_json(rep, f"{sec}/{p.name}", p)
            if data is None:
                if sec == "process-map":
                    maps[p.stem] = False
                continue
            if sec == "process-map":
                maps[p.stem] = check_map(rep, p, data, idx, schemas)
            elif sec == AI_SECTION:
                check_ai(rep, p, data, idx, schemas, maps)   # every map is checked by now: SECTIONS lists them first
            else:
                check_proposal(rep, p, data, idx, schemas)
    rep.maps, rep.idx = maps, idx
    return rep


def section_files(ws):
    """[(section, name, path)] for every section file whose name the check accepts, in check order."""
    out = []
    for sec in SECTIONS:
        d = ws / sec
        for p in sorted(d.iterdir()) if d.is_dir() else []:
            if not p.name.startswith(".") and p.is_file() and p.suffix == EXTS[sec] and FILE_RE.match(p.stem):
                out.append((sec, p.stem, p))
    return out


# ================================================================== the git guard

def guard(ws):
    """Exit 2 on a workspace that git tracks: client material never enters git. Only the toolkit's examples/ is
    tracked by design. .gitignore can be edited, so this is the second guard."""
    ws = pathlib.Path(ws).resolve()
    if ws == (HERE / "examples").resolve():
        return
    try:
        r = subprocess.run(["git", "-C", str(ws), "ls-files", "-z", "--", "."], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return   # no git, so nothing is tracked
    tracked = [t for t in r.stdout.split(b"\0") if t] if r.returncode == 0 else []
    if tracked:
        raise SystemExit(f"cannot run: git tracks {len(tracked)} file(s) in {ws}; a workspace never enters git (only examples/ does). "
                         "Untrack it with git rm -r --cached, keep it in work/, and check .gitignore")


# ================================================================== convert

def record_json(data):
    """A record file as the examples write it: the header one field per line, then one record per line."""
    head = ",\n".join(f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items() if k != "records")
    recs = ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in data["records"])
    return "{\n" + head + ',\n "records": [\n' + recs + "\n ]\n}\n"


def input_rel(ws, given):
    """The input as the record names it, 'inputs/…', from a path relative to the workspace or to here."""
    if given.startswith("inputs/") and (ws / given).is_file():
        return given
    p = pathlib.Path(given).resolve()
    inputs = (ws / "inputs").resolve()
    if p.is_file() and inputs in p.parents:
        return "inputs/" + p.relative_to(inputs).as_posix()
    raise SystemExit(f"cannot run: {given} is not a file in {ws}/inputs/")


def convert(ws, rel, a):
    """Write records/ID.json from one input. The flags are the whole header."""
    load()
    ws = pathlib.Path(ws)
    rel = input_rel(ws, rel)
    f = ws / rel
    if a.kind not in KINDS:
        raise SystemExit(f"cannot run: kind is one of {', '.join(KINDS)}")
    if not real_date(a.captured):
        raise SystemExit(f"cannot run: --captured {a.captured} is not a calendar date; write it as YYYY-MM-DD, e.g. 2026-10-22")
    out = ws / "records" / f"{a.id}.json"
    if out.exists():
        raise SystemExit(f"cannot run: {out} exists; a record file is never rewritten")
    for p in sorted((ws / "records").glob("*.json")) if (ws / "records").is_dir() else []:
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("file") == rel:
                raise SystemExit(f"cannot run: {rel} is already converted as records/{p.name}; one input becomes one record file")
        except (ValueError, UnicodeDecodeError, AttributeError):
            continue
    try:
        units = extract_units(a.kind, f)
    except ReadError as e:
        raise SystemExit(f"cannot run: {rel} {e}")
    if units is None:
        raise SystemExit(f"cannot run: no reader for {f.suffix} as {a.kind}; the converter agent converts it into this form")
    data = {"id": a.id, "title": a.title, "kind": a.kind, "captured": a.captured}
    data.update({k: v for k, v in (("detail", a.detail), ("url", a.url)) if v})
    if a.legacy:
        data["legacy"] = True
    data.update({"file": rel, "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "coverage": "partial" if a.partial else "complete",
                 "records": [dict({"locator": loc, "text": text}, **({"context": ctx} if ctx else {})) for loc, text, ctx in units]})
    errs = SchemaSet().validate(data, "source-record.schema.json")
    if errs:
        raise SystemExit("cannot run: " + "; ".join(f"{ptr(*p)} {m}" for p, m in errs[:5]))
    out.parent.mkdir(exist_ok=True)
    out.write_text(record_json(data), encoding="utf-8")
    print(f"wrote records/{a.id}.json: {len(units)} records from {rel}")
    return 0


# ================================================================== build: what the builders receive

def prepare(ws, outdir, builtin=False):
    """build --prepare: write each document's copy without its mode line and its sources map, and each deck with its
    register, into OUTDIR, and print the builder commands, which run from the toolkit folder. build hands the
    builders exactly these files."""
    ws, outdir = pathlib.Path(ws).resolve(), pathlib.Path(outdir).resolve()   # the commands run from the toolkit folder
    rep = check(ws, builtin)
    if rep.errors():
        rep.print()
        print("bs.py check fails, so nothing is prepared")
        return 1
    for sec, name, p in section_files(ws):
        if sec == "document":
            (outdir / "document").mkdir(parents=True, exist_ok=True)
            text = p.read_text(encoding="utf-8")
            (outdir / "document" / p.name).write_text(strip_mode(text), encoding="utf-8")
            sm = outdir / "document" / f"{name}.sources.json"
            sm.write_text(json.dumps(sources_map(rep.idx), ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"python3 {BUILDERS['document']} {outdir}/document/{p.name} {ws}/out/document/{name}.html --{doc_mode(text)} --sources {sm} --strict")
        elif sec == "proposal":
            (outdir / "proposal").mkdir(parents=True, exist_ok=True)
            data = json.loads(p.read_text(encoding="utf-8"))
            (outdir / "proposal" / p.name).write_text(json.dumps(with_register(data, rep.idx), ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"python3 {BUILDERS['proposal']} {outdir}/proposal/{p.name} {ws}/out/proposal/{name}.html --strict")
    return 0


BUILDERS = {"process-map": "design-system/process-map/build_map.py",
            AI_SECTION: "design-system/process-map/build_map.py",
            "document": "design-system/document/build_doc.py",
            "proposal": "design-system/proposal/build_proposal.py",
            RECEIVED: "design-system/data-received/build_received.py"}
DESIGN_FOLDERS = {"process-map": ["process-map"], AI_SECTION: ["process-map", AI_SECTION],
                  "document": ["document"], "proposal": ["proposal"], RECEIVED: [RECEIVED]}
# Generated files inside design-system/ (gitignored) and folders that never feed a page: left out of the build hash.
NOT_SOURCES = {"specimen.html", "example-a4.html", "example-screen.html", "example-proposal.html", "proposal/template.html"}
NOT_SOURCE_DIRS = {"__pycache__", "qa", "previews"}


def page_out(ws, section, name):
    return ws / "out" / f"{RECEIVED}.html" if section == RECEIVED else ws / "out" / section / f"{name}.html"


def page_label(section, name):
    return f"out/{RECEIVED}.html" if section == RECEIVED else f"out/{section}/{name}.html"


def design_files(section):
    """The design-system files a section's page is made from: its folders, less docs and generated pages."""
    out = []
    for folder in DESIGN_FOLDERS[section]:
        root = HERE / "design-system" / folder
        for p in sorted(root.rglob("*")) if root.is_dir() else []:
            rel = p.relative_to(root)
            if (not p.is_file() or any(x.startswith(".") or x in NOT_SOURCE_DIRS for x in rel.parts[:-1]) or p.name.startswith(".")
                    or p.suffix in (".md", ".pyc") or p.name in NOT_SOURCES or f"{folder}/{rel.as_posix()}" in NOT_SOURCES):
                continue
            out.append(p)
    return out


def ai_base(ws, name):
    return json.loads((ws / AI_SECTION / f"{name}.json").read_text(encoding="utf-8"))["base"]


def page_evs(ws, rep, section, name):
    """Every citation the page prints: the file's own, and on an AI page its base map's too."""
    evs = list(rep.cited.get(f"{section}/{name}{EXTS[section]}", []))
    if section == AI_SECTION:
        evs += rep.cited.get(f"process-map/{ai_base(ws, name)}.json", [])
    return evs


def page_hash(ws, rep, section, name):
    """build-3: the hash of the source file, its records, a document's mode and design-system/ (plus
    formats/citation-types.json, whose kind labels every page prints). The Original data received page hashes
    inputs/, records/ and every section file instead of one source file."""
    h = hashlib.sha256()

    def add(label, data):
        data = data.encode("utf-8") if isinstance(data, str) else data
        h.update(f"{label}\0{len(data)}\0".encode("utf-8"))
        h.update(data)

    add("bs-build", section)
    if section == RECEIVED:
        for f in sorted(p for p in (ws / "inputs").rglob("*") if p.is_file()):
            add(f.relative_to(ws).as_posix(), hashlib.sha256(f.read_bytes()).hexdigest())
        for f in sorted((ws / "records").iterdir()) if (ws / "records").is_dir() else []:
            if f.is_file():
                add(f"records/{f.name}", f.read_bytes())
        for sec, nm, p in section_files(ws):
            add(f"{sec}/{p.name}", p.read_bytes())
    else:
        src = ws / section / f"{name}{EXTS[section]}"
        add(f"{section}/{src.name}", src.read_bytes())
        if section == AI_SECTION:
            add("base", (ws / "process-map" / f"{ai_base(ws, name)}.json").read_bytes())
        if section == "document":
            add("mode", doc_mode(src.read_text(encoding="utf-8")))
        for sid in sorted({ref["source"] for e in page_evs(ws, rep, section, name) for ref in e.refs}):
            add(f"records/{sid}.json", (ws / "records" / f"{sid}.json").read_bytes())
    for p in design_files(section):
        add(p.relative_to(HERE).as_posix(), p.read_bytes())
    add("formats/citation-types.json", (HERE / "formats" / "citation-types.json").read_bytes())
    return h.hexdigest()


STAMP = re.compile(r'<meta name="bs-build" content="([0-9a-f]{64})">')


def stamped_hash(path):
    """The bs-build hash a built page carries, or None."""
    try:
        m = STAMP.search(path.read_bytes().decode("utf-8", "replace"))
    except OSError:
        return None
    return m.group(1) if m else None


def stamp(page, digest):
    """Insert <meta name="bs-build"> right after <meta charset>."""
    m = re.search(r"<meta\s+charset\s*=[^>]*>", page, re.I)
    if not m:
        return None
    return page[:m.end()] + f'<meta name="bs-build" content="{digest}">' + page[m.end():]


# ================================================================== build: the pages as HTML trees (build rules)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
UNSEEN = {"script", "style", "template", "title", "head", "desc", "noscript"}   # text that is never printed on the page


class El:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.kids = tag, attrs, []

    def classes(self):
        return (self.attrs.get("class") or "").split()

    def walk(self):
        yield self
        for k in self.kids:
            if isinstance(k, El):
                yield from k.walk()

    def text(self):
        """The printed text: no script, style, template, <title> or <desc>, and no attribute value. Element
        boundaries count as white space, so that two blocks never run together."""
        if self.tag in UNSEEN:
            return ""
        return " ".join(k if isinstance(k, str) else k.text() for k in self.kids)

    def raw(self):
        return "".join(k if isinstance(k, str) else k.raw() for k in self.kids)


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = El("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        el = El(tag, dict(attrs))
        self.stack[-1].kids.append(el)
        if tag not in VOID:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].kids.append(El(tag, dict(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].kids.append(data)


def parse_html(page):
    t = _Tree()
    t.feed(page)
    t.close()
    return t.root


def anchor(address):
    """FORMATS.md section 2.6: src- plus the address in lower case, ¶ written para, other runs written -."""
    s = address.lower().replace("¶", "para")
    return "src-" + re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def addr(ref):
    return f"{ref['source']} {ref['locator']}" if ref.get("locator") else ref["source"]


END = r"(?![A-Za-z0-9]|[.,:;!\-–][A-Za-z0-9])"


def printed_in(text, address):
    """True when the address is printed in text as one run: 'WB1 Steps!D3', not 'WB1 Steps!D30'."""
    a = fold(address)
    if re.search(r"(?<![A-Za-z0-9])" + re.escape(a) + END, text):
        return True
    return re.search(re.escape(a.replace(" ", "")) + END, text.replace(" ", "")) is not None


# Script that loads from the network: calls, a static import of a URL, and a URL set as an element's src.
SCRIPT_LOADS = re.compile(r"\b(?:fetch|importScripts|sendBeacon)\s*\(|\bXMLHttpRequest\b|\bnew\s+(?:WebSocket|EventSource)\b"
                          r"|\bimport\s*\(|\b(?:import|from)\s*[\"'](?:https?:)?//[^\"']{0,40}"
                          r"|\.src(?:set)?\s*=\s*[\"'`](?:https?:)?//[^\"'`]{0,40}")


def rule_self_contained(rep, label, root, page, paths, shas, roots, received=False):
    """build-2: no network loads (a meta refresh included), no inputs/ path (the Original data received page lists
    the inputs, so it may), no absolute path of the workspace or the toolkit (roots), and no input's sha256."""
    bad = set()
    for el in root.walk():
        for k, v in el.attrs.items():
            v = (v or "").strip()
            loads = (k in ("src", "srcset", "poster") or (k in ("href", "xlink:href") and el.tag not in ("a", "area"))
                     or (k == "data" and el.tag == "object"))
            if loads and v and not v.startswith(("data:", "#")):
                bad.add(f"<{el.tag} {k}=\"{v[:60]}\">")
        if el.tag == "meta" and (el.attrs.get("http-equiv") or "").strip().lower() == "refresh":
            bad.add(f"<meta http-equiv=\"refresh\" content=\"{(el.attrs.get('content') or '')[:60]}\">")
        css = (el.raw() if el.tag == "style" else "") + " " + (el.attrs.get("style") or "")
        for m in re.finditer(r"url\(([^)]*)\)", css):
            v = m.group(1).strip().strip("'\"").strip()
            if v and not v.startswith(("data:", "#")):
                bad.add(f"url({v[:60]})")
        for m in re.finditer(r"@import[^;]*", css):
            bad.add(m.group(0)[:60])
        if el.tag == "script" and re.fullmatch(r"(?i)|text/javascript|application/javascript|module", (el.attrs.get("type") or "").strip()):
            for m in SCRIPT_LOADS.finditer(el.raw()):
                bad.add(m.group(0))
    for b in sorted(bad):
        rep.err("build-2", label, f"the page loads {b}", "inline it: a page is self-contained")
    for path in sorted(paths) if not received else []:
        if path in page:
            rep.err("build-2", label, f"the page holds the path {path}", "print the record's title and address, never its file")
    for r in sorted(roots, key=len, reverse=True):   # the workspace may sit inside the toolkit: report the longer once
        if re.search(r"(?<![\w.-])" + re.escape(r) + r"(?![\w.-])", page):
            rep.err("build-2", label, f"the page holds the absolute path {r}", "print a path relative to the workspace, or none")
            break
    for sha, what in sorted(shas.items()):
        if sha in page:
            rep.err("build-2", label, f"the page holds the full sha256 of {what}", "print a record's title and address, never its hash")


def rule_sources(rep, label, root, section, evs, idx):
    """build-1: the Sources block lists exactly what the page uses. A document or deck lists one row per source, at
    #src-<ID>; a board lists every record address the page cites, at the anchor of FORMATS.md section 2.6."""
    ids = {el.attrs["id"] for el in root.walk() if el.attrs.get("id")}
    dangling = {}
    for el in root.walk():
        href = el.attrs.get("href") or ""
        if href.startswith("#src-") and href[1:] not in ids:
            dangling[href] = dangling.get(href, 0) + 1
    for href, n in sorted(dangling.items()):
        rep.err("build-1", label, f"{'a link points' if n == 1 else f'{n} links point'} at {href}, which no Sources entry has",
                "every marker links to its Sources entry")
    cited = {ref["source"] for e in evs for ref in e.refs}
    if section in ("document", "proposal"):
        listed = {i[4:] for i in ids if i.startswith("src-") and i[4:] in idx.sources}
        for sid in sorted(cited - listed):
            rep.err("build-1", label, f"{sid} is cited but has no Sources row (#src-{sid})")
        for sid in sorted(listed - cited):
            rep.err("build-1", label, f"the Sources block lists {sid}, which nothing on the page cites")
        return
    need = {anchor(addr(ref)): addr(ref) for e in evs if e.type != "absent" for ref in e.refs}
    allowed = {anchor(addr(ref)) for e in evs for ref in e.refs} | {anchor(r["address"]) for e in evs if e.type != "absent" for r in e.recs}
    for a, address in sorted(need.items()):
        if a not in ids:
            rep.err("build-1", label, f"{address} is cited but the Sources card has no entry #{a}")
    records = {anchor(r["address"]): r["address"] for src in idx.sources.values() for r in src.records}
    heads = sorted(((anchor(sid), sid) for sid in idx.sources), key=lambda x: -len(x[0]))
    for i in sorted(x for x in ids if x.startswith("src-")):
        sid = next((s for a, s in heads if i == a or i.startswith(a + "-")), None)
        if sid is None:
            continue
        if sid not in cited:
            rep.err("build-1", label, f"the Sources card lists {sid} (#{i}), which nothing on the page cites")
        elif i in records and i not in allowed:
            rep.err("build-1", label, f"the Sources card lists {records[i]}, which no citation on the page uses")


def rule_printed(rep, label, root, evs):
    """build-4: every cited address is printed: in the page's text (a detail line, a marker, a provenance line), or
    as the Sources entry at its anchor. A tooltip, <title>, title= or aria-label does not count."""
    text = fold(root.text())
    entries = {el.attrs["id"]: el for el in root.walk() if (el.attrs.get("id") or "").startswith("src-")}
    seen = set()
    for e in evs:
        for ref in e.refs:
            address = addr(ref)
            if address in seen:
                continue
            seen.add(address)
            el = entries.get(anchor(address))
            if printed_in(text, address) or (el is not None and fold(ref.get("locator") or ref["source"]) in fold(el.text())):
                continue
            rep.err("build-4", label, f"{address} is cited but not printed", "print it on its element, or as a Sources entry")


def is_ai_class(c):
    return c.startswith("pm-ai") or c == "has-ai" or c.startswith("is-ai-")


def board(root):
    """build-5: the board, which is every svg.pm-board, with each .pm-ai* element removed and the layer's state
    classes (has-ai, is-ai-*) dropped."""
    def sig(node):
        if isinstance(node, str):
            return norm_ws(node) or None
        if any(c.startswith("pm-ai") for c in node.classes()):
            return None
        cls = " ".join(c for c in node.classes() if not is_ai_class(c))
        attrs = tuple(sorted((k, v) for k, v in node.attrs.items() if k != "class")) + ((("class", cls),) if cls else ())
        return (node.tag, attrs, tuple(s for s in (sig(k) for k in node.kids) if s))
    return [sig(el) for el in root.walk() if "pm-board" in el.classes()]


def rule_layer(rep, label, root, page, section, base_root):
    """build-5: a process-map page holds no pm-ai; an AI page with every .pm-ai* element removed is its base board."""
    if section == "process-map":
        if "pm-ai" in page:
            rep.err("build-5", label, "a process-map page holds pm-ai", "the AI layer lives only on process-map-ai-opportunity pages")
        return
    mine, base = board(root), board(base_root)
    if not mine:
        rep.err("build-5", label, "the page has no svg.pm-board", "the board is svg.pm-board (process-map-ai-opportunity README section 4)")
    elif mine != base:
        rep.err("build-5", label, "with every .pm-ai* element removed, the board differs from its base page's board",
                "the layer fills the base's slots and never changes the base")


# ================================================================== build: running the builders

SECTION_NAMES = {RECEIVED: "Original data received"}


def builder_path(section):
    p = HERE / BUILDERS[section]
    if not p.is_file():
        raise SystemExit(f"cannot run: {BUILDERS[section]} is missing, so the {SECTION_NAMES.get(section, section)} page cannot be built")
    return p


def run(cmd):
    """Run one builder from the toolkit folder. Returns (exit code, its output lines)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")   # no __pycache__ in design-system/
    try:
        r = subprocess.run([sys.executable] + [str(c) for c in cmd], cwd=HERE, capture_output=True, timeout=600,
                           text=True, encoding="utf-8", errors="replace", env=env)
    except subprocess.TimeoutExpired:
        return 2, ["the builder ran for more than 10 minutes"]
    return r.returncode, [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]


def builder_cmds(ws, rep, section, name, tmp):
    """The builder command for one page, as a function of its output path, after writing what it reads (the sources
    map, the document without its mode line beside its source, the deck with its register). Returns (cmd, cleanup)."""
    script = builder_path(section)
    if section in ("process-map", AI_SECTION):
        return (lambda out: [script, ws, section, name, out]), None
    if section == RECEIVED:
        return (lambda out: [script, ws, out]), None
    if section == "document":
        src = ws / "document" / f"{name}.md"
        text = src.read_text(encoding="utf-8")
        sm = tmp / f"{name}.sources.json"
        sm.write_text(json.dumps(sources_map(rep.idx), ensure_ascii=False, indent=1), encoding="utf-8")
        md, cleanup = src, None
        if strip_mode(text) != text:
            md = ws / "document" / f".{name}.bs-build.md"   # beside the source, so relative image paths still resolve
            md.write_text(strip_mode(text), encoding="utf-8")
            cleanup = md
        return (lambda out: [script, md, out, f"--{doc_mode(text)}", "--sources", sm, "--strict"]), cleanup
    data = json.loads((ws / "proposal" / f"{name}.json").read_text(encoding="utf-8"))
    prepared = tmp / f"{name}.json"
    prepared.write_text(json.dumps(with_register(data, rep.idx), ensure_ascii=False, indent=2), encoding="utf-8")
    return (lambda out: [script, prepared, out, "--strict"]), None


def build_page(ws, rep, section, name, tmp):
    """Build one page twice (build-3). Returns (worst exit code, page text or None, builder output lines)."""
    work = pathlib.Path(tempfile.mkdtemp(dir=tmp))
    cmd, cleanup = builder_cmds(ws, rep, section, name, work)
    try:
        outs, lines = [], []
        for k in ("a", "b"):
            (work / k).mkdir()
            out = work / k / f"{name or RECEIVED}.html"
            code, said = run(cmd(out))
            said = [l.replace(str(out), page_label(section, name)) for l in said]
            lines = lines or said
            if code != 0:
                return (2 if code == 2 else 1), None, said
            if not out.is_file():
                return 1, None, said + ["the builder exited 0 but wrote no page"]
            outs.append(out.read_bytes())
    finally:
        if cleanup is not None:
            cleanup.unlink(missing_ok=True)
    label = page_label(section, name)
    if outs[0] != outs[1]:
        rep.err("build-3", label, "two builds of the same inputs give different bytes", "the builder writes no timestamp and no random id")
    try:
        page = outs[0].decode("utf-8")
    except UnicodeDecodeError:
        rep.err("build-2", label, "the page is not UTF-8")
        return 1, None, lines
    if 'name="bs-build"' in page:
        rep.err("build-3", label, "the builder wrote a bs-build meta", "only bs.py stamps a page")
    return 0, page, lines


def build(ws, target=None, builtin=False):
    """bs.py build: check, then each page's builder (twice), then the build rules; a page that passes is stamped
    with its bs-build hash and written to out/. A whole-workspace build also builds the Original data received page.

    That page is computed from inputs/, records/ and the section files alone, so it is built even when check fails:
    it is most useful just after new material arrives (NOT CONVERTED). The section pages are built only when check
    passes. A failed check makes the build exit 1 whatever else it builds."""
    shown, ws = ws, pathlib.Path(ws).resolve()   # the builders run from the toolkit folder, so they get the absolute path
    rep = check(ws, builtin)
    checked = not rep.errors()
    pages = [(sec, name) for sec, name, _ in section_files(ws)]
    if target:
        t = re.sub(r"\.(json|md|html)$", "", target.strip("/"))
        if t in (RECEIVED, f"out/{RECEIVED}"):
            pages = [(RECEIVED, None)]
        else:
            pages = [p for p in pages if f"{p[0]}/{p[1]}" == t]
            if not pages:
                raise SystemExit(f"cannot run: {target} is not a section file of {shown} "
                                 f"(section/name, e.g. process-map/current-state, or {RECEIVED})")
    else:
        pages.append((RECEIVED, None))
    warnings = [i for i in rep.items if i[0] == "WARN"]
    if not checked:
        rep.print()
        pages = [p for p in pages if p[0] == RECEIVED]
        print(f"check: {len(rep.errors())} error(s), {len(warnings)} warning(s)  [{rep.engine}]: bs.py check fails, so "
              + ("only the Original data received page is built" if pages else "nothing is built"))
        if not pages:
            return 1
    missing = {}   # every builder this build needs, before any page is written
    for sec in sorted({p[0] for p in pages}):
        if not (HERE / BUILDERS[sec]).is_file():
            missing.setdefault(BUILDERS[sec], []).append(SECTION_NAMES.get(sec, sec))
    if missing:
        raise SystemExit("cannot run: " + "; ".join(f"{b} is missing, so no {' or '.join(w)} page can be built"
                                                     for b, w in missing.items()))
    if checked:
        print(f"check: 0 error(s), {len(warnings)} warning(s)  [{rep.engine}]")
    worst, built, failed, trees = 0 if checked else 1, 0, 0, {}
    shas = {hashlib.sha256(f.read_bytes()).hexdigest(): f.relative_to(ws).as_posix() for f in sorted((ws / "inputs").rglob("*")) if f.is_file()}
    shas.update({s.header["sha256"]: s.header["file"] for s in rep.idx.sources.values()})
    paths = set(shas.values())
    roots = sorted({str(ws), str(HERE)})
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        for sec, name in pages:
            label = page_label(sec, name)
            n0 = len(rep.errors())
            code, page, said = build_page(ws, rep, sec, name, tmp)
            if code:
                worst = max(worst, code)
                failed += 1
                print(f"{'ERROR':5}  {'build':8}  {label}  {BUILDERS[sec].rsplit('/', 1)[-1]} exited {code}"
                      + ("  -> cannot run" if code == 2 else ""))
                for line in said:
                    print(f"         {line}")
                continue
            root = parse_html(page)
            trees[(sec, name)] = root
            rule_self_contained(rep, label, root, page, paths, shas, roots, received=sec == RECEIVED)
            if sec != RECEIVED:
                evs = page_evs(ws, rep, sec, name)
                rule_sources(rep, label, root, sec, evs, rep.idx)
                rule_printed(rep, label, root, evs)
            if sec in ("process-map", AI_SECTION):
                base_root = None
                if sec == AI_SECTION:
                    base = ai_base(ws, name)
                    base_root = trees.get(("process-map", base))
                    if base_root is None:
                        _, bpage, _ = build_page(ws, rep, "process-map", base, tmp)
                        base_root = parse_html(bpage) if bpage else None
                if sec == AI_SECTION and base_root is None:
                    rep.err("build-5", label, f"the base map {base} does not build, so the layer cannot be compared with it",
                            f"python3 bs.py build {shown} process-map/{base}")
                else:
                    rule_layer(rep, label, root, page, sec, base_root)
            stamped = stamp(page, page_hash(ws, rep, sec, name))
            if stamped is None:
                rep.err("build-3", label, "the page has no <meta charset>, so bs.py cannot stamp it")
            new = rep.items[n0:]
            for level, rule, where, msg, fix in new:
                print(f"{level:5}  {rule:8}  {where}  {msg}" + (f"  -> {fix}" if fix else ""))
            if any(i[0] == "ERROR" for i in new):
                worst, failed = max(worst, 1), failed + 1
                continue
            out = page_out(ws, sec, name)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(stamped, encoding="utf-8")
            built += 1
            print(f"built  {label}" + "".join(f"\n         {line}" for line in said))
    print(f"{built} page(s) built, {failed} failed")
    return worst


# ================================================================== status

def status(ws, as_json=False, builtin=False):
    """The folders are the state. One row per input, record, section file and page, then the workspace state
    (the first of NOT CONVERTED, INVALID, NOT BUILT or STALE, DONE that applies) and its next step."""
    ws = pathlib.Path(ws)
    rep = check(ws, builtin)
    errors = {}
    for i in rep.errors():
        errors.setdefault(finding_file(i[2]), []).append(i)
    rows, covered = [], set()
    record_of = {}
    for p in sorted((ws / "records").glob("*.json")) if (ws / "records").is_dir() else []:
        try:
            record_of[json.loads(p.read_text(encoding="utf-8")).get("file")] = f"records/{p.name}"
        except (ValueError, UnicodeDecodeError, AttributeError):
            pass
    for rel, state, note in rep.inputs:
        covered.add(rel)
        rec = record_of.get(rel)
        if state == "CONVERTED":
            covered.add(rec)
            n = len(errors.get(rec, []))
            rows.append({"file": rel, "state": "INVALID" if n else "CONVERTED", "record": note,
                         "note": f"{note}: {n} error(s)" if n else note})
        elif state == "DUPLICATE":
            rows.append({"file": rel, "state": "DUPLICATE", "note": f"a copy of {note}"})
        elif state == "HIDDEN":
            rows.append({"file": rel, "state": "INVALID", "note": "a hidden file in inputs/"})
        else:
            rows.append({"file": rel, "state": "NOT CONVERTED", "note": note})
    for rec in sorted(set(record_of.values()) | {f for f in errors if f.startswith("records/")}):
        if rec not in covered and rec in errors:
            covered.add(rec)
            rows.append({"file": rec, "state": "INVALID", "note": f"{len(errors[rec])} error(s): {errors[rec][0][3]}"})
    pages = [(sec, name, p) for sec, name, p in section_files(ws)] + [(RECEIVED, None, None)]
    for sec, name, p in pages:
        f = f"{sec}/{p.name}" if p else page_label(sec, name)
        covered.add(f)
        out = page_out(ws, sec, name)
        row = {"file": f, "page": page_label(sec, name)}
        if p and f in errors:
            row.update(state="INVALID", note=f"{len(errors[f])} error(s)")
        else:
            note = page_label(sec, name) if p else "the Original data received page"
            if not out.is_file():
                row.update(state="NOT BUILT", note=note)
            elif stamped_hash(out) != page_hash(ws, rep, sec, name):
                row.update(state="STALE", note=note)
            else:
                row.update(state="DONE", note=note)
        rows.append(row)
    for f in sorted(set(errors) - covered):
        rows.append({"file": f, "state": "INVALID", "note": f"{len(errors[f])} error(s): {errors[f][0][3]}"})
    states = {r["state"] for r in rows}
    if "NOT CONVERTED" in states:
        state = "NOT CONVERTED"
        nxt = (f"convert the new inputs with .claude/workflows/convert.js (bs.py convert for a format it reads, the converter agent "
               f"otherwise), then python3 bs.py check {ws}")
    elif rep.errors():
        state, nxt = "INVALID", f"fix what each -> fix hint names (the author agent): python3 bs.py check {ws}"
    elif "NOT BUILT" in states or "STALE" in states:
        state = "NOT BUILT" if "NOT BUILT" in states else "STALE"
        nxt = f"python3 bs.py build {ws}"
    else:
        state, nxt = "DONE", "nothing"
    unchecked = [{"record": w, "file": f} for w, f in rep.unchecked]
    duplicate = [{"file": rel, "of": note} for rel, state, note in rep.inputs if state == "DUPLICATE"]
    if as_json:
        print(json.dumps({"workspace": str(ws), "state": state, "next": nxt, "errors": len(rep.errors()),
                          "warnings": len(rep.items) - len(rep.errors()), "items": rows, "unchecked": unchecked,
                          "duplicate": duplicate}, ensure_ascii=False, indent=1))
        return 0
    width = max([len(r["file"]) for r in rows] + [4])
    print(f"{'STATE':14} {'FILE':{width}}  NOTE")
    for r in rows:
        print(f"{r['state']:14} {r['file']:{width}}  {r['note']}".rstrip())
    if unchecked or duplicate:
        print()
    for u in unchecked:
        print(f"UNCHECKED      {u['record']}: a person compares it with {u['file']}")
    for d in duplicate:
        print(f"DUPLICATE      {d['file']}: a byte-identical copy of {d['of']}, nothing to convert")
    print(f"\nState: {state}  ({len(rep.errors())} error(s), {len(rep.items) - len(rep.errors())} warning(s))")
    print(f"Next step: {nxt}")
    return 0


# ================================================================== rules table

def rules_table():
    load()
    rows = ["| Section · category | Allowed | Needs | Note |", "|---|---|---|---|"]
    for sec, cats in RULES["categories"].items():
        for cat, r in cats.items():
            needs = " **and** ".join(" or ".join(g) for g in r["require"]) or "nothing"
            if r.get("quoteWithAiTerm"):
                needs += ", with a quote holding an AI term"
            if r.get("orToConfirm"):
                needs += " **or** `to_confirm`"
            rows.append(f"| {sec} · {cat} | {', '.join(r['allowed']) or 'none'} | {needs} | {r['note']} |")
    return "\n".join(rows)


# ================================================================== self-test: one break per rule, every one caught

def _json(path, fn):
    def apply(ws):
        p = ws / path
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return apply


def _text(path, old, new):
    def apply(ws):
        p = ws / path
        t = p.read_text(encoding="utf-8")
        if old not in t:
            raise AssertionError(f"mutation text not found in {path}: {old!r}")
        p.write_text(t.replace(old, new, 1), encoding="utf-8")
    return apply


def _new(path, text):
    def apply(ws):
        p = ws / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text) if isinstance(text, bytes) else p.write_text(text, encoding="utf-8")
    return apply


def _record(rid, kind, file, records, raw):
    """A new input and a record file for it, with the right sha256."""
    def apply(ws):
        f = ws / file
        f.write_bytes(raw) if isinstance(raw, bytes) else f.write_text(raw, encoding="utf-8")
        d = {"id": rid, "title": f"Placeholder {rid} record", "kind": kind, "captured": "2026-10-20", "file": file,
             "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "coverage": "complete", "records": records}
        (ws / "records" / f"{rid}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return apply


def _seq(*fns):
    def apply(ws):
        for fn in fns:
            fn(ws)
    return apply


PM = "process-map/current-state.json"
AI = "process-map-ai-opportunity/current-state-ai.json"
DOC = "document/request-handling-summary.md"
PR = "proposal/request-handling-pilot.json"
PARA = "Client A handles requests across three teams [D1 ¶2]."
OPEN = "## What is still open\n"


def _node(d, nid):
    return next(n for n in d["nodes"] if n["id"] == nid)


def _item(d, aid):
    return next(i for i in d["ai"] if i["id"] == aid)


def _sit(d):
    return next(s for s in d["slides"] if s["type"] == "situation")


MUTATIONS = [
    ("schema-1", "an unknown field in a node", _json(PM, lambda d: _node(d, "SUB-01").update({"titel": "x"}))),
    ("schema-1", "a record file with a dropped kind", _json("records/WB1.json", lambda d: d.update({"kind": "data"}))),
    ("schema-1", "a record file that is a JSON list", _new("records/T1.json", "[]")),
    ("schema-1", "a record file whose path leaves inputs/", _json("records/D1.json", lambda d: d.update({"file": "inputs/../records/T1.json"}))),
    ("schema-1", "a decision with an owner", _json(PM, lambda d: _node(d, "REV-02").update({"owner": "Team B"}))),
    ("schema-1", "a flow edge with a label", _json(PM, lambda d: d["edges"][0].update({"label": "Sent"}))),
    ("schema-1", "a proposal claim with neither cite nor to_confirm", _json(PR, lambda d: _sit(d)["points"][0].pop("cite"))),
    ("schema-1", "a deck locator over 20 characters", _json(PR, lambda d: _sit(d)["points"][1]["cite"][0].update({"locator": "Steps rows 2-7 and 12"}))),
    ("schema-1", "a cited record captured on a day not on the calendar", _json("records/D1.json", lambda d: d.update({"captured": "2026-13-45"}))),
    ("schema-1", "a deck dated on a day not on the calendar", _json(PR, lambda d: d["meta"].update({"date": "2026-02-30"}))),
    ("ws-1", "an input with no record file", _new("inputs/extra-notes.md", "# Extra\n\nOne more note.\n")),
    ("ws-1", "a container in inputs/", _new("inputs/pack.zip", b"PK\x05\x06" + b"\x00" * 18)),
    ("ws-2", "a stray folder in the workspace", lambda ws: (ws / "sources").mkdir()),
    ("ws-2", "a hidden file in inputs/", _new("inputs/.secret.txt", "Client data\n")),
    ("ws-2", "a stray file in records/", _new("records/notes.txt", "scratch\n")),
    ("rec-1", "a record file whose id differs from its name", _json("records/T1.json", lambda d: d.update({"id": "T2"}))),
    ("rec-2", "an input edited after conversion", _text("inputs/follow-up-call.txt", "5,000", "6,000")),
    ("rec-2", "a record whose input is not on disk", _seq(_record("T2", "transcript", "inputs/ghost-call.txt",
        [{"locator": "00:00:10", "text": "Team C approves everything over 90,000.", "context": "Speaker C"}], "x"),
        lambda ws: (ws / "inputs/ghost-call.txt").unlink())),
    ("rec-3", "a sheet locator written without '!'", _json("records/WB1.json", lambda d: d["records"][0].update({"locator": "Steps A1"}))),
    ("rec-4", "records out of reading order", _json("records/T1.json", lambda d: d["records"].reverse())),
    ("rec-5", "a record paraphrased", _json("records/T1.json", lambda d: d["records"][2].update({"text": "Incomplete requests are returned to Team A."}))),
    ("rec-5", "complete coverage with a unit missing", _json("records/D1.json", lambda d: d["records"].pop())),
    ("rec-5", "a record context paraphrased", _json("records/T1.json", lambda d: d["records"][0].update({"context": "Team A lead"}))),
    ("rec-5", "an input whose extension its kind does not take", _record("WB2", "sheet", "inputs/thread.txt",
        [{"locator": "Sheet1!A1", "text": "We would like AI to approve every request."}], "Team A: Can someone check the tracker?\n")),
    ("rec-5", "a binary .xlsx that is not a workbook", _record("WB2", "sheet", "inputs/book.xlsx",
        [{"locator": "Sheet1!A1", "text": "Step"}], b"PK\x03\x04\x14\x00binary")),
    ("rec-6", "one input converted twice", lambda ws: (ws / "records/T9.json").write_text(
        (ws / "records/T1.json").read_text(encoding="utf-8").replace('"id": "T1"', '"id": "T9"'), encoding="utf-8")),
    ("cite-1", "a citation to a source that does not exist", _json(PM, lambda d: _node(d, "LOG-01")["cite"].append({"source": "WB9", "locator": "Steps!A3"}))),
    ("cite-1", "a locator that resolves to no record", _json(PM, lambda d: _node(d, "LOG-01")["cite"][0].update({"locator": "Steps row 99"}))),
    ("cite-1", "a locator in the wrong grammar for its kind", _json(PM, lambda d: _node(d, "APP-01")["cite"][1].update({"locator": "turn 4"}))),
    ("cite-1", "a step citing a whole source", _json(PM, lambda d: _node(d, "LOG-01").update({"cite": [{"source": "WB1"}]}))),
    ("cite-1", "a document Grounded line citing a whole source", _text(DOC, "No source names who records the outcome.\n\nGap · not in WB1 Steps row 7: “Team”",
        "Team C approves requests up to 5,000 by email.\n\nGrounded · T1")),
    ("cite-2", "one letter of a quote changed", _json(PM, lambda d: _node(d, "REV-01")["cite"][1].update({"quote": "checks it is completed"}))),
    ("cite-3", "an absent needle that does occur", _json(PM, lambda d: d["gaps"][0]["cite"][2].update({"needle": "request"}))),
    ("cite-3", "a document Gap line over a partial source", _seq(_json("records/WB1.json", lambda d: d.update({"coverage": "partial"})))),
    ("cite-4", "a gap card with no absent proof", _json(PM, lambda d: d["gaps"][0].update({"cite": d["gaps"][0]["cite"][:1]}))),
    ("cite-4", "a grounded step with only an inferred citation", _json(PM, lambda d: _node(d, "APP-01").update(
        {"cite": [{"type": "inferred", "reading": "Approval follows review", "from": [{"source": "WB1", "locator": "Steps row 6"}]}]}))),
    ("cite-4", "an absent citation on a step", _json(PM, lambda d: _node(d, "SUB-01")["cite"].append({"type": "absent", "needle": "fax", "in": [{"source": "T1"}]}))),
    ("cite-5", "a web record cited for a process step", _json(PM, lambda d: _node(d, "LOG-01")["cite"].append({"source": "WEB1", "locator": "¶2"}))),
    ("cite-5", "a suggested AI item resting on web records alone", _json(AI, lambda d: _item(d, "AI-04").update(
        {"cite": [{"type": "inferred", "reading": "Tools can keep one history", "from": [{"source": "WEB1", "locator": "¶3"}]}]}))),
    ("map-1", "a node in an unknown lane", _json(PM, lambda d: _node(d, "APP-01").update({"lane": "team-c"}))),
    ("map-1", "a lane id that a system already uses", _json(PM, lambda d: d["lanes"].append(
        {"id": "email", "label": "Team C", "cite": [{"source": "WB1", "locator": "Steps!B2"}]}))),
    ("map-2", "nodes not listed group by group", _json(PM, lambda d: d["nodes"].insert(0, d["nodes"].pop(2)))),
    ("map-2", "a node with no group in a map with groups", _json(PM, lambda d: _node(d, "SUB-01").pop("group"))),
    ("map-3", "an empty lane with no citation", _json(PM, lambda d: d["lanes"].append({"id": "team-c", "label": "Team C"}))),
    ("map-4", "a decision with one branch", _json(PM, lambda d: d["edges"].pop(next(i for i, e in enumerate(d["edges"]) if e.get("label") == "No")))),
    ("map-5", "an edge listed twice", _json(PM, lambda d: d["edges"].append({"from": "SUB-01", "to": "LOG-01"}))),
    ("map-6", "a gap card listing a grounded step", _json(PM, lambda d: d["gaps"][0]["nodes"].append("APP-01"))),
    ("map-7", "an inferred reading too long for the card", _json(PM, lambda d: _node(d, "RES-01")["cite"][0].update(
        {"reading": "Team A completes the request again and sends it back for review"}))),
    ("map-8", "a system whose label is not in its record", _json(PM, lambda d: d["systems"][1].update({"label": "Ledger"}))),
    ("map-9", "an AI idea as a node title", _json(PM, lambda d: _node(d, "LOG-01").update({"title": "Automate logging with AI"}))),
    ("map-9", "an AI idea in gap prose", _json(PM, lambda d: d["gaps"][0].update({"text": d["gaps"][0]["text"] + " Automation could record it."}))),
    ("map-10", "a col hint left of the derived column", _json(PM, lambda d: _node(d, "APP-01").update({"col": 1}))),
    ("prose-1", "a bracket in map prose that is not a citation", _json(PM, lambda d: d["clarifications"][0].update({"ask": "Who sets the limit [TBD]?"}))),
    ("prose-1", "a citation in the map subtitle", _json(PM, lambda d: d["meta"].update({"subtitle": "Six steps [WB1 Steps rows 2-7]."}))),
    ("prose-1", "a document bracket that is not a citation", _text(DOC, "by hand [WB1 Steps!D3]", "by hand [TBD]")),
    ("prose-1", "a deck claim with a bracket that is not a placeholder", _json(PR, lambda d: _sit(d)["points"][0].update(
        {"text": "Requests pass between the teams by email [D1 ¶3]."}))),
    ("prose-2", "a straight double quote in map prose", _json(PM, lambda d: d["gaps"][0].update({"text": d["gaps"][0]["text"] + ' The sheet says "Tracker".'}))),
    ("prose-2", "a straight double quote in a document", _text(DOC, "“Incomplete requests go back to Team A.”", '"Incomplete requests go back to Team A."')),
    ("prose-3", "a quote that no cited record holds", _json(PM, lambda d: d["clarifications"][0].update({"shows": "The step list says Team B “sets the limit”."}))),
    ("prose-4", "a number with no source", _json(PM, lambda d: d["clarifications"][0].update({"ask": "Who sets the limit, and is it reviewed every 12 months?"}))),
    ("prose-4", "a number in a node title", _json(PM, lambda d: _node(d, "APP-01").update({"title": "Approve requests up to 50,000"}))),
    ("prose-4", "a number in an inferred reading", _json(PM, lambda d: _node(d, "RES-01")["cite"][0].update({"reading": "Team A redoes 40% of requests"}))),
    ("prose-4", "a number that only part of a record number matches", _json(PM, lambda d: d["clarifications"][0].update(
        {"ask": "Who sets the limit, and do 5 people approve?"}))),
    ("prose-4", "a gap figure supported only by an absent span", _json(PM, lambda d: d["gaps"][0].update({"text": d["gaps"][0]["text"] + " Team C approves up to 5,000."}))),
    ("prose-4", "an invented figure in an agentic plan", _json(AI, lambda d: _item(d, "AI-02")["agentic"].update({"trigger": "A new request arrives, about 40 a day."}))),
    ("prose-4", "a document number with no source", _text(DOC, "approves requests up to 5,000", "approves requests up to 50,000")),
    ("prose-4", "a document heading with an invented figure", _text(DOC, "## What is still open", "## 90,000 requests are still open")),
    ("prose-4", "a number inside inline code", _text(DOC, PARA, "Client A handles `90,000` requests across three teams [D1 ¶2].")),
    ("prose-4", "a figure in a document Inferred reading", _text(DOC, "Inferred · the completeness check is part of review ·", "Inferred · the check takes 45 minutes per request ·")),
    ("prose-4", "a cited deck stat that its record does not hold", _json(PR, lambda d: _sit(d)["stats"][0].update({"value": "40"}))),
    ("prose-4", "a deck point with an invented figure", _json(PR, lambda d: _sit(d)["points"][2].update({"text": "Each request takes 45 minutes to log by hand."}))),
    ("prose-5", "an unknown count token", _json(PM, lambda d: d["meta"].update({"subtitle": "{count:step} steps across {count:groups} views."}))),
    ("prose-6", "an element id in map prose that names nothing", _json(PM, lambda d: d["gaps"][0].update({"text": d["gaps"][0]["text"] + " It follows SUB-99."}))),
    ("prose-6", "an element id in an AI item that names nothing", _json(AI, lambda d: _item(d, "AI-01").update({"does": "Drafts a summary for Team B to check at REV-09."}))),
    ("ai-1", "an AI layer whose base does not exist", _json(AI, lambda d: d.update({"base": "future-state"}))),
    ("ai-2", "an AI item on a node the base lacks", _json(AI, lambda d: _item(d, "AI-01").update({"nodes": ["REV-09"]}))),
    ("ai-2", "an all-views item that also lists steps", _json(AI, lambda d: _item(d, "AI-04").update({"nodes": ["LOG-01"]}))),
    ("ai-2", "AI items out of id order", _json(AI, lambda d: d["ai"].reverse())),
    ("ai-2", "an AI item on a decision", _json(AI, lambda d: _item(d, "AI-01").update({"nodes": ["REV-02"]}))),
    ("ai-3", "a named item whose quote does not ask for AI", _json(AI, lambda d: _item(d, "AI-01")["cite"][0].update(
        {"locator": "00:01:02", "quote": "Logging each request by hand takes time"}))),
    ("ai-4", "an agentic decision after a step that does not exist", _json(AI, lambda d: _item(d, "AI-02")["agentic"]["decides"][0].update({"after": 5}))),
    ("ai-4", "an agentic system the base lacks", _json(AI, lambda d: _item(d, "AI-02")["agentic"]["systems"].append("ledger"))),
    ("doc-1", "an unknown front matter key", _text(DOC, "footer: Request handling summary", "footer: Request handling summary\ncolour: green")),
    ("doc-1", "a code fence that is never closed", _text(DOC, OPEN, OPEN + "\n```\nunclosed\n")),
    ("doc-1", "a front matter key written twice", _text(DOC, "footer: Request handling summary", "footer: Request handling summary\nmode: screen\nmode: a4")),
    ("doc-2", "a malformed Gap line", _text(DOC, "Gap · not in WB1 Steps row 7: “Team”", "Gap · WB1 Steps row 7 has no team")),
    ("doc-2", "a provenance line after a heading", _text(DOC, OPEN, OPEN + "\nGrounded · WB1 Steps row 7\n")),
    ("doc-2", "an Inferred reading too short, in straight quotes", _text(DOC, "Inferred · the completeness check is part of review ·", 'Inferred · "x" ·')),
    ("doc-3", "a claim paragraph with no citation", _text(DOC, OPEN, OPEN + "\nThe review usually takes a day.\n")),
    ("doc-3", "an uncited list item", _text(DOC, "The outcome is logged in the tracker [WB1 Steps!D7].", "The outcome is logged in the tracker.")),
    ("doc-3", "an uncited table row", _text(DOC, "| Record outcome | Not stated | [WB1 Steps row 7] |", "| Record outcome | Not stated | none |")),
    ("doc-3", "an uncited sentence in a cited paragraph", _text(DOC, PARA, PARA + " Team C signs off every request.")),
    ("doc-3", "a citation hidden in an inline comment", _text(DOC, PARA, "Client A handles requests across three teams <!-- [D1 ¶2] -->.")),
    ("doc-3", "a claim after <!-- page --> on the same line", _text(DOC, OPEN, OPEN + "\n<!-- page --> Team B approves requests every day.\n")),
    ("doc-3", "pipe lines with no separator row", _text(DOC, OPEN, OPEN + "\n| Team B approves requests |\n| Team A sends them |\n")),
    ("doc-3", "a ```word``` line followed by a claim", _text(DOC, OPEN, "```note```\n\n" + OPEN + "\nTeam B approves requests every day.\n")),
    ("deck-1", "a deck with no needs slide", _json(PR, lambda d: d.update({"slides": [s for s in d["slides"] if s["type"] != "needs"]}))),
    ("deck-1", "a deck whose sources slide is not last", _json(PR, lambda d: d["slides"].insert(1, d["slides"].pop()))),
    ("deck-2", "a hand-written register", _json(PR, lambda d: d.update({"sources": [{"id": "D1", "title": "Call notes", "kind": "document"}]}))),
    ("deck-3", "a claim with both cite and to_confirm", _json(PR, lambda d: _sit(d)["stats"][0].update({"to_confirm": "Confirm the number of teams"}))),
    ("cite-1", "a deck locator that resolves to nothing", _json(PR, lambda d: _sit(d)["points"][0]["cite"][0].update({"locator": "¶9"}))),
]


def selftest(builtin):
    clean = check(HERE / "examples", builtin)
    if clean.errors():
        clean.print()
        print("the clean examples do not pass; fix them before the self-test")
        return 1
    caught = 0
    for rule, what, fn in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            ws = pathlib.Path(tmp) / "ws"
            shutil.copytree(HERE / "examples", ws, ignore=shutil.ignore_patterns("out"))
            fn(ws)
            rep = check(ws, builtin)
            ok = rule in rep.rules()
            caught += ok
            print(f"{'caught' if ok else 'MISSED'}  {rule:8}  {what:60}  ({', '.join(sorted(rep.rules())) or 'nothing'})")
    contracts = selftest_contracts(builtin)
    for ok, what in contracts:
        print(f"{'ok' if ok else 'FAILED':6}  {'contract':8}  {what}")
    print(f"caught {caught} of {len(MUTATIONS)}; contracts {sum(ok for ok, _ in contracts)} of {len(contracts)}  [{clean.engine}]")
    return 0 if caught == len(MUTATIONS) and all(ok for ok, _ in contracts) else 1


def selftest_contracts(builtin):
    out = []
    formats = (HERE / "formats/FORMATS.md").read_text(encoding="utf-8")
    m = re.search(r"<!-- generated by bs\.py check --rules -->\n(.*?)\n<!-- end generated -->", formats, re.S)
    out.append((bool(m) and m.group(1).strip() == rules_table(), "FORMATS.md section 2.3 is the --rules table"))
    cite = defn("proposal.schema.json", "cite")["properties"]
    out.append((cite["source"]["pattern"] == SOURCE_RE.pattern
                and cite["locator"]["maxLength"] <= defn("citation.schema.json", "locator")["maxLength"],
                "the deck's cite uses the shared source id and a locator no longer than the shared one"))
    kinds = defn("proposal.schema.json", "source")["properties"]["kind"]["enum"]
    out.append((all(k["deckKind"] in kinds for k in KINDS.values()), "every source kind maps to a deck kind"))
    out.append((set(map_counts({"nodes": []})) == set(COUNT_SELECTORS), "the checker counts exactly the schema's count selectors"))
    # an input is never edited: its new version is a new file, converted under a new id, and the workspace passes
    with tempfile.TemporaryDirectory() as tmp:
        ws = pathlib.Path(tmp) / "ws"
        shutil.copytree(HERE / "examples", ws, ignore=shutil.ignore_patterns("out"))
        (ws / "inputs/follow-up-call-v2.txt").write_text(
            (ws / "inputs/follow-up-call.txt").read_text(encoding="utf-8") + "00:01:30 Speaker B: The tracker keeps one row per request.\n", encoding="utf-8")
        before = "ws-1" in check(ws, builtin).rules()
        ns = argparse.Namespace(id="T2", kind="transcript", title="Follow-up call notes, second version (placeholder)",
                                captured="2026-10-21", detail=None, url=None, partial=False, legacy=False)
        with io.StringIO() as buf:
            old, sys.stdout = sys.stdout, buf
            try:
                convert(ws, "inputs/follow-up-call-v2.txt", ns)
            finally:
                sys.stdout = old
        out.append((before and not check(ws, builtin).errors(), "a new version of an input goes NOT CONVERTED -> convert -> 0 errors"))
    # the readers: xlsx, docx, vtt and srt round-trip through convert's core
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        out.append((reader_cases(t), "the xlsx, docx, vtt, srt and html readers give the documented units"))
    return out


def reader_cases(t):
    x = t / "Book.xlsx"
    with zipfile.ZipFile(x, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   '<sheet name="Steps" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<si><t>Step</t></si><si><t>Limit</t></si><si><r><t>Approve </t></r><r><t>request</t></r></si></sst>')
        z.writestr("xl/styles.xml", '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="inlineStr"><is><t>Due</t></is></c></row>'
                   '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>5000</v></c><c r="C2" s="1"><v>46266</v></c></row>'
                   '</sheetData></worksheet>')
    d = t / "notes.docx"
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(d, "w") as z:
        z.writestr("word/document.xml", f'<w:document {w}><w:body>'
                   '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Call notes</w:t></w:r></w:p>'
                   '<w:p><w:r><w:t xml:space="preserve">Team A sends </w:t></w:r><w:r><w:t>requests.</w:t></w:r></w:p>'
                   '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Step</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Owner</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                   '</w:body></w:document>')
    (t / "call.vtt").write_text("WEBVTT\n\n1\n00:00:05.000 --> 00:00:07.000\n<v Speaker A>Team A sends\neach request.</v>\n\n"
                                "00:00:05.600 --> 00:00:09.000\n<v Speaker B>By email.\n", encoding="utf-8")
    (t / "call.srt").write_text("1\n00:00:05,000 --> 00:00:07,000\nSpeaker A: Team A sends each request.\n", encoding="utf-8")
    (t / "page.html").write_text("<h1>Tools</h1><p>One history.</p><table><tr><th>Tool</th><th>Use</th></tr><tr><td>Tracker</td><td>Logs</td></tr></table>", encoding="utf-8")
    (t / "notes.md").write_text("# Notes\n\n| Step | Owner |\n|---|---|\n| Submit | Team A |\n\n- one\n  continued\n- two\n", encoding="utf-8")
    want = {
        ("sheet", x): [("Steps!A1", "Step", None), ("Steps!B1", "Limit", None), ("Steps!C1", "Due", None),
                       ("Steps!A2", "Approve request", "Step"), ("Steps!B2", "5000", "Limit"), ("Steps!C2", "2026-09-01", "Due")],
        ("document", d): [("¶1", "Call notes", None), ("¶2", "Team A sends requests.", "Call notes"), ("¶3", "Step | Owner", "Call notes")],
        ("transcript", t / "call.vtt"): [("00:00:05", "Team A sends each request.", "Speaker A"), ("00:00:05.600", "By email.", "Speaker B")],
        ("transcript", t / "call.srt"): [("00:00:05", "Team A sends each request.", "Speaker A")],
        ("web", t / "page.html"): [("¶1", "Tools", None), ("¶2", "One history.", "Tools"), ("¶3", "Tool | Use", "Tools"), ("¶4", "Tracker | Logs", "Tools")],
        ("document", t / "notes.md"): [("¶1", "Notes", None), ("¶2", "Step | Owner", "Notes"), ("¶3", "Submit | Team A", "Notes"),
                                       ("¶4", "one continued", "Notes"), ("¶5", "two", "Notes")],
    }
    ok = True
    for (kind, path), units in want.items():
        got = extract_units(kind, path)
        if got != units:
            print(f"reader {path.name} as {kind}: got {got}")
            ok = False
    return ok


# ================================================================== command line

def cmd_check(a):
    if a.rules:
        print(rules_table())
        return 0
    if a.selftest:
        load()
        return selftest(a.builtin)
    if not a.workspace:
        raise SystemExit("cannot run: bs.py check needs a workspace (or --selftest, or --rules)")
    guard(a.workspace)
    ws = pathlib.Path(a.workspace)
    only = None
    if a.file:
        p = pathlib.Path(a.file)
        if (ws / p).exists():
            only = pathlib.PurePosixPath(*p.parts).as_posix()
        elif p.exists() and ws.resolve() in p.resolve().parents:
            only = p.resolve().relative_to(ws.resolve()).as_posix()
        else:
            raise SystemExit(f"cannot run: {a.file} is not a file of {ws}")
    rep = check(ws, a.builtin)
    rep.print(only=only)
    for name, data in sorted(rep.maps.items()):
        if data and only in (None, f"process-map/{name}.json"):
            print(f"note   map {name}: " + ", ".join(f"{k} {v}" for k, v in map_counts(data).items() if v) + f", columns {layout(data)[1]}")
    items = [i for i in rep.items if only is None or finding_file(i[2]) == only]
    e = sum(1 for i in items if i[0] == "ERROR")
    print(f"{e} error(s), {len(items) - e} warning(s)" + (f" in {only}" if only else "") + f"  [{rep.engine}]")
    return 1 if e else 0


def cmd_convert(a):
    load()
    if a.units:
        path, kind = pathlib.Path(a.units[0]), a.units[1]
        if kind not in KINDS:
            raise SystemExit(f"cannot run: '{kind}' is not a kind; KIND is one of {', '.join(KINDS)}")
        if not path.is_file():
            raise SystemExit(f"cannot run: {path} is not a file")
        try:
            units = extract_units(kind, path)
        except ReadError as e:
            raise SystemExit(f"cannot run: {path} {e}")
        if units is None:
            raise SystemExit(f"cannot run: no reader for {path.suffix or 'an extensionless file'} as {kind} "
                             f"(a {kind} reads {', '.join(KINDS[kind]['read'])})")
        for loc, text, ctx in units:
            print(json.dumps(dict({"locator": loc, "text": text}, **({"context": ctx} if ctx else {})), ensure_ascii=False))
        return 0
    if not a.workspace or not a.input:
        raise SystemExit("cannot run: bs.py convert needs a workspace and an inputs/ file (or --units FILE KIND)")
    if not all((a.id, a.kind, a.title, a.captured)):
        raise SystemExit("cannot run: convert needs --id, --kind, --title and --captured")
    guard(a.workspace)
    return convert(a.workspace, a.input, a)


def cmd_build(a):
    guard(a.workspace)
    if a.prepare:
        return prepare(a.workspace, a.prepare, a.builtin)
    return build(a.workspace, a.target, a.builtin)


def cmd_status(a):
    guard(a.workspace)
    return status(a.workspace, a.json, a.builtin)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bs.py", description="\n\n".join(__doc__.split("\n\n")[:4]),
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="formats/FORMATS.md section 6 lists the rule ids. Run bs.py COMMAND --help for its flags.")
    sub = ap.add_subparsers(dest="command", metavar="status | convert | check | build")
    sub.required = True
    s = sub.add_parser("status", help="the state of each file, the workspace state and the next step")
    s.add_argument("workspace")
    s.add_argument("--json", action="store_true", help="print the state as JSON")
    s.add_argument("--builtin", action="store_true", help="use the built-in JSON Schema subset checker")
    s.set_defaults(fn=cmd_status)
    c = sub.add_parser("convert", help="write records/ID.json from one input; the flags are the whole header")
    c.add_argument("workspace", nargs="?")
    c.add_argument("input", nargs="?", help="the input, inputs/FILE")
    c.add_argument("--id", help="the source id, e.g. WB1; the record file is records/ID.json")
    c.add_argument("--kind", help="sheet, document, transcript or web")
    c.add_argument("--title", help="what the input is, in plain words")
    c.add_argument("--captured", help="when it was received or retrieved (ISO date)")
    c.add_argument("--detail", help="one line: who provided it, size, version, how speakers were pseudonymised")
    c.add_argument("--url", help="where a web page was retrieved from (required for web)")
    c.add_argument("--partial", action="store_true", help="the records are an excerpt (coverage partial)")
    c.add_argument("--legacy", action="store_true", help="the material was already old when it arrived")
    c.add_argument("--units", nargs=2, metavar=("FILE", "KIND"), help="print the records FILE converts to, and write nothing")
    c.set_defaults(fn=cmd_convert)
    k = sub.add_parser("check", help="every rule in formats/FORMATS.md section 6")
    k.add_argument("workspace", nargs="?")
    k.add_argument("file", nargs="?", help="list only this file's findings, e.g. process-map/current-state.json")
    k.add_argument("--builtin", action="store_true", help="use the built-in JSON Schema subset checker")
    k.add_argument("--selftest", action="store_true", help="break the examples one rule at a time; every break must be caught")
    k.add_argument("--rules", action="store_true", help="print the citation rules table of formats/FORMATS.md section 2.3")
    k.set_defaults(fn=cmd_check)
    b = sub.add_parser("build", help="check, then the builders, then the build rules, into WS/out/")
    b.add_argument("workspace")
    b.add_argument("target", nargs="?", help="one page: section/name (e.g. document/request-handling-summary), or data-received "
                   "for the Original data received page; default: every page, that one included")
    b.add_argument("--builtin", action="store_true", help="use the built-in JSON Schema subset checker")
    b.add_argument("--prepare", metavar="OUTDIR", help="write what build hands the document and proposal builders, and build nothing")
    b.set_defaults(fn=cmd_build)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as x:
        if isinstance(x.code, str):
            print(x.code, file=sys.stderr)
            sys.exit(2)
        raise
    except BrokenPipeError:   # the reader stopped early (bs.py status WS | head): no traceback
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(1)

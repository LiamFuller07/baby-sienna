#!/usr/bin/env python3
"""Build a Source document from a small Markdown subset.

Usage:
  python3 build_doc.py <input.md> <output.html> [--a4|--screen] [--sources sources.json] [--strict]
                       [--data-links PREFIX]

  --a4       A4 sheets (default). Split sheets with a line "<!-- page -->".
  --screen   One long column for reading on screen. Prints onto numbered A4 pages.
  --sources  JSON object mapping each source id to its full name, either
             {"WB1": "Sample workbook, Sheet1"} or {"WB1": {"name": "...", "note": "..."}}.
             bs.py adds "points": {"<locator>": [{"locator", "text", "context"?}, ...]}, the
             verbatim records of each address the document cites, for --data-links.
  --strict   Treat every warning (such as a cited id with no name) as an error.
  --data-links  In a workspace (bs.py build passes "../"): each citation, a bracket or an address
             on a provenance line, prints as a small numbered marker linked to its row in
             the page's Citation points section, which replaces the Sources block. Each row
             prints the address, the verbatim records (the sources file's "points"), the
             headings it supports, and links to PREFIX + data-received.html#<ID> and
             PREFIX + citation-points.html#<anchor>. Without it the page is exactly as before.

The output is one self-contained HTML file: doc.css, the Source fonts and the
wordmark are inlined from this folder. Python 3 standard library only.

The Markdown subset (see README.md for examples):
  Front matter   ---  title: / label: / date: / footer:  ---   (first lines of the file)
  # Title (qualifier)       h1; a trailing "(...)" becomes the lighter qualifier
  > lead                    first ">" block after the h1 is the lead, a second one the support line
  ## Heading, ### Heading   h2 and h3
  paragraphs, **bold**, `code`, [text](url), fenced ``` code blocks
  - item                    bullet list; indent "  - item" for one nested level, and indent a
                            fenced block (two spaces or more) to put code inside a bullet or step
  1. item                   numbered steps (orange numeral column), counted up from the first number
  | a | b |                 pipe table, with |---|---:| alignment row
  ---                       rule
  [ID locator]              citation, e.g. [G1-S1 H9] or [G1-S1 H9; G2-CT R16]; \\[ for a literal [.
                            With a sources file, an id is a citation only when the file names it.
                            Without one, an id with a digit or hyphen is; [TBD], [API] and [TODO] stay text.
  Grounded · ... / Inferred · ... / Gap · ...   provenance line (a paragraph starting with one of these);
                            "Grounded · ID locator; ID locator", "Inferred · from ID ..."
  :::callout Title ... :::  the "Next step" callout; an :::aside Title block right after it forms the closing grid
  :::examples ... :::       examples grid; each item starts with "+++ eyebrow", then ### title,
                            an art block (```svg, any other fenced block, or ![alt](image)),
                            a short line and an optional caption, one line each
  :::columns ... :::        two-column section split at a "+++" line; without "+++", lists inside
                            it become two-column lists
  <!-- page -->             new A4 sheet (ignored with --screen); other HTML comments are dropped
"""

import base64
import html
import json
import mimetypes
import pathlib
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
FRONT_KEYS = {"title", "label", "date", "footer"}
ID = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*"
PROV = re.compile(r"^(Grounded|Inferred|Gap) · (.+)$", re.S)


class BuildError(Exception):
    pass


WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print(f"build_doc: warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------- blocks

# A fence may be indented (CommonMark allows up to 3 spaces; any indent is taken, so that an
# indented block is never read as inline code). Groups: indent, fence, language. The language is
# the first word of the info string; any words after it (```svg title) are ignored. A backtick
# fence's info string has no backticks, so ```a``` on one line stays inline code.
FENCE = re.compile(r"^([ \t]*)(```+|~~~+)[ \t]*([\w+-]*)(?:[ \t]+[^`]*?)?[ \t]*$")
DIRECTIVE = re.compile(r"^:::\s*([a-z]+)\s*(.*?)\s*$")
HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
RULE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
SEP = re.compile(r"^\+\+\+(?:\s+(.*?))?\s*$")
UL = re.compile(r"^[-*]\s+(.*)$")
OL = re.compile(r"^(\d{1,3})[.)]\s+(.*)$")
QUOTE = re.compile(r"^>\s?(.*)$")
TABLE_SEP = re.compile(r"^(?=.*\|)\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
PAGE = re.compile(r"^<!--\s*page\s*-->\s*$")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
SETEXT = re.compile(r"^=+\s*$")
# svg art is checked against an allowlist and written back out from the parsed tree, so the page
# gets only shapes, text and paint: nothing that runs, animates, styles the page or loads a file.
SVG_NS, XLINK_NS, XML_NS = (
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xlink",
    "http://www.w3.org/XML/1998/namespace",
)
SVG_TAGS = {
    "svg",
    "g",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "tspan",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "mask",
    "marker",
    "use",
    "title",
    "desc",
}
LINK_SCHEMES = {"http", "https", "mailto", "tel"}


def closes(fence, line):
    """A fence closes on a line of the same character, at least as long, and nothing else."""
    return re.fullmatch(re.escape(fence[0]) + "{" + str(len(fence)) + ",}", line.strip()) is not None


def dedent(line, k):
    """Remove up to k spaces of indentation (a fenced block's own indent) from a code line."""
    t = line.expandtabs(4)
    return t[min(k, len(t) - len(t.lstrip(" "))) :]


def read_fence(lines, i, fence, indent, no):
    """The code lines after an opening fence at lines[i], and the index after the closing fence."""
    body, i = [], i + 1
    while i < len(lines) and not closes(fence, lines[i][1]):
        body.append(dedent(lines[i][1], indent))
        i += 1
    if i >= len(lines):
        raise BuildError(f"line {no}: code fence {fence} is never closed")
    return "\n".join(body), i + 1


def split_row(row):
    """Split a table row on | that is neither escaped (\\|) nor inside a `code` span."""
    s = row.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    cells, cur, k, tick = [], "", 0, None
    while k < len(s):
        if s.startswith("\\|", k):
            cur, k = cur + "|", k + 2
        elif s[k] == "`":
            run = re.match(r"`+", s[k:]).group(0)
            if tick == run:
                tick = None
            elif tick is None and re.search(rf"(?<!`){run}(?!`)", s[k + len(run) :]):
                tick = run
            cur, k = cur + run, k + len(run)
        elif s[k] == "|" and tick is None:
            cells.append(cur.strip())
            cur, k = "", k + 1
        else:
            cur, k = cur + s[k], k + 1
    return cells + [cur.strip()]


def starts_block(lines, i):
    s = lines[i][1]
    return bool(
        FENCE.match(s)
        or DIRECTIVE.match(s)
        or HEADING.match(s)
        or RULE.match(s)
        or SEP.match(s)
        or UL.match(s)
        or OL.match(s)
        or QUOTE.match(s)
        or s.startswith("<!--")
        or (s.startswith("|") and i + 1 < len(lines) and TABLE_SEP.match(lines[i + 1][1]))
    )


def parse_list(lines, i, kind):
    """A bullet list or numbered steps from lines[i]. Each item is [text, kids], where a kid is
    ["ul", [texts]] (one nested level of bullets), ["code", lang, body] or ["p", text]: whatever
    is indented two spaces or more under the item, in order."""
    n, pat = len(lines), UL if kind == "ul" else OL
    items, sub_indent, blank = [], None, False
    while i < n:
        lno, t = lines[i][0], lines[i][1].expandtabs(4)
        m, fm = pat.match(t), FENCE.match(t)
        indent, body = len(t) - len(t.lstrip()), t.strip()
        kids = items[-1][1] if items else None
        last = kids[-1] if kids else None
        if m:
            items.append([m.group(m.lastindex), []])
            sub_indent, blank, i = None, False, i + 1
        elif items and indent >= 2 and fm:
            code, i = read_fence(lines, i, fm.group(2), indent, lno)
            kids.append(["code", fm.group(3), code])
            sub_indent, blank = None, False
        elif items and indent >= 2 and (UL.match(body) or OL.match(body)):
            # One level of nesting: an indented "- item" under a bullet or a step.
            if not UL.match(body):
                raise BuildError(
                    f"line {lno}: numbered lists cannot be nested; indent '- item' bullets instead, or use template.html"
                )
            if sub_indent is None:
                sub_indent = indent
            elif indent > sub_indent:
                raise BuildError(f"line {lno}: lists nest one level only; use template.html for deeper lists")
            if last and last[0] == "ul":
                last[1].append(UL.match(body).group(1))
            else:
                kids.append(["ul", [UL.match(body).group(1)]])
            blank, i = False, i + 1
        elif items and indent >= 2 and body:
            if blank or (last and last[0] == "code"):
                kids.append(["p", body])  # a new paragraph inside the item
            elif last and last[0] == "ul":
                last[1][-1] += " " + body  # a wrapped line of the nested bullet
            elif last:
                last[1] += " " + body
            else:
                items[-1][0] += " " + body
            blank, i = False, i + 1
        elif (
            not body
            and i + 1 < n
            and (
                pat.match(lines[i + 1][1])
                or (items and lines[i + 1][1].startswith((" ", "\t")) and lines[i + 1][1].strip())
            )
        ):
            blank, i = True, i + 1
        else:
            break
    return items, i


def parse_blocks(lines):
    """lines: list of (line_number, text). Returns a list of block tuples."""
    lines = list(lines)  # a comment that ends mid-line leaves the rest of that line to parse
    out, i, n = [], 0, len(lines)
    while i < n:
        no, s = lines[i]
        if not s.strip():
            i += 1
            continue
        m = FENCE.match(s)
        if m:
            code, i = read_fence(lines, i, m.group(2), len(m.group(1).expandtabs(4)), no)
            out.append(("code", m.group(3), code))
            continue
        m = DIRECTIVE.match(s)
        if m:
            name, arg, body, i, in_fence = m.group(1), m.group(2), [], i + 1, None
            while i < n:
                t = lines[i][1]
                f = FENCE.match(t)
                if in_fence:
                    if closes(in_fence, t):
                        in_fence = None
                elif f:
                    in_fence = f.group(2)
                elif t.strip() == ":::":
                    break
                elif DIRECTIVE.match(t):
                    raise BuildError(
                        f"line {lines[i][0]}: ::: blocks cannot be nested (inside :::{name} from line {no})"
                    )
                body.append(lines[i])
                i += 1
            if i >= n:
                raise BuildError(f"line {no}: :::{name} is never closed with a ::: line")
            if name not in ("callout", "aside", "examples", "columns"):
                raise BuildError(
                    f"line {no}: unknown block :::{name} (use callout, aside, examples or columns)"
                )
            out.append(("dir", name, arg, body, no))
            i += 1
            continue
        if s.strip() == ":::":
            raise BuildError(f"line {no}: ::: closes nothing")
        if s.startswith("<!--"):
            # Dropped, except <!-- page -->. Text after the closing --> on the same line is kept.
            j = i
            while j < n and "-->" not in lines[j][1][4 if j == i else 0 :]:
                j += 1
            if j >= n:
                raise BuildError(f"line {no}: HTML comment is never closed")
            end = lines[j][1].index("-->", 4 if j == i else 0) + 3
            if j == i and PAGE.match(s[:end]):
                out.append(("page", no))
            rest = lines[j][1][end:].lstrip()
            if rest:
                lines[j] = (lines[j][0], rest)
                i = j
            else:
                i = j + 1
            continue
        m = HEADING.match(s)
        if m:
            out.append(("h", len(m.group(1)), m.group(2)))
            i += 1
            continue
        if RULE.match(s):
            out.append(("hr",))
            i += 1
            continue
        m = SEP.match(s)
        if m:
            out.append(("sep", m.group(1) or "", no))
            i += 1
            continue
        if QUOTE.match(s):
            text = []
            while i < n and QUOTE.match(lines[i][1]):
                text.append(QUOTE.match(lines[i][1]).group(1))
                i += 1
            out.append(("quote", " ".join(t.strip() for t in text)))
            continue
        if UL.match(s) or OL.match(s):
            kind = "ul" if UL.match(s) else "ol"
            start = int(OL.match(s).group(1)) if kind == "ol" else None
            items, i = parse_list(lines, i, kind)
            out.append((kind, items, start))
            continue
        if s.startswith("|") and i + 1 < n and TABLE_SEP.match(lines[i + 1][1]):
            head, aligns = split_row(s), []
            for c in split_row(lines[i + 1][1]):
                aligns.append(
                    "right"
                    if c.endswith(":") and not c.startswith(":")
                    else "center"
                    if c.startswith(":") and c.endswith(":")
                    else ""
                )
            rows, i = [], i + 2
            while i < n and lines[i][1].startswith("|"):
                row = split_row(lines[i][1])
                if len(row) > len(head):
                    warn(
                        f"line {lines[i][0]}: this table row has {len(row)} cells and the header {len(head)}; "
                        f"the extra cells are dropped (write \\| for a | inside a cell)"
                    )
                rows.append((row + [""] * len(head))[: len(head)])  # a short row gets empty cells
                i += 1
            out.append(("table", head, aligns, rows))
            continue
        para = [s.strip()]
        i += 1
        while i < n and lines[i][1].strip() and not starts_block(lines, i):
            if SETEXT.match(lines[i][1].strip()):
                warn(
                    f"line {lines[i][0]}: a line of = under text is a setext heading, which the builder does not "
                    "read; write ## Heading instead (the = line is left out)"
                )
                i += 1
                break
            para.append(lines[i][1].strip())
            i += 1
        if i < n and RULE.match(lines[i][1]) and lines[i][1].strip().startswith("-"):
            warn(
                f"line {lines[i][0]}: --- straight under text is a rule here, not a heading; "
                "leave a blank line before a rule, or write ## Heading"
            )
        out.append(("p", " ".join(para), para, no))  # the source lines are kept for :::examples
    return out


# ---------------------------------------------------------------- inline


def point_anchor(sid, loc, needle=None):
    """--data-links: a citation point's anchor in citation-points.html (formats/FORMATS.md section 2.6):
    src- plus the address in lower case, ¶ written para, other runs written -; an absent search
    adds -not- and its needle."""
    s = f"{sid} {loc}" if loc else sid
    a = "src-" + re.sub(r"[^a-z0-9]+", "-", s.lower().replace("¶", "para")).strip("-")
    if needle is None:
        return a
    return (
        a
        + "-not-"
        + (re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", needle).lower()).strip("-") or "x")
    )


class Doc:
    def __init__(self, sources, base, sources_given=False, data=None):
        self.sources = sources  # id -> {"name", "note"}
        self.given = sources_given  # a --sources file was passed
        self.base = base  # folder of the input file (for images)
        self.data = data  # --data-links prefix, or None
        self.used = []  # source ids in order of first use
        self.points = {}  # --data-links: anchor -> citation point, numbered in order of first use
        self.cur = ("Title and lead", "intro")  # --data-links: the element a citation supports, its heading
        self.known = set(sources)
        self.slugs = set()

    def use(self, sid):
        if sid not in self.used:
            self.used.append(sid)

    def missing(self, sid):
        """True when a sources file was given and does not name this id."""
        return self.given and sid not in self.sources

    @staticmethod
    def looks_cited(sid, loc):
        """An ID-shaped bracket part that reads like a citation rather than a word such as [TBD] or
        [API]: an id with a digit or hyphen ([WB1 H9], [G1-S1]), or an id followed by a locator that
        holds a digit, a § or a short capital token ([DOC §2], [DOC col H]). [TODO fix this] does not."""
        return bool(re.search(r"[\d-]", sid)) or (bool(loc) and bool(re.search(r"[\d§]|\b[A-Z]{1,3}\b", loc)))

    def is_source(self, sid, loc):
        """With a sources file, the file decides: only the ids it names are cited, so that prose such
        as [Q1 2024] stays text. Without one, an id that looks cited is."""
        return sid in self.sources if self.given else self.looks_cited(sid, loc)

    def parse_bracket(self, inner, quiet=True):
        """'G1-S1 H9; G2-CT R16' -> [(id, locator)], or None when the bracket is not a citation."""
        parts = [p.strip() for p in inner.split(";")]
        found = [re.fullmatch(rf"({ID})(?:\s+(.+))?", p) for p in parts]
        if not all(found):
            if not quiet:
                for p in parts:
                    low = re.fullmatch(r"([a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?:\s+.+)?", p)
                    if low and low.group(1).upper() in self.known:
                        warn(
                            f"[{inner}] looks like a citation of {low.group(1).upper()} in lower case; left as text"
                        )
            return None
        pairs = [(f.group(1), f.group(2)) for f in found]
        if all(self.is_source(sid, loc) for sid, loc in pairs):
            return pairs
        odd = list(
            dict.fromkeys(
                sid for sid, loc in pairs if not self.is_source(sid, loc) and self.looks_cited(sid, loc)
            )
        )
        # With a sources file, a bracket that names at least one of its ids, and whose other parts
        # all look cited, is a citation: the unnamed ids are cited as missing (a Gap row in Sources)
        # rather than turning the whole bracket back into text.
        if (
            self.given
            and any(self.is_source(sid, loc) for sid, loc in pairs)
            and all(self.is_source(sid, loc) or self.looks_cited(sid, loc) for sid, loc in pairs)
        ):
            if not quiet:
                warn(
                    f"[{inner}] cites unknown id {', '.join(odd)}; it is marked missing: add it to the sources file"
                )
            return pairs
        if not quiet and self.given and odd:
            warn(
                f"[{inner}] is left as text: possible citation of unknown id {', '.join(odd)}; "
                f"add it to the sources file, or write \\[{inner}] if it is not a citation"
            )
        return None

    def cite(self, sid, loc):
        """loc arrives HTML-escaped. A long locator (spaces, or over 16 characters) goes in a .loc
        span that may wrap on a narrow screen; the id and the brackets never split."""
        self.use(sid)
        cls = "c missing" if self.missing(sid) else "c"
        if not loc:
            return f'<cite class="{cls}" data-src="{sid}"><a href="#src-{sid}">{sid}</a></cite>'
        label = f'<span class="loc">{loc}</span>' if " " in loc or len(html.unescape(loc)) > 16 else loc
        return f'<cite class="{cls}" data-src="{sid}" data-loc="{loc}"><a href="#src-{sid}">{sid} {label}</a></cite>'

    def point(self, sid, loc, kind="grounded", needle=None):
        """--data-links: the citation point of an address (with its needle, for an absent search), numbered in
        order of first use, and used by the heading the citation sits under."""
        self.use(sid)
        a = point_anchor(sid, loc, needle)
        p = self.points.setdefault(
            a, {"n": len(self.points) + 1, "anchor": a, "sid": sid, "loc": loc, "needle": needle, "uses": []}
        )
        if (kind, *self.cur) not in p["uses"]:
            p["uses"].append((kind, *self.cur))
        return p

    def marks(self, pts):
        """--data-links: one superscript of numbered markers, ³ or ³,⁷, each linked to its row in Citation
        points; hover or focus shows the address and the first words of its verbatim text (doc.css)."""
        out = []
        for p in sorted({p["n"]: p for p in pts}.values(), key=lambda p: p["n"]):
            cls = "cp-mk missing" if self.missing(p["sid"]) else "cp-mk"
            out.append(
                f'<a class="{cls}" href="#{p["anchor"]}" data-tip="{html.escape(self.tip(p), quote=True)}" '
                f'aria-label="Citation {p["n"]}: {html.escape(address(p), quote=True)}">{p["n"]}</a>'
            )
        return f'<sup class="cp-mks">{",".join(out)}</sup>'

    def records(self, p):
        """The verbatim records of a point, from the sources file's points."""
        return (self.sources.get(p["sid"]) or {}).get("points", {}).get(p["loc"] or "") or []

    def tip(self, p):
        if p["needle"] is not None:
            return f"{address(p)} · searched for “{p['needle']}”: not found"
        recs = self.records(p)
        words = recs[0]["text"].split() if recs else []
        if not words:
            return f"{address(p)} · no verbatim text in the sources file"
        return f"{address(p)} · “{' '.join(words[:8])}{'…' if len(words) > 8 else ''}”"

    def prov_marks(self, word, rest):
        """--data-links: a provenance line as a map prints one, its addresses as numbered markers: Grounded³,⁴,
        Inferred · <reading>⁵, Gap · “needle” not found⁶. None when the line does not read as FORMATS.md
        section 4 writes it (then it renders as before)."""
        needle, head, kind = None, "", {"Grounded": "grounded", "Inferred": "inferred", "Gap": "absent"}[word]
        if word == "Inferred":
            m = re.fullmatch(r"(.+?) · from (.+)", rest, re.S)
            if not m:
                return None
            head, refs = f" · {self.inline(m.group(1))}", m.group(2)
        elif word == "Gap":
            m = re.fullmatch(r"not in (.+?): “([^”]+)”", rest, re.S)
            if not m:
                return None
            refs, needle = m.group(1), m.group(2)
            head = f" · “{html.escape(needle)}” not found"
        else:
            refs = rest
        pairs = []
        for part in refs.split(";"):
            part = part.strip()
            if part.startswith("[") and part.endswith("]"):
                part = part[1:-1].strip()
            f = re.fullmatch(rf"({ID})(?:\s+(.+))?", part)
            if not f or (not f.group(2) and word != "Gap"):
                return None
            pairs.append((f.group(1), f.group(2)))
        return head + self.marks([self.point(sid, loc, kind, needle) for sid, loc in pairs])

    def inline(self, text):
        keep = []

        def hold(fragment):
            keep.append(fragment)
            return f"\x00{len(keep) - 1}\x00"

        text = re.sub(
            r"(`+)(.+?)\1",
            lambda m: hold(f"<code>{html.escape(m.group(2).strip(), quote=False)}</code>"),
            text,
        )
        text = re.sub(r"<!--.*?-->", "", text)  # a comment inside a line is dropped too
        text = re.sub(r"\\([\\`*\[\]_#+.!|-])", lambda m: hold(html.escape(m.group(1))), text)
        im = IMAGE.search(text)
        if im:
            raise BuildError(
                f"image {im.group(0)} is outside :::examples; images go in an :::examples item "
                "as the art, or use template.html"
            )
        text = html.escape(text, quote=True)

        def link(m):
            # Browsers drop control characters and edge spaces from a URL before reading its
            # scheme, so the check does too, and the page gets the cleaned URL it checked.
            url = re.sub(r"[\x00-\x1f\x7f]", "", html.unescape(m.group(2))).strip()
            scheme = re.match(r"([A-Za-z][A-Za-z0-9+.-]*):", url)
            if scheme and scheme.group(1).lower() not in LINK_SCHEMES:
                raise BuildError(
                    f"link target not allowed: {url!r} (use http:, https:, mailto:, tel:, "
                    "a #fragment or a relative path)"
                )
            return hold(f'<a href="{html.escape(url, quote=True)}">{self.bold(m.group(1))}</a>')

        text = re.sub(r"\[([^\[\]]+)\]\(([^)\s]+)\)", link, text)

        def cites(m):
            # The text is HTML-escaped by now, and an escape such as &quot; holds a ";", so the
            # bracket is parsed as written and each locator is escaped again for the page.
            # --data-links: the bracket prints as its numbered markers, on the word before it.
            pairs = self.parse_bracket(html.unescape(m.group(2)), quiet=False)
            if not pairs:
                return m.group(0)
            if self.data is not None:
                return hold(self.marks([self.point(sid, loc) for sid, loc in pairs]))
            marks = [self.cite(sid, html.escape(loc, quote=True) if loc else loc) for sid, loc in pairs]
            return m.group(1) + hold(
                marks[0] if len(marks) == 1 else f'<span class="cites">{"; ".join(marks)}</span>'
            )

        text = re.sub(r"(\s*)\[([^\[\]]+)\]", cites, text)
        text = self.bold(text)
        while "\x00" in text:
            text = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)
        return text

    @staticmethod
    def bold(text):
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    def link_ids(self, fragment):
        """Link bare source ids in a provenance line (ids from --sources or cited elsewhere)."""
        ids = sorted(self.known, key=len, reverse=True)
        if not ids:
            return fragment
        pat = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, ids)) + r")(?![\w-])")
        out, depth = [], 0
        for piece in re.split(r"(<[^>]+>)", fragment):
            if piece.startswith("<"):
                if re.match(r"<(a|code|cite)\b", piece):
                    depth += 1
                elif re.match(r"</(a|code|cite)>", piece):
                    depth -= 1
                out.append(piece)
            elif depth:
                out.append(piece)
            else:

                def repl(m):
                    self.use(m.group(1))
                    cls = ' class="missing"' if self.missing(m.group(1)) else ""
                    return f'<a href="#src-{m.group(1)}"{cls}>{m.group(1)}</a>'

                out.append(pat.sub(repl, piece))
        return "".join(out)

    def slug(self, text):
        base = (
            re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>|\[[^\]]*\]", "", text).lower()).strip("-")
            or "section"
        )
        s, k = base, 2
        while s in self.slugs:
            s, k = f"{base}-{k}", k + 1
        self.slugs.add(s)
        return s


def prov_ids(word, rest):
    """The source ids a provenance line names, and the first part that does not read 'ID locator'.
    A Grounded line is 'ID locator; ID locator'. An Inferred line names its source after 'from'."""
    if word == "Grounded":
        ids = []
        for part in rest.split(";"):
            m = re.match(rf"\s*\[?({ID})(?![\w-])", part)
            if not m:
                return ids, part.strip()
            ids.append(m.group(1))
        return ids, None
    if word == "Inferred":
        return re.findall(rf"\bfrom\s+\[?({ID})(?![\w-])", rest), None
    return [], None


def collect_ids(blocks, doc):
    """Before rendering, learn every source id the document uses, so that provenance lines can
    link an id that is cited only later, or only as the second entry of a shared bracket."""
    for b in blocks:
        kind, texts = b[0], []
        if kind in ("p", "quote"):
            texts = [b[1]]
            m = PROV.match(b[1]) if kind == "p" else None
            if m:
                doc.known.update(prov_ids(m.group(1), m.group(2))[0])
        elif kind == "h":
            texts = [b[2]]
        elif kind in ("ul", "ol"):
            texts = [t for text, kids in b[1] for t in [text, *kid_texts(kids)]]
        elif kind == "table":
            texts = b[1] + [c for row in b[3] for c in row]
        elif kind == "sep":
            texts = [b[1]]
        elif kind == "dir":
            texts = [b[2]]
            collect_ids(parse_blocks(b[3]), doc)
        for t in texts:
            t = re.sub(r"(`+).+?\1|\\.", "", t)
            for inner in re.findall(r"\[([^\[\]]+)\](?!\()", t):
                doc.known.update(sid for sid, _ in doc.parse_bracket(inner) or [])


# ---------------------------------------------------------------- render


def render(blocks, doc, two_col_lists=False):
    out, i = [], 0
    while i < len(blocks):
        b = blocks[i]
        kind = b[0]
        if kind == "h":
            level, text = b[1], b[2]
            if level == 1:
                raise BuildError("only one # title is allowed, at the top of the document")
            hid = doc.slug(text)
            doc.cur = (re.sub(r"\*\*|`|\s*\[[^\]]*\]", "", text).strip() or "Heading", hid)
            out.append(f'<h{level} id="{hid}">{doc.inline(text)}</h{level}>')
        elif kind == "p":
            m = PROV.match(b[1])
            if m:
                word, rest = m.group(1), m.group(2)
                ids, bad = prov_ids(word, rest)
                if bad is not None:
                    warn(
                        f"line {b[3]}: a Grounded line reads 'ID locator; ID locator', but '{bad}' does not start with a source id"
                    )
                doc.known.update(ids)
                for sid in ids:
                    doc.use(sid)
                marked = doc.prov_marks(word, rest) if doc.data is not None else None
                tail = " · " + doc.link_ids(doc.inline(rest)) if marked is None else marked
                out.append(f'<p class="prov prov-{word.lower()}"><b>{word}</b>{tail}</p>')
            else:
                out.append(f"<p>{doc.inline(b[1])}</p>")
        elif kind == "quote":
            out.append(f'<p class="lead">{doc.inline(b[1])}</p>')
        elif kind == "hr":
            out.append("<hr>")
        elif kind == "ul":
            cls = ' class="two"' if two_col_lists else ""
            out.append(
                f"<ul{cls}>"
                + "".join(f"<li>{doc.inline(t)}{kids_html(kids, doc)}</li>" for t, kids in b[1])
                + "</ul>"
            )
        elif kind == "ol":
            # Numbered from the first item and counting up, so "1. 1. 1." reads 01 02 03.
            items = "".join(
                f'<li><span class="num">{b[2] + k:02d}</span><p>{doc.inline(t)}</p>{kids_html(kids, doc)}</li>'
                for k, (t, kids) in enumerate(b[1])
            )
            out.append(f'<ol class="steps">{items}</ol>')
        elif kind == "code":
            out.append(code_html(b[1], b[2]))
        elif kind == "page":
            # Sheets are split at the top level only; build() takes those out before rendering.
            warn(f"line {b[1]}: <!-- page --> inside a ::: block is ignored; put it between blocks")
        elif kind == "table":
            head, aligns, rows = b[1], b[2], b[3]

            def st(k, aligns=aligns):
                return f' style="text-align:{aligns[k]}"' if k < len(aligns) and aligns[k] else ""

            th = "".join(f"<th{st(k)}>{doc.inline(c)}</th>" for k, c in enumerate(head))
            body = "".join(
                "<tr>" + "".join(f"<td{st(k)}>{doc.inline(c)}</td>" for k, c in enumerate(r)) + "</tr>"
                for r in rows
            )
            out.append(
                f'<div class="table"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'
            )
        elif kind == "dir":
            outer = doc.cur  # a heading inside the block holds only to the block's end
            name, arg, body, no = b[1], b[2], parse_blocks(b[3]), b[4]
            title = f"<h2>{doc.inline(arg)}</h2>" if arg else ""
            if name == "callout":
                callout = f'<section class="callout">{title}{render(body, doc)}</section>'
                nxt = blocks[i + 1] if i + 1 < len(blocks) else None
                if nxt and nxt[0] == "dir" and nxt[1] == "aside":
                    aside_title = f"<h2>{doc.inline(nxt[2])}</h2>" if nxt[2] else ""
                    aside = f"<aside>{aside_title}{render(parse_blocks(nxt[3]), doc)}</aside>"
                    out.append(f'<div class="closing">{callout}{aside}</div>')
                    i += 1
                else:
                    out.append(callout)
            elif name == "aside":
                out.append(f"<aside>{title}{render(body, doc)}</aside>")
            elif name == "columns":
                parts, cur = [], []
                for x in body:
                    if x[0] == "sep":
                        parts.append(cur)
                        cur = []
                    else:
                        cur.append(x)
                parts.append(cur)
                if len(parts) == 1:
                    out.append(render(parts[0], doc, two_col_lists=True))
                else:
                    if len(parts) != 2:
                        raise BuildError(f"line {no}: :::columns takes one +++ line (two columns)")
                    out.append(
                        '<div class="columns">'
                        + "".join(f"<section>{render(p, doc)}</section>" for p in parts)
                        + "</div>"
                    )
            elif name == "examples":
                out.append(render_examples(body, doc, no))
            doc.cur = outer
        elif kind == "sep":
            raise BuildError(f"line {b[2]}: +++ is only used inside :::columns or :::examples")
        i += 1
    return "".join(out)


def render_examples(body, doc, no):
    items = []
    for x in body:
        if x[0] == "page":
            warn(f"line {x[1]}: <!-- page --> inside :::examples is ignored; put it between blocks")
        elif x[0] == "sep":
            items.append([x[1], []])
        elif not items:
            raise BuildError(f"line {no}: each :::examples item starts with a '+++ eyebrow' line")
        else:
            items[-1][1].append(x)
    if not items:
        raise BuildError(f"line {no}: :::examples has no items")
    html_items = []
    for eyebrow, blocks in items:
        art, title, texts = "", "", []
        for x in blocks:
            if x[0] == "code" and not art:
                if x[1] == "svg":
                    art = clean_svg(x[2], f"line {no}, item '{eyebrow}'")
                else:
                    rows = x[2].split("\n")
                    cols = max(len(r) for r in rows)
                    if len(rows) > 8 or cols > 32:
                        warn(
                            f"line {no}: the code art in '{eyebrow}' is {len(rows)} lines, up to {cols} columns; "
                            "a panel shows about 8 lines of 32 columns, so it wraps and fades out at the foot"
                        )
                    art = code_html(x[1], x[2])
            elif x[0] == "h" and x[1] == 3 and not title:
                title = f"<h3>{doc.inline(x[2])}</h3>"
            elif x[0] == "p":
                # Each line of text is one part: the short line, then the caption. A blank line
                # between them is optional. An image line before them is the art.
                for ln in x[2]:
                    im = IMAGE.match(ln)
                    if im and (art or texts):
                        raise BuildError(
                            f"line {x[3]}: an example item has one art block, and an image art comes before the short line"
                        )
                    if im:
                        art = image(im.group(0), doc)
                        if ln[im.end() :].strip():
                            texts.append(ln[im.end() :].strip())
                    else:
                        texts.append(ln)
            else:
                raise BuildError(
                    f"line {no}: an example item holds a ### title, one art block, a short line and a caption"
                )
        if len(texts) > 2:
            raise BuildError(
                f"line {no}: the item '{eyebrow}' has {len(texts)} lines of text; it takes a short line and a caption, one line each"
            )
        if not art:
            warn(
                f"line {no}: the item '{eyebrow}' has no art, so its panel is empty; "
                "add a ```svg block, a code block or an ![alt](image) line"
            )
        line = f"<p>{doc.inline(texts[0])}</p>" if texts else ""
        cap = f'<p class="caption">{doc.inline(texts[1])}</p>' if len(texts) > 1 else ""
        eb = f'<p class="eyebrow">{doc.inline(eyebrow)}</p>' if eyebrow else ""
        html_items.append(
            f'<article class="example"><div class="art">{art}</div>{eb}{title}{line}{cap}</article>'
        )
    return '<div class="examples">' + "".join(html_items) + "</div>"


def clean_svg(src, where):
    """Check svg art against the allowlist and return it re-serialised from the parsed tree, so the
    page holds exactly what was checked (no comments, no markup outside the one <svg> root)."""

    def refuse(why):
        raise BuildError(f"{where}: svg art draws only shapes, text and paint; {why}")

    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", src, re.I):
        refuse("a DOCTYPE or ENTITY is not allowed")
    try:
        root = ET.fromstring(src.strip())
    except ET.ParseError as e:
        hint = "; write &#160; for a non-breaking space" if "undefined entity" in str(e) else ""
        refuse(f"it must be well-formed XML with one <svg> root ({e}){hint}")
    for el in root.iter():
        ns, _, local = el.tag[1:].rpartition("}") if el.tag.startswith("{") else ("", "", el.tag)
        if ns not in ("", SVG_NS) or local not in SVG_TAGS:
            refuse(f"<{local}> is not allowed (allowed: {', '.join(sorted(SVG_TAGS))})")
        el.tag = local
        attrs = {}
        for key, value in el.attrib.items():
            ans, _, name = key[1:].rpartition("}") if key.startswith("{") else ("", "", key)
            if ans not in ("", XLINK_NS, XML_NS):
                refuse(f"the attribute {key} is not allowed")
            plain = re.sub(r"[\x00-\x20\x7f]", "", value).lower()
            if name.lower().startswith("on"):
                refuse(f"the event handler {name} is not allowed")
            if (
                "javascript:" in plain
                or "@import" in plain
                or "expression(" in plain
                or (name == "style" and "\\" in value)
            ):
                refuse(f'{name}="{value}" is not allowed')
            if name == "href" and not re.match(r"#|data:image/", plain):
                refuse(f'{name}="{value}" may point only at #id or a data:image')
            for target in re.findall(r"url\(['\"]?([^'\")]*)", plain):
                if not re.match(r"#|data:image/", target):
                    refuse(f"url({target}) may point only at #id or a data:image")
            attrs["xml:" + name if ans == XML_NS else name] = value  # xlink:href becomes href (SVG 2)
        el.attrib.clear()
        el.attrib.update(attrs)
    if root.tag != "svg":
        refuse(f"the root must be <svg>, not <{root.tag}>")
    return ET.tostring(root, encoding="unicode")


def code_html(lang, body):
    cls = f' class="lang-{lang}"' if lang else ""
    return f"<pre><code{cls}>{html.escape(body, quote=False)}</code></pre>"


def kid_texts(kids):
    """The prose inside a list item's kids (nested bullets and paragraphs), for collecting ids."""
    return [t for k in kids if k[0] != "code" for t in (k[1] if k[0] == "ul" else [k[1]])]


def kids_html(kids, doc):
    """What sits under a bullet or a step: one nested level of bullets, code blocks, paragraphs."""
    out = []
    for k in kids:
        if k[0] == "ul":
            out.append("<ul>" + "".join(f"<li>{doc.inline(t)}</li>" for t in k[1]) + "</ul>")
        elif k[0] == "code":
            out.append(code_html(k[1], k[2]))
        else:
            out.append(f"<p>{doc.inline(k[1])}</p>")
    return "".join(out)


def image(md, doc):
    alt, src = IMAGE.fullmatch(md).groups()
    path = (doc.base / src).resolve()
    if not path.is_file():
        raise BuildError(f"image not found: {src}")
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in ("image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"):
        raise BuildError(f"image type not supported: {src}")
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:{mime};base64,{data}" alt="{html.escape(alt)}">'


# ---------------------------------------------------------------- page


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def inline_css():
    css = (HERE / "doc.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(
        r"url\(fonts/([\w.-]+\.ttf)\)",
        lambda m: f"url({data_uri(HERE / 'fonts' / m.group(1), 'font/ttf')})",
        css,
    )
    return "\n".join(line.rstrip() for line in css.splitlines() if line.strip())


def front_matter(lines):
    meta = {}
    if lines and lines[0][1].strip() == "---":
        for k in range(1, len(lines)):
            s = lines[k][1]
            if s.strip() == "---":
                return meta, lines[k + 1 :]
            m = re.match(r"^([A-Za-z]+)\s*:\s*(.*?)\s*$", s)
            if not m:
                raise BuildError(f"line {lines[k][0]}: front matter lines read 'key: value'")
            key = m.group(1).lower()
            key = "label" if key == "context" else key
            if key not in FRONT_KEYS:
                warn(
                    f"line {lines[k][0]}: unknown front matter key '{key}' (known: {', '.join(sorted(FRONT_KEYS))})"
                )
            meta[key] = m.group(2).strip("\"'")
        raise BuildError("front matter starts with --- but is never closed")
    return meta, lines


def load_sources(path):
    if not path:
        return {}
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BuildError("--sources must be a JSON object of id -> name")
    out = {}
    for sid, v in raw.items():
        if not re.fullmatch(ID, sid):
            raise BuildError(f"source id '{sid}' must look like G1-S1 (capitals, digits, hyphens)")
        out[sid] = (
            {"name": v, "note": ""}
            if isinstance(v, str)
            else {"name": v.get("name", ""), "note": v.get("note", ""), "points": v.get("points") or {}}
        )
    return out


def sources_block(doc):
    if not doc.used:
        return ""
    order = [s for s in doc.sources if s in doc.used] + [s for s in doc.used if s not in doc.sources]
    rows = []
    for sid in order:
        src = doc.sources.get(sid)
        if src:
            note = f' <span class="note">· {html.escape(src["note"])}</span>' if src["note"] else ""
            text = html.escape(src["name"]) + note
        else:
            warn(f"source {sid} is cited but has no name (add it to the --sources file)")
            why = "no name in the sources file" if doc.given else "no name given (no sources file)"
            text = f'<span class="missing"><b>Gap</b> · {why}</span>'
        sid_html = (
            sid
            if doc.data is None
            else f'<a href="{html.escape(doc.data, quote=True)}data-received.html#{sid}">{sid}</a>'
        )
        rows.append(f'<li id="src-{sid}"><b>{sid_html}</b><span>{text}</span></li>')
    if doc.data is not None:
        return points_section(doc, rows)
    return f'<section class="sources" id="sources"><h2>Sources</h2><ol>{"".join(rows)}</ol></section>'


USE_WORD = {"grounded": "Grounded", "inferred": "Inferred from", "absent": "Absent search"}  # as on a map


def address(p):
    return f"{p['sid']} {p['loc']}" if p["loc"] else p["sid"]


def plural(n, one):
    return f"{n} {one if n == 1 else one + 's'}"


def verbatim(doc, p):
    """A point's verbatim text, as a map's Citation points prints it: an absent search, one record (with its
    context), or a span's records."""
    if p["needle"] is not None:
        return f'<span class="cp-absent">Searched for “{html.escape(p["needle"])}”: not found</span>'
    recs = doc.records(p)
    if not recs:
        warn(f"{address(p)} has no verbatim records in the sources file (its points)")
        return '<span class="cp-absent">No verbatim text in the sources file</span>'
    if len(recs) == 1 and recs[0].get("locator") == p["loc"]:
        r = recs[0]
        ctx = f"{html.escape(r['context'])} · " if r.get("context") else ""
        return f"{ctx}<q>{html.escape(r['text'])}</q>"
    text = " · ".join(f"<q>{html.escape(r['text'])}</q>" for r in recs[:10])
    more = f" · and {len(recs) - 10} more" if len(recs) > 10 else ""
    return f'<span class="cp-recs">{text}{more}</span>'


def points_section(doc, sources):
    """--data-links: the Sources block extended as the page's Citation points section (FORMATS.md section 2.6):
    its sources, one line each (#src-<ID>), then one row per point, numbered as its markers, at the point's
    anchor: the address, the verbatim text, the headings it supports, and links back to the data."""
    d = html.escape(doc.data, quote=True)
    rows = []
    for p in doc.points.values():
        sid, a = p["sid"], p["anchor"]
        uses = {}
        for kind, label, hid in p["uses"]:
            uses.setdefault(kind, []).append(f'<a href="#{hid}">{html.escape(label)}</a>')
        used = "".join(
            f'<span class="cp-use"><b>{USE_WORD[k]}</b> · {", ".join(uses[k])}</span>'
            for k in USE_WORD
            if k in uses
        )
        rows.append(
            f'<li class="cp-row" id="{a}"><span class="cp-n">{p["n"]}</span>'
            f'<a class="cp-addr" href="{d}data-received.html#{sid}" title="Open {sid} in Original data received">'
            f'{html.escape(address(p))}</a><span class="cp-text">{verbatim(doc, p)}</span>'
            f'<span class="cp-used">{used}</span><a class="cp-all" href="{d}citation-points.html#{a}" '
            f'aria-label="Point {p["n"]} in Citation points" title="Open in Citation points">↗</a></li>'
        )
    count = f"{plural(len(rows), 'point')} from {plural(len(sources), 'record')}"
    return (
        '<section class="cp" id="citation-points" aria-labelledby="cp-h"><div class="cp-head">'
        f'<h2 id="cp-h">Citation points</h2><span class="cp-count">{count}</span></div>'
        f'<ol class="cp-srcs">{"".join(sources)}</ol><ol class="cp-list">{"".join(rows)}</ol></section>'
    )


def build(md_path, mode, sources_path, data=None):
    text = pathlib.Path(md_path).read_text(encoding="utf-8")
    lines = list(enumerate(text.splitlines(), start=1))
    meta, lines = front_matter(lines)
    doc = Doc(
        load_sources(sources_path), pathlib.Path(md_path).resolve().parent, sources_path is not None, data
    )
    if data is not None:
        doc.slugs.update({"intro", "citation-points", "cp-h"})  # the ids the page itself gives
    blocks = parse_blocks(lines)
    collect_ids(blocks, doc)

    # The intro: the # title and the ">" blocks right after it.
    intro, h1_text = "", ""
    if blocks and blocks[0][0] == "h" and blocks[0][1] == 1:
        h1_text = blocks[0][2]
        m = re.fullmatch(r"(.*?)\s*(\([^()]+\))", h1_text)
        h1 = doc.inline(m.group(1)) + f" <span>{doc.inline(m.group(2))}</span>" if m else doc.inline(h1_text)
        k, quotes = 1, []
        while k < len(blocks) and blocks[k][0] == "quote" and len(quotes) < 2:
            quotes.append(blocks[k][1])
            k += 1
        intro = f"<h1>{h1}</h1>"
        if quotes:
            intro += f'<p class="lead">{doc.inline(quotes[0])}</p>'
        if len(quotes) > 1:
            intro += f'<p class="support">{doc.inline(quotes[1])}</p>'
        # --data-links: the element a citation in the title or lead supports
        intro_id = "" if data is None else ' id="intro"'
        intro = f'<section class="intro"{intro_id}>{intro}</section>'
        blocks = blocks[k:]

    sheets, cur = [], []
    for b in blocks:
        if b[0] == "page":
            if mode == "a4":
                sheets.append(cur)
                cur = []
        else:
            cur.append(b)
    sheets.append(cur)
    bodies = [render(s, doc) for s in sheets]
    bodies[0] = intro + bodies[0]
    bodies[-1] += sources_block(doc)

    title = meta.get("title") or re.sub(r"\*\*|`", "", h1_text) or pathlib.Path(md_path).stem
    logo = data_uri(HERE / "fonts" / "source-wordmark.png", "image/png")
    label = f"<span>{html.escape(meta['label'])}</span>" if meta.get("label") else ""
    header = f'<header><img src="{logo}" alt="Source">{label}</header>'
    left = " / ".join(html.escape(meta[k]) for k in ("footer", "date") if meta.get(k))

    pages = []
    for n, body in enumerate(bodies, start=1):
        folio = f"<span>{n} / {len(bodies)}</span>" if mode == "a4" else ""
        # Screen mode has no folio, so with no footer: or date: there is no footer at all.
        foot = f"<footer><span>{left}</span>{folio}</footer>" if left or folio else ""
        top = header if n == 1 else ""
        pages.append((top, f'<div class="flow">{body}</div>', foot))

    if len(pages) == 1:
        cls = "page screen" if mode == "screen" else "page"
        main = f'<main class="{cls}">{"".join(pages[0])}</main>'
    else:
        main = "<main>" + "".join(f'<div class="page">{"".join(p)}</div>' for p in pages) + "</main>"
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title>\n<style>\n{inline_css()}\n</style></head>\n"
        f"<body>\n{main}\n</body></html>\n"
    )


def main(argv):
    args, mode, sources, strict, data = [], "a4", None, False, None
    it = iter(argv[1:])
    for a in it:
        if a in ("--a4", "--screen"):
            mode = a[2:]
        elif a == "--strict":
            strict = True
        elif a == "--sources":
            sources = next(it, None)
            if not sources:
                sys.exit("build_doc: --sources needs a file")
        elif a.startswith("--sources="):
            sources = a.split("=", 1)[1]
        elif a == "--data-links":
            data = next(it, None)
            if data is None:
                sys.exit("build_doc: --data-links needs a path prefix, such as ../")
        elif a.startswith("--data-links="):
            data = a.split("=", 1)[1]
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            args.append(a)
    if len(args) != 2:
        sys.exit(__doc__)
    try:
        out = build(args[0], mode, sources, data)
    except (BuildError, OSError, json.JSONDecodeError) as e:
        sys.exit(f"build_doc: error: {e}")
    if strict and WARNINGS:
        sys.exit(f"build_doc: error: --strict and {len(WARNINGS)} warning(s); nothing written")
    pathlib.Path(args[1]).write_text(out, encoding="utf-8")
    print(f"build_doc: wrote {args[1]} ({mode}, {len(out) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

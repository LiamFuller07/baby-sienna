# baby-sienna formats

This file covers what the sections share: the conventions, the standard source format, the citation types and their rules, the prose rules, how documents cite, the optional inventory data (section 3), the pages computed from the whole workspace (section 5), the check ids and what is never authored. Each map section's own format sits with its design system, in `design-system/<section>/README.md`.

Machine-readable facts have one owner each. Id patterns, field limits and enums live in the schemas. Kinds, readers, locator grammars, the rules per category, web sources and AI terms live in `citation-types.json`. This file explains them, and where it gives an example the JSON is the definition.

All content is placeholder: Client A, Team A to Team C, "Submit request".

---

## 0. Conventions

- **Files.** JSON files are UTF-8 objects, and every object is closed: an unknown key is an error. Markdown files are UTF-8.
- **Dates.** Data holds ISO dates (`2026-10-22`). Every page prints them as `22 Oct 2026`.
- **One notation.** A record's address is `<source id> <locator>`, such as `WB1 Steps!C3` or `T1 00:00:31`. You type that string in a `[ ]` marker. JSON splits it as `{"source": "WB1", "locator": "Steps!C3"}`. The page prints it unchanged.
- **Ids.** Rule ids (`map-4`) name checks, never elements. Every id in a map is unique across all its arrays (map-1).

| Id | Example | Unique in | Pattern |
|---|---|---|---|
| source | `WB1`, `T1`, `D1`, `WEB1` | workspace | `citation.schema.json › sourceId`; it is the file name `records/<id>.json` |
| section file | `current-state` | its section folder | `process-map.schema.json › sectionFile` |
| lane, system | `team-a`, `tracker` | map | `process-map.schema.json › slug` |
| group | `G01` | map | `› groupId` |
| node (step or decision) | `SUB-01` | map | `› nodeId`; the prefix is a mnemonic of the activity |
| gap, clarification | `GAP-01`, `P01` | map | `› gapId`, `› clarificationId`; the badge number is the list position |
| AI item | `AI-01` | AI layer | `ai-layer.schema.json › aiId`; the square shows `01` |
| module | `MOD-01` | inventory file | `inventory.schema.json › moduleId` |

---

## 1. Source records: `records/<ID>.json`

Every raw input becomes one record file (`schemas/source-record.schema.json`). A header describes the input once, and `records` holds its units verbatim, in reading order. The header fields are exactly the flags of `bs.py convert`, so nobody types a header by hand.

| Field | Set by | Rule |
|---|---|---|
| `id` | `--id` | equals the file name |
| `title` | `--title` | what the input is, in plain words. Printed on its line in every Citation points section |
| `kind` | `--kind` | `sheet`, `document`, `transcript` or `web` (table below) |
| `captured` | `--captured` | when the material was received or retrieved |
| `detail` | `--detail` | one line: who provided it, size, version, how speakers were pseudonymised. Printed after the title |
| `url` | `--url` | required for `web`; its domain is printed |
| `legacy` | `--legacy` | plain metadata: the material was already old when it arrived. Nothing reads it |
| `file` | the input path | `inputs/…`, inside `inputs/` |
| `sha256` | computed | of `file` at conversion |
| `coverage` | `--partial` | `complete` (default): the records hold every unit of the input, and the input is the whole material. `partial`: an excerpt, or only some units recorded. An absent search over it is PROVISIONAL |
| `records` | read from the input | `{locator, text, context?}` each |

A record holds `locator` (unique in the file, in its kind's grammar), `text` (verbatim, 1–4000 characters) and an optional `context` (what the text sits under).

**Kinds.** The full extension lists and the locator regexes are in `citation-types.json › kinds`.

| Kind | Inputs (examples) | One record per | Locator | Spans a citation may use | Context | Printed as |
|---|---|---|---|---|---|---|
| `sheet` | .csv, .xlsx (.xls is unchecked) | non-empty cell | `Steps!C3` | `Steps!C2:D4` · `Steps row 5` · `Steps rows 2-4` | row 1 of the column | Workbook |
| `document` | .md, .txt, .docx (.pdf, email and images are unchecked) | paragraph, heading, list item or table row; in an email export, one message | `¶4`, or `p2 ¶3` when the file has pages | `¶2-4` · `p2` · `p2 ¶1-3` | the nearest heading; for a message, its author | Document |
| `transcript` | timed .txt, .vtt, .srt (audio is unchecked) | turn | `00:00:31`, or `00:00:31.400` | `00:00:05-00:00:47` | the speaker | Meeting notes |
| `web` | a saved .html page (.mhtml is unchecked) | paragraph, heading, list item or table row | `¶3` | `¶2-3` | the nearest heading | Website |

**What a reader gives.** `bs.py check` re-reads each input with the same readers, so these rules are exact.
- **Text as stored.** A .csv cell is the text as written. An .xlsx cell is its stored value: text as stored, a number unformatted (`5000`), and a date cell as an ISO date (`2026-09-01`, with ` 14:30` when it has a time). In .docx, .html and .md, line breaks and runs of white space become one space.
- **Tables.** A table row is one record: its cells joined by ` | `, with the separator row skipped.
- **Sheets.** A .csv file has one sheet, named after the file: `inputs/Steps.csv` gives `Steps`.
- **Turns.** A turn's locator is its start time to the second. A later turn that starts in a second already used keeps its milliseconds (`00:00:31.400`). A timed .txt turn reads `HH:MM:SS Speaker: text` and may wrap onto the lines after it. In .vtt and .srt one cue is one turn, and its speaker is a `<v Name>` tag or a leading `Name:`.
- **Containers.** A .zip is not an input. Save its members in `inputs/<name>/` and keep the .zip outside the workspace.

**Resolution: containment.** A span resolves to every record of its source whose locator lies inside it. For example, `WB1 Steps row 7` resolves to A7, C7 and D7. A citation with no locator means the whole source; only an absent span may use one.

**Lifecycle.**
- **Inputs never change.** An input is never edited, renamed or removed. A new version is a new file in `inputs/`: it shows as NOT CONVERTED and gets a new id. An edited input fails rec-2. To fix it, restore the original.
- **Record files are never edited by hand.** When a record file fails rec-1, rec-3, rec-4, rec-5 or rec-6, delete it and convert its input again under the same id, so citations keep resolving. If an original input is lost, delete its record file; `bs.py check` then lists every citation to repoint (cite-1).
- **Who converts.** `bs.py convert` reads every extension in a kind's `read` list. For the `unchecked` formats, the converter agent writes the same form, and rec-5 reports the record file as UNCHECKED: a person compares it with the input. `bs.py status` lists these.

**Example** (`examples/records/T1.json`, abridged):

```json
{
 "id": "T1",
 "title": "Follow-up call notes (placeholder)",
 "kind": "transcript",
 "captured": "2026-10-15",
 "detail": "Call with Team A and Team B, speakers pseudonymised",
 "file": "inputs/follow-up-call.txt",
 "sha256": "b22028a859e4c9350d625271d9767d3d1fc21361d1b8b11a67ce185c25434d8b",
 "coverage": "complete",
 "records": [
  {"locator": "00:00:31", "text": "Incomplete requests go back to Team A.", "context": "Speaker B"},
  {"locator": "00:00:47", "text": "Team B approves requests up to 5,000.", "context": "Speaker A"}
 ]
}
```

---

## 2. Citations

### 2.1 The closed set: three types

| Type | JSON (`schemas/citation.schema.json`) | Written inline as | Resolves to | Word | Checked by |
|---|---|---|---|---|---|
| **grounded** | `{"source": "WB1", "locator": "Steps!D6", "quote": "…"}`. `type` (`"grounded"`) and `quote` are optional | `[WB1 Steps!D6]` or `[WB1 Steps!D6; T1 00:00:47]` in prose; a document line `Grounded · WB1 Steps!D6; T1 00:00:47` | ≥ 1 record | **Grounded** | cite-1 resolves; cite-2 the quote is verbatim in a resolved record |
| **inferred** | `{"type": "inferred", "reading": "…", "from": [{source, locator}, …]}` | a document line `Inferred · <reading> · from WB1 Steps!D4; T1 00:00:18` | the records in `from` | **Inferred** | cite-1 every `from` resolves; the reading is prose in our words, checked like design prose against its `from` records |
| **absent** | `{"type": "absent", "needle": "Team", "in": [{source, locator?}, …]}` | a document line `Gap · not in WB1 Steps row 7; T1: “Team”` | the spans in `in`, each holding ≥ 1 record | **Gap** | cite-3: the needle (case-insensitive, quote folding) is in none of their texts. It is PROVEN when every source searched is complete, and PROVISIONAL otherwise: a warning on a board, an error in a document |

**Quote folding.** NFKC, curly quotes to straight, en and em dashes to hyphen, no-break space to space, and runs of white space to one space. Case is kept, except for needles and system labels.

**Not citations.**
- *Counts* are computed by the build: `{count:steps}` tokens and the AI summary strip.
- *Element ids* (`SUB-01`) are links to the board, never evidence.
- *A web page* is a source kind, so it is cited like any record.

### 2.2 Where each section writes them

| Section | Element citations | Inline |
|---|---|---|
| process-map | `cite` on systems, lanes, nodes, gaps and clarifications. Groups and edges carry none. A system's `software.cite` is printed by Original data received and the systems inventory, not by the board | `[SRC locator]` markers in gap and clarification prose: a grounded citation of the card, printed in place |
| process-map-ai-opportunity | `cite` on each `ai[]` item | none: `does` and `agentic` are our design |
| document | — | `[SRC locator]` brackets in a sentence, and Grounded, Inferred and Gap lines straight after a block (section 4) |
| inventory | `cite` on each module | none |

### 2.3 Rules per element category

**Allowed** lists the types an element may carry. **Needs** lists what it must have. This table is generated from `citation-types.json › categories` by `bs.py check --rules`, and the self-test fails when they differ.

<!-- generated by bs.py check --rules -->
| Section · category | Allowed | Needs | Note |
|---|---|---|---|
| process-map · system | grounded | grounded | map-8: its label occurs in a record it cites. Its marker is in the system key; its Citation points row names the system under Used by |
| process-map · system.software | grounded, inferred | grounded or inferred | inv-1: Named in the sources when a grounded record holds its name; otherwise its inferred reading is the evidence. Printed by Original data received and the systems inventory, not by the board |
| process-map · lane | grounded, inferred | nothing | map-3: a lane that holds no step needs a grounded citation for its role. Its marker is in the gutter; its Citation points row names the lane under Used by |
| process-map · node.grounded | grounded, inferred | grounded |  |
| process-map · node.inferred | inferred | inferred | map-7: the reading printed on the card is at most cardReadingMax characters |
| process-map · node.gap | grounded, inferred | grounded | the step exists in the sources; its gap card proves what is missing (map-6) |
| process-map · group | none | nothing | no citation: a view is our framing of the board |
| process-map · edge | none | nothing | no citation: the nodes at its ends hold the evidence. A branch label's numbers come from a record its decision cites |
| process-map · gap | grounded, inferred, absent | absent **and** grounded | a cited weakness is not a gap: a gap proves with an absent search what the sources do not say; a weakness the sources state is a clarification |
| process-map · clarification | grounded, inferred, absent | grounded | the grounded citations are what the sources show |
| process-map-ai-opportunity · ai.named | grounded, inferred | grounded, with a quote holding an AI term | ai-3: the client asked for it in their own words, in a source that is not web |
| process-map-ai-opportunity · ai.suggested | grounded, inferred | inferred | our idea, read from the records |
| document · sentence | grounded, inferred, absent | grounded or inferred or absent | through a bracket in the sentence, or a provenance line straight after its block. A Gap line must be PROVEN |
| inventory · module | grounded, inferred | inferred | our suggestion, read from the records, like ai.suggested. inv-2 checks its software and steps against the map |
<!-- end generated -->

### 2.4 Web sources and AI terms

- **Web sources** may be cited only by suggested AI items, modules and document sentences, and they are never the only evidence of a suggested item or a module (cite-5). Process facts come from the client's own material.
- **AI terms** (`citation-types.json › aiTerms`) match whole words, so `AI-assisted` matches `AI`. They drive two rules:
  - ai-3: a named item needs a grounded quote holding one;
  - map-9: a current-state map may use one only where a record the element cites uses it, so today's automation can be described but no AI idea enters the map.

### 2.5 Prose rules

| Rule | What it requires |
|---|---|
| prose-1 | Brackets. In claim prose every `[ ]` is a list of citations, `SRC locator; SRC locator`, naming record files. Write `\[` for a literal bracket. Design prose, labels and a map's subtitle hold no brackets, and maps hold no links |
| prose-2 | No straight `"`. Quote with `“…”` |
| prose-3 | Every `“…”` occurs verbatim, after quote folding, in a record the element cites |
| prose-4 | Every number token (a run of digits, with `.` `,` `:` between digits) equals a whole number token of a record the element cites. Numbers inside a citation bracket, a verified quote, a source id, an element id that resolves or a `{count:…}` token are exempt |
| prose-5 | `{count:<selector>}` tokens appear only in a map's `meta.subtitle`, with a selector from `process-map.schema.json › count`. No other `{ }` |
| prose-6 | In maps and AI layers, a token shaped like an element id names an element of that map (or of the layer and its base). Documents name no element ids |

**Which records an element cites**, for prose-3 and prose-4: its grounded and inferred citations and its markers, never the spans of an absent search.
- A label of an element that cites nothing uses every record the file cites. That covers the meta kicker, title and footer, group labels, an uncited lane and the AI layer's meta.
- A branch label uses its decision's records.
- An inferred reading uses its `from` records.
- A map's subtitle cites nothing, so its numbers come only from tokens.

**Where they apply.** Every prose rule applies to every field below; the kinds differ only in the brackets prose-1 allows. In a map every field is also checked by map-9.

| Prose | Fields | Brackets |
|---|---|---|
| claim | gap `title` and `text`; clarification `title`, `shows` and `ask`; every document sentence and exempt part | citations |
| subtitle | map `meta.subtitle` | none; numbers only from `{count:…}` tokens |
| design | AI `meta.subtitle`, item `title` and `does`, the `agentic` texts; every inferred `reading` | none |
| label | map meta kicker, title and footer; system, lane, group and node labels; a system's `role`; owners; branch labels; AI meta kicker and title; `decides[].who` | none |
| name | a system's `software.name`; a module's `title` | none; a letter-and-digit token (`A1` in `Module A1 · request intake`) is part of the name and carries no number for prose-4, but every other number, standalone or in what the module does, needs a source like any label's |

### 2.6 What a page prints (computed, never typed)

- **Marker.** One small numbered marker on each cited element (`a.cp-mk`, a muted numeral), linked to its point's row in the page's own Citation points section (`section#citation-points`), with `aria-label="Citation 3: WB1 Steps!D6"`; hover or focus shows the address and the first words of the verbatim text. A document's source still writes `[WB1 Steps!D6]`, and `build_doc.py --data-links` prints a marker in its place.
- **Anchor.** `src-` plus the address in lower case, with `¶` written `para` and any other run of characters that are not letters or digits written `-`. For example, `src-wb1-steps-d6`, `src-d1-para2` and `src-t1-00-00-31`. An absent search adds `-not-` and its needle: `src-wb1-steps-row-7-not-team`.
- **Provenance line** of a card item or a row, built from its citations in a fixed order, each clause in its own colour and each address replaced by its marker:
  1. One Gap clause, one needle per search: `Gap · “Team” not found ⁿ · “outcome” not found ⁿ`. A PROVISIONAL search adds a PROVISIONAL tag (boards only).
  2. One Grounded clause: `Grounded ⁿ`, one marker per address.
  3. One Inferred clause per reading: `Inferred · <reading> ⁿ`.
- **Citation points section.** It ends every template page and lists exactly the points that page uses (build-1, build-7), in the same markup on every template:
  - a heading with its count (`17 points from 2 records`);
  - one line per record (`ul.cp-srcs`): `WB1 · Request steps workbook (placeholder) · Shared by Team A, one sheet · Workbook · captured 1 Sep 2026`, the domain added for a web source, and the record id linking to its row in Original data received;
  - one numbered row per point (`ol.cp-list > li.cp-row`, at the point's anchor): the address in monospace (`a.cp-addr`, linking to `data-received.html#<ID>`), the verbatim text (`.cp-text`), Used by (`.cp-used`: Grounded, Inferred from or Absent search, then each element it supports, named as its page shows it and linked to it), and ↗ (`a.cp-all`) to its row in `citation-points.html`.
  - It is the only place where full addresses and verbatim text appear. Pages print no `file` and no `sha256`, except Original data received, which shows relative `inputs/` paths and 8-character hashes, never an absolute path or a full hash (build-2).
- **Kind words and dates.** The kind is printed with its `label` from `citation-types.json` (Workbook, Document, Meeting notes, Website), and dates as `1 Sep 2026`, on every page.

---

## 3. The section formats

| Section | Format | Look and builder |
|---|---|---|
| process-map | `design-system/process-map/README.md`, `process-map.schema.json` | `board.html`, `build_map.py` (it builds both map sections) |
| process-map-ai-opportunity | `design-system/process-map-ai-opportunity/README.md`, `ai-layer.schema.json` | `fills.html` |
| document | section 4 below; the subset in `design-system/document/README.md`, as built | `doc.css`, `build_doc.py`, as built |
| inventory (optional) | 3.1 and 3.2 below; `design-system/data-received/inventory.schema.json` | printed by Original data received and the systems inventory (section 5.1) |

Software and modules are the smallest additions that fill the Overview of Original data received and its deliverable, the systems inventory: two optional fields on a map's systems, and one optional section file. Every citation reuses the three types; there is no new kind or locator grammar.

### 3.1 A system's `role` and `software` (`process-map.schema.json › system`)

| Field | Rule |
|---|---|
| `role` | Optional, 3–60 characters: what the system does in this process (`Where Team B logs each request`). Label prose, checked against the system's own records |
| `software` | Optional: the product behind the system, `{name, category, cite}` |
| `software.name` | 1–40 characters, name prose: the product as the sources name it. Placeholder data uses `Software A` to `Software E`. Several systems may share one name; the page joins them in one row |
| `software.category` | `spreadsheet app`, `ticketing tool`, `ERP suite`, `email client`, `document store`, `database`, `web app` or `other`: our generic label, not a claim. One name has one category in a map (inv-1) |
| `software.cite` | Grounded or inferred citations (category `process-map · system.software`); no web source |

The page computes its status: **Named in the sources** when a grounded citation resolves to a record whose text holds the name (case-insensitive, after quote folding), as map-8 does for a system's label; **Inferred** otherwise, and then it must carry an inferred citation whose reading says why we take the system to be that product (inv-1). The board does not print either field.

### 3.2 `inventory/<name>.json`: the modules likely to be used

```json
{"type": "inventory", "map": "current-state",
 "modules": [
  {"id": "MOD-01", "title": "Module A1 · request intake", "software": "Software A", "steps": ["LOG-01"], "likelihood": "likely",
   "cite": [{"type": "inferred", "reading": "Requests are logged in the tracker by hand, which an intake module could take over",
             "from": [{"source": "WB1", "locator": "Steps!D3"}, {"source": "T1", "locator": "00:01:02"}]}]}]}
```

| Field | Rule |
|---|---|
| `type` | `"inventory"` |
| `map` | a map in `process-map/` that passes its checks (inv-2) |
| `modules[]` | 1–30, in display order |
| `id` | `MOD-01`, unique in the file (inv-2) |
| `title` | 3–60 characters, name prose: the module as the product names it, then what it does |
| `software` | a `systems[].software.name` of the map (inv-2) |
| `steps` | 1–12 step ids of the map, never a decision: the steps the module would serve (inv-2). A step need not use that software today; that is the suggestion |
| `likelihood` | `likely` or `possible` |
| `cite` | at least one **inferred** citation: a module is always our suggestion (cite-4). Grounded ones may be added; web sources never alone (cite-5) |

**Example:** `examples/inventory/end-to-end.json`, with `systems[].software` in `examples/process-map/end-to-end.json` (three products named in `inputs/notes/systems-notes.md`, two inferred); and `examples/inventory/request-handling.json` over `current-state.json`.

---

## 4. document: `document/<name>.md`

The format is the document type as built, unchanged. `bs.py check` parses a document with that type's own parser (`build_doc.py`'s blocks and inline rules), so the check and the page read the same text.

**Front matter** (`design-system/document/document-front-matter.schema.json`). It is optional, between `---` lines at the very top, one `key: value` per line. The keys are `title`, `label`, `date` and `footer`, as built, plus `mode`.
- `mode` is `a4` (the default) or `screen`.
- `bs.py` passes `mode` to the builder as `--a4` or `--screen` and removes the line from what the builder reads. It is part of the build hash (build-3).
- Any other key fails doc-1.

**Body.** The document type's Markdown subset, as built. A body the builder would stop on, or warn about under `--strict`, fails doc-1.

**Citations.** These use the type's own `[ID locator]` bracket and its three lines, with the shared grammar inside them.
- **Bracket:** `[T1 00:00:31]` or `[WB1 Steps!D3; T1 00:00:05]`. A bracket is a citation when it names a record file, and its locator must resolve (cite-1). Any other bracket fails prose-1.
- **Grounded line:** `Grounded · WB1 Steps row 2; T1 00:00:05`.
- **Inferred line:** `Inferred · <reading> · from WB1 Steps!D4; T1 00:00:18`.
- **Gap line:** `Gap · not in WB1 Steps row 7; T1: “Team”`. It must be PROVEN.

Each line is a paragraph of its own, straight after the paragraph, list or table it supports (doc-2), and it must form a valid citation: a reading of 8–300 characters, a needle in curly quotes. Grounded and Inferred lines name a locator.

**Claim sentences (doc-3).** Paragraphs, list items, steps, table body rows and `>` blocks after the intro are split into sentences: at `.`, `?` or `!` before white space, but not inside `“…”`. Each sentence must cite.
- A bracket covers the sentence it sits in. A bold lead-in such as `**Approve.**` belongs to the sentence after it.
- A provenance line covers its whole block.
- HTML comments are dropped, as the builder drops them. A bracket inside one cites nothing, and text after `-->` on the same line is a claim.

**Exempt parts** need no citation, but they still face the prose rules, against every record the document cites. They are the title, the intro (the first two `>` blocks after the title), headings, table header rows, and `:::callout`, `:::aside` and `:::examples` blocks. Fenced code is exempt from everything. The `:::aside` is text only: logos need `template.html`.

**The `--sources` map** is generated by `bs.py build` from the record headers, in id order: `{"WB1": {"name": <title>, "note": <detail> · <domain>}}`, with `note` left out when it would be empty. Nobody writes it by hand.

**Example:** `examples/document/request-handling-summary.md`.

---

## 5. Computed pages

Three pages are computed from the whole workspace, never authored, and written to `out/<name>.html`: Original data received and its deliverable, the systems inventory (5.1), and Citation points (5.2).

### 5.1 Original data received: `out/data-received.html`, and the systems inventory: `out/systems-inventory.html`

Original data received is one page with two views, Overview (the default) and Folder view, and one Citation points section. The Overview shows Folders of data, Systems identified, Software used and Modules likely to be used; the Folder view is a full-width table of `inputs/` whose rows (`id="<RECORD ID>"`) are where every citation on the other pages lands. The systems inventory is the client-ready page of the last three Overview sections, with its own Citation points. Both are computed from `inputs/`, `records/`, the section files and `inventory/` (section 3.2), with `design-system/data-received/build_received.py`; `design-system/data-received/README.md` describes every element.
- `bs.py build <ws>` builds both on every whole-workspace build; `bs.py build <ws> data-received` and `bs.py build <ws> systems-inventory` build one alone. Original data received is built even when check fails, once its required elements are fulfilled (a map with cited systems and software, and an inventory), so new material shows at once; until then status lists each MISSING element and the build exits 1. When check fails the build exits 1 and builds no other page. The systems inventory is built only when check passes.
- Each page has required elements (`design-system/data-received/template.json`); the builder exits 1, naming the file and field that fulfils each missing one, and the build keeps that page out of `out/`.
- Each file shows the status `bs.py status` reads: Converted · ID, Not converted (ws-1), Unchecked (rec-5), Duplicate (ws-1), or an error when its input is missing or edited (rec-2).
- Every cited row carries numbered markers, and each page ends with the shared Citation points section (section 2.6): each point with its address, its verbatim text, what uses it, and links to its file's row and to `citation-points.html#src-<address>`. `bs.py build` checks the section and the markers as on every page (build-7). The Folder view's rows are in the page's HTML, so every `#<RECORD ID>` lands without the script.
- Like every page they are self-contained, give the same bytes twice and carry a `bs-build` hash: of `inputs/`, `records/`, the section files, `inventory/`, `design-system/data-received/` and `formats/citation-types.json`. Original data received prints `inputs/` paths but no absolute path and no full sha256; the systems inventory prints neither `inputs/` paths nor hashes (build-2).

### 5.2 Citation points: `out/citation-points.html`

Citation points lists every citation point the workspace's pages use, so it is the union of every page's own Citation points section. A point is either a record address as a citation writes it (`WB1 Steps row 2`), or an absent search of one address for one needle. It is computed from the section files' citations and the records, with `design-system/citation-points/build_citations.py`, and `design-system/citation-points/README.md` describes every element.
- **Builds.** `bs.py build <ws>` builds it on every whole-workspace build that passes check, and `bs.py build <ws> citation-points` builds it alone. Its required elements are in `design-system/citation-points/template.json`: at least one point, every point resolving, and Used by for every point.
- **Groups.** Points are grouped by record file. Each group's header gives the title, kind, captured date and the legacy flag, and links to the file's row in Original data received (`data-received.html#<ID>`).
- **Rows.** Each row gives the address in monospace and the verbatim records it resolves to: one record, a span's records, or what an absent search searched. Then comes **Used by**: the kind (Grounded, Inferred from, Absent search) and the elements that cite the point, each linked to the page that shows it.
- **Anchors.** A row's id is its point's anchor (section 2.6). An absent search adds `-not-` and its needle: `src-wb1-steps-row-7-not-team`. These are the anchors every page's Citation points rows link to with ↗. For a document, `bs.py build` passes `--data-links ../` to `build_doc.py`, which prints its markers and its Citation points section.
- **Filter and switch.** The page has a filter, and a **Show only unused records** switch that lists instead the records no grounded or inferred point reaches.
- **Build rules.** build-1 holds both ways: every page's link into the page lands on a row, and every row is linked from a page. Every Used by link also lands on its element. Like every page, it is self-contained, gives the same bytes twice, and holds no `inputs/` path, absolute path or hash (build-2, build-3).

---

## 6. Validation rules

`bs.py check <workspace>` uses the standard library only, plus jsonschema when it is installed. Without it, a built-in checker for the schemas' fixed keyword subset runs, and any other keyword stops it with exit 2.

- **Output:** one line per finding: `LEVEL RULE file#/json/pointer message -> fix`. A Markdown finding names `file:line`.
- **Exit codes:** 0 pass (warnings listed), 1 a rule failed, 2 cannot run.
- **Order:** records, then maps, then AI layers (after their base), then documents, then inventory files. A broken base fails its layer (ai-1). A broken map leaves its inventory unchecked with an inv-2 warning, since the map's own errors already fail the check; the inventory is checked once the map passes.

| Id | Rule |
|---|---|
| ws-1 | Every file in `inputs/` is named by a record file's `file` (NOT CONVERTED). A byte-identical copy of a converted input is a DUPLICATE warning; a container is unpacked first |
| ws-2 | The workspace holds only `inputs/ records/ process-map/ process-map-ai-opportunity/ document/ inventory/ out/`. `records/` holds only `<ID>.json`; section and inventory files are `<name>.json` or `<name>.md`; `inputs/` holds no hidden files |
| schema-1 | A file matches its schema: types, required fields, lengths, enums, patterns, no unknown keys. A date is on the calendar |
| rec-1 | A record file's `id` equals its file name |
| rec-2 | Its `file` is inside `inputs/`, exists, and has the recorded sha256 |
| rec-3 | Every locator matches its kind's record grammar and is unique in the file |
| rec-4 | Records are in reading order |
| rec-5 | The kind takes the file's extension. Every record equals a unit re-read from the input (text and context), and complete coverage has a record for every unit. An unchecked format is a warning: UNCHECKED |
| rec-6 | No two record files share a `file` or a `sha256` |
| cite-1 | Every citation resolves: a record file exists, the locator is in its kind's grammar, and it reaches ≥ 1 record. Grounded and inferred citations name a locator |
| cite-2 | A grounded `quote` is verbatim in a resolved record |
| cite-3 | An absent needle is in no record of its spans (PROVISIONAL is a warning on a board and an error in a document) |
| cite-4 | Allowed and required citation types per category (section 2.3) |
| cite-5 | Web sources only where allowed, never alone on a suggested item |
| prose-1 to prose-6 | Section 2.5 |
| map-1 | Ids are unique across the map; lanes, groups, systems, edge ends and card nodes resolve |
| map-2 | With groups, every node names one, every group holds a node, and nodes are listed group by group |
| map-3 | A lane that holds no step cites its role with a grounded citation |
| map-4 | A decision has ≥ 2 conditional branches with different labels; conditional edges leave decisions, and every edge from a decision is conditional |
| map-5 | No self-loops and no duplicate edges |
| map-6 | Each gap-state step is listed by exactly one gap card; gap cards list only gap-state steps |
| map-7 | An inferred node's reading, printed on its card, is ≤ `cardReadingMax` (48) characters |
| map-8 | A system's label occurs in a record it cites |
| map-9 | An AI term in a map occurs in a record the element cites |
| map-10 | A `col` hint is not left of the node's derived column, and the board needs ≤ 14 columns |
| ai-1 | `base` is a map in `process-map/` that passes its checks |
| ai-2 | Targets exist in the base and are steps; not both empty; `"all"` takes no nodes; no listed step sits in a listed group; view targets need a base with ≥ 2 groups; ids unique and sorted |
| ai-3 | A named item quotes, from a source that is not web, words holding an AI term |
| ai-4 | Agentic: `after` is within the steps; systems exist in the base |
| doc-1 | Front matter is closed, reads `key: value` with each key once, and matches its schema; the body parses as the subset, with no builder warning; images sit only in `:::examples` |
| doc-2 | Grounded, Inferred and Gap lines parse, form valid citations and follow the block they support |
| doc-3 | Every claim sentence cites |
| inv-1 | A system's software is named in a record its grounded citations resolve to, or carries an inferred citation; one software name has one category in a map |
| inv-2 | An inventory's `map` is a map in `process-map/` (one that fails its own checks leaves the inventory unchecked: a warning); module ids are unique; every module's `software` is a software name of that map, and its `steps` are steps of that map |
| **Build** | **Run by `bs.py build`** |
| build-1 | A page's Citation points section lists exactly the points the page uses (no more, no fewer), and every marker links to its row. Citation points lists exactly the points the pages link to: every link into it lands on a row, every row is linked from a page, and every Used by link lands on its element (section 5.2). A one-page build warns when the page links to a row `out/citation-points.html` does not have yet |
| build-2 | The page is self-contained (no network loads) and holds no `inputs/` path (except `out/data-received.html`, which lists the inputs), no absolute path of the workspace or the toolkit, and no sha256 |
| build-3 | Building twice gives the same bytes. `out/<section>/<name>.html` carries `<meta name="bs-build">`: the hash of the source file, its records, a document's `mode`, `design-system/` and `formats/citation-types.json` |
| build-4 | Every citation's address is printed as visible text: in the page's Citation points row, whose Used by names the element. None appears only in a tooltip, `title` or `aria-label` |
| build-5 | Removing every `.pm-ai*` element from an AI page gives its base page's board; a process-map page contains no `pm-ai` |
| build-6 | On a board, no line crosses a card or a mark (a badge, a system icon, a chip, a decision's id label, the AI room under a step's bottom-right corner); no two lines from different sources to different targets share a stretch; a gap holds at most three sources' tracks; and every pill sits on a free stretch at least its width plus 16 units long, clear of cards and their AI halo, marks, other pills and 4 units from any line that crosses it. The error names the edge and the blocking node. On the Flow, a line through a step or a label is an error; crossing lines, lines closer than 12 units and a forward line that runs right to left are warnings. A title cut with … is a warning |
| build-7 | A page fulfils every required element of `design-system/<template>/template.json`. On every template, `section#citation-points` has one `li.cp-row` per point the page uses (no more), each with its verbatim text, Used by and links to `data-received.html#<ID>` and `citation-points.html#<anchor>`, and every cited element (card, step, row, claim) carries an `a.cp-mk` linking to its row. `bs.py build` exits 1 with the element's `fulfilled_by` hint, naming the file and JSON pointer when one item is at fault (`process-map/end-to-end.json#/nodes/3/owner`) |

**What the checker cannot see.** These are the checker agent's duties (`.claude/agents/checker.md`), because no rule can decide them:
- every grounded node title, read against its records;
- every absent needle: is it what the sources would say if the fact were there?
- every named AI item: is it the client asking? ai-3 is necessary, not sufficient;
- every edge: does it follow from its end nodes' records?
- every UNCHECKED record file, compared with its input.

**Mutation proof.** `bs.py check --selftest` proves every rule above.
- **Check rules:** it copies `examples/`, makes one break, and requires that break's rule id.
- **Required elements:** it takes one required element from each template; check still passes and the build refuses the page (build-7).
- **Build rules:** it builds a copy of `examples/` once, breaks one built page's HTML at a time (a dropped Citation points row, a row no citation uses, a link into Citation points with no row, a network script, an `inputs/` path, a full sha256, a `bs-build` meta from the builder, an address only in a `title`, `pm-ai` on a map page, a changed edge on the AI board, a cited element without its marker, no Citation points section, a row with no verbatim text, on maps, AI pages, documents, Original data received and the systems inventory), and requires the rule id from the build rules. For build-6 it breaks a map file (a line through a card, a pill with no room, two sources sharing a line, a feedback line through a badge chip) and requires the builder to fail.
- **Contracts**, ten of them:
  - section 2.3 equals the generated table;
  - the checker counts exactly the schema's `count` selectors;
  - a new version of an input goes NOT CONVERTED, then convert, then 0 errors;
  - `bs.py check <ws> document/<name>.md` prints the document's cite-1 findings;
  - each template's README opens with its `template.json` checklist (five contracts);
  - the xlsx, docx, vtt, srt, html and Markdown readers give the units this file describes.

---

## 7. Never authored

The build computes all of these, and typing one is a schema error or a prose failure:
- **Board:** badge numbers; citation markers and their numbers; decision diamonds; feedback styling (an edge to an earlier-listed node); group meta and lane notes (`3 steps`); `{count:…}` values; every coordinate, route, track and pill place.
- **Evidence:** provenance lines; Citation points sections, rows and anchors; tooltips.
- **AI layer:** square digits; the summary strip; scope labels; the agentic meta line.
- **Document:** its `--sources` map.
- **Computed pages:** `out/data-received.html`, `out/systems-inventory.html` and `out/citation-points.html`, every value (section 5): a software's status, the citation point numbers and markers, every count.

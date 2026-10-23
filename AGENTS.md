# AGENTS.md

The one guide for any AI agent working in baby-sienna. `CLAUDE.md` imports it. Every command and path below is real: run commands from the repo root.

baby-sienna turns a folder of client material into cited, self-contained HTML pages. It holds no client material, ever: every example is placeholder content (Client A, Team A to Team C, Submit request).

---

## 1. What baby-sienna makes

Five templates. Each has a design system in `design-system/<template>/` (its README, its required elements in `template.json`, its builder) and one skill in `.claude/skills/<template>/SKILL.md`.

**data-received: Original data received.** A computed page with two views. **Overview** (the default) shows Folders of data, Systems identified, Software used and Modules likely to be used. **Folder view** is one full-width table of every file in `inputs/`, one row per file, with `id="<RECORD ID>"`: every citation on every other page links back to these rows. Its named deliverable is **the systems inventory**, a client-ready A4 page with Systems identified, Software used and Modules likely to be used, its own header (`Client A · systems inventory`), a one-line summary and its own Citation points section. Examples: `examples/out/data-received.html`, `examples/out/systems-inventory.html`.

**process-map: the current-state swimlane board.** One `process-map/<name>.json` becomes one board: lanes (roles), steps with owners, decisions, flows, the Gaps and Clarifications cards and a Citation points section. It shows the process as the sources describe it today, with no AI on it at all. Example: `examples/out/process-map/end-to-end.html`, the showcase (35 nodes in 7 lanes and 6 views, 3 gaps, 5 clarifications). `examples/out/process-map/current-state.html` is the small one.

**process-map-ai-opportunity: AI opportunities over a map.** One `process-map-ai-opportunity/<name>.json` names a base map and adds AI items. The page leads with the AI automation list, never the map: an `AI OPPORTUNITIES` kicker, a headline summary, then three views of the same data: **List** (the default; one row per opportunity with its agentic version), **Flow** (the steps on one line, with an AI lane under it) and **On the map** (the base board with halos, squares and a layer toggle). Example: `examples/out/process-map-ai-opportunity/end-to-end-ai.html` (7 items over `end-to-end`).

**citation-points: every citation point in the workspace.** A computed page: the union of every page's own Citation points section. For each point: its record and locator, the verbatim text, what uses it (linked to the element), and a link back to its file's row in Original data received. Example: `examples/out/citation-points.html`.

**document: the Source document.** One `document/<name>.md` in the document type's Markdown subset becomes an A4 one-pager or a long screen page, for a reference-point document. Every claim carries a numbered marker, and the page ends with its Citation points section. Example: `examples/out/document/request-handling-summary.html`.

---

## 2. The model

```
inputs/  ──bs.py convert──▶  records/  ──author──▶  section files  ──bs.py build──▶  out/ pages
raw, as received             verbatim units          cited JSON or Markdown         self-contained HTML
```

**A workspace** is a folder: `examples/` is one, and real engagements live in `work/<engagement>/` (gitignored). **The folders are the state**: there is no manifest.

| Folder | Holds | Who writes it |
|---|---|---|
| `inputs/` | raw files exactly as received; subfolders allowed | a person. Never edited, renamed or removed |
| `records/` | `<ID>.json`, one per input: a header and the units verbatim | `bs.py convert`, or the converter agent |
| `process-map/` | `<name>.json`, one per current-state map | the author agent |
| `process-map-ai-opportunity/` | `<name>.json`, one per AI layer; `base` names a map | the author agent |
| `document/` | `<name>.md`, one per document | the author agent |
| `inventory/` | `<name>.json`, the modules likely to be used (optional) | the author agent |
| `out/` | every built page; gitignored; never edited | `bs.py build` |

`bs.py status` reads the folders and prints the next step:

| State | How bs.py knows | Next step |
|---|---|---|
| NOT CONVERTED | a file in `inputs/` that no record names (ws-1) | `.claude/workflows/convert.js`, or the convert skill |
| INVALID | `bs.py check` exits 1 | fix what each `-> fix` hint names |
| NOT BUILT or STALE | a page is missing, or its `bs-build` hash differs | fulfil each MISSING element, then `bs.py build` |
| DONE | none of the above | nothing |

It also lists UNCHECKED record files (a person compares them with their input) and DUPLICATE inputs. Neither blocks DONE.

### Commands

`bs.py` is the one command. It uses the standard library only (plus jsonschema when installed), so `python3 bs.py …` is the no-uv fallback for every line.

| Command | Does |
|---|---|
| `uv run python bs.py status <ws> [--json] [--strict]` | each file's state, each page's `n of m required elements fulfilled`, a `MISSING` line per missing element with the file and field that fulfils it, the next step. `--strict` exits 1 unless DONE |
| `uv run python bs.py convert <ws> inputs/<file> --id ID --kind KIND --title T --captured YYYY-MM-DD [--detail D] [--url U] [--partial] [--legacy]` | writes `records/ID.json`; the flags are the whole header. Refuses to overwrite; exits 2 for a format it cannot read |
| `uv run python bs.py convert --units <file> <kind>` | prints the records a file converts to, and writes nothing |
| `uv run python bs.py check <ws> [<file>]` | every rule in `formats/FORMATS.md` section 6; one line per finding, `LEVEL RULE file#/pointer message -> fix` |
| `uv run python bs.py check --rules` | prints the citation rules per category (`formats/FORMATS.md` section 2.3) |
| `uv run python bs.py check --selftest [--builtin]` | breaks the examples, and the pages built from them, one rule at a time (check rules, required elements, build rules); every break must be caught |
| `uv run python bs.py build <ws> [<section>/<name> \| data-received \| systems-inventory \| citation-points]` | check, then the builders, then the build rules, into `<ws>/out/`. With no target it builds every page |
| `uv run python bs.py build <ws> --prepare <dir>` | writes what build hands the document builder, and builds nothing |

Exit codes: **0** pass (warnings listed), **1** a rule failed, **2** cannot run. Every command exits 2 on a workspace that git tracks, except `examples/`.

`bs.py build` stamps `<meta name="bs-build" content="<sha256>">` on each page. The builders never write it, nor timestamps or random ids: the same inputs give the same bytes (build-3). `bs.py build` calls these builders, which can also run alone:

| Builder | Command |
|---|---|
| maps | `python3 design-system/process-map/build_map.py <ws> process-map\|process-map-ai-opportunity <name> <out.html>` |
| specimens | `python3 design-system/process-map/build_map.py --specimen examples` (both gitignored `specimen.html` files) |
| document | `python3 design-system/document/build_doc.py <prepared.md> <out.html> --a4\|--screen --sources <prepared.json> --strict --data-links ../` |
| data received | `python3 design-system/data-received/build_received.py [--inventory] <ws> <out.html>` |
| citation points | `python3 design-system/citation-points/build_citations.py <ws> <out.html>` |

### Tooling

- **uv.** `uv sync` installs the dev group pinned in `uv.lock` (jsonschema, ruff); `uv run` runs inside it.
- **ruff.** `uv run ruff check` and `uv run ruff format` (settings in `pyproject.toml`; `reference/` and `work/` are excluded).
- **pre-commit.** `uvx pre-commit install` once; then every commit runs ruff check `--fix` and ruff format (`.pre-commit-config.yaml`).
- **CI.** `.github/workflows/ci.yml` runs the toolkit against its own examples: ruff check and format, `bs.py check examples`, `check --selftest` on both engines, `bs.py build examples` twice (byte for byte, and no `build_doc: warning`), the systems inventory and its Citation points section, the specimens and the document type's own examples, `bs.py status examples --strict`, and `node --check` on a wrapped copy of each `.claude/workflows/*.js`. It uploads `examples/out/`.

---

## 3. The templates

Each template's required elements are in `design-system/<template>/template.json`. **Fulfil every required element.** `bs.py build` refuses a page that leaves one unfulfilled (build-7, exit 1, with a `-> fix` hint), and `bs.py status` names each missing one.

### 3.1 data-received (computed)

| | |
|---|---|
| Required elements | Original data received: **6 of 6**. The systems inventory: **4 of 4** (the four marked ★) |
| Reads | `inputs/`, `records/`, every map's `systems[]`, `inventory/<name>.json`, every citation in the section files |
| Writes | nothing by hand. To change the page, change the workspace: fill `systems[].role` and `systems[].software` in a map, and write `inventory/<name>.json` |
| Build | `uv run python bs.py build <ws> data-received` · `uv run python bs.py build <ws> systems-inventory` |
| Skill · README · example | `.claude/skills/data-received/SKILL.md` · `design-system/data-received/README.md` · `examples/inventory/end-to-end.json` → `examples/out/data-received.html`, `examples/out/systems-inventory.html` |

- [ ] **Folders of data**: computed from `inputs/`: at least one file (ws-1).
- [ ] ★ **Systems identified**: `process-map/<name>.json › systems[]` (id, label, icon, cite, role), with `nodes[].systems` (map-8).
- [ ] ★ **Software used**: `process-map/<name>.json › systems[].software` (name, category, cite) (inv-1).
- [ ] ★ **Modules likely to be used**: `inventory/<name>.json › modules[]` (id, title, software, steps, likelihood, cite) (inv-2).
- [ ] **Folder view**: computed from `inputs/` and `records/`: one row per file (ws-1).
- [ ] ★ **Citation points section**: a map with cited `systems[]`; every cited row then carries a numbered marker (cite-1).

**Fulfilled looks like:** status reads `DONE out/data-received.html … 6 of 6 required elements fulfilled` and `DONE out/systems-inventory.html … 4 of 4`; every file in the Folder view is Converted; no Overview section shows its empty line. Original data received is built even when check fails, once its required elements are fulfilled (a map with cited systems and software, and an inventory), so new material shows at once; until then status lists each MISSING element and the build exits 1. The systems inventory is built only when check passes.

### 3.2 process-map

| | |
|---|---|
| Required elements | **7 of 7** |
| Reads | `records/*.json`, `design-system/process-map/README.md`, `design-system/process-map/process-map.schema.json` |
| Writes | `<ws>/process-map/<name>.json` |
| Build | `uv run python bs.py build <ws> process-map/<name>` |
| Skill · README · example | `.claude/skills/process-map/SKILL.md` · `design-system/process-map/README.md` · `examples/process-map/end-to-end.json` → `examples/out/process-map/end-to-end.html` |

- [ ] **Header**: `meta`: kicker, title, client and date (schema-1).
- [ ] **Lanes**: `lanes[] {id, label}`: at least one, each a role (map-3).
- [ ] **Steps with owners**: `nodes[]`: at least one step, each in the lane of the role that owns it, with its `owner`, state and cite; only a gap-state step may leave `owner` out, its gap card saying so (build-7).
- [ ] **Flows**: `edges[] {from, to}`: every node joined to the flow (map-5).
- [ ] **Gaps card**: `gaps[] {id, title, text, nodes, cite}`: at least one, proven by an absent search (cite-4).
- [ ] **Clarifications card**: `clarifications[] {id, title, shows, ask, nodes, cite}`: at least one (cite-4).
- [ ] **Citation points section, with in-place markers**: computed from every `cite`: one numbered marker on each cited element, and one row per point (build-7).

Optional: the system key (`systems[]`) and the views band (`groups[]`, two or more).

**Fulfilled looks like:** check prints `note map <name>: steps …, decisions …` and 0 errors; the build passes build-6 (no line crosses a card or a mark, no two sources share a line, every branch pill sits on a free stretch); status reads `7 of 7`. Each card shows its title, owner, step id and one small marker, nothing more. A board too wide to read at Fit opens at 100%; Fit shows it whole. For a large map, read the process-map skill's Large maps note: map-10 lists each view's columns and longest chain.

### 3.3 process-map-ai-opportunity

| | |
|---|---|
| Required elements | **9 of 9** |
| Reads | the base map (it must pass check), `records/*.json`, `design-system/process-map-ai-opportunity/README.md`, `design-system/process-map-ai-opportunity/ai-layer.schema.json` |
| Writes | `<ws>/process-map-ai-opportunity/<name>.json` |
| Build | `uv run python bs.py build <ws> process-map-ai-opportunity/<name>` |
| Skill · README · example | `.claude/skills/process-map-ai-opportunity/SKILL.md` · `design-system/process-map-ai-opportunity/README.md` · `examples/process-map-ai-opportunity/end-to-end-ai.json` → `examples/out/process-map-ai-opportunity/end-to-end-ai.html` |

- [ ] **Base map**: `base`: a map in `process-map/` that passes check (ai-1).
- [ ] **At least one AI item**: `ai[] {id, title, origin, does, nodes or groups, cite, agentic}` (ai-2).
- [ ] **Origin, named or suggested**: `ai[].origin`: `named` (a grounded quote) or `suggested` (an inferred reading) (ai-3).
- [ ] **What it would do**: `ai[].does`: one to three sentences (prose-4).
- [ ] **The agentic version of every item**: `ai[].agentic {trigger, steps, decides, systems, logging}` (ai-4).
- [ ] **List view, the default**: computed: the first tab, selected on load, one row per item (build-7).
- [ ] **Flow view**: computed from the base: the second tab, every base node on it (build-6).
- [ ] **On-the-map view**: computed: the third tab, the base board with the layer (build-5).
- [ ] **Citation points section, with numbered markers**: computed from every `cite` in the file and its base (build-7).

Optional: the layer toggle.

**Fulfilled looks like:** status reads `9 of 9`; the page opens on the List; every row shows its square, id, title and origin tag, What it would do, Steps it touches, its evidence with a marker, and an Agentic version expander. Filled squares mean named by the client, outlined squares our suggestion. Orange marks AI and gaps only.

### 3.4 citation-points (computed)

| | |
|---|---|
| Required elements | **3 of 3** |
| Reads | every citation in `process-map/`, `process-map-ai-opportunity/`, `document/` and `inventory/`, resolved against `records/` |
| Writes | nothing by hand. Points come from the other templates' citations |
| Build | `uv run python bs.py build <ws>` (build-1 checks it against every other page) · `uv run python bs.py build <ws> citation-points` |
| Skill · README · example | `.claude/skills/citation-points/SKILL.md` · `design-system/citation-points/README.md` · `examples/out/citation-points.html` |

- [ ] **At least one citation point**: a `cite` array in a map, an AI layer or an inventory, or a bracket or provenance line in a document (cite-1).
- [ ] **Every point resolves**: each point's locator reaches at least one record in `records/<ID>.json` (cite-1).
- [ ] **Used by for every point**: computed: the element that cites the point, linked to the page that shows it (build-1).

Optional and computed: one group per record file; the filter and **Show only unused records**.

**Fulfilled looks like:** status reads `3 of 3`; the build reports `n citation points from m record files`; every link from a page into `citation-points.html` lands on a row, and every row is linked from a page (build-1).

### 3.5 document

| | |
|---|---|
| Required elements | **4 of 4** |
| Reads | `records/*.json`, `design-system/document/README.md`, `formats/FORMATS.md` section 4 |
| Writes | `<ws>/document/<name>.md` (front matter keys `title`, `label`, `date`, `footer`, `mode: a4\|screen`) |
| Build | `uv run python bs.py build <ws> document/<name>` |
| Skill · README · example | `.claude/skills/document/SKILL.md` · `design-system/document/README.md` · `examples/document/request-handling-summary.md` → `examples/out/document/request-handling-summary.html` |

- [ ] **Title and lead**: the `#` title, then a `>` lead block right under it (doc-1).
- [ ] **At least one claim section**: a `##` heading with at least one cited claim under it (doc-3).
- [ ] **Every claim cited, with an in-place marker**: a `[ID locator]` bracket, or a Grounded, Inferred or Gap line, on every claim (doc-3).
- [ ] **Citation points section**: computed by `build_doc.py --data-links`: `section#citation-points` in place of the type's Sources block, one row per point with its record id and locator, the verbatim text, the element it supports, and links to `data-received.html#<ID>` and `citation-points.html#<anchor>` (build-7).

Optional: the `:::callout Next step`.

**Fulfilled looks like:** check passes doc-1 to doc-3; status reads `4 of 4`; the source still writes `[WB1 Steps!D3]`, and the page shows a numbered marker in its place.

---

## 4. Citations

Every claim cites a record. Nothing is uncited except computed counts. A missing fact is a gap (an absent search) or a clarification, never an uncited sentence. The full rules are `formats/FORMATS.md` section 2; the machine facts are `formats/citation-types.json`. The cite skill is `.claude/skills/cite/SKILL.md`.

**An address** is `<source id> <locator>`: `WB1 Steps!D3`, `WB1 Steps row 2`, `T1 00:00:31`, `D1 ¶2`. JSON splits it as `{"source": "WB1", "locator": "Steps!D3"}`. A span resolves to every record inside it.

### The three types

| Type | JSON | In a document | Proves |
|---|---|---|---|
| **grounded** | `{"source": "T1", "locator": "00:00:47", "quote": "…"}` (`quote` optional, verbatim) | `[T1 00:00:47]`, or the line `Grounded · WB1 Steps row 2; T1 00:00:05` | a record says it (cite-1, cite-2) |
| **inferred** | `{"type": "inferred", "reading": "…", "from": [{source, locator}, …]}` | `Inferred · <reading> · from WB1 Steps!D4; T1 00:00:18` | our reading of those records |
| **absent** | `{"type": "absent", "needle": "Team", "in": [{source, locator?}, …]}` | `Gap · not in WB1 Steps row 7: “Team”` | the needle is in none of those records (cite-3): PROVEN when every source searched is complete |

### Rules per category (the essentials)

| Element | Needs |
|---|---|
| map system | grounded; its label occurs in a record it cites (map-8) |
| map system software | grounded (Named in the sources) or inferred |
| map lane | nothing, unless it holds no step: then a grounded citation for its role (map-3) |
| map node | grounded (state grounded or gap) or inferred (state inferred; reading ≤ 48 characters) |
| map group, edge | none: they carry no citation |
| map gap | an absent search **and** a grounded citation |
| map clarification | grounded |
| AI item, named | a grounded quote holding an AI term, from a source that is not web (ai-3) |
| AI item, suggested | inferred; web pages may add to it, never alone (cite-5) |
| inventory module | inferred |
| document sentence | any of the three, through a bracket or a provenance line; a Gap line must be PROVEN |

The generated table is `uv run python bs.py check --rules`. Prose rules (section 2.5): no straight `"` (quote with `“…”`); every quoted phrase and every number occurs in a record the element cites; brackets only in claim prose; `{count:…}` tokens only in a map's subtitle.

### On the page

- **One small numbered marker** on every cited element: a card, a step, a row, a claim. A muted 9–10px numeral (`a.cp-mk`), never a locator string. It links to that point's row in the page's Citation points section; hover or focus shows one line, the address and the first words of the verbatim text.
- **The Citation points section** (`section#citation-points`) ends every template page. It lists every point that page uses, numbered to match: the address in monospace, the verbatim text, the elements it supports (linked to them), and two links back to the data. It is the only place full locators and verbatim text appear.
- **Links back to the data.** Every point the page cites links to its file's row in Original data received, `data-received.html#<RECORD ID>` (rows carry `id="<RECORD ID>"` and highlight on `:target`), and to its row in `citation-points.html#<anchor>`, with `../` from a page in `out/<section>/`. The anchor is `src-` plus the address in lower case, `¶` written `para`, other runs written `-`; an absent search adds `-not-<needle>`: `src-wb1-steps-row-2`, `src-wb1-steps-row-7-not-team`.
- **The build refuses** a page whose cited elements lack markers, or whose Citation points section is missing or does not equal the points the page uses: the section is a required element of every template (build-7), and build-1 checks every link into `citation-points.html`. **build-2** forbids `inputs/` paths and hashes on every page except Original data received, which shows relative `inputs/` paths and short hashes, never absolute paths or full hashes. **build-4**: no citation lives only in a tooltip.

---

## 5. Workflows and agents

Two Claude Code workflow scripts run the agents. Run one with the Workflow tool, for example `{scriptPath: ".claude/workflows/make.js", args: {ws: "work/client-a", section: "process-map", name: "end-to-end", brief: "…"}}`, or do the same steps by hand with the skills.

| Workflow | Args | Does |
|---|---|---|
| `.claude/workflows/convert.js` | `{ws, captured, notes?}`: `captured` is the ISO date the material arrived, for any input `notes` gives no date | `bs.py status --json` → one header per NOT CONVERTED input → `bs.py convert` for a format it reads, the converter agent otherwise, at most 4 at once → `bs.py check`, with one repair round |
| `.claude/workflows/make.js` | `{ws, section, name, brief}`: `section` is `process-map`, `process-map-ai-opportunity`, `document` or `inventory` | the author writes `<section>/<name>` → `bs.py check` loop, at most 3 rounds → the checker reads it → the author answers each finding → `bs.py build <ws>` and `bs.py status <ws>` |

| Agent | Reads | Writes | Duties |
|---|---|---|---|
| `.claude/agents/converter.md` | `inputs/` | `records/` only | transcribes, never interprets: units verbatim, in reading order, with the right kind, locators and coverage |
| `.claude/agents/author.md` | `records/`, the template's README and skill | one section file | writes it, loops on `bs.py check` until it exits 0, fulfils every required element |
| `.claude/agents/checker.md` | everything | nothing | the duties no rule can decide (`formats/FORMATS.md` section 6): grounded node titles, absent needles, named AI items, edges, UNCHECKED record files |

The supporting skills: `.claude/skills/convert/SKILL.md` (inputs → records) and `.claude/skills/cite/SKILL.md` (the three types and the rules).

---

## 6. Hard rules

- **Confidentiality.** Never commit, paste or upload workspace content. Client material lives only in `work/` (gitignored) or outside the repo.
- **Placeholder-only examples.** Every example, test and specimen uses obvious placeholders: Client A, Team A to Team C, Submit request, `[PRICE]`, `[Name]`. Never write a real company, client, partner or person name into any repo file.
- **Roles, not names.** Lanes, owners and speakers are roles (Team A, Finance, Speaker A), never people.
- **Never edit inputs.** An input is never edited, renamed or removed. A new version is a new file in `inputs/`.
- **Never edit records by hand.** A record file that fails a check is deleted and converted again under the same id. If an original is lost, delete its record file and repoint the citations `bs.py check` lists.
- **Citations back to the data.** Every claim cites a record that `bs.py check` can resolve; nothing is uncited except computed counts. Never type a computed value: badge numbers, markers, counts, coordinates, Citation points rows.
- **Pages are built, never edited.** Change the section file, then `bs.py build`.
- **Local only.** `reference/` (earlier client pages) and `work/` (real engagements) are gitignored and never committed. Never copy or quote anything from either into a repo file. Design references from other firms (`*reference*.html`) are for their design only: never their text, names or logos, and never saved in the repo.

---

## 7. Done means

- [ ] `uv run python bs.py check <ws>` exits 0.
- [ ] `uv run python bs.py status <ws>` shows every required element fulfilled on every page (`--strict` exits 0, State: DONE).
- [ ] `uv run python bs.py build <ws>` exits 0, and you have looked at the pages in `<ws>/out/`.
- [ ] The checker agent's findings are fixed or answered.

# Original data received

**Required elements** (`template.json`). `bs.py build` refuses a page, with exit 1 and a `-> fix` hint (build-7), until each is fulfilled, and `bs.py status` prints `n of m required elements fulfilled` for each page and names each missing one with the file and field that fulfils it.

- [ ] **Folders of data** (data-received): computed from `inputs/`: at least one file (ws-1).
- [ ] **Systems identified** (both pages): `process-map/<name>.json › systems[]` (with `role`), and `nodes[].systems` (map-8).
- [ ] **Software used** (both pages): `process-map/<name>.json › systems[].software {name, category, cite}` (inv-1).
- [ ] **Modules and capabilities** (both pages): `inventory/<name>.json › modules[]` (inv-2).
- [ ] **Folder view** (data-received): computed from `inputs/` and `records/`: one row per file (ws-1).
- [ ] **Citation points section** (both pages): computed: every cited row carries a numbered marker, and `section#citation-points` lists exactly the points the page uses, in the markup of every template (build-7).

The builder decides these itself, from `outputs` in `template.json`: it exits 1, still writing the page, and prints each missing element with its fix. `bs.py build` then checks the Citation points section and every row's markers as it does on every page (build-7).

---

The data-received template is one page and one deliverable, both computed, never authored:

- **`out/data-received.html`**, Original data received. One page with two views and a quiet switch at the top: **Overview** (the default) and **Folder view**. A Citation points section closes the page under both views. Every citation on the other pages lands on this page's Folder view rows: `../data-received.html#WB1`.
- **`out/systems-inventory.html`**, the systems inventory, the template's named deliverable. A client-ready page of the Overview's last three sections (Systems identified, Software used, Modules likely to be used) with its own header, a one-line summary, its own Citation points section and a clean A4 print. It prints no `inputs/` path and no hash.

Nobody writes or edits any of their content. To change what they say, change the workspace: add an input, convert it, cite it, give a map's systems their software, or write an inventory file.

| File | Role |
|---|---|
| `build_received.py` | `[--inventory] <ws> <out.html>`: reads the workspace and fills a template. Standard library only |
| `template.html` | Original data received: the switch, the Folder view's CSS and JS, and the slots `title`, `css`, `js`, `lede`, `overview`, `points`, `rows` (the Folder view's rows, static) and `data` |
| `inventory.html` | the systems inventory: header, sections, Citation points, footer |
| `overview.css`, `overview.js` | what both pages share: the tokens, the four-column grid of the Overview tables, the numbered markers, Citation points, the tooltip, the folder toggles and the "+n" step chips. The builder inlines them |
| `inventory.schema.json` | `inventory/<name>.json`, the modules (FORMATS.md section 3.2) |
| `template.json` | the required elements of each page |
| `README.md` | this file |

```
python3 bs.py build <ws>                          # builds both with every other page
python3 bs.py build <ws> data-received            # Original data received alone
python3 bs.py build <ws> systems-inventory        # the systems inventory alone
python3 design-system/data-received/build_received.py <ws> <ws>/out/data-received.html
python3 design-system/data-received/build_received.py --inventory <ws> <ws>/out/systems-inventory.html
```

**Example.** `examples/` fills every section: `process-map/end-to-end.json` (the showcase) gives five of its six systems their software, three of them named in `inputs/notes/systems-notes.md` (record D2), and `inventory/end-to-end.json` and `inventory/request-handling.json` hold the modules.

Exit codes: 0 the page is written. 1 a required element is not fulfilled: the builder still writes the page and prints `missing <element> -> <file and field>`, and `bs.py build` keeps the page out of `out/`. 2 cannot run (no `inputs/` folder, a toolkit file missing or unreadable, the page cannot be written). Invalid workspace data never stops the builder (section 4).

`bs.py build <ws>` builds Original data received even when check fails, once its required elements are fulfilled (a map with cited systems and software, and an inventory), so new material shows at once; until then status lists each MISSING element and the build exits 1. The systems inventory is a deliverable, so it is built only when check passes.

The required set is strict: a workspace with inputs and records but no map or inventory yet gets no page, because Systems identified, Software used, Modules likely to be used and Citation points are unfulfilled. `bs.py status` says so before any build: the page's row reads `2 of 6 required elements fulfilled`, a `MISSING` line names each missing element with the file and field that fulfils it, and the next step is to fulfil them rather than to build.

---

## 1. Original data received

**Label.** `<label>` is the client's name, the maps' `meta.client` when every map gives the same one (`Client A` in the examples); with no map, or maps that disagree, it is the workspace folder's name. Both pages use it.

**Header.** The kicker, `<label> · data received`, and one line: `4 files received 1 Sep – 16 Oct 2026 · 2 systems used by 3 steps · 2 software products · 3 modules we suggest`, with empty parts left out. Under it, the switch: `Overview | Folder view`, two quiet text tabs (arrow keys move between them), the selected one in ink with a 2px rule.

### 1.1 Overview

An "On this page" row with counts, a small key (the numbered marker, a step chip, our-suggestion square, Grounded, Inferred), then four sections on one grid: the first column 260px, the second 160px, the last 280px, 24px gaps.

| # | Section | Rows | Columns |
|---|---|---|---|
| 01 | Folders of data | `inputs/` with its totals, every folder under it (nested), then the files directly in `inputs/`. A folder's button shows its own files. Each file name opens its row in the Folder view | Folder · Files · Converted (`n of m`, plus `n unchecked`) · Kinds (icon and count) · Size · Received (range) |
| 02 | Systems identified | one per system label across every map, the largest map (most nodes) first | System (icon, label) · Teams (the lanes of the steps that use it, in the maps' lane order) · Role and evidence (the first `role` a map gives, the largest map first, then `Grounded¹,²`) · Steps (count, three step chips, `+n`) |
| 03 | Software used | one per `software.name`, sorted by name; several systems may share one | Software · Category (`our label`) · Status and evidence · Powers (the systems, linked to their rows) |
| 04 | Modules likely to be used | inventory files by name, modules in file order, each with the outlined square of our suggestion | Module · Software (linked to its row) · Likelihood and reading · Steps it would serve |

- **Status of a software**, computed: **Named in the sources** when a grounded citation's records hold its name (case-insensitive, after quote folding); **Inferred** when it carries an inferred reading; otherwise *Not named in its records*, in accent ink (check fails it with inv-1).
- **Step chips** link to `process-map/<map>.html#<node id>`; an inferred step's chip is dashed; a chip's tooltip is the step title and the map title. A chip is an element link, never evidence.
- **Empty section.** A section with no rows says which file and field fill it.

### 1.2 Folder view

One full-width table of every file in `inputs/`: Name · Kind · Status · Record · Size · Received · Used by. Nothing is selected at load.

- **Strip** above it: file count and total size, a count per kind, a count per status. When it wraps, no line starts on a divider.
- **To do**, one slim line: `To do  2 files not converted · 1 to compare · 1 duplicate · 1 to fix`, zero counts left out, hidden when every file is converted. Each item lands on the first file of its status and briefly highlights every row of that status.
- **Group by** Folder (a tree: subfolders first, then files, in natural name order), Kind (in `citation-types.json` order, then Archive, then Unknown format) or Received date (by week, Monday to Sunday, "No record yet" last). **Search** matches the name, path, record id, title, detail, kind and status; a match outside the name shows as a muted "in title". **Expand all / collapse all**; collapse all keeps `inputs` open.
- **Quiet line.** Clicking a row, or Enter on its name, opens one line under it (Esc closes it). Left: the record's own header (title · detail or URL · units) or the next step: convert it, unpack it, cite the original instead, restore it, or fix the record. Right: the file's short hash and whether it matches its record. It never quotes a record: verbatim text is printed only in Citation points.
- **Received** is the record's `captured` date. A file with no record has none: a file's modification date is not a fact about the material.
- **Legend.** Converted, Unchecked, Not converted and Duplicate always show; Error only when a file has it.
- **Phone (≤ 900 px).** A flat list grouped by folder path, kind or week.

**Status chips.** Each row has exactly one status, decided the way `bs.py check` and `bs.py status` decide it:

| Status | Chip | Rule |
|---|---|---|
| `converted` | **Converted**, ink on `--panel` | A record names the file, the sha256 matches, and the extension is in its kind's `read` list |
| `unchecked` | **Unchecked**, ink on `--peach` | As converted, but the extension is in its kind's `unchecked` list: a person compares the record with its input (rec-5) |
| `not-converted` | **Not converted**, `--accent-ink` text, `--accent` outline | No record names the file (ws-1). A container is always this, with the next step "unpack it first" |
| `duplicate` | **Duplicate**, muted text, `--line-strong` outline | No record names the file, but its sha256 equals a record's (ws-1). A warning, never a blocker |
| `error` | **Error**, ink on `--accent` | A record names the file and something is wrong: missing, edited, the wrong kind, malformed, unreadable, outside `inputs/`, or named twice (rec-2, rec-5, rec-6) |

Text on the filled `--accent` chip is ink (`#111`), not white: white on `#ff5600` is about 3.2:1 and fails AA.

**Anchors: where citations land.** The rows are in the page's HTML, grouped by folder, so every link lands without the script (with the script off, both views show); the script redraws them with its grouping and search when the Folder view opens. Every row with a record has `id="<RECORD ID>"`; every row's name cell has `id="file-<slug>"` (the path in lower case, other runs written `-`: `inputs/workbooks/Steps copy.xlsx` → `file-inputs-workbooks-steps-copy-xlsx`). On load, on every hash change and on a click of such a link, the page switches to the Folder view, clears a search only if it hides the row, opens its folders, scrolls it to the middle and highlights it: a 2px `--accent` rule on `--panel` that fades over 2.6 s. `#folder-view` and `#overview` open a view. A click that lands on a row records the view it left in the history entry, so Back returns to that view (the Overview for an empty hash). A hash that names no file, record or element shows one line in the Folder view: `No file or record “WB9” in this workspace.`

### 1.3 Citation points (both pages)

Every cited row carries its citations as **numbered markers**, the look of every template: a muted 9.5px superscript numeral, `<sup class="cp-mks"><a class="cp-mk">3</a></sup>`, with the same class and CSS as the process map and AI pages, never a locator string. A grounded citation gives one marker; an inferred one gives a marker per `from` address, after its reading: `Grounded¹,²`, `Inferred · <reading>³,⁴`.

- A marker links to its row in the page's Citation points section, `#src-<address>` (FORMATS.md section 2.6). Hover or focus shows one line: the address and the first words of the verbatim text.
- **The section** is the one every template ends with (process-map README section 3.1), in the same markup and CSS: `section#citation-points.cp`, a heading with its count (`30 points from 6 records`), one line per record (`ul.cp-srcs`: id, title, detail, kind, captured date, the id linking to its row), then `ol.cp-list` with one `li.cp-row` per **citation point**: one per address as written (`WB1 Steps row 2`), numbered in the order the page first shows it. A row holds its number (`.cp-n`), the address in monospace (`a.cp-addr`, linking to its file's row: `#WB1` here, `data-received.html#WB1` from the systems inventory), the verbatim text (`.cp-text`), Used by (`.cp-used`: Grounded or Inferred from, then the rows that use it, named as the page shows them and linked), and ↗ (`a.cp-all`) to `citation-points.html#src-<address>`.
- The section is the only place on these pages where full locators and verbatim text appear. A point that resolves to no record (check fails with cite-1) says so in accent ink.
- The points are exactly the cite arrays the Overview prints: systems, their software, and modules. Folders, the Folder view and step chips cite nothing.

### 1.4 Print

A4 portrait: the header, the visible view, then Citation points, whose heading and list of cited records stay together and never split across pages. The Folder view prints its own table (file, kind, status, record and units, detail, size, received, short hash, used by) on A4 landscape pages. Folders, file names and step chips print in full, and the footer stays with the last section.

## 2. The systems inventory

`<label> · systems inventory`, a one-line summary (`2 systems used by 3 steps · 2 software products, none named in the sources · 3 modules likely to be used`), "On this page", the key, sections 01 Systems identified, 02 Software used, 03 Modules likely to be used (as in the Overview), then Citation points and a client-ready footer (`Client A · systems inventory · 22 Oct 2026 · sources listed in Citation points`: no tool words, no paths). It is the page to hand over; it prints cleanly on A4 portrait.

## 3. Where the data comes from

| Data | Computed from |
|---|---|
| Folders and files | `inputs/` (hidden entries skipped), `records/*.json` (headers, records, sha256) |
| Used by (Folder view) | every cite array and bracket in `process-map/`, `process-map-ai-opportunity/`, `document/` and `inventory/`, counted per record (a grounded citation counts 1, an inferred one each `from`, an absent one each `in`) |
| Systems | every map's `systems[]`: `label`, `icon`, `cite`, the optional `role`; and `nodes[].systems` for the steps and teams |
| Software | `systems[].software`: `name`, `category` (our generic label), `cite`. FORMATS.md section 3.1 |
| Modules | `inventory/<name>.json`: `map`, and `modules[]` with `id`, `title`, `software`, `steps`, `likelihood` (`likely` or `possible`), `cite` (at least one inferred). FORMATS.md section 3.2 |
| Citation points | the citations above, resolved by containment against `records/` |

**The data island** (Folder view only). `template.html` renders the Folder view from `<script type="application/json" id="data">`: `workspace {path, label}`, `kinds[]`, `sections[]` (the folders that cite records, with their Used by labels), `folders[]`, and `files[]`, one per input and one per record that names no file inside `inputs/`. A file holds `file`, `bytes`, `sha256` (8 hex characters), `status`, `kind`, `kindFrom`, `captured`, `record` (the header, well-formed fields only, plus `recordCount` and `units`), `usedBy [{section, name, citations}]`, and `duplicateOf`, `convertWith` or `problem` when they apply. The page derives every total, sentence, grouping and anchor from `files[]`. The island holds no record text.

## 4. Rules the pages keep

- **Never authored.** Every value comes from `inputs/`, `records/`, the section files, `inventory/` and `formats/citation-types.json`.
- **Never stopped by data.** A record file it cannot use becomes an Error row; a section file that does not parse is skipped; every field is type-checked before use; a citation that does not resolve is shown as such; a file name that is not UTF-8 prints with `�`. `bs.py check` names each fix.
- **Deterministic** (build-3). No timestamps, no file dates, no random ids, every list sorted. Only `bs.py` stamps the `bs-build` meta.
- **Self-contained** (build-2). No network loads. Original data received lists `inputs/` paths, which is its job, so `bs.py` exempts it from the path check; it holds no full sha256. The systems inventory holds no `inputs/` path and no hash.
- **No absolute paths**, on the pages or in what the builder prints. A builder failure prints its exception and line number, never a traceback.
- **Sizes** print in decimal units (1 KB = 1000 bytes), one decimal below 10. **Dates** print as `1 Sep 2026`.

## 5. Look

The map tokens: `--bg #faf9f6`, `--paper #fff`, `--panel #f3efe7`, `--ink #111`, `--muted #626260`, `--line #dedbd6`, `--line-strong #c8c8c4`, `--flow #454542`, `--accent #ff5600` (the only accent), `--accent-ink #b84000` for small orange text, and 2px corners. `--peach #fbd9c4`, a quiet tint of the accent, marks Unchecked. Hairlines rather than boxes, one grid for every Overview table, nothing selected at load, short legend labels. The orange marks only what needs attention (Not converted, To do) and our suggestions (the module square).

### Current-state inventory mode

When the brief excludes suggestions, use `"mode": "observed"` in an inventory file. Its required modules/capabilities entry is fulfilled by documented use instead of the default suggested-module analysis; the required section is not skipped. Each entry keeps `id`, `title`, `software`, `steps` and `cite`, omits `likelihood`, and has grounded citations only. Its software must be named in grounded map evidence, and each linked step must name a system using that software. Use a capability name when the source does not identify a formal product module; never invent a module name.

The page says **Documented modules and capabilities** and **Observed in supplied sources**. Its summary explicitly scopes the inventory to systems and capabilities linked to mapped steps, not an exhaustive company inventory. These mean source-reported use at the source's date, not a live verification of implementation. A semantic checker must inspect the cited material to verify the capability and its association with the step; structural checks cannot prove that claim. Missing facts remain clarifications or evidence gaps.

Without `mode`, or with `"mode": "suggested"`, the original contract is unchanged: each entry needs `likelihood: "likely" | "possible"` and at least one inferred citation. Mixed inventories label observed and suggested entries separately. No AI layer is required for a current-state brief.

```json
{"type":"inventory","map":"end-to-end","mode":"observed","modules":[
  {"id":"MOD-01","title":"Budget holding","software":"Software C","steps":["RSV-01"],
   "cite":[{"source":"D2","locator":"¶3"}]}]}
```

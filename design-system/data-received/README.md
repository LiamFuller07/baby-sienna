# Original data received

The Original data received page is a calm, folder-style view of one workspace's `inputs/`. It shows what came in, what each file became, and where each file is cited.

It is **computed, never authored**. `bs.py build <ws>` builds it on every whole-workspace build, into `<ws>/out/data-received.html`. Nobody writes or edits any of its content, and there is no file to fill in. To change what the page says, change the workspace: add an input, convert it, or cite it.

| File | Role |
|---|---|
| `build_received.py` | `<ws> <out.html>`: reads the workspace and fills the template. Standard library only |
| `template.html` | the page: tokens, CSS, the tree, the detail pane, the overview and the print table. Two slots: the title and the data island |
| `README.md` | this file |

```
python3 design-system/data-received/build_received.py <ws> <ws>/out/data-received.html
python3 bs.py build <ws>                     # builds it with every other page
python3 bs.py build <ws> data-received       # builds only this page
```

Exit codes: 0 the page is written; 1 a data error (a record or section file that cannot be read, which `bs.py check` names); 2 cannot run (no `inputs/` folder, a toolkit file missing, the page cannot be written).

---

## 1. What the page shows

- **Header.** The workspace label, one sentence of totals (`13 files · captured 3 Aug – 20 Oct 2026 · 6 converted · 2 unchecked …`, with zero counts left out), and a summary strip: file count and total size, a count per kind, and a count per status.
- **File tree.** Every file in `inputs/`, with its subfolders, one row per file: name, status chip, size and captured date. It can be grouped by folder, by kind (in `citation-types.json` order, with unknown formats last), or by captured week (Monday to Sunday, with files that have no record last). A search box matches the name, the path, the record id, title and detail, the kind and the status. The keys are the usual tree keys: arrows move and fold, Enter selects, Esc closes.
- **Detail pane.** For the selected file:
  - the next step, when there is one;
  - **File:** kind, size, captured date and fingerprint (the first 8 hex characters of its sha256, compared with its record's);
  - **Record:** id and title (linked to `records/<ID>.json`), detail line, URL for a web source, coverage and units;
  - **Records:** the first 4 records, verbatim;
  - **Used by:** one row per section file that cites the record, with its citation count, linked to that file's page.
- **Overview** (nothing selected): files per kind, a captured strip with one mark per file coloured by status, and the next steps for every file that is not converted.
- **Phone.** The tree becomes a flat list grouped by folder, and the detail opens inline.
- **Print.** One table, grouped by folder: file, kind, status, record and units, detail, size, captured date, short hash and used by.

**Status chips.** Each file has exactly one status. `build_received.py` decides it the same way `bs.py check` and `bs.py status` do:

| Status | Chip | Rule | Rule id |
|---|---|---|---|
| `error` | **Error · ID**, ink on `--accent` | A record names this path, and the file is missing (`problem: missing`), its sha256 differs from the record's (`edited`), or the record's kind cannot take its extension (`kind`) | rec-2, rec-5 |
| `unchecked` | **Unchecked · ID**, ink on `--peach` | A record names the file, the sha256 matches, and the extension is in its kind's `unchecked` list: the converter agent wrote the record, and a person compares it | rec-5 |
| `converted` | **Converted · ID**, ink on `--panel` | A record names the file, the sha256 matches, and the extension is in its kind's `read` list | |
| `not-converted` | **Not converted**, `--accent-ink` text with an `--accent` outline | No record names the file. A container (`.zip` and the other `containers`) is always this, with the next step "unpack it" | ws-1 |
| `duplicate` | **Duplicate**, muted text with a `--line-strong` outline | No record names the file, but its sha256 equals a record's sha256. A warning, never a blocker | ws-1 |

Text on the filled `--accent` chip is ink (`#111`), not white: white on `#ff5600` is about 3.2:1 and fails AA.

## 2. The data island

The page renders everything from one block, `<script type="application/json" id="data">`. The island holds facts only; the page derives every total, sentence and grouping from `files[]`, so a count can never disagree with the rows.

**Top level**

| Field | Computed from |
|---|---|
| `workspace.path` | The workspace relative to the toolkit folder (`examples`, `work/client-a`). A workspace outside the toolkit is named by its folder alone. Never an absolute path |
| `workspace.label` | The workspace folder name, with hyphens as spaces and each word capitalised (`client-a` → `Client A`). The title is `<label> · data received` |
| `kinds[]` | `formats/citation-types.json › kinds`, in file order: `{id, label}` |
| `sections[]` | The four section folders, in order, with their page labels: Process map, AI layer, Document, Proposal |
| `folders[]` | Every folder under `inputs/`, `inputs` included, sorted. Empty folders show in the tree |
| `files[]` | One entry per file in `inputs/`, plus one per record whose input is missing. Sorted by path |

**`files[]`**

| Field | Computed from |
|---|---|
| `file` | The path relative to the workspace, always `inputs/…`. It equals the record's `file` when a record names it |
| `bytes` | The file's size on disk; `null` when it is missing |
| `sha256` | The first 8 hex characters of the file's sha256 now; `null` when it is missing. The page never holds a full hash |
| `status` | Section 1 |
| `kind`, `kindFrom` | The record's `kind` (`record`). Without a record, from the extension (`extension`): the first kind whose `read` list holds it, else the first whose `unchecked` list holds it, else `null`, shown as "Unknown format" |
| `captured` | The record's `captured` date. `null` for a file with no record of its own (not converted, or a duplicate): a file's modification date is not a fact about the material, so it is never used |
| `record` | The record header, or `null` (below) |
| `usedBy` | Citations of this file's record, one row per section file (below). `[]` without a record |
| `duplicateOf` | Only for `duplicate`: `{file, id}` of the record with the same sha256 |
| `convertWith` | Only for `not-converted`: `bs.py` when the extension is in its kind's `read` list (the page prints a `bs.py convert` command), `converter agent` otherwise, `unpack` for a container |
| `problem` | Only for `error`: `missing`, `edited` or `kind` |

**`record`**: the header of `records/<ID>.json`, copied verbatim (`id`, `title`, `kind`, `captured`, `detail`, `url`, `legacy`, `file`, `coverage`) except `sha256`, which is cut to 8 characters. Four page fields are added:
- `href`: `../records/<ID>.json`, relative to the page;
- `recordCount`: the number of records;
- `units`: `[{n, of}]`. A sheet gives its distinct sheet names (`sheet`) and its records (`cell`); a document or web page gives its distinct `p<n>` pages when the locators have pages (`page`) and its records (`paragraph`); a transcript gives its records (`turn`);
- `preview`: the first 4 records, verbatim, as `{locator, text, context?}`. The page clamps long text to three lines without changing it.

The detail line is the record's `detail`, printed verbatim (it is the "shared by" line). A web source prints its domain and URL. `legacy` is passed through and never printed.

**`usedBy`**: `{section, name, href, citations}`, in section order and then by name. `href` is `<section>/<name>.html`, relative to `out/data-received.html`. `citations` counts every source address whose source is this record:
- process map and AI layer: every entry of every `cite` array. A grounded citation counts 1, an inferred one counts each `from` entry, an absent one each `in` entry. Each source in a `[SRC locator]` marker in gap and clarification prose counts too;
- document: each source in a citation bracket (split at `;`), and each address on a Grounded, Inferred or Gap line. Front matter, fenced code, HTML comments, code spans, escaped brackets and link targets cite nothing, as in the document builder;
- proposal: every `cite` entry on a claim.

## 3. Rules the page keeps

- **Never authored.** Every value comes from `inputs/`, `records/`, the section files and `formats/citation-types.json`. Nothing is typed, and nothing in the page is edited per workspace.
- **Deterministic** (build-3). No timestamps, no file dates, no random ids, every list sorted: the same workspace gives the same bytes, wherever it is built from. Only `bs.py` stamps the `bs-build` meta.
- **Self-contained** (build-2). No network loads. This page is the one page that lists `inputs/` paths, which is its job, so `bs.py` exempts it from the path check. It still holds no full sha256: only the first 8 characters.
- **No absolute paths**, on the page or in what the builder prints.
- **Hidden files** in `inputs/` are skipped (ws-2 forbids them; `bs.py check` reports them).
- **Sizes** print in decimal units (1 KB = 1000 bytes), with one decimal below 10. **Dates** print as `1 Sep 2026`.

## 4. Look

The map tokens: `--bg #faf9f6`, `--paper #fff`, `--panel #f3efe7`, `--ink #111`, `--muted #626260`, `--line #dedbd6`, `--line-strong #c8c8c4`, `--flow #454542`, `--accent #ff5600` (the only accent), `--accent-ink #b84000` for small orange text, and 2px corners. `--peach #fbd9c4`, a quiet tint of the accent, marks Unchecked. Hairlines rather than boxes, nothing selected at load, and a legend that lists only the statuses present.

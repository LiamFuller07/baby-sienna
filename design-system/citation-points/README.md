# Citation points

**Required elements** (`template.json`). `bs.py build` refuses the page, with exit 1 and a `-> fix` hint (build-7), until each is fulfilled, and `bs.py status` prints `n of m required elements fulfilled` for it and names each missing one with the file and field that fulfils it.

- [ ] **At least one citation point**: a `cite` array in `process-map/`, `process-map-ai-opportunity/` or `inventory/`, or a `[ ]` bracket or Grounded, Inferred or Gap line in `document/` (cite-1).
- [ ] **Every point resolves**: each point's locator reaches at least one record in `records/<ID>.json` (cite-1).
- [ ] **Used by for every point**: computed, so it is always there: the element of a section file that cites the point, linked to the page that shows it (build-1).

The page also has one group per record file and the filter with its unused-records switch. They are computed, and nothing fulfils them.

## What it is

`out/citation-points.html` is one generated page per workspace. It lists every citation point the workspace's pages use, so it is the union of every page's own Citation points section. A point is either:
- a record address as a citation writes it, such as `WB1 Steps row 2`;
- an absent search of one address for one needle, such as `WB1 Steps row 7` for “Team”.

The page is computed from `records/` and the section files and is never authored (`formats/FORMATS.md` section 5.2). `bs.py build <ws>` builds it on every whole-workspace build that passes check, and `bs.py build <ws> citation-points` builds it alone:

```
python3 design-system/citation-points/build_citations.py <ws> <out.html>
```

The builder uses the standard library only and is deterministic. Its exit codes:
- **0**: the page is written.
- **1**: a section or record file cannot be read, or a required element is not fulfilled. The page is still written, and `bs.py` keeps it out of `out/`.
- **2**: it cannot run.

## Where the points come from

| Section file | What cites | Shown on, at |
|---|---|---|
| `process-map/<name>.json` | `systems[].cite` | `process-map/<name>.html#sys-<id>`, named by its label |
| | `systems[].software.cite` | `data-received.html#sw-<name>` (the board does not print it) |
| | `lanes[].cite` | `process-map/<name>.html#lane-<id>`, named by its label |
| | `nodes[].cite` | `process-map/<name>.html#<id>` |
| | `gaps[]` and `clarifications[]`: `cite` and the `[ ]` markers in their prose | `process-map/<name>.html#<id>` |
| `process-map-ai-opportunity/<name>.json` | `ai[].cite` | `process-map-ai-opportunity/<name>.html#<id>` |
| `document/<name>.md` | `[ ]` brackets and Grounded, Inferred and Gap lines, read by the document type's own parser | `document/<name>.html#<heading id>`, named by the heading they sit under (the title and lead link to the page) |
| `inventory/<name>.json` | `modules[].cite` | `data-received.html#mod-<id>` |

A grounded citation is used as **Grounded**, each record in an inferred citation's `from` as **Inferred from**, and each span in an absent citation's `in` as **Absent search**.

## The page, element by element

| Element | What it shows |
|---|---|
| Header | The kicker "Citation points" in accent-ink. Then `<label> · citation points` and one summary line: points, record files cited, records cited, and the elements and pages that use them. `<label>` is the client's name, as on Original data received: the maps' `meta.client` when they agree, else the workspace folder's name |
| On this page | One row of record files with their point counts. Each links to its group |
| Bar | A filter by address, text or element, the **Show only unused records** switch, and a count. It appears once the script runs; without the script, the page shows every point |
| Record file group, `#src-<id>` | One per record file, in natural id order. The id links to its row in Original data received (`data-received.html#<ID>`). Then the title, kind, captured date, the domain of a web source, the word Legacy when the record file says so, and the detail line. On the right: the file's points and how many of its records are cited, or "Not cited by any page" |
| Point row, `#<anchor>` | The address in monospace, such as `T1 · whole source` for an absent search with no locator. Then the verbatim records: one record as context and “text”; a span as one line per record with its locator, folding after six; an absent search as `Searched 3 records for “Team”: not found · Proven` (or Provisional). Last, **Used by**: one line per kind and page, the kind said once, then the elements, each named as its page shows it (`SUB-01`, `Gap 1`, `Clarification 4`, `Module B1`, a system's label) and linked to itself, then the page, named by its title and linked to its own Citation points section. A label never wraps |
| Unused records | With the switch on, each group lists instead the records that no grounded or inferred point reaches. The searched spans of an absent search do not count as used |
| Footer | What the page is computed from, and an example anchor |

Points within a group follow the record file's reading order: the first record a point reaches comes first, and the wider span leads. Absent searches come last.

## Anchors

A point row's id is the point's anchor from `formats/FORMATS.md` section 2.6: `src-` plus the address in lower case, with `¶` written `para` and any other run of characters that are not letters or digits written `-`. An absent search adds `-not-` and its needle, slugged the same way after NFKD: `src-wb1-steps-row-7-not-team`, and `src-t1-not-outcome` for a whole source. Every page links to these rows:
- every template page from the ↗ of each row of its Citation points section: process maps, AI pages, documents, Original data received and the systems inventory. For a document, `bs.py build` passes `--data-links ../` to `build_doc.py`, which prints that section.

A row lands with the shared 2px accent rule and fade. When the target is hidden by the filter or the switch, the script clears both.

## The build rule

`bs.py build` runs build-1 on this page, against every other page built in the same run, or against the page's current copy in `out/`:
- every link from a page into `citation-points.html` lands on an element;
- every point row is linked from some page. This is checked only when every page is at hand;
- every Used by link lands on an element of its page. The Folder view rows of Original data received are drawn by its script, so the workspace's record ids count as its elements.

build-2 and build-3 apply as on every page: the page is self-contained, holds no `inputs/` path, absolute path or hash, and gives the same bytes twice. Its `bs-build` hash covers `inputs/`, `records/`, the section files, `inventory/`, this folder, `design-system/document/` (whose parser it uses) and `formats/citation-types.json`.

## Look

The page uses the map tokens and the look of Original data received:
- `bg #faf9f6`, `ink #111`, `muted #626260`, hairlines `#dedbd6` and `#c8c8c4`, `flow #454542`, and accent-ink `#b84000` for the kicker only;
- one grid for every row: address 260px, records, Used by 300px;
- hairline rows and no boxes.

At phone width the rows stack. In print (A4), the bar and the On this page row go, the rows tighten, and the unused records stay hidden.

## Files

| File | What it is |
|---|---|
| `build_citations.py` | the builder: section files and records to the page |
| `template.html` | the page, its CSS and its script, with `{{slots}}` |
| `template.json` | the required elements |

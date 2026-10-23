---
name: citation-points
description: Use to build or explain the computed Citation points page, find what cites a record or which records nothing cites, or fix a citation point that does not resolve.
---

# citation-points: every citation point in the workspace

## Required elements (`design-system/citation-points/template.json`)

- [ ] **At least one citation point**: a `cite` array in `process-map/`, `process-map-ai-opportunity/` or `inventory/`, or a `[ ]` bracket or Grounded, Inferred or Gap line in `document/` (cite-1).
- [ ] **Every point resolves**: each point's locator reaches at least one record in `records/<ID>.json` (cite-1).
- [ ] **Used by for every point**: computed: the element that cites the point, linked to the page that shows it (build-1).

Optional and computed: one group per record file; the filter and **Show only unused records**. Fulfil every required element. The work is done only when `python3 bs.py status <ws>` shows them all fulfilled: `3 of 3`.

## What the template shows

`out/citation-points.html`, computed and never authored: the union of every page's own Citation points section. A header with one summary line, one group per record file (linked to its row in Original data received, `data-received.html#<ID>`), and one row per point: the address in monospace (`WB1 Steps row 2`), the verbatim records it resolves to (or, for an absent search, `Searched 3 records for “Team”: not found · Proven`), and **Used by**: Grounded, Inferred from or Absent search, then each element, linked to it. Row ids are the point anchors every page links to: `src-wb1-steps-row-2`, `src-wb1-steps-row-7-not-team`.

## Read

- `design-system/citation-points/README.md`: where the points come from, every element, the anchors and build-1.
- `formats/FORMATS.md` sections 2.6 and 5.2.

## Write

Nothing on this page. To add, fix or remove a point, change the citation in the section file that holds it (with that template's skill and the cite skill). A point that does not resolve fails `bs.py check` with cite-1: repoint it to a record that holds the fact, or turn the claim into a gap or a clarification.

## Commands

```sh
python3 bs.py check <ws>                       # cite-1: every point resolves
python3 bs.py build <ws>                       # every page, then build-1 checks this page against all of them
python3 bs.py build <ws> citation-points       # this page alone, against the pages already in out/
python3 bs.py status <ws>                      # 3 of 3
```

## The loop

fix citations in the section files → `python3 bs.py check <ws>` until it exits 0 → `python3 bs.py build <ws>` (the whole workspace, so every page links in) → open `<ws>/out/citation-points.html` and look: every row has its verbatim text and a Used by line; switch on Show only unused records to see which records no page cites yet.

## Watch for

- build-1 holds both ways: every link from a page into this page lands on a row, and every row is linked from a page. Build the whole workspace after any change to citations.
- The page holds no `inputs/` path, absolute path or hash (build-2).

## Example

`examples/out/citation-points.html`: 115 citation points from 7 record files, built from every section file in `examples/`. README: `design-system/citation-points/README.md`.

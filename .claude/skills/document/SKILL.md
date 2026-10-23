---
name: document
description: Use when writing or fixing document/<name>.md, a Source document (an A4 one-pager or a long screen page) whose every claim cites a record.
---

# document: the Source document

## Required elements (`design-system/document/template.json`)

- [ ] **Title and lead**: the `#` title, then a `>` lead block right under it (doc-1).
- [ ] **At least one claim section**: a `##` heading with at least one cited claim under it (doc-3).
- [ ] **Every claim cited, with an in-place marker**: a `[ID locator]` bracket, or a Grounded, Inferred or Gap line, on every claim (doc-3).
- [ ] **Citation points section**: computed by `build_doc.py --data-links`: `section#citation-points` in place of the type's Sources block, one row per point with its record id and locator, the verbatim text, the element it supports, and links to `data-received.html#<ID>` and `citation-points.html#<anchor>` (build-7).

Optional: the `:::callout Next step`. Fulfil every required element. The work is done only when `python3 bs.py status <ws>` shows them all fulfilled: `4 of 4`.

## What the template shows

A reference-point document in the Source design system: prose read top to bottom, on fixed A4 sheets (`mode: a4`, the default) or one long screen column (`mode: screen`). Every claim carries a small numbered marker where the source writes `[WB1 Steps!D3]`; the full locator and the verbatim text appear only in the Citation points section at the end. A document uses its own green ink and `#e9713b`, never the map tokens. To show a process, link to the map.

## Read

- `records/*.json`: every claim comes from a record.
- `design-system/document/README.md`: the Markdown subset, blocks, citations, pages and print.
- `formats/FORMATS.md` section 4: front matter, the citation forms and the claim rule.
- The cite skill.

## Write

`<ws>/document/<name>.md`:

```markdown
---
title: Request handling summary
label: Client A · Request handling
date: 22 October 2026
footer: Request handling summary
mode: a4
---

# Request handling (summary)

> One lead line: what the document is.

## What the sources show

Team A sends each request by email [T1 00:00:05], and Team B logs it in the tracker by hand [WB1 Steps!D3].

The completeness check is part of the review step.

Inferred · the completeness check is part of review · from WB1 Steps!D4; T1 00:00:18
```

- A bracket covers the sentence it sits in; a Grounded, Inferred or Gap line covers the whole block straight above it.
- A Gap line (`Gap · not in WB1 Steps row 7: “Team”`) must be PROVEN.
- Exempt from citing: the title, the first two `>` blocks, headings, table header rows, and `:::callout`, `:::aside` and `:::examples`. They still face the prose rules.
- Front matter keys are `title`, `label`, `date`, `footer` and `mode` only. Never write the sources map: `bs.py build` writes it from the record headers.

## Commands

```sh
python3 bs.py check <ws> document/<name>.md       # doc-1, doc-2, doc-3, prose-*
python3 bs.py build <ws> document/<name>          # -> <ws>/out/document/<name>.html
python3 bs.py build <ws> --prepare <dir>          # what build hands build_doc.py, to inspect
python3 bs.py status <ws>                         # 4 of 4
```

## The loop

write the Markdown → `python3 bs.py check <ws>` until it exits 0 → `python3 bs.py build <ws>` → open `<ws>/out/document/<name>.html` and look: one marker per claim, no A4 sheet running past its page (move `<!-- page -->`), and a Citation points section that lists every point.

The Citation points section is computed onto the last A4 sheet, about one line per point, and nothing warns when it pushes that sheet past its page. With more than about 8 points, put `<!-- page -->` before the last `##` section so the section gets room, or use `mode: screen`.

## Watch for

- **prose-1**: every `[ ]` in claim prose is a citation list naming record files. Write `\[` for a literal bracket.
- **prose-2 to prose-4**: quote with `“…”`; every quoted phrase and every number occurs in a record the sentence cites.
- **prose-6**: a document names no element ids (`SUB-01`).
- A sentence the sources cannot support is a Gap line or a question for the client, never an uncited sentence.

## Example

`examples/document/end-to-end-summary.md` → `examples/out/document/end-to-end-summary.html`, the showcase: the end-to-end purchase process of `examples/process-map/end-to-end.json` and `examples/process-map-ai-opportunity/end-to-end-ai.json`, its AI items and points to confirm linked to their cards by id. Its `<!-- page -->` after the callout keeps the document on one A4 sheet and gives its Citation points section the second. The small one is `examples/document/request-handling-summary.md` → `examples/out/document/request-handling-summary.html`. The type's own guide is `design-system/document/example.md`. README: `design-system/document/README.md`.

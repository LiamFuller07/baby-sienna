---
name: cite
description: Use whenever you write or fix a citation in a map, an AI layer, an inventory or a document - the three citation types, the rules per element, and how a page prints them.
---

# cite: the three citation types and the rules

Supports every template. Every claim cites a record that `bs.py check` can resolve; nothing is uncited except computed counts. A citation is done when `python3 bs.py check <ws>` reports no `cite-*` or `prose-*` finding and the page's Citation points section is fulfilled in `python3 bs.py status <ws>`.

## An address

`<source id> <locator>`, typed the same everywhere: `WB1 Steps!D3`, `WB1 Steps row 2`, `WB1 Steps rows 2-4`, `T1 00:00:31`, `T1 00:00:05-00:00:47`, `D1 ¶2`, `D1 ¶2-4`. In JSON: `{"source": "WB1", "locator": "Steps!D3"}`. A span resolves to every record inside it (containment). No locator means the whole source; only an absent search may use that.

## The three types

| Type | JSON | In a document | Rule |
|---|---|---|---|
| **grounded** | `{"source": "T1", "locator": "00:00:47", "quote": "…"}`; `quote` optional | `[T1 00:00:47]` or `[WB1 Steps!D3; T1 00:00:05]`; the line `Grounded · WB1 Steps row 2; T1 00:00:05` | resolves to ≥ 1 record (cite-1); a quote is verbatim in one (cite-2) |
| **inferred** | `{"type": "inferred", "reading": "…", "from": [{"source": "WB1", "locator": "Steps!D4"}]}` | `Inferred · <reading> · from WB1 Steps!D4; T1 00:00:18` | every `from` resolves; the reading is our words, 8–300 characters |
| **absent** | `{"type": "absent", "needle": "Team", "in": [{"source": "WB1", "locator": "Steps row 7"}]}` | `Gap · not in WB1 Steps row 7: “Team”` | the needle (case-insensitive, after quote folding) is in none of those records (cite-3). PROVEN when every source searched has complete coverage |

## Rules per element (cite-4)

```sh
python3 bs.py check --rules      # the generated table, formats/FORMATS.md section 2.3
```

- **Map:** a system needs grounded (its label in a record it cites); a node grounded (state grounded or gap) or inferred (state inferred); a gap an absent search **and** a grounded citation; a clarification grounded; a lane nothing unless it holds no step. Groups and edges carry none.
- **AI item:** named needs a grounded quote holding an AI term, from a source that is not web (ai-3); suggested needs inferred.
- **Inventory module:** inferred.
- **Document sentence:** any of the three, by a bracket in the sentence or a line straight after its block. A Gap line must be PROVEN.
- **Web sources** (cite-5) only on suggested AI items, modules and document sentences, and never alone.

## Prose rules (prose-1 to prose-6)

- Brackets only in claim prose (gap and clarification text, document sentences), each a list of addresses. Write `\[` for a literal bracket.
- No straight `"`: quote with `“…”`, and the quoted words occur in a record the element cites.
- Every number occurs as a whole token in a record the element cites; counts come from `{count:…}` tokens in a map's subtitle only.
- An element-id-shaped token names a real element; documents name none. A missing fact is a gap or a clarification, never an uncited sentence.

## How a page prints them (computed, never typed)

- **One small numbered marker** on each cited element (`a.cp-mk`, a muted 9–10px numeral): a card, a step, a row, a claim. It links to the point's row in the page's **Citation points** section; hover or focus shows the address and the first words of the text.
- **The Citation points section** ends every page: number, address in monospace, verbatim text, the elements it supports, a link to the file's row in Original data received (`data-received.html#<ID>`) and to `citation-points.html#<anchor>`.
- **Anchor:** `src-` + the address in lower case, `¶` as `para`, other runs as `-`; an absent search adds `-not-<needle>`: `src-wb1-steps-row-7-not-team`.
- No citation lives only in a tooltip (build-4).

## Example

Every file in `examples/` cites; `examples/out/citation-points.html` lists all 115 points. README: `formats/FORMATS.md` section 2.

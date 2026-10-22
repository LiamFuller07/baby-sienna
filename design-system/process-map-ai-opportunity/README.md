# process-map-ai-opportunity: the AI layer over a current-state map

One `process-map-ai-opportunity/<name>.json` names a base map and adds AI items. The page is the base board, with the layer's marks, legend block, toggle, summary strip and AI card added in the base page's slots. The base is never changed. With the layer off, the page shows the base board (build-5).

This folder holds:
- **This README:** the file, the contract with the base, and every element.
- **`ai-layer.schema.json`:** fields, limits and patterns. It takes the node, group and file patterns from `process-map.schema.json`.
- **`fills.html`:** slot fills only: `pm-ai-*` CSS, the legend block, toggle, summary, AI card and overlay JS.
- **`specimen.html`:** every element in every state, built from `examples/` by `build_map.py --specimen`.

There is no builder here: `design-system/process-map/build_map.py` builds both map sections. The shared rules are in `formats/FORMATS.md`.

---

## 1. The file

| Field | Req | What it is |
|---|---|---|
| `type` | req | `"process-map-ai-opportunity"` |
| `base` | req | a map in `process-map/` that passes its checks (ai-1). Lanes, nodes, edges, cards, systems, client and footer come from it |
| `meta` | req | `title` is required; `kicker`, `subtitle` (design prose) and `date` are optional. They replace the base's header text and, when given, its footer date |
| `ai[]` | req | items sorted by id (ai-2). `[]` is valid and draws the empty state |

**Item.** `{id, title, origin, does, nodes?, groups?, cite, agentic?}`.
- `title` is sentence case, starts with a verb and has no final full stop.
- `origin` is `named` (the client asked for it in their own words) or `suggested` (our idea). Filled marks mean named and outlined marks mean suggested, everywhere.
- `does` is "What it would do", in one to three sentences.
- `nodes` lists base steps (kind step, not decisions). Each step gets a halo and a square.
- `groups` lists base groups, or is `"all"`. A view item marks the group cell, not its steps. View items need a base with two or more groups.

**Targets (ai-2).** `nodes` and `groups` are not both empty; `"all"` takes no nodes; a listed step may not sit in a group the same item lists; every id exists in the base.

**Citations.**
- A named item needs a grounded quote, from a source that is not web, that holds an AI term (ai-3). This is necessary, not sufficient: the checker agent reads every named item.
- A suggested item needs an inferred citation. It may also cite web pages, but never web pages alone (cite-5).

**Agentic version (ai-4).** `{trigger, steps (2–8, each starting with a verb), decides (≥ 1 of {after, who, what}), systems, logging}`.
- `after` is a step number; the person decides after that step. An agentic version with no human decision is invalid.
- `systems` are base `systems[]` ids.
- It cites nothing, but its numbers must occur in records the item cites (prose-4).

**Example:** `examples/process-map-ai-opportunity/current-state-ai.json` has four items:
- AI-01: named, on a step;
- AI-02: suggested, on a step, with an agentic version;
- AI-03: suggested, on one view;
- AI-04: suggested, across all views, citing a web page beside an inferred reading.

---

## 2. The contract with the base board

- **Slots.** The layer fills five named slots in `board.html`, and one script hook:
  - `toolbar`: the toggle, then the summary strip.
  - `legend-end`: the AI legend block.
  - `board-under`: halos and band tints. They are drawn after the lanes and band, and before the edges.
  - `board-over`: squares, view underlines, the all-views bracket, and the transparent hit targets that carry `data-ai`, `tabindex`, `role` and `aria-label`. They are drawn after nodes and pills. Its gutter part, `board-over:gutter`, holds `ALL VIEWS` and its squares, since the gutter is its own SVG.
  - `evidence-start`: the AI card, first in the evidence grid.
  - The `tooltip-lines` hook adds a node's AI lines to the base tooltip. There is one tooltip.
  - Two carriers, not slots of the board: `style` takes the `pm-ai-*` CSS and `script` the overlay JS.
- **Nothing on the base changes.** Removing every `.pm-ai*` element gives the base page's board (build-5).
- **Band geometry**, for a base with two or more groups:
  - The band runs from y 8 to 44.
  - A view underline is 2 units, at y 41, from `gx + 6` to `gx + gw − 6`.
  - A view's squares are 16 units, centred at y 26 at the cell's right end, stepping left 20; after two comes `+n`. The group label is cut so that it ends 8 units before them.
  - The all-views bracket runs along y 8, with ticks down at each end.
  - The gutter's band cell holds `ALL VIEWS` and its squares, and nothing else.
- **Node geometry.** The halo is a rect at `(x − 4, y − 4, W + 8, H + 8)` with rx 6. With k squares, square j is centred at `(x + W − 21·(k − 1 − j), y + H + 5)`. Squares hang from the bottom-right corner, right of the centre line and clear of the gap tag. A step shows up to three; with four or more items it shows two and `+n`.
- **Corners.** Badges own the top-left corner, the system icon the top-right, and AI squares the bottom-right.
- **Marks.** AI marks are squares and gap and clarification marks are circles. A dashed border or pill means inferred or gap; a dashed line means feedback.

---

## 3. Elements

Driven by names data fields. `(derived)` is computed by the build and `(ui)` is viewer state. The anchor is the element's section in `specimen.html`.

| # | Element | States | Driven by | Anchor |
|---|---|---|---|---|
| 1 | Header text | — | `meta.kicker`, `.title`, `.subtitle` override the base; the rest is inherited | `#ai-header` |
| 2 | Halo | default · thick (focus, hover) · faded · hidden (layer off) · peek (layer off, item hovered) | a step in `ai[].nodes`. One per step, never dashed | `#ai-halo` |
| 3 | Node square | named (filled) · suggested (outlined) · faded · hidden · peek · `+n` | `ai[].nodes`, `.origin`, `.id` (the digits are derived). `<title>`: `AI-01 Draft the review summary · Named by the client` | `#ai-square` |
| 4 | View underline | default · on (band cell tinted) · hidden · peek | `ai[].groups` (a list). One per listed view, never joined | `#ai-view` |
| 5 | All-views bracket | default · on (every band cell tinted, nothing fades) · hidden · peek | `ai[].groups = "all"`. Drawn once | `#ai-all` |
| 6 | Legend block | on · off (40%, heading `AI LAYER · HIDDEN`) · left out when `ai` is empty | base `meta.client`: `AI named by Client A`, `AI suggested by us`, `Step with an AI opportunity`, `AI across a view or all views` | `#ai-legend` |
| 7 | Toggle | on (every load, not remembered) · off · hover · focus-visible · `None` when `ai` is empty | (ui) | `#ai-toggle` |
| 8 | Summary strip | standard · off (adds "hidden on the board") · empty | (derived), e.g. `4 AI opportunities · ■ 1 named by the client · □ 3 our suggestions · touches 2 of 6 steps · 1 across a whole view · 1 across all views`. A zero segment is left out; decisions are not steps | `#ai-summary` |
| 9 | AI card | list · empty | `ai[]` by id: heading "AI opportunities" and `4 items · hover a row to see it on the map` | `#ai-card` |
| 10 | Card row | default · active · linked (its step hovered) · pinned | one item: square, `AI-01` and title, origin chip (`Named by the client` or `Our suggestion`), `Show on map`, "What it would do", target chips (`REV-01 Review request`, `G02 Review and approval · whole view`, `All views`), and evidence | `#ai-row` |
| 11 | Evidence | grounded quote · grounded without a quote · inferred | A grounded citation shows its `quote`, or else the text of its first record, then `Grounded · T1 00:01:15`, with `· Speaker A` (the record's context) for a transcript and `· example.com` for a web page. An inferred one shows **Basis:** the reading, then `Inferred · from WB1 Steps!D3, T1 00:01:02`. Addresses link to Sources | `#ai-evidence` |
| 12 | Agentic version | folded (default) · open · print (open) · absent | `agentic.*`; the meta line `3 steps · 1 place a person decides · 2 systems` (derived). Steps on a numbered spine, each `decides` entry after its step as **Person decides** · `Team B checks the entry…`, then systems with the base icons, then logging. No orange inside | `#ai-agentic` |
| 13 | Empty state | `ai: []` | the base board; the toggle reads `AI layer · None`; no legend block; one dashed card row: **No AI opportunities identified for this process yet.** | `#ai-empty` |
| 14 | Tooltip lines | a step with items | (derived) through the `tooltip-lines` hook: one line per item (square, id, title, origin word), then "Click to open the card" | `#ai-tip` |
| 15 | Linking | card to board · board to card · click pins · Esc unpins | (ui). A row lights its steps and fades the rest; a view item tints its cells; an all-views item fades nothing. It works with the layer off while the hover lasts | `#ai-link` |

**Responsive and print.**
- At 900px and below, card rows stack. At 700px and below, the page gutter is 16px, and the board keeps a minimum width of 860px inside its own scroll.
- There is never a horizontal page scroll; this is checked at 390px.
- Print forces the layer on and opens every agentic block.

---

## 4. Class and attribute index

| Class or attribute | Element |
|---|---|
| `svg.pm-board.has-ai` | the board with the layer on |
| `.pm-ai` | any element hidden when the layer is off |
| `.pm-ai-under`, `.pm-ai-over` | the board-under and board-over slots |
| `.pm-ai-node[data-node][data-ai]`, `.pm-ai-halo` | halo |
| `.pm-ai-marks`, `.pm-ai-sq.is-named`, `.pm-ai-sq.is-suggested`, `.pm-ai-more` | squares |
| `.pm-ai-hit[data-node][data-ai]` | hit targets (`tabindex`, `role=button`, `aria-label`) |
| `.pm-ai-view[data-group][data-ai]`, `.pm-ai-all[data-ai]`, `.pm-ai-rail[data-ai]`, `.pm-ai-all-text`, `.pm-ai-band-hit[data-group]` | view and all-views marks |
| `.pm-ai-toggle`, `.pm-ai-toggle-ind`, `.pm-ai-toggle-state` | toggle |
| `.pm-ai-summary`, `.pm-ai-summary-in`, `.pm-ai-sum-sq` | summary strip |
| `.pm-ai-legend`, `.pm-ai-sw-named`, `.pm-ai-sw-suggested`, `.pm-ai-sw-halo`, `.pm-ai-sw-rail`, `.pm-legend.is-ai-off` | legend |
| `.pm-ai-card`, `.pm-ai-count`, `.pm-ai-list`, `.pm-ai-item[data-ai]`, `.pm-ai-mark`, `.pm-ai-head`, `.pm-ai-title`, `.pm-ai-id`, `.pm-ai-origin`, `.pm-ai-show`, `.pm-ai-cols`, `.pm-ai-label`, `.pm-ai-does`, `.pm-ai-steps`, `.pm-ai-step`, `.pm-ai-step.is-scope`, `.pm-ai-cite.is-quote`, `.pm-ai-cite.is-inferred` | card |
| `.pm-ai-agentic`, `.pm-ai-ag-title`, `.pm-ai-ag-meta`, `.pm-ai-ag`, `.pm-ai-flow`, `.pm-ai-sys` | agentic version |
| `.pm-ai-empty` | empty state |
| `.pm-ai-tip-line` | tooltip lines |
| `.is-ai-focus`, `.is-ai-hit`, `.is-ai-on`, `.is-ai-hover`, `.is-ai-peek`, `.is-ai-flash`, `.is-ai-active`, `.is-ai-linked`, `.is-ai-pinned` | interaction states |

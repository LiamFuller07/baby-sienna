# process-map: the current-state swimlane board

One `process-map/<name>.json` becomes one self-contained page: a header, the system key and legend, the board (lanes, nodes, decisions, lines, badges), the Gaps, Clarifications needed and Sources cards, and a footer. It shows the process as the sources describe it today, and holds no AI ideas (map-9).

This folder holds everything about the section:
- **This README:** the file, the layout, every element and its states.
- **`process-map.schema.json`:** fields, limits and id patterns.
- **`board.html`:** tokens, `pm-*` CSS, the viewer JS (Fit and 100%, the gutter, the tooltip, jumps), and the named slots the AI layer fills.
- **`build_map.py`:** computes the layout and routing (so build-6 can fail the build) and builds both map sections.
- **`specimen.html`:** every element in every state. It is built from `examples/` by `build_map.py --specimen`.

The shared rules (records, citation types, prose rules, check ids) are in `formats/FORMATS.md`. Tokens and sizes live only in `board.html`.

---

## 1. The file

Arrays are in display order: lanes top to bottom, groups left to right, nodes group by group in flow order (map-2). The schema holds every limit; the limits are layout limits.

| Field | Req | What it is |
|---|---|---|
| `type` | req | `"process-map"` |
| `meta` | req | `kicker`, `title`, `client` and `date` are required; `subtitle`, `flags` (`confidential`, `draft`) and `footer` are optional. The subtitle cites nothing: its numbers come from `{count:steps}`-style tokens, filled in by the build |
| `systems[]` | opt | `{id, label, icon, cite}`: the key row and the node icons. `cite` names a record that holds the label (map-8) |
| `lanes[]` | req | `{id, label, cite?}`: a role, never a person. A lane that holds no step cites its role (map-3) |
| `groups[]` | opt | `{id, label}`: views. With two or more groups the board draws a band of group cells; with groups, every node names one (map-2) |
| `nodes[]` | req | a step or a decision (below) |
| `edges[]` | opt | `{from, to, kind?, label?}`. An edge carries no citation: its end nodes hold the evidence |
| `gaps[]` | opt | `{id, title, text, nodes, cite}`: what the sources do not say, proven by an absent search |
| `clarifications[]` | opt | `{id, title (the question), shows (what the sources show), ask (what to confirm, with whom), nodes, cite}` |

**Node.** `{id, title, kind?, lane, group?, state, owner?, systems?, col?, cite}`.
- `kind` is `step` (the default) or `decision`. A decision's `title` is its question; it has no owner or systems, and its branches are conditional edges with different labels (map-4).
- `state` is `grounded` (a record says it), `inferred` (our reading, printed on the card, map-7) or `gap` (the step exists, but something about it is missing; exactly one gap card lists it, map-6). A gap-state step stays in its own lane and keeps its owner line.
- `col` is a layout hint: the node's column within its group. It may push a node right of its derived column, never left (map-10).

**Edges.**
- `flow` (the default) joins two nodes. An edge to an earlier-listed node is feedback and is drawn dashed.
- `conditional` leaves a decision and carries its branch `label`, the only label an edge has. The label's numbers come from a record its decision cites.
- An edge may cross groups and lanes; a line that crosses lanes is the hand-over.

**Citations on a map** (rules in `formats/FORMATS.md` section 2.3):
- Nodes, systems, lanes, gaps and clarifications cite; groups do not. Edges may carry their own `cite` list, checked and printed in the Connection evidence card. Endpoint citations alone do not establish a connection.
- Gap and clarification prose may hold `[SRC locator]` markers, which count as the card's grounded citations.
- A `quote` on a map citation is a check aid (cite-2); the board does not print it.
- Where it prints: a node's first grounded address is on its detail line, and a decision's under its bottom vertex. Card citations are in the card's provenance line. Everything else (systems, lanes, a node's other addresses) is printed as a Sources entry whose "Used by" names the element (build-4).

**Example:** `examples/process-map/current-state.json`. It has every node state, a decision with Yes and No branches, a feedback flow, flows across lanes and across groups, a gap step drawn in its lane, a gap proven by two absent searches, and a clarification whose marker `[T1 00:00:47]` both cites the call and sources the number 5,000.

---

## 2. Layout (derived, never authored)

The formats fix the layout, so one map always gives the same board (build-3).

**Columns.**
- With no groups, the board is one group.
- Groups take consecutive columns, left to right.
- Within a group, a node's column is 1 plus the longest path to it over forward edges inside the group (an edge to a later-listed node). A `col` hint may raise it.
- A node's board column `c` (from 0) is the columns of the earlier groups, plus its column within its group, minus 1. A board has at most 14 columns (map-10).

**Rows.** A node's row is its rank, in listing order, among the nodes in the same lane and board column. A lane is 144 units per row, or 56 when it holds no node.

**Coordinates** (SVG units at 100%).
- A card is 156 × 104 at `x = 166 + 188c`, `y = laneTop + 20 + 144·row`.
- A decision is a 60.2 square, turned 45° about the card's centre `(x + 78, y + 52)`.
- With two or more groups, the group band runs from y 8 to 44 and the lanes start at y 52. Otherwise the lanes start at y 18.
- The board is as wide as the last card's right edge plus 28, and as tall as the last lane's bottom plus 16.
- It is drawn as two SVGs, the gutter (`0 0 150 H`) and the canvas, so the gutter can stick.
- The draw order is lanes, band, edges, nodes and diamonds, then pills.

**Routing.**

| Case | Route |
|---|---|
| forward, target in the same row and lane | straight, from the source's right edge (a decision's right vertex) to the target's left edge |
| forward, target in another row or lane | from the right edge into the gap just left of the target's column, vertically to the target's centre line, then into its left edge |
| a decision's second branch | leaves the top vertex (target higher) or the bottom vertex (target lower or level), then runs as above. The first-listed branch takes the right vertex |
| feedback (target listed earlier) | dashed; from the source's top edge centre, up into the channel 10 units above the source row, along it, then into the target's top edge centre (its bottom edge centre when the target sits higher, so the line never crosses it) |

A branch pill shows the label only. It is centred on the line's longest horizontal stretch. If a line would cross a card, or a pill would not fit its stretch with 16 units to spare, the build fails and names the edge (build-6). The fix is to shorten the label or set `col`.

Before failing, the router now searches deterministic detours through column
gaps and row channels. A detour must pass the same card-collision and free-label
checks as the normal route. Graph endpoints and direction never change.
Two differently labelled branches may share a destination; identical edges
remain invalid. A decision with unavailable branches may set
`branchesIncomplete: true` only with a cited clarification attached to it.
Map-level source notes can be clarifications with an empty `nodes` list.
Sources are shown first in a right-hand evidence panel on wide screens, and
below the map on small screens and in print. Large source spans expand to show
all records instead of dropping everything after the first ten.

**Room the AI layer relies on.**
- 20 units of lane padding below each card row.
- No base line along a card's bottom edge to the right of its centre.
- No base stroke on the band's top edge or across its cells' bottom 6 units, other than the band's own bottom border.
- The right 70 units of each band cell: the group label is cut short of them, so the layer's view squares never cover it (build-5).

---

## 3. Elements

Driven by names data fields. `(derived)` is computed by the build, `(template)` is fixed text in `board.html`, and `(ui)` is viewer state. The anchor is the element's section in `specimen.html`.

| # | Element | States | Driven by | Anchor |
|---|---|---|---|---|
| 1 | Page header | full · minimal (kicker and title only) · long title (wraps, never cut) | `meta.kicker`, `.flags` (chips; confidential has an orange border), `.title`, `.subtitle` with tokens filled (derived) | `#pm-header` |
| 2 | System key | systems · omitted when there are none | `systems[].icon`, `.label` | `#pm-key` |
| 3 | Legend | 3 × 3 on desktop · 2 columns under 640px | (template): Process flow, Feedback, Decision, Clarification, Grounded, Inferred, Gap | `#pm-legend` |
| 4 | Lane and gutter | alternating fills · long name (3 lines, then …) · stacked rows · empty | `lanes[]` order and `label`; the note `3 steps` (derived) | `#pm-lane` |
| 5 | Group band | drawn with two or more groups · targeted (`#G01`) · long label (cut with …) | `groups[].id`, `.label`; the meta `4 steps` (derived) | `#pm-band` |
| 6 | Node card | grounded · inferred · gap · with or without owner · long title (3 lines, then …) · several systems · hover · keyboard focus · targeted | `title`, `state`, `owner`, `systems`, `cite`. The detail line (derived) is `SUB-01 · WB1 Steps row 2 +1` (`+1` counts the other grounded citations) or `Inferred · <reading>`. A gap step adds the tag `Needs confirmation`. The focus ring is 2px ink, 8 units out, so it never reads as an AI halo | `#pm-node` |
| 7 | Badges | gap (filled orange) · clarification (dashed orange ring) · `+n` after three | `gaps[].nodes`, `clarifications[].nodes`. The number is the list position (derived), and the badge links to its card item | `#pm-badge` |
| 8 | System icon | 1 · 2 · `+n` | `nodes[].systems` → `systems[].icon` | `#pm-sys` |
| 9 | Decision diamond | grounded · inferred (dashed grey) · gap (dashed orange) · with a clarification · long question (2 lines) | `kind: decision`, `title`, `state`, its branches. The detail line `REV-02 · WB1 Steps row 5` (derived) sits under the bottom vertex, or in two lines right of the line when a branch leaves that vertex | `#pm-decision` |
| 10 | Edges | flow · branch with its label pill · feedback (dashed) · hover | `edges[]`; feedback (derived) | `#pm-edge` |
| 11 | Board shell | Fit · 100% (sticky gutter, drag to pan) · phone (compact gutter) | (ui) | `#pm-shell` |
| 12 | Tooltip | step · decision · truncated title | (derived): id · group, title, lane, owner, systems, marks, provenance line. It only repeats printed facts. On an AI page it also gains the AI lines | `#pm-tip` |
| 13 | Gaps card | list · targeted item · empty: **No gaps on this map.** / "Every step has at least one source." | `gaps[]`: numbered marker, title, text with markers, `Steps: REC-01`, provenance line | `#pm-gaps` |
| 14 | Clarifications card | list · targeted item · empty: **Nothing to confirm on this map.** | `clarifications[]`: title, `What the sources show:` `shows`, `To confirm:` `ask`, `Steps: APP-01`, provenance line | `#pm-clar` |
| 15 | Sources card | per source · span entry (`3 records`, up to 10 listed) · absent search (`Searched for “Team”: not found · PROVEN`) · targeted entry | every record the page uses (derived, `formats/FORMATS.md` section 2.6). It spans both columns, after Gaps and Clarifications | `#pm-sources` |
| 16 | Footer | flags · no flags · phone (the sides stack) | Left: `meta.footer`, default `Source · process map`. Right: `Contains Client A confidential information` (confidential) · `Draft` (draft) · `22 Oct 2026`, each clause only when it applies | `#pm-footer` |
| 17 | Empty states | lane with no steps (`No steps in this lane`) · no gaps · no clarifications · no systems · no flags · 0 or 1 group (no band) | empty arrays | `#pm-empty` |

The tooltip, the Fit and 100% zoom, the flags chips, lane notes and the Sources card are additions to the reference; section 4 lists them.

---

## 4. Departures from the design reference

The reference is another client's swimlane board, and only its design is used. These are the intended differences; anything else that differs is a bug.

| Reference | This board | Why |
|---|---|---|
| node radius rx 4, diamond rx 3 | rx 2 for both | one radius across the board |
| a dashed `?` clarification badge | numbered badges only | the number links to the card item |
| a node detail line naming the system and evidence | `<id> · <address>` | the address is the citation, in the one notation |
| provenance lines with personal names | addresses | speakers and owners are roles, and an address resolves |
| an inferred diamond dashed in orange | dashed grey (`--soft`) | orange is kept for gaps and AI |
| orange small text in the base orange | `--accent-ink` (`#b84000`) under 14px | at least 4.5:1 on every board background |
| one Gaps legend item | separate Gap and Clarification items | they are different marks |
| no zoom; the shell hides overflow | Fit and 100% | a 14-column board needs Fit; size is capped at 40 nodes, 8 lanes and 14 columns so Fit stays legible |
| no focus ring | 2px ink ring 8 units out | keyboard use, and never confused with the AI halo |
| — | flags chips, lane notes, the group band (with two or more groups), the tooltip, the Sources card | these show the formats' metadata and evidence |

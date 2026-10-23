# process-map: the current-state swimlane board

**Required elements** (`template.json`). `bs.py build` refuses the page, with exit 1 and a `-> fix` hint (build-7), until each is fulfilled, and `bs.py status` prints `n of m required elements fulfilled` for it and names each missing one with the file and field that fulfils it.

- [ ] **Header**: `process-map/<name>.json › meta`: kicker, title, client and date (schema-1).
- [ ] **Lanes**: `lanes[] {id, label}`: at least one, each a role (map-3).
- [ ] **Steps with owners**: `nodes[]`: at least one step, each in the lane of the role that owns it, with its `owner`, state and cite. Only a gap-state step may leave `owner` out: its gap card says what is missing (build-7).
- [ ] **Flows**: `edges[] {from, to}`: every node joined to the flow, and at least one edge when the map has two or more nodes; a step whose order no source states is listed instead by an order clarification (`order: true`) that asks where it comes, and has no edge (map-5).
- [ ] **Gaps card**: `gaps[]`: at least one, proven by an absent search (cite-4); or, when no step is in gap state and every step's owner and outcome is in a record it cites (a step whose order no record states is asked by an order clarification instead), one None found card (`none: true`, `nodes: []`) that cites those records, grounded or inferred (map-6). Never invent a gap.
- [ ] **Clarifications card**: `clarifications[]`: at least one (cite-4); or one None found card (`none: true`, `nodes: []`) that cites why nothing is left to confirm, grounded or inferred (map-6). An order clarification (`order: true`) asks where its steps come.
- [ ] **Citation points section, with in-place markers**: computed from every `cite`: one numbered marker (`a.cp-mk`) on each cited element, and `section#citation-points` with one `li.cp-row` per point the page uses, each with its verbatim text, Used by, and links to `data-received.html#<ID>` and `citation-points.html#<anchor>` (build-7).

Optional: the system key (`systems[]`) and the views band (`groups[]`, two or more).

One `process-map/<name>.json` becomes one self-contained page: a header, the system key and legend, the board (lanes, nodes, decisions, lines, badges), the Gaps and Clarifications needed cards, the Citation points section, and a footer. It shows the process as the sources describe it today, and holds no AI ideas (map-9): the page holds no `pm-ai` at all (build-5).

Every cited element carries one quiet numbered marker, and the Citation points section at the end lists every point the page uses, numbered to match, with links back to the data (section 3.1).

This folder holds everything about the section:
- **This README:** the file, the layout, every element and its states.
- **`process-map.schema.json`:** fields, limits and id patterns.
- **`board.html`:** tokens, `pm-*` and `cp-*` CSS, the viewer JS (Fit and 100%, the gutter, the tooltips, jumps), and the named slots the AI page fills.
- **`build_map.py`:** computes the layout and routing (so build-6 can fail the build), numbers the citation points, and builds both map sections (the AI page's List and Flow included).
- **`specimen.html`:** every element in every state. It is built from `examples/` by `build_map.py --specimen`.

The shared rules (records, citation types, prose rules, check ids) are in `formats/FORMATS.md`. Tokens and CSS sizes live only in `board.html`; the board geometry of section 2 lives in `build_map.py`.

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
| `gaps[]` | opt | `{id, title, text, none?, nodes, cite}`: what the sources do not say, proven by an absent search; or one None found card, `none: true` and `nodes: []`, the only card of its kind, citing the records that show nothing is missing (map-6) |
| `clarifications[]` | opt | `{id, title (the question), shows (what the sources show), ask (what to confirm, with whom), order?, none?, nodes, cite}`. `order: true` asks where its steps come: it lists only steps no edge joins, and excuses them from Flows (map-5). Or one None found card (map-6) |

**Node.** `{id, title, kind?, lane, group?, state, owner?, systems?, col?, cite}`.
- `kind` is `step` (the default) or `decision`. A decision's `title` is its question; it has no owner or systems, and its branches are conditional edges with different labels (map-4).
- `state` is `grounded` (a record says it), `inferred` (our reading: the card is dashed, and the reading is printed in Citation points and the tooltip; map-7 caps it) or `gap` (the step exists, but something about it is missing; exactly one gap card lists it, map-6). A gap-state step stays in its own lane.
- `owner` is the role that owns a step, printed on its card. Every step needs one (build-7), except a gap-state step whose gap is that no owner is named.
- `col` is a layout hint: the node's column within its group. It may push a node right of its derived column, never left (map-10).

**Edges.**
- `flow` (the default) joins two nodes. An edge to an earlier-listed node is feedback and is drawn dashed.
- `conditional` leaves a decision and carries its branch `label`, the only label an edge has. The label's numbers come from a record its decision cites.
- An edge may cross groups and lanes; a line that crosses lanes is the hand-over.

**Citations on a map** (rules in `formats/FORMATS.md` section 2.3):
- Nodes, systems, lanes, gaps and clarifications cite; groups and edges do not.
- Gap and clarification prose may hold `[SRC locator]` markers, which count as the card's grounded citations.
- A `quote` on a map citation is a check aid (cite-2); the board does not print it.
- Where it prints: every cited element carries one numbered marker in place (a card after its title, a decision after its id, a system in the key, a lane in the gutter, each `[SRC locator]` bracket in card prose, each clause of a card's provenance line). The full address and the verbatim text print only in the Citation points section, whose row for each point names every element it supports (build-1, build-4).

**Examples.**
- `examples/process-map/end-to-end.json`, the showcase: a purchase request from submission to close. 35 nodes (31 steps, 4 decisions) in 7 lanes and 6 views over the full 14 columns, four loops (an incomplete request goes back, an approval pack is reworked, an unconfirmed order is resent, a mismatched invoice is queried and matched again), 3 gaps and 5 clarifications, from a 33-step sheet (`WB3`, `inputs/Process.csv`) and a 25-turn walkthrough call (`T3`, `inputs/walkthrough-call.txt`). On a laptop screen it opens at 100%, where every card reads; Fit shows the whole process.
- `examples/process-map/current-state.json`, the small one the specimens are built from. It has every node state, a decision with Yes and No branches, a feedback flow, flows across lanes and across groups, a gap step drawn in its lane, a gap proven by two absent searches, and a clarification whose marker `[T1 00:00:47]` both cites the call and sources the number 5,000.

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
- A card is 156 × 104 at `x = 170 + 196c`, `y = laneTop + 20 + 144·row`. Two columns stand 40 apart; a group divider runs down the middle of its gap, 20 left of the card.
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
| a decision's second branch | leaves the top vertex (target higher) or the bottom vertex (target lower or level), then runs as above. The first-listed branch takes the right vertex. A level target goes through the channel 16 units above (or below) the row |
| feedback (target listed earlier) | dashed; from the source's top edge centre, up into the channel 16 units above the source row (clear of the corner marks, which reach 11 above), along it, then into the target's top edge centre (its bottom edge centre when the target sits higher, so the line never crosses it). A decision whose top vertex carries a forward branch sends it from its bottom vertex instead, through the channel 16 units below the row, so the two lines never share a segment. A line into a decision's bottom vertex moves its id label to the right, as a line out of it does |

**Tracks in a gap.** Lines from different sources never share a vertical line. In each gap, every source whose lines turn there takes its own track, 6 units apart (the middle, then 6 left, then 6 right); sources whose stretches of the gap do not meet share one. The tracks are ordered so no line runs through a mark or shares a stretch with another source's line, then for the fewest crossings. A gap holds three tracks.

**Pills.** A branch pill shows the label only. It is centred on the longest free horizontal stretch of its line: clear of cards and the 4-unit AI halo round each step (so never directly over a card), of marks and other pills, and at least 4 units from any other line that crosses the stretch.

**build-6.** The build fails and names the edge when a line crosses a card or a mark (badge, system icon, chip, a decision's id label, the AI room under a step), when two lines from different sources to different targets share a stretch (the board would show a path the sources never describe), when a gap needs more than three tracks, or when a pill has no stretch of its width plus 16. Each error names the blocking node and a fix: move a node to another lane, set `col`, or list a decision's branches in another order.

**Large maps.** Columns come from the longest chain of forward edges inside each view, not from the number of steps: steps in other lanes that do not follow one another share a column. A board holds 14 columns; map-10 lists each view's columns and its longest chain (`G03 Review: 3 (QUE-01 → REV-01 → PCK-01)`). To fit, keep edges to what the sources say follows what (steps side by side need no edge between them), move a step that runs alongside another into its own lane, or split the process into several maps by view.

**Room the AI layer relies on.**
- 20 units of lane padding below each card row.
- No base line along a card's bottom edge to the right of its centre.
- No base stroke on the band's top edge or across its cells' bottom 6 units, other than the band's own bottom border.
- The right 70 units of each band cell: the group label is cut short of them, so the layer's view squares never cover it (build-5).

---

## 3. Elements

Driven by: the data fields each element reads. `(derived)` is computed by the build, `(template)` is fixed text in `board.html`, and `(ui)` is viewer state. The anchor is the element's section in `specimen.html`.

| # | Element | States | Driven by | Anchor |
|---|---|---|---|---|
| 1 | Page header | full · minimal (kicker and title only) · long title (wraps, never cut) | `meta.kicker`, `.flags` (chips; confidential has an orange border), `.title`, `.subtitle` with tokens filled (derived) | `#pm-header` |
| 2 | System key | systems · omitted when there are none | `systems[].icon`, `.label`, and the system's marker | `#pm-key` |
| 3 | Legend | 3 × 3 on desktop · 2 columns under 640px | (template): Process flow, Feedback, Decision, Grounded, Inferred, Citation point, Gap, Clarification | `#pm-legend` |
| 4 | Lane and gutter | alternating fills · long name (3 lines, then …) · stacked rows · empty | `lanes[]` order and `label`, the lane's marker when it cites; the note `3 steps` (derived) | `#pm-lane` |
| 5 | Group band | drawn with two or more groups · targeted (`#G01`) · long label (cut with …) | `groups[].id`, `.label`; the meta `4 steps` (derived) | `#pm-band` |
| 6 | Node card | grounded · inferred · gap (with no owner when that is its gap) · long title (3 lines, then …) · several systems · hover · keyboard focus · targeted | `title` with the card's one marker after it (the number of its first citation point), `owner`, `state`, `systems`, and the step id as a 9px muted label on the last line. A gap step adds the tag `Needs confirmation`. Nothing else: no address, no reading. The focus ring is 2px ink, 8 units out, so it never reads as an AI halo | `#pm-node` |
| 7 | Badges | gap (filled orange) · clarification (dashed orange ring) · `+n` after three | `gaps[].nodes`, `clarifications[].nodes`. The number is the list position (derived), and the badge links to its card item | `#pm-badge` |
| 8 | System icon | 1 · 2 · `+n` | `nodes[].systems` → `systems[].icon` | `#pm-sys` |
| 9 | Decision diamond | grounded · inferred (dashed grey) · gap (dashed orange) · with a clarification · long question (2 lines) | `kind: decision`, `title`, `state`, its branches. The id and its marker (`REV-02 ⁸`) sit under the bottom vertex, or right of the line when a branch leaves that vertex | `#pm-decision` |
| 10 | Edges | flow · branch with its label pill · feedback (dashed) · hover | `edges[]`; feedback (derived) | `#pm-edge` |
| 11 | Board shell | Fit · 100% (sticky gutter, drag to pan) · phone (compact gutter). A page opens at Fit, or at 100% when Fit would draw the board below 0.6 of its size (titles under about 7px) and always on a phone | (ui) | `#pm-shell` |
| 12 | Tooltip | step · decision · truncated title · citation marker | (derived): id · group, title, lane, owner, systems, an inferred reading, marks, and `Citation points 3, 4`. A marker's tooltip is one line, on hover and on keyboard focus: the address and the first words of the verbatim text, read from its row. It only repeats printed facts. On an AI page a step's tooltip also gains the AI lines | `#pm-tip` |
| 13 | Gaps card | list · targeted item · None found. Required, so never empty: when no step is in gap state and every step's owner and outcome is in a record it cites (a step whose order no record states is asked by an order clarification instead), its one None found card (`none: true`, `nodes: []`, no number, `None found · no step listed`, a search on it labelled Searched) says so and cites why; never invent a gap | `gaps[]`: numbered badge, title, text with citation markers, `Steps: REC-01`, and the provenance line `Gap · “Team” not found¹⁵ · “outcome” not found¹⁶` then `Grounded¹³` | `#pm-gaps` |
| 14 | Clarifications card | list · targeted item · order to confirm · None found. Required, so never empty: when nothing is left to confirm, one None found card cites why. A step whose order no source states is listed by an order clarification (`order: true`), whose Steps line reads Order to confirm | `clarifications[]`: title, `What the sources show:` `shows`, `To confirm:` `ask`, `Steps: APP-01`, the provenance line with its markers | `#pm-clar` |
| 15 | Citation points section | per point · span point (its records' texts, up to 10) · absent search (`Searched for “Team”: not found · PROVEN`) · inferred reading · targeted row | every citation point the page uses (derived; section 3.1). A reading no element prints (a lane's, a system's, a node's) is printed in its first record's row: `Inferred · <reading> · RES-01`. It follows Gaps and Clarifications, full width | `#pm-cp` |
| 16 | Footer | flags · no flags · phone (the sides stack) | Left: `meta.footer`, default `Source · process map`. Right: `Contains Client A confidential information` (confidential) · `Draft` (draft) · `22 Oct 2026`, each clause only when it applies | `#pm-footer` |
| 17 | Empty states | lane with no steps (`No steps in this lane`) · no systems · no flags · 0 or 1 group (no band) | empty arrays | `#pm-empty` |
| 18 | Citation marker | on a card · in prose · in a provenance line · hover and focus (tooltip) | the point's number (derived), linked to its row in the Citation points section, with `aria-label="Citation 7: WB3 Process!C2"`. A muted 9px numeral, raised like a footnote; never a locator string | `#pm-marker` |

The tooltip, the Fit and 100% zoom, the flags chips, lane notes, the markers and the Citation points section are additions to the reference; section 4 lists them.

### 3.1 Citation points: numbering, markup and links

- **A point** is a record address an element cites (`WB1 Steps row 2`, `T1 00:00:05`), or one absent search of one address for one needle. Points are numbered 1, 2, 3… in the order the page first uses them: systems, lanes, nodes, gaps, clarifications, then (on an AI page) the AI items. So the AI page numbers its base map's points exactly as the base page does, and its own after them.
- **A marker** is `<a class="cp-mk" href="#<anchor>">n</a>` (in an SVG, the same `a.cp-mk` around a `text.cp-mk-t`). An element shows one marker, the number of its first point; prose shows one per bracket address. Every cited element has a marker.
- **The section** is `section#citation-points.cp`: a heading, the count (`17 points from 2 records`), one line per record (`ul.cp-srcs`, each record id linking to the data), and `ol.cp-list` with one `li.cp-row` per point, `id` = its anchor, `data-n` = its number. A row holds `.cp-n` (the number), `a.cp-addr` (record id and locator, monospace), `.cp-text` (the verbatim text), `.cp-used` (Grounded, Inferred from or Absent search, then each element it supports, linked to it on the page) and `a.cp-all` (↗).
- **Anchors** are `formats/FORMATS.md` section 2.6: `src-wb1-steps-row-2`; an absent search adds `-not-<needle>`: `src-wb1-steps-row-7-not-team`.
- **Links back to the data.** The page sits at `out/<section>/<name>.html`, so `a.cp-addr` and each record line link to `../data-received.html#<RECORD ID>`, and `a.cp-all` to `../citation-points.html#<anchor>`. The specimens link to `../../examples/out/`.
- **The page's required ids:** `#header`, `#board`, `#gaps`, `#clarifications`, `#citation-points`.

---

## 4. Departures from the design reference

The reference is another client's swimlane board, and only its design is used. These are the intended differences; anything else that differs is a bug.

| Reference | This board | Why |
|---|---|---|
| node radius rx 4, diamond rx 3 | rx 2 for both | one radius across the board |
| a dashed `?` clarification badge | numbered badges only | the number links to the card item |
| a node detail line naming the system and evidence | the title, the owner, the id, and one numbered marker | a card stays quiet; the address and the verbatim text are in Citation points |
| provenance lines with personal names | addresses | speakers and owners are roles, and an address resolves |
| an inferred diamond dashed in orange | dashed grey (`--soft`) | orange is kept for gaps and AI |
| — | an ink bar on each card heading (Gaps, Clarifications needed, Citation points) | quiet; orange is kept for gaps and AI |
| orange text in the base orange | `--accent-ink` (`#b84000`) for orange words, the page kicker included | at least 4.5:1 on every board background; the base orange is 3:1 |
| one Gaps legend item | separate Gap and Clarification items | they are different marks |
| no zoom; the shell hides overflow | Fit and 100% | a 14-column board needs Fit to be seen whole. Size is capped at 40 nodes, 8 lanes and 14 columns; at the caps Fit draws a board at about half size on a 1440px screen, so such a page opens at 100% (the reading view) and Fit shows the whole |
| no focus ring | 2px ink ring 8 units out | keyboard use, and never confused with the AI halo |
| — | flags chips, lane notes, the group band (with two or more groups), the tooltip, the citation markers and the Citation points section | these show the formats' metadata and evidence |

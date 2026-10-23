# process-map-ai-opportunity: AI opportunities over a current-state map

**Required elements** (`template.json`). `bs.py build` refuses the page, with exit 1 and a `-> fix` hint (build-7), until each is fulfilled, and `bs.py status` prints `n of m required elements fulfilled` for it and names each missing one with the file and field that fulfils it.

- [ ] **Base map**: `process-map-ai-opportunity/<name>.json › base`: a map in `process-map/` that passes check (ai-1).
- [ ] **At least one AI item**: `ai[]`. An empty layer passes check and draws its empty state, but build refuses it (ai-2).
- [ ] **Origin, named or suggested**: `ai[].origin`: `named` with a grounded quote, or `suggested` with an inferred reading (ai-3).
- [ ] **What it would do**: `ai[].does`, one to three sentences (prose-4).
- [ ] **The agentic version of every item**: `ai[].agentic {trigger, steps, decides, systems, logging}` (ai-4); `systems` is `[]` only when the steps the item touches use no system (an error otherwise, ai-4), and the page prints None named.
- [ ] **List view, the default**: computed: the first tab, selected on load, with one row per item (build-7).
- [ ] **Flow view**: computed from the base: the second tab, with every base node on it (build-6).
- [ ] **On-the-map view**: computed: the third tab, the base board (`svg.pm-board`) with the layer (build-5).
- [ ] **Citation points section, with numbered markers**: computed from every `cite` in the file and its base: one numbered marker (`a.cp-mk`) on each cited element and AI row, and `section#citation-points` with one `li.cp-row` per point the page uses, as on a process map (build-7).

Optional: the layer toggle.

One `process-map-ai-opportunity/<name>.json` names a base map and adds AI items. Its page leads with the AI opportunities, not the map: an `AI OPPORTUNITIES` kicker, a headline summary, then three views of the same map and layer, switched by one quiet tab row:
- **List** (the default): one row per opportunity, named by the client first. The look the user approved.
- **Flow**: the steps in one horizontal line, with an AI lane under them ("AI opportunities along the flow").
- **On the map**: the base board with the layer in its slots: halos, squares, the toggle and the highlight squares.

Below the views come the base's Gaps and Clarifications cards and the page's Citation points section. The base is never changed: with the layer off, On the map shows the base board (build-5). Orange marks AI and gaps only: card headings carry an ink bar, and only the AI opportunities heading carries the accent.

This folder holds:
- **This README:** the file, the contract with the base, the three views and every element.
- **`ai-layer.schema.json`:** fields, limits and patterns. It takes the node, group and file patterns from `process-map.schema.json`.
- **`fills.html`:** slot fills only: `pm-ai-*` and `pm-fl-*` CSS, the legend block, the toggle, the List card frame, and the page JS (views, layer, highlighting).
- **`specimen.html`:** every element in every state, built from `examples/` by `build_map.py --specimen`.

There is no builder here: `design-system/process-map/build_map.py` builds both map sections and computes the List rows, the Flow and the board marks. The shared rules are in `formats/FORMATS.md`.

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

**Examples.**
- `examples/process-map-ai-opportunity/end-to-end-ai.json`, the showcase, over `end-to-end` (35 nodes): seven items, every one with an agentic version. Its Flow draws with no crossing and no two lines closer than 12 units. AI-01 to AI-03 are named by the client in the walkthrough call (one quotes "automate"); AI-04 and AI-05 are our suggestions on one and two steps; AI-06 covers one view and AI-07 all views, citing a web page beside an inferred reading.
- `examples/process-map-ai-opportunity/current-state-ai.json`, the small one the specimen is built from: AI-01 named, on a step; AI-02 suggested, on a step; AI-03 suggested, on one view; AI-04 suggested, across all views, citing a web page beside an inferred reading. Every item has an agentic version.

---

## 2. The page, and the contract with the base board

**The page**, top to bottom: the header (kicker, flags, title, subtitle, the summary, and on the right a small key: named, our suggestion, citation point), the view switch, the List, the Flow and On the map (one shown at a time), Gaps and Clarifications, Citation points, the footer. The page ids are `#header`, `#ai-list`, `#ai-flow`, `#board` (On the map), `#gaps`, `#clarifications`, `#citation-points`.

**Views.** The tabs are `button.pm-view-tab[role=tab][data-view=list|flow|map]`; the panels carry `data-view-panel`, and a hidden one carries `data-off`. Every load opens on the List. A link to an element in a hidden view opens that view first (a step chip opens On the map; a Flow caption opens the List row). Without script, and in print, every view shows, List first.

- **Slots.** The page fills these named slots in `board.html`, and one script hook:
  - `views`: the view switch, then the List and Flow panels. The board section that follows is the On the map panel.
  - `board-head`: inside the board section, above the board: the toggle and the highlight squares, the system key, and the base legend with its AI block (`legend-end`).
  - `toolbar`: the layer's data, read by the script.
  - `board-under`: halos and band tints. They are drawn after the lanes and band, and before the edges.
  - `board-over`: squares, view underlines, the all-views bracket, and the transparent hit targets that carry `data-ai`, `tabindex`, `role` and `aria-label`. They are drawn after nodes and pills. Its gutter part, `board-over:gutter`, holds `ALL VIEWS` and its squares, since the gutter is its own SVG.
  - The `tooltip-lines` hook adds a node's AI lines to the base tooltip. There is one tooltip.
  - Two carriers, not slots of the board: `style` takes the CSS (and the one-line script that marks the page as scripted, so the hidden views never flash) and `script` the page JS.
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

## 3. The Flow view (derived, never authored)

- **The line.** The main path is the longest run of forward edges (edges to later-listed nodes), ties keeping the earlier-listed step; it reads left to right on one line. Columns are the board's, closed up where none is used.
- **The rows above.** Every other step sits on a row above the line, placed in listing order in the cheapest cell near its first choices: just above the step it branches from, else one column after the step before it, else its board column. A cell is ruled out when one of its lines would cross a step or run through a step's label, or when a line already drawn passes it. Among the rest, each crossing of another line costs 10, a stretch along another line 40, a row up 2, a column away from a first choice 1, a column left of the step before it 4, and a column that already holds another step with AI items 5 (their squares would share a place in the AI lane). When the cheapest cell costs 10 or more, a new column at the first choice is weighed against it at 8 more. Then two passes move each step to its cheapest cell now that all its lines are known; a step whose lines still cross tries a neighbour's cell, the neighbour moving to its own cheapest cell. Each line is then routed again, and empty columns close up. So a decision's other branch sits straight above the decision, and a chain of parallel steps runs along one row.
- **Lines.** Only the map's own edges, each drawn once, arrow at the target: straight along a row; a vertical between a step on the line and the step straight above it; up from the line then along a row into a step's side; along a row then down into a line step's top; along a row into the gap beside the target's column, then up or down into its side; otherwise through the channel between the line and the first row (the line's steps leave and enter at the top, the rows' at the bottom). No line runs through a step or a label. A feedback line is dashed. A branch label sits beside the first stretch of its line where it meets nothing.
- **Stems and tracks.** Lines that leave one side of a step heading the same way share one trunk, and lines that enter one side from the same side share one stem, as on the board. Other stems on a step stand 12 units apart, a straight line keeping the centre, in the order that leaves the fewest crossings. Channel lines that share a stem share a track; the rest take tracks 12 apart, a line whose stem rises from the line inside another's span running lower, and one whose stem drops from a row inside it running higher. Lines that turn in one gap between columns stand 12 apart unless they share a stem. So no two lines run closer than 12 units.
- **The check (build-6, the Flow).** A line through a step or a label fails the build and names the edge; the fix is a `col` hint or another node order. Two lines that cross, or run side by side closer than 12 units, are a warning that names both, and so is a branch label with no free place, and a forward line that runs right to left. A step off the line is never placed left of the step before it, and a feedback line never shares a stem, a gap track or an end with a forward line: two lines between the same two steps run 4 units apart.
- **Steps** are circles numbered by their place in the map's list of steps (`01`, `02`…; dashed for a gap step or an inferred one), decisions small diamonds (a gap decision dashed orange). The title (up to three lines) with its marker, then `SUB-01 · Team A` (the owner, `no owner`, or `Decision`), sit under a line step and over a step above; a label stays 6 units clear of a line turning in the gap beside it. Gap and clarification badges are small numbered circles at the step's top right, clear of any stem, linked to their card.
- **The count** beside the heading counts steps and decisions apart, as the summary does: `10 steps and 4 decisions on the line · 21 steps off it, above · 7 AI opportunities under the steps they touch`.
- **Stages.** With two or more groups, a bracket over each view's steps on the line, labelled `G01 Intake`.
- **The AI lane**, under the line: one track per item, packed into as few rows as their captions allow. Items on steps first, left to right, then whole-view items, then all-views items. A track is its caption (`AI-01 Read each request form into the tracker · named by the client`, linked to the List row), a square under each step it touches, and a thin bar joining them. A square under a step above the line whose column holds another step with AI items prints that step's number under it (`step 26`), so it never reads as the line's step. A whole-view item has a square under each step of its view (`· whole view: Intake`); an all-views item is one bar along the whole line (`· every step`).
- **Size.** 132 units a column, so a 14-column map is about 1,900 wide (more when columns open for steps above the line) and scrolls sideways inside its card; the page itself never does. Print scales it to the page width.
- **Phone** (700px and below): the same order as a vertical list. The line's steps in order, each under its view's heading (with that view's squares). Each step off the line hangs under the step it comes from: its first step on the line, else nested under its first step off the line (a loop's target last), with the label of the branch that leads to it (`No →`). Badges and markers inline, the item squares on the right, and all-views items noted at the top.

---

## 4. Elements

Driven by: the data fields each element reads. `(derived)` is computed by the build and `(ui)` is viewer state. The anchor is the element's section in `specimen.html`.

| # | Element | States | Driven by | Anchor |
|---|---|---|---|---|
| 1 | Header and summary | standard · empty | `meta.kicker`, `.title`, `.subtitle` override the base; flags and client are inherited. The summary (derived), e.g. `4 AI opportunities · ■ 1 named by Client A · □ 3 our suggestions · touches 2 of 6 steps · 1 across a whole view · 1 across all views`; a zero segment is left out; decisions are not steps. The key on the right: Named by the client, Our suggestion, Citation point | `#ai-header` |
| 2 | View switch | List (default, every load) · Flow · On the map · focus-visible · arrow keys | (ui) | `#ai-views` |
| 3 | List | list · empty: one dashed row, **No AI opportunities identified for this process yet.** | `ai[]`, named by the client first, then our suggestions, each by id; heading `AI opportunities` and `7 items · named by the client first` | `#ai-list` |
| 4 | List row | default · targeted | one item: square, `AI-01` and title, origin tag (`Named by the client` filled, `Our suggestion` outlined), `Show on map`; left, "What it would do" then "Steps it touches" (or "Where it applies") as chips (`REV-01 Review request`, `G02 Review and approval · whole view`, `All views`); right, the evidence; then the agentic version | `#ai-row` |
| 5 | Evidence | grounded quote · grounded without a quote · inferred | A grounded citation shows its `quote`, or else the text of its first record, then `Grounded · Speaker A ¹⁸` (the record's context for a transcript, the domain for a web page) with its marker. An inferred one shows **Basis:** the reading, then `Inferred · from ¹⁹,²⁰`. Markers link to Citation points | `#ai-evidence` |
| 6 | Agentic version | folded (default) · open · print (open) · no system named · absent | `agentic.*`; the meta line `3 steps · 1 place a person decides · 2 systems` (derived; `no system named` when `systems` is `[]`, and Systems reads None named; `[]` is an error when a step the item touches uses a system, ai-4). Steps on a numbered spine, each `decides` entry after its step as **Person decides** · `Team B checks the entry…`, then systems with the base icons, then logging. No orange inside | `#ai-agentic` |
| 7 | Flow | desktop (one line, rows above, scrolls inside its card) · phone (vertical list) · print (scaled to the page) | the base map's nodes and edges (section 3), its badges, the points' markers; the count (derived) | `#ai-flow` |
| 8 | AI lane | on a step · on several steps (bar) · a whole view · every step · a step's number under a square that shares its column | `ai[].nodes`, `.groups`, `.origin` | `#ai-lane` |
| 9 | Halo | default · thick (focus, hover) · faded · hidden (layer off) · peek (layer off, item highlighted) | a step in `ai[].nodes`. One per step, never dashed | `#ai-halo` |
| 10 | Node square | named (filled) · suggested (outlined) · faded · hidden · peek · `+n` | `ai[].nodes`, `.origin`, `.id` (the digits are derived). `<title>`: `AI-01 Draft the review summary · Named by the client` | `#ai-square` |
| 11 | View underline | default · on (band cell tinted) · hidden · peek | `ai[].groups` (a list). One per listed view, never joined | `#ai-view` |
| 12 | All-views bracket | default · on (every band cell tinted, nothing fades) · hidden · peek | `ai[].groups = "all"`. Drawn once | `#ai-all` |
| 13 | Legend block | on · off (the swatches at 40%, the words at full colour, heading `AI LAYER · HIDDEN`) · left out when `ai` is empty | On the map, appended to the base legend. Base `meta.client`: `AI named by Client A`, `AI suggested by us`, `Step with an AI opportunity`, `AI across a view or all views` | `#ai-legend` |
| 14 | Toggle | on (every load, not remembered) · off · hover · focus-visible · `None` when `ai` is empty | (ui) | `#ai-toggle` |
| 15 | Highlight squares | none pressed (default) · pressed · hover (preview) | On the map: one per item, in List order (`01 AI-01`). Pressing one highlights its item; pressing it again, or Esc, releases it | `#ai-pick` |
| 16 | Empty state | `ai: []` | the List's dashed row; no AI lane; On the map, the base board, the toggle reading `AI layer · None` and no legend block | `#ai-empty` |
| 17 | Tooltip lines | a step with items | (derived) through the `tooltip-lines` hook: one line per item (square, id, title, origin word), then "Click to highlight it on the map" | `#ai-tip` |
| 18 | Highlighting | Show on map · a highlight square · a click on a marked step (each click the step's next item) · Esc releases | (ui). Show on map opens On the map with the item lit: its steps stay, the rest of the board steps back; a view item tints its cells; an all-views item fades nothing. It works with the layer off | `#ai-link` |

**Responsive and print.**
- At 900px and below, row columns stack. At 700px and below, the page gutter is 16px, the Flow becomes its vertical list, the highlight squares drop their ids, and the board opens at 100% inside its own scroll. On a wider screen On the map opens at Fit, or at 100% when Fit would draw the board below 0.6 of its size (process-map README, element 11).
- There is never a horizontal page scroll; this is checked at 390px.
- Print (A4 landscape) shows the three views in turn, forces the layer on and opens every agentic block. The List follows the header on the first page; each row stays whole.

---

## 5. Class and attribute index

| Class or attribute | Element |
|---|---|
| `svg.pm-board.has-ai` | the board with the layer on |
| `.pm-ai` | any element hidden when the layer is off |
| `.pm-ai-under`, `.pm-ai-over` | the board-under and board-over slots |
| `.pm-ai-node[data-node][data-ai]`, `.pm-ai-halo` | halo |
| `.pm-ai-marks`, `.pm-ai-sq.is-named`, `.pm-ai-sq.is-suggested`, `.pm-ai-more` | squares |
| `.pm-ai-hit[data-node][data-ai]` | hit targets (`tabindex`, `role=button`, `aria-label`) |
| `.pm-ai-view[data-group][data-ai]`, `.pm-ai-all[data-ai]`, `.pm-ai-rail[data-ai]`, `.pm-ai-all-text`, `.pm-ai-band-hit[data-group]` | view and all-views marks |
| `.pm-views`, `.pm-view-tab[data-view]`, `[data-view-panel]`, `[data-off]` | view switch and panels |
| `.pm-ai-key` | the header key |
| `.pm-map-head`, `.pm-map-tools`, `.pm-ai-picks`, `.pm-ai-pick[data-ai][aria-pressed]` | On the map: its head and the highlight squares |
| `.pm-ai-toggle`, `.pm-ai-toggle-ind`, `.pm-ai-toggle-state` | toggle |
| `.pm-ai-summary`, `.pm-ai-summary-in`, `.pm-ai-sum-sq` | summary |
| `.pm-fl-card`, `.pm-fl-scroll`, `.pm-fl-svg`, `.pm-fl-node[data-node]`, `.pm-fl-step`, `.pm-fl-dec`, `.pm-fl-edge[data-from][data-to]`, `.pm-fl-line.is-feedback`, `.pm-fl-branch`, `.pm-fl-stage`, `.pm-fl-badge`, `.pm-fl-legend` | Flow |
| `.pm-ai-fl-track[data-ai]`, `.pm-ai-fl-cap`, `.pm-ai-fl-bar`, `.pm-ai-fl-at` | AI lane |
| `.pm-fl-phone`, `.pm-fl-plist`, `.pm-fl-pg`, `.pm-fl-pi.is-branch`, `.pm-fl-pi.is-d2`, `.pm-fl-pi.is-d3`, `.pm-fl-pall` | Flow on a phone |
| `.pm-ai-legend`, `.pm-ai-sw-named`, `.pm-ai-sw-suggested`, `.pm-ai-sw-halo`, `.pm-ai-sw-rail`, `.pm-legend.is-ai-off` | legend |
| `.pm-ai-card`, `.pm-ai-count`, `.pm-ai-list`, `.pm-ai-item[data-ai]`, `.pm-ai-mark`, `.pm-ai-head`, `.pm-ai-title`, `.pm-ai-id`, `.pm-ai-origin`, `.pm-ai-show`, `.pm-ai-cols`, `.pm-ai-label`, `.pm-ai-does`, `.pm-ai-steps`, `.pm-ai-step`, `.pm-ai-step.is-scope`, `.pm-ai-cite.is-quote`, `.pm-ai-cite.is-inferred` | List |
| `.pm-ai-agentic`, `.pm-ai-ag-title`, `.pm-ai-ag-meta`, `.pm-ai-ag`, `.pm-ai-flow`, `.pm-ai-sys` | agentic version |
| `.pm-ai-empty` | empty state |
| `.pm-ai-tip-line` | tooltip lines |
| `.is-ai-focus`, `.is-ai-hit`, `.is-ai-on`, `.is-ai-hover`, `.is-ai-peek`, `.is-ai-flash` | interaction states |
| `.is-hover`, `.is-focus` on `.pm-view-tab`, `.pm-ai-pick`, `.pm-ai-toggle`, `a.cp-mk` | a hover or focus state drawn without the pointer, for the specimen |
| `a.cp-mk`, `section#citation-points.cp`, `li.cp-row` | citation markers and the Citation points section (`design-system/process-map/README.md` section 3.1) |

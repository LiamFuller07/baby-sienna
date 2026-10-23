---
name: process-map
description: Use when writing or fixing process-map/<name>.json, the current-state swimlane board, from a workspace's records.
---

# process-map: the current-state swimlane board

## Required elements (`design-system/process-map/template.json`)

- [ ] **Header**: `meta`: kicker, title, client and date (schema-1).
- [ ] **Lanes**: `lanes[] {id, label}`: at least one, each a role (map-3).
- [ ] **Steps with owners**: `nodes[]`: at least one step, each in the lane of the role that owns it, with its `owner`, state and cite; only a gap-state step may leave `owner` out, its gap card saying so (build-7).
- [ ] **Flows**: `edges[] {from, to}`: every node joined to the flow; a step whose order no source states is listed instead by a clarification that asks where it comes (map-5).
- [ ] **Gaps card**: `gaps[] {id, title, text, nodes, cite}`: at least one, proven by an absent search (cite-4); or, when the sources leave no step out, one None found card (`none: true`, `nodes: []`) that cites why (map-6). Never invent a gap.
- [ ] **Clarifications card**: `clarifications[] {id, title, shows, ask, nodes, cite}`: at least one (cite-4); or one None found card (`none: true`, `nodes: []`) that cites why nothing is left to confirm (map-6).
- [ ] **Citation points section, with in-place markers**: computed from every `cite`: one numbered marker on each cited element, and one row per point the page uses (build-7).

Optional: the system key (`systems[]`) and the views band (`groups[]`, two or more). Fulfil every required element. The work is done only when `python3 bs.py status <ws>` shows them all fulfilled: `7 of 7`.

## What the template shows

The process as the sources describe it today, and nothing else: a header, the system key and legend, the board (lanes, step cards, decision diamonds, flows, gap and clarification badges), the Gaps and Clarifications needed cards, the Citation points section and a footer. A card shows its title, its owner, its step id and one small numbered marker. **No AI at all**: AI ideas go in an AI layer (map-9, build-5).

## Read

- `records/*.json`: every fact on the map comes from a record.
- `design-system/process-map/README.md`: section 1 (the file), section 2 (the derived layout) and section 3 (every element).
- `design-system/process-map/process-map.schema.json`: fields, limits, id patterns.
- The cite skill: which citation each element needs.

## Write

`<ws>/process-map/<name>.json` (`<name>` like `end-to-end`). Arrays are in display order.

- `type: "process-map"`; `meta {kicker, title, client, date, subtitle?, flags?, footer?}`. The subtitle takes numbers only from `{count:steps}`-style tokens.
- `lanes[] {id, label, cite?}`: roles, never people. A lane with no step cites its role.
- `groups[] {id: "G01", label}`: views, left to right. With groups, every node names one, and nodes are listed group by group.
- `nodes[] {id: "SUB-01", title, kind?, lane, group?, state, owner, systems?, col?, cite}`. `owner` is the role that owns a step; a decision has none, and a gap-state step may leave it out when the missing owner is its gap. `state` is `grounded`, `inferred` (dashed; reading ≤ 48 characters) or `gap` (listed by exactly one gap card). A `decision` asks a question and has at least two conditional branches with different labels; the first-listed branch takes its right vertex.
- `edges[] {from, to, kind?, label?}`: an edge to an earlier-listed node is feedback (dashed). Edges cite nothing.
- `gaps[]`: an **absent** search proves what the sources do not say, plus a grounded citation of what they do. Both cards are required: when the sources seem complete, search for what a reader of the map would expect and not find (an owner, an outcome, a limit) and record that absent search. `clarifications[]`: `title` is the question, `shows` what the sources show, `ask` what to confirm and with whom.
- `systems[] {id, label, icon, cite, role?, software?}`: the label occurs in a record it cites. `role` and `software` feed the data-received template.

Limits: 40 nodes, 8 lanes, 14 board columns, 48-character titles, 12-character branch labels.

## Commands

```sh
python3 bs.py check <ws> process-map/<name>.json     # this file's findings
python3 bs.py check <ws>                             # must exit 0
python3 bs.py build <ws> process-map/<name>          # -> <ws>/out/process-map/<name>.html
python3 bs.py status <ws>                            # 7 of 7
python3 design-system/process-map/build_map.py --specimen examples   # every element in every state
```

## The loop

write the JSON → `python3 bs.py check <ws>` until it exits 0, fixing what each `-> fix` names → `python3 bs.py build <ws>` → open `<ws>/out/process-map/<name>.html` at Fit and at 100% and look: no line crosses a card, no two sources share a line, no label overlaps, nothing selected by default.

## Watch for

- **build-6** names the edge and the blocking node: a line crossing a card or a mark (badge, system icon, a decision's id label), two lines from different sources sharing a stretch, or a branch pill with no free stretch. Fix it as the hint says: move the blocking node to another lane, set a `col` hint, or list the decision's branches in another order. Never move a card by hand: the layout is derived.
- **Large maps.** A board holds 14 columns, and columns come from the longest chain of forward edges in each view, not from the number of steps: steps in other lanes that do not follow one another share a column. When map-10 says the board needs too many columns, it lists each view's columns and its longest chain. Shorten those chains: keep only the edges the sources describe (steps side by side need no edge between them), put a step that runs alongside another in its own lane, or split the process into several maps by view. The showcase fits 35 nodes into 14 columns because many of its steps run side by side.
- **prose-3, prose-4**: a quoted phrase or a number must occur in a record the element cites. **prose-2**: quote with `“…”`, never `"`.
- **map-9**: an AI term may appear only where a record the element cites uses it.
- Never type computed values: badge numbers, citation markers, step counts, coordinates.

## Example

`examples/process-map/end-to-end.json`, the showcase: 35 nodes (31 steps, 4 decisions) in 7 lanes and 6 views, four loops, 3 gaps and 5 clarifications, from `WB3` (`inputs/Process.csv`) and `T3` (`inputs/walkthrough-call.txt`) → `examples/out/process-map/end-to-end.html`. The small one is `examples/process-map/current-state.json`. README: `design-system/process-map/README.md`.

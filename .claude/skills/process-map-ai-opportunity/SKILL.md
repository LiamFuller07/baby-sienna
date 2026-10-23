---
name: process-map-ai-opportunity
description: Use when writing or fixing process-map-ai-opportunity/<name>.json, the AI opportunities layer over a valid current-state map.
---

# process-map-ai-opportunity: AI opportunities over a map

## Required elements (`design-system/process-map-ai-opportunity/template.json`)

- [ ] **Base map**: `base`: a map in `process-map/` that passes check (ai-1).
- [ ] **At least one AI item**: `ai[] {id, title, origin, does, nodes or groups, cite, agentic}` (ai-2).
- [ ] **Origin, named or suggested**: `ai[].origin`: `named` (a grounded quote) or `suggested` (an inferred reading) (ai-3).
- [ ] **What it would do**: `ai[].does`: one to three sentences (prose-4).
- [ ] **The agentic version of every item**: `ai[].agentic {trigger, steps, decides, systems, logging}` (ai-4).
- [ ] **List view, the default**: computed: the first tab, selected on load, one row per item (build-7).
- [ ] **Flow view**: computed from the base: the second tab, every base node on it (build-6).
- [ ] **On-the-map view**: computed: the third tab, the base board with the layer (build-5).
- [ ] **Citation points section, with numbered markers**: computed from every `cite` in the file and its base (build-7).

Optional: the layer toggle. Fulfil every required element. The work is done only when `python3 bs.py status <ws>` shows them all fulfilled: `9 of 9`.

## What the template shows

A page that leads with the AI automation list, never the map: the `AI OPPORTUNITIES` kicker, a headline summary (`7 AI opportunities · 3 named by Client A · 4 our suggestions · …`), then three views:
- **List** (the default): one row per opportunity, named by the client first. The square, id, title and origin tag (NAMED BY THE CLIENT filled, OUR SUGGESTION outlined); left, What it would do and the Steps it touches as chips; right, the evidence (the quote with its Grounded line, or `Basis:` with its Inferred line) with a numbered marker; the Agentic version expander; Show on map.
- **Flow**: the steps on one horizontal line, with an AI lane under it.
- **On the map**: the base board with halos, squares hanging from each step's bottom-right corner, the all-views bracket and the layer toggle.

Then the base's Gaps and Clarifications cards and the Citation points section. Orange marks AI and gaps only. The base map is never changed.

## Read

- The base map `process-map/<base>.json` (it must pass check first) and `records/*.json`.
- `design-system/process-map-ai-opportunity/README.md`: section 1 (the file) and section 2 (the contract with the base).
- `design-system/process-map-ai-opportunity/ai-layer.schema.json`.

## Write

`<ws>/process-map-ai-opportunity/<name>.json` (`<name>` like `end-to-end-ai`):
- `type: "process-map-ai-opportunity"`, `base: "<map name>"`, `meta {title, kicker?, subtitle?, date?}`.
- `ai[]`, sorted by id (`AI-01`…). Each item:
  - `title`: sentence case, starts with a verb, no full stop, ≤ 60 characters.
  - `origin`: `named` only when the client asked for it in their own words: a grounded citation with a `quote` holding an AI term, from a source that is not web. Otherwise `suggested`, with an inferred citation (web pages may add to it, never alone).
  - `does`: one to three sentences. Its numbers must occur in records the item cites.
  - Targets: `nodes` (base steps, not decisions) and/or `groups` (base groups, or `"all"`). Not both empty; `"all"` takes no nodes; a listed step may not sit in a listed group.
  - `agentic {trigger, steps (2–8, each starting with a verb), decides [{after, who, what}] (at least one: a person decides), systems (base system ids), logging}`. `what` is a lower-case clause that follows its role in one sentence (`Person decides · Team B checks the entry and accepts or corrects it`): write `checks the entry and accepts or corrects it`, never `Checks …` (check warns, ai-4).

## Commands

```sh
python3 bs.py check <ws>                                        # the base first, then the layer
python3 bs.py build <ws> process-map-ai-opportunity/<name>      # -> <ws>/out/process-map-ai-opportunity/<name>.html
python3 bs.py status <ws>                                       # 9 of 9
```

## The loop

write the JSON → `python3 bs.py check <ws>` until it exits 0 → `python3 bs.py build <ws>` → open `<ws>/out/process-map-ai-opportunity/<name>.html` and look: it opens on the List, every row has its evidence marker and its agentic version, the Flow has no line through a step, and Show on map lights the item.

## Watch for

- **ai-3** is necessary, not sufficient: the checker agent reads every named item to confirm it is the client asking.
- **build-6 in the Flow**: a line through a step or label fails the build; set a `col` hint on the base node or reorder.
- AI ideas never go in the base map. The plain process-map page carries no AI at all.

## Example

`examples/process-map-ai-opportunity/end-to-end-ai.json`, the showcase over `end-to-end`: seven items, AI-01 to AI-03 named in the walkthrough call, AI-04 and AI-05 our suggestions on steps, AI-06 on one view and AI-07 across all views → `examples/out/process-map-ai-opportunity/end-to-end-ai.html`. The small one is `examples/process-map-ai-opportunity/current-state-ai.json`. README: `design-system/process-map-ai-opportunity/README.md`.

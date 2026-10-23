---
name: data-received
description: Use to fulfil Original data received and its deliverable, the systems inventory - give a map's systems their role and software, and write inventory/<name>.json - or to explain what those computed pages show.
---

# data-received: Original data received and the systems inventory

## Required elements (`design-system/data-received/template.json`)

Original data received (`out/data-received.html`), 6 of 6. The systems inventory (`out/systems-inventory.html`) needs the four marked ★.

- [ ] **Folders of data**: computed from `inputs/`: at least one file (ws-1).
- [ ] ★ **Systems identified**: `process-map/<name>.json › systems[]` (id, label, icon, cite, role), with `nodes[].systems` (map-8).
- [ ] ★ **Software used**: `process-map/<name>.json › systems[].software` (name, category, cite) (inv-1).
- [ ] ★ **Modules and capabilities**: `inventory/<name>.json › modules[]` (id, title, software, steps, likelihood, cite) (inv-2).
- [ ] **Folder view**: computed from `inputs/` and `records/`: one row per file (ws-1).
- [ ] ★ **Citation points section**: a map with cited `systems[]`: every cited row then carries a numbered marker (cite-1).

Fulfil every required element. The work is done only when `python3 bs.py status <ws>` shows them all fulfilled: `6 of 6` and `4 of 4`.

## What the template shows

Both pages are computed, never authored.

- **Original data received**, two views. **Overview** (the default): 01 Folders of data, 02 Systems identified (System · Teams · Role and evidence · Steps, with step chips and `+n`), 03 Software used, 04 Modules likely to be used. **Folder view**: one full-width table of every file in `inputs/` (Name · Kind · Status · Record · Size · Received · Used by), no detail pane. Each row with a record has `id="<RECORD ID>"` and highlights on `:target`: every citation on every page lands here. A Citation points section closes the page.
- **The systems inventory**, the named client deliverable: `Client A · systems inventory`, a one-line summary, Systems identified, Software used, Modules likely to be used, its own Citation points section, a clean A4 print. No `inputs/` path, no hash.

## Read

- `design-system/data-received/README.md`: every section, column, status and anchor.
- `formats/FORMATS.md` section 3: a system's `role` and `software`, and the inventory format.
- `design-system/data-received/inventory.schema.json`, and the map's `systems[]` and `nodes[]`.

## Write

Only the workspace, never the page:
- **In the map** (`process-map/<name>.json › systems[]`, with the process-map skill): `role`, 3–60 characters, what the system does here; `software: {name, category, cite}`. `category` is one of `spreadsheet app`, `ticketing tool`, `ERP suite`, `email client`, `document store`, `database`, `web app`, `other`. Cite the software grounded when a record names the product (the page prints **Named in the sources**), else inferred with a reading that says why.
- **`inventory/<name>.json`**: `{"type": "inventory", "map": "<map name>", "modules": [...]}`. Each module is `{id: "MOD-01", title: "Module A1 · request intake", software (a software name of that map), steps (step ids of that map, never decisions), likelihood: likely|possible, cite}`, with at least one **inferred** citation: a module in default/suggested mode is our suggestion; observed mode follows the current-state contract below.

## Commands

```sh
python3 bs.py check <ws>                      # inv-1, inv-2, map-8
python3 bs.py build <ws> data-received        # Original data received alone (built even when check fails)
python3 bs.py build <ws> systems-inventory    # the systems inventory alone (only when check passes)
python3 bs.py build <ws>                      # both, with every other page
python3 bs.py status <ws>                     # 6 of 6, 4 of 4
```

## The loop

write the map's `systems[]` fields and `inventory/<name>.json` → `python3 bs.py check <ws>` until it exits 0 → `python3 bs.py build <ws>` → open `<ws>/out/data-received.html` and `<ws>/out/systems-inventory.html` and look: every Folder view row Converted, no empty Overview section, a numbered marker on every cited row.

## Watch for

- A new workspace gets no page until a map and an inventory exist: status reads `2 of 6` and names each missing element. That is expected; fulfil them, do not build around them.
- Received is the record's `captured` date, never a file date.
- `Not converted` rows mean the convert skill, not this one.

## Example

`examples/process-map/end-to-end.json` (six systems, five with software, three named in `examples/inputs/notes/systems-notes.md`, record D2) and `examples/inventory/end-to-end.json` give `examples/out/data-received.html` and `examples/out/systems-inventory.html`. README: `design-system/data-received/README.md`.

### Current-state inventory mode

When the brief excludes suggestions, use `"mode": "observed"` in an inventory file. Its required modules/capabilities entry is fulfilled by documented use instead of the default suggested-module analysis; the required section is not skipped. Each entry keeps `id`, `title`, `software`, `steps` and `cite`, omits `likelihood`, and has grounded citations only. Its software must be named in grounded map evidence, and each linked step must name a system using that software. Use a capability name when the source does not identify a formal product module; never invent a module name.

The page says **Documented modules and capabilities** and **Observed in supplied sources**. Its summary explicitly scopes the inventory to systems and capabilities linked to mapped steps, not an exhaustive company inventory. These mean source-reported use at the source's date, not a live verification of implementation. A semantic checker must inspect the cited material to verify the capability and its association with the step; structural checks cannot prove that claim. Missing facts remain clarifications or evidence gaps.

Without `mode`, or with `"mode": "suggested"`, the original contract is unchanged: each entry needs `likelihood: "likely" | "possible"` and at least one inferred citation. Mixed inventories label observed and suggested entries separately. No AI layer is required for a current-state brief.

```json
{"type":"inventory","map":"end-to-end","mode":"observed","modules":[
  {"id":"MOD-01","title":"Budget holding","software":"Software C","steps":["RSV-01"],
   "cite":[{"source":"D2","locator":"¶3"}]}]}
```

# baby-sienna

A template toolkit: a folder of client material becomes cited, self-contained HTML pages. Every claim on every page links back to the record it came from.

**AI agents: read [AGENTS.md](AGENTS.md).** It is the one complete guide: the model, every command, each template's required elements, citations and the hard rules.

## The five templates

| Template | What it makes | Example output |
|---|---|---|
| **data-received** | Original data received: an Overview (folders, systems, software, modules) and a Folder view of every input; plus its deliverable, the systems inventory | `examples/out/data-received.html`, `examples/out/systems-inventory.html` |
| **process-map** | A current-state swimlane board: roles, steps, decisions, flows, gaps and clarifications | `examples/out/process-map/end-to-end.html` |
| **process-map-ai-opportunity** | AI opportunities over a map: the list first, then the flow and the board | `examples/out/process-map-ai-opportunity/end-to-end-ai.html` |
| **citation-points** | Every citation point the workspace's pages use, with its verbatim text and what cites it | `examples/out/citation-points.html` |
| **document** | A Source document: an A4 one-pager or a long screen page, every claim cited | `examples/out/document/end-to-end-summary.html` (the small one: `examples/out/document/request-handling-summary.html`) |

Build the examples with `python3 bs.py build examples` (or `uv run python bs.py build examples`), then open `examples/out/`.

## Start a workspace

```sh
mkdir -p work/<engagement>/inputs          # work/ is gitignored
# drop the files you received into work/<engagement>/inputs/, exactly as received
python3 bs.py status work/<engagement>     # the state of every file, and the next step
```

Then follow the next step it prints, with the workflows or the skills (AGENTS.md section 5):

### Running a real evidence folder

Keep originals in an ignored workspace and retain their received filenames. Run
`status`, convert each input, author cited sections, then `check` and `build`.
Email `.eml` files now have a standard-library reader. PDF embedded-text extraction
uses the optional, pinned local reader in `requirements-pdf.txt`:

```sh
python3 -m pip install -r requirements-pdf.txt
python3 bs.py convert WS inputs/process.pdf --id PDF1 --kind document --title "Received process" --captured 2026-10-22 --partial
python3 bs.py check WS
python3 bs.py build WS
python3 scripts/build_workspace_menu.py WS
python3 -m http.server 4899 --bind 127.0.0.1 --directory WS/out
```

Open the local server's root for the material menu. It filters by material type,
source type and title, and embeds the original report templates. Empty material
types are hidden. Maps show citations in a right-hand panel on wide screens,
with full span text available through expandable source entries.

PDF and email records **must be partial**: PDF text does not prove arrows or
image content; email extraction excludes binary attachment contents. Original
bytes remain intact. A `.vsdx` file is readable only when its bytes are actually
PDF; this is not native Visio support. Images remain visibly UNCHECKED and need
visual transcription/review. `DONE` means the pages are built and structurally
valid, not that warnings or human evidence-review duties have disappeared.

Connections can now carry their own optional `cite` list, independent of node
citations. Retain direct evidence for the route itself; endpoint text alone does
not establish sequence. Missing decision branches may use `branchesIncomplete:
true`, but require a cited clarification. Map-level source annotations use a
clarification with `scope: "map"` and an empty `nodes` list, without becoming fake process steps.

With top-level `routing: "detour"`, the map router retains the template’s normal routes and uses checked orthogonal
detours for obstructed lines or labels. It never deletes an edge to make it fit.
Distinct labelled branches may reach the same destination; exact duplicate
edges remain invalid. Larger processes still need separate maps with explicit
continuations.

Verification without a browser:

```sh
python3 bs.py check --selftest --builtin
python3 -m unittest discover -s tests -v
python3 scripts/source_design.py check --site http://127.0.0.1:4899 --local-source-app --css design-system/workspace/source-tokens.css
```

The menu is a local Source application using the pinned Fused tokens and bundled
Geist font. The report templates retain their own design. Token checks, CLI
checks and deterministic builds do not establish browser acceptance or deployment.

## Workflow

1. **Convert** each input into `records/`: `.claude/workflows/convert.js`, or `python3 bs.py convert …`.
2. **Write** the section files (a map, an AI layer, an inventory, a document): `.claude/workflows/make.js`, or the template's skill.
3. **Check** until it exits 0: `python3 bs.py check work/<engagement>`.
4. **Build**: `python3 bs.py build work/<engagement>`, until `python3 bs.py status work/<engagement>` reads DONE.

## The repo

```
AGENTS.md        the guide for AI agents (CLAUDE.md imports it)
CLAUDE.md        a pointer to AGENTS.md, plus notes for Claude Code
bs.py            the one command: status | convert | check | build (Python standard library only)
formats/         what every template shares: records, citation types and rules, the check ids
design-system/   one folder per template: its README, required elements (template.json), look and builder
examples/        the placeholder workspace: inputs, records, section files; its out/ is built
.claude/         the skills, agents and workflows the AI uses
.github/         CI: the toolkit checks, builds and lints itself on its own examples
reference/       local only, gitignored: earlier client pages, kept as references
work/            local only, gitignored: real engagements, one folder each
```

## Confidentiality

- Client material never enters git. It lives only in `work/` or outside the repo.
- Examples, tests and specimens use placeholder content only: Client A, Team A to Team C, Submit request, `[PRICE]`, `[Name]`.
- No real company, client, partner or person name goes into any repo file. Owners and speakers are roles, never people.
- Design references from other firms are used for their design only, and never saved here.

`reference/` is local only: it is gitignored as a whole, because everything in it is client-confidential. Nothing in the repo depends on it.

### Current-state inventory mode

When the brief excludes suggestions, use `"mode": "observed"` in an inventory file. Its required modules/capabilities entry is fulfilled by documented use instead of the default suggested-module analysis; the required section is not skipped. Each entry keeps `id`, `title`, `software`, `steps` and `cite`, omits `likelihood`, and has grounded citations only. Its software must be named in grounded map evidence, and each linked step must name a system using that software. Use a capability name when the source does not identify a formal product module; never invent a module name.

The page says **Documented modules and capabilities** and **Observed in supplied sources**. Its summary explicitly scopes the inventory to systems and capabilities linked to mapped steps, not an exhaustive company inventory. These mean source-reported use at the source's date, not a live verification of implementation. A semantic checker must inspect the cited material to verify the capability and its association with the step; structural checks cannot prove that claim. Missing facts remain clarifications or evidence gaps.

Without `mode`, or with `"mode": "suggested"`, the original contract is unchanged: each entry needs `likelihood: "likely" | "possible"` and at least one inferred citation. Mixed inventories label observed and suggested entries separately. No AI layer is required for a current-state brief.

```json
{"type":"inventory","map":"end-to-end","mode":"observed","modules":[
  {"id":"MOD-01","title":"Budget holding","software":"Software C","steps":["RSV-01"],
   "cite":[{"source":"D2","locator":"¶3"}]}]}
```

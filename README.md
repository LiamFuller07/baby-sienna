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
| **document** | A Source document: an A4 one-pager or a long screen page, every claim cited | `examples/out/document/request-handling-summary.html` |

Build the examples with `python3 bs.py build examples` (or `uv run python bs.py build examples`), then open `examples/out/`.

## Start a workspace

```sh
mkdir -p work/<engagement>/inputs          # work/ is gitignored
# drop the files you received into work/<engagement>/inputs/, exactly as received
python3 bs.py status work/<engagement>     # the state of every file, and the next step
```

Then follow the next step it prints, with the workflows or the skills (AGENTS.md section 5):

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

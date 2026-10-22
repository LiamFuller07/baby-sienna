# baby-sienna

A template toolkit that turns a folder of client inputs into cited, self-contained pages. Every claim on every page cites a source record, and every record is the verbatim text of a file you received.

Start with **[AGENTS.md](AGENTS.md)**, the single guide for people and AI agents.

## The templates

| Template | What it shows | Example output (`python3 bs.py build examples`) |
|---|---|---|
| Data received | Every raw file received: folders, kinds, status, record, and where it is cited | `examples/out/data-received.html` |
| Process map | The current-state swimlane board: steps, owners, decisions, gaps and clarifications | `examples/out/process-map/current-state.html` |
| AI opportunities | The same process with AI opportunities: named by the client, or our suggestion | `examples/out/process-map-ai-opportunity/current-state-ai.html` |
| Reference document | A Source-style A4 or screen document, every claim cited | `examples/out/document/request-handling-summary.html` |
| Citation points | Every citation point the pages use, back to the data | in progress |

`design-system/proposal/` is being retired from the showcase and will leave in the next commit.

## Quick start

```sh
python3 bs.py status examples          # the state and the next step
python3 bs.py check examples           # every format and citation rule
python3 bs.py check --selftest         # break the examples one rule at a time; every break is caught
python3 bs.py build examples           # build every page into examples/out/
```

Python 3.8+ standard library only. A real engagement lives in `work/<engagement>/` (gitignored); see AGENTS.md.

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
clarification with an empty `nodes` list, without becoming fake process steps.

The map router retains the template's normal routes and uses checked orthogonal
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

## Layout

```
bs.py            the one command: status | convert | check | build
formats/         the shared formats: records, citations, rules (FORMATS.md)
design-system/   one folder per template: format, look and builder
examples/        the placeholder workspace, the only sample data
```

Client material never enters this repository: `work/` and `reference/` are gitignored, and examples use placeholder content only.

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

## Layout

```
bs.py            the one command: status | convert | check | build
formats/         the shared formats: records, citations, rules (FORMATS.md)
design-system/   one folder per template: format, look and builder
examples/        the placeholder workspace, the only sample data
```

Client material never enters this repository: `work/` and `reference/` are gitignored, and examples use placeholder content only.

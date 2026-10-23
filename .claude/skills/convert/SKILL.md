---
name: convert
description: Use when bs.py status shows NOT CONVERTED inputs - turn each raw file in inputs/ into records/<ID>.json, verbatim, with bs.py convert or by hand for a format it cannot read.
---

# convert: inputs to records

Supports every template: nothing can be cited until its input is a record. The work is done only when `python3 bs.py status <ws>` shows every input CONVERTED (or UNCHECKED, for a person to compare) and `python3 bs.py check <ws>` reports no `rec-*` or `ws-1` finding.

## What a record is

`records/<ID>.json` (`formats/schemas/source-record.schema.json`): a header that describes the input once, then `records[]`, its units verbatim in reading order, each `{locator, text, context?}`. The header is exactly the flags of `bs.py convert`, so nobody types one by hand.

| Kind | Inputs | One record per | Locator | Context |
|---|---|---|---|---|
| `sheet` | .csv, .tsv, .xlsx, .xlsm | non-empty cell | `Steps!C3` | row 1 of the column |
| `document` | .md, .txt, .docx | paragraph, heading, list item or table row | `¶4`, or `p2 ¶3` | the nearest heading |
| `transcript` | timed .txt, .vtt, .srt | turn | `00:00:31` | the speaker |
| `web` | a saved .html page | paragraph, heading, list item or table row | `¶3` | the nearest heading |

`formats/citation-types.json › kinds` is the definition: each kind's `read` list (formats `bs.py convert` reads) and `unchecked` list (formats the converter agent transcribes, which a person then compares).

## Read

- `formats/FORMATS.md` section 1: kinds, what a reader gives, resolution and the lifecycle.
- The input itself, only to choose its kind and header.

## Write

`<ws>/records/<ID>.json` only. Ids by convention: `WB1` for sheets, `D1` documents, `T1` transcripts, `WEB1` web pages; capitals, digits and hyphens, unique in the workspace.

## Commands

```sh
python3 bs.py status <ws>                                   # NOT CONVERTED files
python3 bs.py convert --units <ws>/inputs/<file> <kind>     # preview the records, write nothing
python3 bs.py convert <ws> inputs/<file> --id WB1 --kind sheet --title "Request steps workbook" \
  --captured 2026-09-01 [--detail "Shared by Team A, one sheet"] [--url URL] [--partial] [--legacy]
python3 bs.py check <ws>                                    # rec-1 to rec-6, ws-1
```

- `--captured` is when the material was received (ask; never a file date). `--url` is required for `web`. `--partial` when the records are an excerpt: an absent search over it is then only PROVISIONAL.
- Limits: `--title` 3–70 characters, `--detail` 1–60, `--url` up to 200. `convert` names the limit when a flag runs over it.
- `--kind` must take the file's extension: a `.csv` or `.xlsx` is a `sheet`, never a transcript. When the extension belongs to another kind, `convert` names it (`-> use --kind sheet`); never transcribe such a file by hand.
- `convert` refuses to overwrite and exits 2 for a format it cannot read. Then transcribe by hand: the same header, `file`, `sha256` (`sha256sum`), `coverage`, and every unit verbatim in reading order. rec-5 then reports it UNCHECKED until a person compares it with the input.

## The loop

`python3 bs.py status <ws>` → convert each NOT CONVERTED file → `python3 bs.py check <ws>` until it exits 0 → `python3 bs.py status <ws>` shows it CONVERTED. Many files at once: `.claude/workflows/convert.js`.

## Rules

- **Transcribe, never interpret.** Text exactly as stored; no summary, correction or translation.
- **Never edit, rename or remove an input.** A new version is a new file in `inputs/`, with a new id.
- **Never edit a record file by hand.** One that fails a check is deleted and converted again under the same id, so citations keep resolving.
- **A .zip is not an input.** A person saves its members in `inputs/<name>/` and keeps the .zip outside the workspace.
- **Speakers are roles.** If a transcript names people, ask for a pseudonymised version to receive instead, and say how in `--detail` (`speakers pseudonymised`).
- A DUPLICATE (a byte-identical copy of a converted input) needs nothing.

## Example

`examples/inputs/` and `examples/records/`: `Steps.csv` → `WB1`, `Process.csv` → `WB3`, `follow-up-call.txt` → `T1`, `walkthrough-call.txt` → `T3`, `intro-notes.md` → `D1`, `notes/systems-notes.md` → `D2`, `tracking-tools.html` → `WEB1`. README: `formats/FORMATS.md` section 1.

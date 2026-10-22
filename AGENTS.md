# AGENTS.md: how to work in baby-sienna

This is the guide for any AI agent, or person, working in this repository. (First cut; the full version, with one skill and one required-elements checklist per template, follows in the next commit.)

## The model

1. **Inputs.** Raw files exactly as received go in `work/<engagement>/inputs/`. They are never edited, renamed or removed; a new version is a new file.
2. **Records.** Each input becomes `records/<ID>.json`: its verbatim units with locators (`Steps!C3`, `00:01:02`, `¶4`). Convert with `python3 bs.py convert`, or the converter agent for formats bs.py cannot read.
3. **Section files.** You write `process-map/<name>.json`, `process-map-ai-opportunity/<name>.json` and `document/<name>.md`, citing records.
4. **Pages.** `python3 bs.py build` computes everything else (layout, counts, provenance, sources, the data-received page) into `out/`.

The folders are the state. Start every session with `python3 bs.py status <ws>` and do its next step.

## Commands

```sh
python3 bs.py status  WS [--json]
python3 bs.py convert WS inputs/FILE --id ID --kind sheet|document|transcript|web --title T --captured YYYY-MM-DD [--detail D] [--url U] [--partial] [--legacy]
python3 bs.py check   WS [FILE]          # exit 0 pass, 1 a rule failed, 2 cannot run
python3 bs.py check   --selftest
python3 bs.py build   WS [SECTION/NAME | data-received]
```

## Citations

- **Three types only:** grounded `{source, locator, quote?}`, inferred `{type: inferred, reading, from: [...]}` and absent `{type: absent, needle, in: [...]}` (an absent search proves what the sources do not say).
- **Every claim cites a record** that `bs.py check` can resolve. A missing fact is a gap or a clarification, never an uncited sentence.
- **The rules per element** are in `formats/FORMATS.md` section 2 and `formats/citation-types.json`.

## Hard rules

- Never commit, paste or upload workspace content. Client material lives only in `work/` (gitignored) or outside the repo.
- Never edit a record file by hand; delete it and convert again.
- Speakers and owners are roles, never personal names.
- Examples and tests use placeholder content only (Client A, Team A, Submit request).
- Design references from other firms are used for their design only, never saved in the repo.

## Done means

`python3 bs.py check <ws>` exits 0, `python3 bs.py build <ws>` exits 0, and `python3 bs.py status <ws>` says DONE.

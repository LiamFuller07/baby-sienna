# Document type

**Required elements** (`template.json`). `bs.py build` refuses a workspace document, with exit 1 and a `-> fix` hint (build-7), until each is fulfilled, and `bs.py status` prints `n of m required elements fulfilled` for it and names each missing one with the file and field that fulfils it.

- [ ] **Title and lead**: `document/<name>.md`: the `#` title, then a `>` lead block right under it (doc-1).
- [ ] **At least one claim section**: a `##` heading with at least one cited claim under it (doc-3).
- [ ] **Every claim cited, with an in-place marker**: a `[ID locator]` bracket, or a Grounded, Inferred or Gap line, on every claim; the page links each point from its marker (doc-3).
- [ ] **Citation points section**: computed by `build_doc.py --data-links`: `section#citation-points` in place of the type's Sources block, with one `li.cp-row` per point the page uses: its record id and locator, the verbatim text, the element it supports, and links to `data-received.html#<ID>` and `citation-points.html#<anchor>`, as on a process map (build-7).

Optional: the Next step callout. A document built with `build_doc.py` alone, outside a workspace, has no required elements.

The Source design system for **documents**: documentation, READMEs, one-pagers, write-ups and reports that people read from top to bottom. It is taken from the Source A4 one-pager. It uses the same type, colours and parts, on either a fixed A4 sheet or a long page for the screen.

You can write a document in Markdown and build one self-contained HTML file. You can also copy `template.html` and write the HTML by hand.

## Document or process map?

| Use | When the page is mainly | Folder |
|---|---|---|
| **Document** (this type) | Prose read top to bottom: guides, READMEs, one-pagers, briefs, reports, write-ups, notes | `document/` |
| **Process map** (`process-map`, `process-map-ai-opportunity`) | A swimlane board of steps, owners and hand-overs, with Gaps, Clarifications and AI cards | `process-map/`, `process-map-ai-opportunity/` |

The two systems do not mix. A document uses green ink and `#e9713b`. A process map uses its own tokens (`#111` ink and `#ff5600`) and its own `pm-*` classes. If a document needs to show a process, link to the map or put a small picture of it in an examples panel. Do not rebuild the board in a document. Both systems share the same citation standard (see [Citations](#citations)).

## Files

| File | What it is |
|---|---|
| `doc.css` | The whole system in one stylesheet: tokens, fonts, page, type and every part |
| `template.html` | A two-sheet skeleton with every part and short placeholder copy |
| `build_doc.py` | Builds one self-contained HTML file from the Markdown subset (Python 3 standard library only) |
| `example.md`, `example-sources.json` | A sample document ("How to use the document template") that uses every part. They are the type's own guide, not workspace data |
| `example-art.png` | The image art in `example.md` (the second examples panel) |
| `example-a4.html`, `example-screen.html` | `example.md` built in both modes |
| `fonts/` | `source-400.ttf`, `source-600.ttf` and `source-wordmark.png`, ready to use |
| `fonts/OFL.txt` | The SIL Open Font License of the two font files. It ships with every copy of them |
| `extract_assets.py` | Regenerates `fonts/` from the Source A4 one-pager; only needed if the brand files change |

## Build

```sh
python3 build_doc.py example.md example-a4.html --a4 --sources example-sources.json
python3 build_doc.py example.md example-screen.html --screen --sources example-sources.json
```

- `--a4` (the default) gives A4 sheets. Use it for one-pagers and short documents that will be printed or sent as PDF.
- `--screen` gives one column as wide as the A4 sheet (210 mm), with no fixed height. Use it for documentation and anything longer than two pages. When printed, it flows onto A4 pages, numbered `1 / N` in the bottom margin.
- `--sources sources.json` gives each source ID its full name in the Sources block. It is optional.
- `--strict` turns every warning into an error, so nothing is written while a cited ID has no name or a bracket looks like a broken citation. Use it before you send a document.
- `--data-links ../` is for a workspace, and `bs.py build` passes it. Each bracket, and each address on a provenance line, prints as one small numbered marker (`a.cp-mk`) linked to its row in the page's Citation points section; hover or focus shows the address and the first words of the verbatim text. The Sources block becomes that section (`section#citation-points`): one line per source (`#src-<ID>`, linked to `data-received.html#<ID>`), then one row per point, numbered to match, with the address, the verbatim records, the heading it supports and a link to `citation-points.html#<anchor>`. The verbatim records come from the sources file's `points`, which `bs.py` writes: `{"WB1": {"name": "…", "points": {"Steps!D3": [{"locator": "Steps!D3", "text": "…"}]}}}`. The source still writes `[WB1 Steps!D3]`. Without the flag, the page is exactly as before.

The output inlines `doc.css`, both fonts, the wordmark and any image art: about 180 KB, plus the images. It loads nothing from the network. Errors stop the build and, where they can, name the Markdown line. Warnings go to stderr. They cover:

- an ID with no name in the sources file, or a bracket that looks like a citation but is left as text;
- a `Grounded ·` line that does not start with a source ID;
- an examples item with no art, or code art longer than about 8 lines of 32 columns;
- a `<!-- page -->` inside a `:::` block, which is ignored;
- a table row with more cells than its header (the extra cells are dropped; shorter rows get empty cells);
- a line of `===` under text (a setext heading, which the builder does not read), and `---` straight under text, which gives a rule.

## The Markdown subset

Front matter goes at the very top. Every key is optional.

```markdown
---
title: Browser tab title (defaults to the # title)
label: Context label, top right of the header
date: Date, shown after the footer text
footer: Footer text, shown as "FOOTER TEXT / DATE"
---
```

| Write | Get |
|---|---|
| `# Title (qualifier)` | The 32px title. A trailing `(…)` becomes the lighter qualifier. Use it once, first. |
| `> Lead line` right after the title | The 14px lead. A second `>` block after it is the muted support line. A `>` block anywhere else is a lead-style paragraph. |
| `## Heading`, `### Heading` | 14px section heading, 12px subheading |
| Paragraphs, `**bold**`, `` `code` ``, `[text](url)` | Body copy at 13px. Bold is the ink-coloured lead-in. Long URLs and paths wrap. Links may be `http:`, `https:`, `mailto:`, `tel:`, a `#fragment` or a relative path; anything else stops the build. A relative link such as `[guide](guide.md)` works only next to its target, so use a full URL in a file you send on its own. |
| ```` ``` ```` fenced block | Code block. The fence may be indented. The language is the first word after the fence; any words after it are ignored. |
| `- item` | Bullet list. Indent `  - item` (two spaces or more) under a bullet or a step for one nested level. Deeper nesting, or a nested numbered list, stops the build. |
| A fenced block indented under a bullet or a step | Code inside that item, under its text. Indented text after the block is a further paragraph of the item. |
| `1. **Step.** Text` | Numbered steps, with orange `01` `02` numerals in their own column. They count up from the first item's number, so `1.` on every line reads 01, 02, 03. |
| Pipe table with a `\|---\|---:\|` row | Table. `---:` aligns right and `:---:` centres. A `\|` inside `` `code` `` does not split a cell; elsewhere write `\\|`. |
| `---` | Rule |
| `[WB1 H9]` | Citation (see below). `[TBD]`, `[API]` and `[TODO]` stay text. Write `\[` for a literal bracket. |
| `Grounded · …` / `Inferred · …` / `Gap · …` | Provenance line (a paragraph that starts with one of these, using the middle dot `·`) |
| `<!-- page -->` | Starts a new A4 sheet (ignored with `--screen`). Put it between blocks, not inside a `:::` block. Other HTML comments are dropped, on a line of their own or inside a line; text after a comment's `-->` is kept. |

Four blocks open with `:::name` and close with a line of `:::`. They cannot be nested.

````markdown
:::callout Next step
The one thing to do now.

A second paragraph for terms or timing.
:::

:::aside Related
Put an aside straight after a callout and the two sit side by side (the closing grid).
:::

:::columns
## Left heading
**Lead-in.** Text with bold lead-ins.
+++
## Right heading
1. **Step.** Numbered steps work in a column.
:::

:::columns
- A list on its own inside :::columns
- becomes a compact two-column list
:::

:::examples
+++ 01 Label
### Title of the example
```svg
<svg viewBox="0 0 300 200">…</svg>
```
One short line on what it shows.
An optional caption, on the next line.
+++ 02 Next
### Image as the art
![What the image shows](art.png)
One short line on what it shows.
+++ 03 Last
…
:::
````

In `:::examples`, each item starts with `+++ eyebrow`. The art is the item's first fenced block: an `svg` block is drawn inline, and any other block is shown as code. The art can also be an `![alt](image.png)` line, inlined from a path relative to the Markdown file. After the art, each line of text is one part: the first is the 10px short line and the second the 8px caption. A blank line between them is optional, and a third line stops the build. Three items fill a row. Phones show one item per row.

- **svg art.** Draw it in the tokens below, on a white sheet (`#fff`) with `--line` borders. Placeholder copy is drawn as bars in the two art tints, `--art-text` for body text and `--art-lead` for lead lines, labels and arrows; no other greys. The block must be well-formed XML with one `<svg>` root and may use only `svg`, `g`, `path`, `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `text`, `tspan`, `defs`, `linearGradient`, `radialGradient`, `stop`, `clipPath`, `mask`, `marker`, `use`, `title` and `desc`. Anything else (scripts, animation, `<style>`, `<image>`, `<a>`), event handlers, and an `href` or `url()` that points anywhere but `#id` or a `data:image` stop the build. The page gets the svg as the builder read it, so comments in it are dropped.
- **Code art.** It wraps to the panel and is centred while it fits. Keep it to about 6 short lines: a panel holds about 8 lines of 32 columns on a desktop and fewer on a phone. A longer block starts at the top and fades out at the panel's foot, and the build warns.
- **Image art.** PNG, JPEG, GIF, WebP or SVG. An SVG file is drawn without the page's fonts, so use a PNG for art with Source text in it.

The builder does not support italics, lists nested more than one level, images outside examples, raw HTML or footnotes. An image outside `:::examples` stops the build. For those, use `template.html`.

## Citations

In a workspace the grammar inside brackets and lines is `formats/FORMATS.md` section 2, for example `[WB1 Steps!D3]`, and a Gap line must be PROVEN.

Every claim carries a visible citation. A citation in a tooltip only does not count.

- **Marker.** Write `[ID locator]` straight after the claim, for example `[G1-S1 H9]` or `[WB1 C4]`. Separate several with `;` inside one bracket: `[WB1 C4; WB1 D4]`. It renders as `<cite class="c" data-src="WB1" data-loc="C4"><a href="#src-WB1">WB1 C4</a></cite>`, a 9px muted marker that links to the source; in a workspace (`--data-links`) it prints as a numbered marker instead. The ID and the brackets never split across lines. A long locator (with spaces, or over 16 characters) goes in `<span class="loc">…</span>` after the ID so that it can wrap on a phone. IDs are capitals, digits and hyphens.
- **What counts as a citation.** With a sources file, a bracket is a citation only when the file names its ID. Any other bracket that looks like one, such as `[Q1 2024]` or a mistyped `[WB2 H9]`, stays text and gets a warning: add the ID to the file, or write `\[Q1 2024]`. When a bracket names at least one ID from the file and its other parts also look like citations, such as `[WB1 H9; WB9 H2]`, it is still a citation: the unknown ID is cited in the accent colour, gets a **Gap** row in Sources and a warning. A locator may hold `&`, `<`, `>` or quotes. Without a sources file, a bracket is a citation when its ID has a digit or hyphen, or its locator has a digit, a `§` or a short capital token, so `[DOC §2]` counts. Words such as `[TBD]`, `[API]` and `[TODO fix this]` always stay text, and `[wb1 H9]` in lower case gets a warning.
- **Provenance line.** It sits straight after the claim, in one of three forms: `Grounded · WB1 H9`, `Inferred · from WB1 col H` or `Gap · not in WB1: who owns the figure`. Only the word `Grounded`, `Inferred` or `Gap` is set in capitals; the rest keeps its case. A Grounded line reads `ID locator; ID locator`, and the ID after `from` in an Inferred line is its source. Those IDs always go into the Sources block, even when they are never cited in brackets. Any other ID in the line is linked when it is in the sources file or cited anywhere in the document, including as the second entry of a shared bracket.
- **Sources block.** It is built automatically at the end of the last sheet. It lists every ID used with its full name, in the order of the sources file. The sources file is a JSON object: `{"WB1": "Sample workbook, Sheet1"}` or `{"WB1": {"name": "…", "note": "…"}}`. An ID with no name is never dropped: its row reads **Gap** · no name in the sources file, in the accent colour. A `Grounded` or `Inferred` line that names such an ID links it in the accent too. In hand-written HTML, `<cite class="c missing">` gives an orange marker (see `template.html`).

## Pages and print

- **A4 mode.** Each sheet is 210 × 297 mm with 14/15/11 mm padding. The footer sits at the foot of every sheet and shows `n / N`. The header (wordmark and label) is on the first sheet only. Each sheet should print as exactly one page. A sheet whose content runs past its page grows taller, and on screens wider than 820 px it shows a dashed orange line at 286 mm, labelled "A4 page ends here" in the right margin. That is where the printed page's content stops: 297 mm less the 11 mm bottom padding. Move `<!-- page -->` above that line. If you print it anyway, everything below the line goes onto an extra page that keeps the sheet's padding.
- **Screen mode.** The column is as wide as the A4 sheet (210 mm), with the same type and no fixed height. The footer comes at the end, and is left out when the front matter has no `footer:` or `date:`. Print gives A4 pages with 14/15/15 mm margins and page numbers.
- **Narrow screens.** Below 820 px the sheet goes full width with 26 px padding. Below 560 px the examples stack (art on the left, text on the right) and the columns become one. Long URLs, paths and title qualifiers wrap, and tables and code blocks scroll inside their own box, so the page never scrolls sideways. In print, tables and code wrap to the paper width.

## Tokens and type

| Token | Value | Use |
|---|---|---|
| `--ink` | `#153e2f` | Headings, bold lead-ins, callout edge |
| `--text` | `#293f34` | Body copy |
| `--muted` | `#65736b` | Support line, labels, captions, citations, footer |
| `--line` | `#dce2dc` | Every hairline and panel border |
| `--soft` | `#f4f6f2` | Panels: art, callout, table head, code |
| `--accent` | `#e9713b` | Pointers only: eyebrows, step numerals, the word "Gap" |
| `--desk` | `#e9ede8` | The surface behind the sheet |
| `--art-text` | `#d0d8d2` | Art only: placeholder body-text bars in svg art |
| `--art-lead` | `#9fb0a6` | Art only: placeholder lead lines, labels and arrows in svg art |

The type scale is: h1 32/600 (−1.05px tracking) with an 18/400 qualifier; lead 14; h2 14/600; h3 12/600; body 13/1.5; columns and callouts 11; table 11; small labels 9–10; footer 8, in capitals. Weights are 400 and 600 only. Panels (art, code) have 5px corners and code chips 3px. Everything else is square. The sheet is the only element with a shadow.

## Brand assets

The typeface is called `Source` in CSS. It is Open Sauce One (© The Open Sauce One Authors), licensed under the SIL Open Font License, which allows embedding; `fonts/OFL.txt` is that licence, and it travels with the fonts. `fonts/source-wordmark.png` is the Source wordmark: it is not part of the font and the licence does not cover it. The three asset files in `fonts/` are final, so there is nothing to run. Only if the brand files change, regenerate them from a Source A4 one-pager saved as HTML with its fonts and wordmark embedded:

```sh
python3 extract_assets.py <source-one-pager.html> fonts/
```

The script takes only the two Source font weights and the wordmark in the page header. It never takes any other image in that file, such as logos of other firms. Example and template copy is always generic: no client names, logos or findings.

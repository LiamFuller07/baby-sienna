# Proposal deck: structure

A **proposal** is a client deck that sets out what we would look at, what the client would receive, how the work would run, what we need from them and what it costs. An AI fills one JSON file, `proposal.json`. `build_proposal.py` checks it and builds **one self-contained HTML page made of 16:9 slides**. The page uses the Source brand, with the same type, colours and parts as the `document` type, set on slides.

It is one section of the toolkit:

| Section | Makes |
|---|---|
| `process-map` | Swimlane board of the current state |
| `process-map-ai-opportunity` | The same board with the AI layer |
| `document` | Source one-pager and long documents (HTML) |
| `proposal` (this one) | Client proposal deck (HTML slides) |

The deck borrows the *structure* of a good one-pager proposal:
- title and framing lead;
- the client's situation;
- the focus to choose;
- example outputs;
- key deliverables;
- how it will work;
- what we need from you;
- the firms we work with;
- next step and commercial terms;
- sources.

## Format

- **The slide is a fixed frame of 1280 × 720 CSS px.** That is PowerPoint widescreen: 13.33 × 7.5 in at 96 px per inch. 1280 is used rather than 1920 because the Source type scale (40 px titles, 16 px body) maps onto it one to one, and it renders crisply at any zoom, since everything is vector. The deck prints to PDF pages of 960 × 540 pt, which is the PowerPoint 16:9 size.
- **On screen**, the slides stack on the desk colour (`#e9ede8`) and scale to the window width. Use these keys:
  - **→ ↓ Page Down Space** go to the next slide;
  - **← ↑ Page Up Shift+Space** go to the previous slide;
  - **Home / End** go to the first and last slides.

  The address bar keeps `#slide-N`, so a link can open any slide.
- **In print**, `@page { size: 1280px 720px }` puts exactly one unscaled slide on each page. "Save as PDF" gives one page per slide. The same file does both, with no switch needed.
- **Self-contained.** The build inlines `deck.css`, both Source font weights and the wordmark. The page loads nothing from the network, and the only script is the screen scaler and key handler.

### Files

| File | What it is |
|---|---|
| `STRUCTURE.md` | This file: slide types, fields, rules |
| `proposal.schema.json` | JSON Schema (2020-12) for `proposal.json`. Its limits are layout limits. |
| `example-proposal.json` | Example: "Process mapping pilot" for **Client A**. Placeholder content only. |
| `example-proposal.html` | The example, built (12 slides, about 230 KB) |
| `template.json` → `template.html` | Every slide type once, with bracketed placeholder copy. `template.html` links `deck.css` and `fonts/` so it can be edited by hand. |
| `deck.css` | The slide system: tokens, frame, chrome, every slide body, art, print |
| `build_proposal.py` | JSON → HTML. Python 3.8+, standard library only. |
| `fonts/` | `source-400.ttf`, `source-600.ttf`, `source-wordmark.png` (from the document type) |
| `previews/` | `slide-NN.png` for every slide, `index.html` (contact sheet), `deck.pdf`, `screen-1440.png`, `screen-390.png` |
| `qa/render.js` | Node Playwright: PNG per slide, layout checks, PDF page count, screen checks, contact sheet |
| `qa/stress.py` | Builds the worst case: every field at its limit and every list at its maximum |
| `qa/test_errors.py` | 18 broken inputs that must each fail clearly, plus a cross-check with the standard `jsonschema` validator |

### Build and check

```sh
python3 build_proposal.py example-proposal.json               # writes example-proposal.html
python3 build_proposal.py proposal.json out.html --strict     # warnings become errors (use before sending)
python3 build_proposal.py proposal.json --check               # validate only
python3 build_proposal.py template.json template.html --linked

NODE_PATH=$(npm root -g) node qa/render.js example-proposal.html previews --sheet
python3 qa/stress.py qa/stress.json && python3 build_proposal.py qa/stress.json qa/stress.html \
  && NODE_PATH=$(npm root -g) node qa/render.js qa/stress.html qa/stress-previews
python3 qa/test_errors.py
```

`render.js` fails the run on any of these:
- content outside the 64 px side margins;
- a body block running into the source line or footer;
- a block whose content is taller than its box;
- overlapping body blocks;
- a cut-off source line;
- any request that is not a `data:` URI;
- a console error;
- sideways scroll at 1440 px or 390 px;
- a PDF page count that differs from the slide count.

## Deck order: required and optional

| # | Type | Required | Purpose | Position |
|---|---|---|---|---|
| 1 | `cover` | **yes** | Title, framing lead, client label | First, exactly once |
| 2 | `situation` | **yes** | The client's situation, as cited claims | Early |
| – | `divider` | no | Opens a section | Anywhere after the cover |
| 3 | `focus` | **yes** | What we'd look at: choose the focus | After the situation |
| 4 | `outputs` | no (recommended) | Example outputs: report, process map, AI-opportunity map, recommendation | After focus |
| 5 | `deliverables` | **yes** | Key deliverables, core and optional | |
| 6 | `process` | **yes** | How it will work: numbered steps on a timeline, or in two columns | |
| 7 | `needs` | **yes** | What we need from you: roles, time, access | |
| 8 | `team` | no | Who you'd work with, and firms we work with (placeholder logos only) | |
| 9 | `commercials` | **yes** | Next step and commercial terms | Near the end |
| 10 | `closing` | no | Thank you, the next step restated, a contact | After commercials |
| 11 | `sources` | **yes when anything is cited** (added automatically) | Appendix: the source register | Last, exactly once; it splits over more slides when long |

Order is free between the cover and the sources slide. The builder enforces only four rules:
- the cover comes first;
- the required types are all present;
- there is one sources slide, at the end;
- the deck has 7 to 30 slides.

A typical proposal has 10–14 slides. That is about 15–20 minutes live, or a pre-read that carries itself.

## The slide frame (shared by every content slide)

```
 52px  eyebrow        14px, accent. The section label. Each type has a default.
       title          40px/600, ink, -1.3px tracking. The slide's message, one line.
       lead           20px, ink, max 900px wide, two lines at most. Optional.
 +34px body           The type's layout, 64px side margins. It ends 112px above the bottom.
 634px source line    12px muted: "SOURCES  S1 Introductory call notes | S2 ... | 1 point to confirm"
 666px footer         Hairline, then: wordmark (62px) · "PROPOSAL FOR DISCUSSION / 22 OCTOBER 2026" · "n / N"
```

- **Wordmark.** It appears large on the cover (154 px) and small in every other footer. Dark slides show it in white.
- **Page numbers.** They read `n / N` on every slide but the cover.
- **Source line.** It appears only on slides that cite something or carry a "to confirm" point. It lists the sources cited on that slide, in register order, with their titles. When the titles would not fit on one line, it shows only the IDs and points to the Sources slide.
- **Footer text.** It reads `meta.status`, then the date written out, then `meta.confidential` when that is set.

## Slide types

Every content type takes the common fields `eyebrow`, `title` and `lead`:

| Field | Required | Limit | Notes |
|---|---|---|---|
| `eyebrow` | no | 40 | Defaults: The situation · What we'd look at · Example outputs · Key deliverables · How it will work · What we need from you · Team · Next step and commercials · Appendix |
| `title` | yes (sources: no) | 46, no final full stop | **The message**, e.g. "Four core outputs, two optional", not "Deliverables". It must not repeat the eyebrow (a warning). |
| `lead` | no | 150 | One or two sentences |

### cover
- **Purpose:** the title and the framing lead. Who chooses what, what we do, what they receive.
- **Layout:**
  - the wordmark top left and the client label top right;
  - a 60 px title with a lighter 32 px qualifier, a 22 px lead and a muted support line;
  - optional art panel on the right.
- **Fields:**
  - `title` (required, 40 characters);
  - `qualifier` (24, e.g. "for Client A" or "(pilot)");
  - `lead` (required, 210);
  - `support` (140);
  - `label` (48; defaults to `meta.client.label`, then the client name);
  - `art`: `process_map`, `ai_map`, `report` or `recommendation`. Leave it out for a typographic cover.

### divider (optional)
- **Purpose:** opens a section in a longer deck.
- **Layout:** a full ink-green slide, with an orange eyebrow, a white 60 px title and a subtitle.
- **Fields:** `eyebrow` (40), `title` (required, 40), `subtitle` (140).

### situation (required)
- **Purpose:** what we understand about the client. **Every statement here is a client claim and must cite.**
- **Layout:**
  - left: 2–3 points as rows, each with a bold heading, a line of text and its citation marker;
  - right: up to two big figures and a "What this means" callout. The callout is a soft panel with the 2 px ink edge, the brand's callout.
- **Fields:**
  - `points` (required, 2–3 × point: `heading` 48 and `text` 150, with `cite` or `to_confirm`);
  - `stats` (0–2 × stat: `value` 6, such as `[N]`, `38%` or `1,240`, and `label` 36, with `cite` or `to_confirm`);
  - `implication` (`heading` 32, default "What this means"; `text` required, 100).

### focus: what we'd look at (required)
- **Purpose:** the client chooses the area. Each option is small enough to do and big enough to matter.
- **Layout:**
  - 2–3 option cards with hairline borders; the recommended card has an ink border and a RECOMMENDED tag;
  - each card shows an orange eyebrow ("Option A" by default), a title, a description and "Questions it answers";
  - an optional "Why this area" line carries a cited claim;
  - an optional note sits under the cards ("Or another area Client A would like to explore.").
- **Fields:**
  - `options` (required, 2–3): `label` 20, `title` (required, 26), `text` (required, 100), `questions` (0–2 × 36), `evidence` (a claim: `text` 50 and one cite), `recommended`;
  - `note` (120).

### outputs: example outputs (optional, recommended)
- **Purpose:** show what the client could receive, like the one-pager's examples row.
- **Layout:**
  - 1–4 columns, each with an art panel (soft fill, hairline, 6 px corners), an orange eyebrow, a title, one line of text and an optional caption;
  - the art row is shared, so the panels always match in height, from 150 to 300 px (whatever the text leaves);
  - one item lays out as art on the left and text on the right.
- **Art kinds:**
  - `report`: a findings report with figures and a ranked bar list;
  - `process_map`: a swimlane slice with a decision, a gap badge and a clarification ring;
  - `ai_map`: the same board with the AI layer (halo and AI squares);
  - `recommendation`: a 2 × 2 of options.

  The art is illustrative and generic. It never shows client data.
- **Fields:**
  - `items` (required, 1–4): `kind` (required), `eyebrow` 28 (default "01 Report"…), `title` (required, 24), `text` (required, 80), `caption` 40;
  - `note` (100).

### deliverables: key deliverables (required)
- **Purpose:** the fixed list of what the client gets.
- **Layout:**
  - two columns of rows with hairlines, read down then across; the rows share the height;
  - a filled ink check marks a core deliverable, and an open square marks an optional one, with an OPTIONAL tag;
  - a legend appears when anything is optional, and a note sits at the foot.
- **Fields:**
  - `items` (required, 3–8): `title` (required, 36), `text` 70, `optional`;
  - `note` (90).

### process: how it will work (required)
- **Purpose:** the steps, the timing and what each step produces.
- **Layout:**
  - `timeline` (default): 2–4 columns on a hairline track, each with an orange numeral `01`, the timing (e.g. "Weeks 1-2"), a title, text and an "Output" chip aligned along the bottom;
  - `steps`: numbered steps in two columns, like the one-pager.
  - `total` gives one muted line on the overall timing.
- **Fields:**
  - `layout`;
  - `steps` (required, 2–4): `title` (required, 28), `text` (required, 110), `when` 16, `output` 44;
  - `total` (90).

### needs: what we need from you (required)
- **Purpose:** the roles, the time and the access we ask of the client.
- **Layout:**
  - one row per item: an icon (a person, or a document for access, documents or data), the role in bold, the time commitment in muted text, then what they do;
  - the rows share the height.
- **Fields:**
  - `items` (required, 1–3): `role` (required, 24), `time` 32 (e.g. "[N] hours a week"), `text` (required, 150);
  - `note` (120).

### team: team and firms we work with (optional)
- **Purpose:** who stays with the work, and partner firms.
- **Layout:** people on the left, up to 2 × 2, each with an avatar placeholder, name, role and one line; "Firms we work with" on the right, as a grid of **placeholder logo tiles**.
- **Fields:**
  - `people` (0–4): `name` (required, 22; `[Name]` in templates), `role` (required, 28), `text` 64;
  - `firms`: `heading` 32, `logos` (required, 1–6 × `name` 24, e.g. "Partner firm 1"), `note` 40 ("And others").

  At least one of `people` and `firms` is required.
- **Placeholder logos only.** The schema has no image field for logos, on purpose. Real partner logos need permission and are placed by hand.

### commercials: next step and commercials (required)
- **Purpose:** the decision we are asking for, and the price.
- **Layout:** on the left, the "Next step" callout: a soft panel with the ink edge, the text and up to three numbered actions. On the right, "Commercial terms": the price in 48 px, a price note, label and value rows, and a note.
- **Fields:**
  - `next_step` (required): `heading` 32, `text` (required, 170), `actions` (0–3 × 48);
  - `terms` (required): `heading` 32, `price` (required, 16; **`[PRICE]` in templates and examples**), `price_note` 48, `rows` (0–4 × `label` 14 and `value` 40), `note` 90.

### closing (optional)
- **Purpose:** thank you, the next step restated, and who to contact.
- **Layout:** an ink-green slide like the divider, with a contact row (Contact · Role · Email · Phone).
- **Fields:**
  - `eyebrow` 40;
  - `title` (required, 40);
  - `text` 140;
  - `contact`: `name` (required, 28), `role` 40, `email` 40, `phone` 24.

### sources: appendix (required when anything is cited)
- **Purpose:** the source register behind every claim.
- **Layout:**
  - a table with columns ID, Source record (title, then detail and the URL's domain), Kind, Date and "Cited on slide", which links to the slides;
  - claims still to confirm follow as TO CONFIRM rows;
  - six rows fit on a slide, and longer registers split into "Appendix · 1 of 3" and so on.
- **Fields:** `eyebrow`, `title` (default "Sources") and `lead` (it has a default). The rows come from `sources[]` and the claims.

## Citations

In a workspace, never write `sources[]`: `bs.py build` writes it from the record headers, and locators use `formats/FORMATS.md` section 1.

The rule: **every claim about the client cites a source record.** A citation shows twice:
- as a small marker beside the claim on the slide;
- as a row on the Sources slide.

1. **The register.** `sources[]` lists every record a claim can cite:
   - `id`: capitals, digits and hyphens, such as `S1` or `WB-2`;
   - `title`;
   - `kind`: document, workbook, meeting-notes, interview, public-filing, website, data or other;
   - optional `date`, `detail` and `url`.
2. **Claim fields.** Claims live only in these fields:
   - situation `points[]`;
   - situation `stats[]`;
   - focus `options[].evidence`.

   Each one carries `cite`, which is 1–2 items of `{ "source": "S1", "locator": "p. 2" }` (the evidence takes one). A locator is the place inside the record: `p. 2`, `§3`, `Sheet1 H9` or `00:14:20`.
3. **The marker.** It is `[S1 p. 2]` in 12 px muted text, linked to the source's row on the Sources slide. This is the same `[ID locator]` notation as the document type.
4. **The source line.** It sits at the foot of each slide and lists the sources cited there by title.
5. **No source yet.** Write `to_confirm` instead of `cite`, saying what to check and with whom. The slide shows an orange **TO CONFIRM**, the source line counts it, and the Sources slide lists it. This is the only way to state something unsourced, and it is always visible.
6. **What fails the build:**
   - a claim with neither `cite` nor `to_confirm` ("uncited client claim");
   - an empty `cite`;
   - a cite to an ID that is not in `sources[]`;
   - a duplicate ID.
7. **What warns** (and fails with `--strict`):
   - a source that is never cited;
   - a plain, uncited field that names the client next to a figure, such as "Client A runs 3 ERPs", which reads like a claim. Move it into a claim field.
8. **What is not a claim:** our own offer. That covers the focus descriptions, deliverables, steps, needs, team, price and terms. These need no citation.

## Content rules for the AI that fills the JSON

- **Placeholders only in examples and templates.**
  - The client is "Client A" (or `[Client]`), people are `[Name]`, the price is `[PRICE]`, terms are `[TERMS]` and `[DATE]`, and unknown figures are `[N]`.
  - Firms are "Partner firm 1…".
  - No real client, person, firm or logo.
- **Titles say the message** in one line, with no final full stop. The eyebrow names the section, and the title must not repeat it.
- **Stay within the limits.** They are measured layout limits, not style advice. `qa/stress.py` builds a deck with every field at its limit and every list at its maximum, and it renders with no overflow. A longer string is an error that names the field and its limit ("is 61 characters; the slide has room for 46").
- **Write in plain words**, with short sentences and typographic apostrophes (’).
- **Facts about the client go only in claim fields**, with a citation.

## Style

- **Tokens** (`deck.css`, the same as `doc.css`):

  | Token | Value | Use |
  |---|---|---|
  | ink | `#153e2f` | titles and headings |
  | text | `#293f34` | body copy |
  | muted | `#65736b` | labels, captions, citations and the footer |
  | line | `#dce2dc` | every hairline |
  | soft | `#f4f6f2` | panels |
  | accent | `#e9713b` | eyebrows, step numerals and TO CONFIRM |
  | desk | `#e9ede8` | the surface behind the slides |
- **Orange is sparing:** only on pointers, and never as fills, bars or stripes. The dark slides use ink green, not orange.
- **Type** is Source, which is Open Sauce One under the SIL OFL, so embedding is allowed. It is inlined into every deck, so nothing needs installing to view or print one.
  - Weights are 400 and 600 only.
  - Sizes: title 40, cover and divider 60, lead 20, item headings 18–21, body 15–17, labels 11 in capitals, citations 12, footer 11 in capitals.
- **Shapes:** the slide frame and cards are square. Art panels have 6 px corners. The only shadow is on the slide on screen.
- **Process-map art** uses the map system's own look from the map design reference, and not the document tokens:
  - warm lanes (`#f3efe7` and `#ece8e0`) and white nodes with `#c8c8c4` hairlines;
  - dark `#454542` flow lines with arrowheads, and dashed lines for feedback and inferred steps;
  - a decision diamond, filled `#ff5600` gap badges and dashed orange clarification rings;
  - for the AI layer, an orange halo and AI squares (filled when named, outlined when suggested).

  Report and recommendation art use the document tokens.

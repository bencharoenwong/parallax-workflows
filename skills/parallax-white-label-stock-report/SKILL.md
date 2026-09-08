---
name: parallax-white-label-stock-report
description: "Render a Parallax full stock research report (the get_stock_report output) under a client's brand as a white-labeled HTML and PDF. Takes a ticker (RIC), pulls the report, and re-renders all sections (cover, factor scores, thesis, company + peers, technical, financial analysis, statements, ratios, analyst ratings, disclosures) with the client's logo, colors, and fonts from the active white-label config. Visual skin only: keeps Chicago Global / MAS regulatory disclosures verbatim and a \"Powered by Parallax\" credit. Standalone, no shared-module dependency. NOT for configuring client branding (use /parallax-white-label-onboard first), not for monthly CIO LP letters (use /parallax-cio-letter-prep), not for ad-hoc single-stock analysis or research workflows (use /parallax-deep-dive or /parallax-due-diligence)."
---

# White-Label Stock Report

Re-render the Parallax full stock research report (the `get_stock_report` output) under a client's brand, as a white-labeled HTML and PDF. The client's logo, colors, and fonts replace the Parallax visual identity; the underlying research, the Chicago Global / MAS regulatory disclosures, and a "Powered by Parallax" credit stay intact.

This is a presentation overlay. The onboarded client is the presentation brand; in the default co-brand mode Chicago Global Capital remains the research author of record.

## Usage

```
/parallax-white-label-stock-report <TICKER>            # resolve, fetch, render with the active brand config
/parallax-white-label-stock-report AAPL.O              # RIC form (preferred)
/parallax-white-label-stock-report <path/to/report.json>  # use an already-downloaded report JSON (no fetch, no paid call)
/parallax-white-label-stock-report <TICKER> --force    # ignore cache, re-fetch the paid report
/parallax-white-label-stock-report <TICKER> --full-white-label  # private-label: client's own disclosures, no CG/Parallax attribution
/parallax-white-label-stock-report <TICKER> --full-white-label --powered-by  # client's own disclosures, keep the Parallax credit
```

The active brand config (written by `/parallax-white-label-onboard`) at `~/.parallax/client-branding/config.yaml` is used automatically. With no config, the report renders in the default Parallax palette (not white-labeled).

## Prerequisites

- Parallax MCP connected (the `get_stock_report` tool available).
- Python 3.9+ with `pyyaml`. Optional `pymupdf` (used to trim a trailing footer-only page from the PDF; if absent, that step is skipped).
- Google Chrome (for `--pdf`). Without it, the skill still writes the HTML; render the PDF separately.
- A brand config from `/parallax-white-label-onboard` to actually white-label the output.

## Compliance (two modes)

**Default - co-brand (recommended).** A presentation skin over Chicago Global research:
- Swap the visual identity only: logo, primary/secondary/accent colors, heading/body fonts, and the client name in the header.
- Keep the Chicago Global / MAS regulatory disclosures verbatim (the renderer bundles them; the JSON does not carry them).
- Show a "Powered by Parallax" credit in the cover header.
- The per-page footer carries the client name and a confidentiality marker ("<Client> - Confidential" plus "Page X of N"); Chicago Global's MAS-regulated identity sits in the disclosures section, not the footer.

**`--full-white-label` - private-label (gated).** The client presents the report as their own:
- Removes the Parallax attribution credit and replaces the Chicago Global / MAS regulatory disclosures with the client's own. The client may opt to keep a "Powered by Parallax" credit (`--powered-by`); otherwise the document carries no Parallax mark.
- Renders the client's OWN regulatory disclosures, taken verbatim from the brand config's `voice.disclaimers[]` ({jurisdiction, text, placement}) - the field the onboard skill already provides for jurisdiction-specific compliance footers.
- Refuses to render if `voice.disclaimers[]` is empty, so it can never emit regulated research with no disclosures.
- This requires the client to actually hold the appropriate authorization in their jurisdiction and to supply their own compliance-approved disclosure language. It goes a step beyond the shared white-label integration pattern (which keeps disclaimers fixed), so confirm with Chicago Global before using it for a live client.
- Note: AI-generated prose fields from `get_stock_report` (score_analysis, analyst_analysis, peers_analysis, financial_analysis) are served brand-neutral by Parallax and pass through verbatim. If you are using a non-standard response source, review the prose for brand mentions before distribution.

## Choosing a mode (jurisdiction and audience)

Which mode is appropriate is a compliance decision driven by who distributes the report and to whom, not a styling preference. Default to co-brand; move to full private-label only with the client's own regulatory details and sign-off.

Thailand, as a worked example, in brief - confirm with local counsel before any live retail launch:
- There is no verified Thai equivalent of the MAS license-number / "Regulated by MAS" stamp. Thai research customarily names the firm and discloses conflicts of interest, rather than printing a license number.
- The binding constraint is on distribution, not branding (SEC Notification Kor Nor. 22/2544): a MAS-licensed (IOSCO-member) firm may provide research into Thailand without a Thai license only DIRECTLY to qualified institutional investors. Any RETAIL distribution must be arranged through a licensed Thai securities company, whose own SEC-approved staff and disclosures stand behind the report.
- Producing or distributing research to clients in Thailand needs a firm securities-business license (investment advisory service) plus individual Investment Consultant (IC) approval; analysts typically hold the CISA credential.

Decision:
- Institutional / qualified-institutional audience only: co-brand is appropriate. The Chicago Global / MAS disclosures and the "Powered by Parallax" credit can stand; the client's brand is the visual skin.
- Client is a licensed Thai securities company distributing to retail: the client is the regulated face of the report. Use --full-white-label, put the client's OWN firm identity and conflict disclosures on the document, and ensure qualified (IC / CISA) sign-off. Whether to keep any Chicago Global credit is then the client's call with their compliance.

To run full private-label, collect from the client and load into the onboard config's voice.disclaimers[] ({jurisdiction, text, placement}): the client's legal entity name, regulatory/license status, the conflict-of-interest / disclaimer wording their compliance approves, and confirmation of qualified analyst sign-off. The renderer refuses --full-white-label if voice.disclaimers is empty.

This is not legal advice. The client's compliance function and Thai counsel should confirm investor classification and the current notification text before any external distribution.

## When not to use

- Setting up or editing the client brand config → use /parallax-white-label-onboard
- Monthly fund-manager letter to LPs → use /parallax-cio-letter-prep
- Interactive single-stock analysis / buy decision → use /parallax-should-i-buy or /parallax-deep-dive
- Full DIY research workflow (Palepu, financials) → use /parallax-due-diligence
- Portfolio-level review → use /parallax-client-review

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3); this skill loads no other shared file by design. The output is a file, not a chat report, so the shared render gate does not apply; the deterministic renderer is the gate.

### Step 0 — Pre-flight

1. `discover-tools`: bind `search_stocks` and `get_stock_report` to the exact callables exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
2. Parse args: ticker, RIC, or a path to a saved report JSON; `--force`; `--full-white-label`; `--powered-by`.
3. `read-config` `~/.parallax/client-branding/config.yaml`: confirm it exists and `metadata.client_name` names the intended client. Absent or wrong client → collect the brand guidelines (logo and colour palette at minimum; fonts optional) and run `/parallax-white-label-onboard` first; without a config the render falls back to the default Parallax palette and is not white-labeled.

### Step 1 — Resolve inputs

A plain ticker or company name → `call-tool` `search_stocks` for the RIC (`AAPL.O`, `V.N`). Single-letter US tickers must be in RIC form or the report call fails with "Symbol too short".

### Step 2 — Fetch (parallel batches)

The renderer reads a `get_stock_report` JSON file; it never calls the MCP itself. Resolve the source cheapest first:
1. **Supplied file** — a saved `get_stock_report` response passed on the command line: no fetch, no paid call (it must be the JSON response, not a rendered PDF).
2. **Same-day cache** — `~/.parallax/stock-report-cache/<RIC>-<YYYY-MM-DD>.json` when present and `--force` was not passed.
3. **Fresh fetch** — `call-tool` `get_stock_report(symbol=<RIC>)` (paid, about 1–2 min) and `write-artifact` the full raw response to the cache path above (`mkdir -p ~/.parallax/stock-report-cache` first).

### Step 3 — Verify

- The JSON carries the sections the renderer reads (`references/field-map.md`); a truncated or non-JSON file stops here.
- For `--full-white-label`: `voice.disclaimers[]` in the brand config is non-empty; the renderer refuses otherwise, so do not attempt the render.

### Step 4 — Compute

None. The renderer is deterministic Python; the model never authors or edits the HTML.

### Step 5 — Confirm

`ask-operator` two independent choices (see Compliance above): **whose disclosures** (Chicago Global / MAS by default, or the client's own via `--full-white-label`) and **keep the "Powered by Parallax" credit** (shown by default; with the client's own disclosures only with `--powered-by`). Three usable variants result: co-brand; client identity with credit; full private-label.

When the client wants their own disclosures, collect what their regulator requires — legal entity name, registration or license number, regulator's name, the conflict-of-interest / disclaimer wording their compliance approves — and load them into the brand config's `voice.disclaimers[]` (`{jurisdiction, text, placement}`). Draft from what the client gives you; the client confirms the final text; the renderer reproduces it verbatim. If `ask-operator` is unavailable on this host, apply conventions §14.3: render the two questions and stop; never default to `--full-white-label`.

### Step 6 — Render

`run-shell`:

```
python3 <skill-dir>/render_stock_report.py \
  ~/.parallax/stock-report-cache/<RIC>-<date>.json \
  --branding ~/.parallax/client-branding/config.yaml \
  --out "Stock Report - <RIC> - <ClientName>.html" \
  --pdf
```

Add `--full-white-label` and/or `--powered-by` per Step 5. `--pdf` renders the PDF next to the HTML via headless Chrome; without Chrome the HTML is still written and the PDF is rendered separately. Output naming: `Stock Report - <RIC> - <ClientName>.pdf`.

## Brand token map (inlined in the renderer)

| CSS variable | From config | Used for |
|---|---|---|
| --brand-primary | colors.primary | H1/H2, rules, table-header fill, score-chip fill |
| --brand-secondary | colors.secondary (fallback primary) | H3, dividers, accents |
| --brand-accent | colors.tertiary | callouts |
| --brand-bg | colors.neutral | page background |
| --brand-text | #333333 | body text |
| --brand-heading-font | typography.h1.fontFamily | headings |
| --brand-body-font | typography.body-md.fontFamily | body |
| (logo) | logos.primary (base64-embedded) | cover/header |

Fixed semantic colors, never branded: positive `#1a7f4b`, negative `#b3261e`, warning `#b8860b`.

## Failure modes

- No brand config: the render is not white-labeled; say so and offer `/parallax-white-label-onboard` before delivering.
- `--full-white-label` with empty `voice.disclaimers[]`: the renderer refuses; collect the disclosures per Step 5, never improvise them.
- `get_stock_report` fails or times out: no render; report the failure and whether a cached copy exists.
- Chrome absent: HTML only; state that the PDF was not produced.
- Host lacks `run-shell` or `write-artifact`: the skill cannot run on this host (conventions §14.3); say so, do not hand-write HTML.

## Done when (review before delivery)

Open the PDF and confirm every line; then deliver:
- client logo on the cover and the brand palette applied to headings, rules, table headers, and score chips;
- positive/negative/warning still in the fixed semantic colors (green/red/amber), NOT recolored to the brand;
- the six factor scores, the peer table, all three financial statements, and the ratios table rendered;
- the Chicago Global / MAS disclosures present verbatim and the "Powered by Parallax" credit in the cover header (or, in the chosen private-label variant, the client's confirmed disclosures and the credit state the client chose);
- no leakage of internal source paths or pre-signed URLs.

During early rollout, do not send externally without Chicago Global sign-off on the compliance posture.

## Cross-model parity

The renderer is plain deterministic Python, so Claude and Codex produce identical HTML for the same report JSON and config. Run the same steps on either engine. The model never authors the HTML; it only orchestrates and reviews.

## Files

- `render_stock_report.py` - the entire renderer (config read + normalize + HTML template + bundled disclosures + optional PDF). Self-contained.
- `references/sample-acme.synthetic.json` - a de-identified synthetic get_stock_report response (fictional company), used as the test fixture.
- `references/field-map.md` - verbatim JSON field paths the renderer reads.
- `tests/test_render_smoke.py` - smoke test (sections present, branding applied, semantic colors fixed, disclosures verbatim).

## Gotchas

- Standalone by design. This skill imports NO sibling or shared module (no _parallax/white-label/ loader, no integration-pattern.md). render_stock_report.py inlines its own branding reader, token map, semantic-color rule, and the CGC disclosure boilerplate. The only files it reads at runtime are the report JSON and the brand config.
- The renderer is deterministic. The model's job is orchestration only (resolve ticker, call get_stock_report, run the script, review). NEVER hand-write or hand-edit the report HTML; that breaks Claude/Codex parity. Same script + same inputs = identical output.
- get_stock_report is PAID (about 1-2 min). Check the cache at ~/.parallax/stock-report-cache/<RIC>-<YYYY-MM-DD>.json first; pass --force only to refresh.
- Single-letter US tickers fail as bare symbols ("Symbol too short"). Resolve to RIC first (Visa = V.N, not V). Use search_stocks to confirm the RIC.
- Disclosures are NOT in the get_stock_report JSON. The skill renders its own bundled verbatim copy of the Chicago Global / MAS disclosure boilerplate. It is a pinned asset; if CGC updates its disclosure wording, re-sync the constant in render_stock_report.py from response.html_url. Never reword it.
- Semantic colors (positive green, negative red, warning amber) are FIXED and never taken from the brand. They carry meaning, not identity. Only primary/secondary/accent/background/fonts/logo come from the client config.
- Output language is English only. Translation hand-offs in the workflow skills operate on chat-layer prose; they do not localize this renderer's HTML/PDF (see `references/field-map.md`, 'Localization boundary').
- No active brand config → the renderer falls back to the default Parallax palette and the output is NOT white-labeled. Run /parallax-white-label-onboard first to skin it for a client.
- Output is two independent choices (see Compliance): whose disclosures (Chicago Global / MAS by default, or the client's OWN via --full-white-label, collected at run time into voice.disclaimers[] and refused if empty), and whether to keep the "Powered by Parallax" credit (shown by default; kept in full white-label only with --powered-by). Never hand-edit disclosures or improvise a private-label without the client's confirmed disclosure language.
- During early rollout, do not send a generated report to an end client until Chicago Global has signed off on the compliance posture.

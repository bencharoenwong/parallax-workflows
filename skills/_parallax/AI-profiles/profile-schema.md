# Parallax AI Investor Profile — Schema Contract

This file is JIT-loaded by every `skills/AI-<name>/SKILL.md` dispatcher. It defines:
1. The YAML frontmatter contract a profile spec must conform to
2. The dispatcher workflow steps every profile runs at invocation time
3. The pre-render cross-validation check required by spec §6.4

## 1. Profile frontmatter contract

Every `profiles/<name>.md` MUST begin with YAML frontmatter containing the following fields. Profiles missing any required field are considered invalid and the dispatcher MUST refuse to render.

```yaml
---
profile_id: <short-name>                    # REQUIRED. Lowercase, alphanumeric + underscore. Matches filename.
display_name: <Display Name-style>          # REQUIRED. Example: "Buffett-style". Always ends in "-style".
status: active | draft | retired            # REQUIRED. Informational; does not gate invocation (see design spec §6.1).
public_anchor:
  type: academic_paper | book | sec_filing  # REQUIRED.
  citation: "<full citation>"               # REQUIRED. Full academic citation with authors, year, title, journal/publisher.
  doi_or_url: "<DOI or URL>"                # REQUIRED if available; otherwise "N/A — book/out-of-print source".
  retrieved: <YYYY-MM-DD>                   # REQUIRED. Date the anchor was last verified to exist.
  notes: "<one-line note>"                  # REQUIRED. Why this anchor is defensible.
direction: bottom_up | top_down             # REQUIRED.
asset_class: equity | multi_asset           # REQUIRED.
factor_tilts:                               # REQUIRED for factor-driven profiles. Empty dict {} for non-factor profiles.
  <factor>: positive_strong | positive | neutral | negative | negative_strong
leverage_overlay: <float or null>           # REQUIRED. null if not applicable. Disclosed, not applied per-stock.
output_shape: single_stock_verdict | ranked_basket | trade_ideas | inferred_exposure_verdict  # REQUIRED.
tool_sequence:                              # REQUIRED. List of Parallax tools to call, in order. Use `tool:param=value` format for parameters.
  - <tool_name>
  - <tool_name>:<param>=<value>
required_factors_present: [<list>]          # REQUIRED for factor-driven profiles. Empty [] otherwise.
thresholds:                                 # REQUIRED if the profile uses score thresholds. Dict of factor -> comparison.
  <factor>: ">= 7"                          # Example: "quality: '>= 7'"
owner: <team>                               # REQUIRED.
last_legal_review: <YYYY-MM-DD or PENDING>  # REQUIRED. Informational; does not gate invocation.
last_anchor_test: <YYYY-MM-DD or PENDING>   # REQUIRED. Gates auto-flip to retired on failure.
---
```

After the frontmatter, the body of the profile spec contains a 300-500 word prose narrative describing:
- Who the anchor is and what it documents
- What the workflow does
- What the workflow does NOT capture (explicit gaps)
- How to interpret the output

### Optional additional fields

Profiles MAY include additional descriptive frontmatter fields beyond the required set above, e.g.:
- `factor_tilts_notes` — free-text note when `factor_tilts` alone doesn't tell the whole story
- `output_shape_single_ticker` — alternate output shape when the profile supports two modes (used by Soros)
- `tool_sequence_basket` / `tool_sequence_single_ticker` — alternate tool sequences for dual-mode profiles (used by Soros)

Optional fields are ignored by dispatchers unless the dispatcher explicitly consumes them. They exist for human readability and future extensibility. Adding an optional field is a schema-compatible change; removing or renaming a REQUIRED field is not.

## 2. Dispatcher workflow

Every `skills/AI-<name>/SKILL.md` dispatcher runs this exact sequence. The dispatcher is generic — all differentiation lives in the profile spec.

### Step 0: JIT-load dependencies

Before any Parallax tool call in the session:
- JIT-load `skills/_parallax/parallax-conventions.md` (RIC resolution, parallel execution, fallback patterns, HK ambiguity)
- JIT-load `skills/_parallax/AI-profiles/profile-schema.md` (this file)
- JIT-load `skills/_parallax/AI-profiles/output-template.md` (render contract)
- JIT-load `skills/_parallax/AI-profiles/profiles/<profile_id>.md` (the specific profile)

Before the first Parallax tool call, call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas.

### Step 1: Parse input

Accept a ticker (or short basket for profiles whose `output_shape` is `ranked_basket` or `trade_ideas`; capped at 5 tickers per call). Resolve RIC per shared conventions.

### Step 2: Pre-render cross-validation gate (spec §6.4)

After any scoring tool call (`get_peer_snapshot`, `get_score_analysis`, `quick_portfolio_scores`), cross-check the `name` field returned by the scoring tool against the `name` field returned by `get_company_info` for the same symbol. If names diverge, the dispatcher MUST refuse to render and emit exactly this error:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  <scoring_tool> returned:   "<name_b>"
Cannot render <display_name> profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

This check is NON-BYPASSABLE. No profile may render output on unverified data.

### Step 3: Execute the profile's tool_sequence

Run the tools declared in the profile's `tool_sequence` frontmatter field. Fire independent calls in parallel per `parallax-conventions.md §3`. Apply graceful fallback patterns per §4.

### Step 4: Apply profile thresholds / logic

For factor-driven profiles (`factor_tilts` non-empty), compare each returned factor score against the profile's `thresholds` and mark pass/fail per factor. For non-factor profiles (e.g., Greenblatt, Klarman, Soros), apply the profile's custom logic as specified in its body narrative.

### Step 5: Compute verdict

Map pass/fail results to a verdict tag:
- `match` — all threshold criteria met (or profile-specific "full fit" criteria)
- `partial_match` — some but not all criteria met; graded by count (e.g., "2 of 4")
- `no_match` — zero criteria met or explicit fail condition triggered
- `skipped` — profile explicitly non-applicable (rare — see Soros for the only v1 case, and even that one runs in both modes per §3.2)

### Step 6: Render through output template

Pass all collected data (profile metadata, factor scores, threshold results, verdict, citation) to the output template at `output-template.md`. The template enforces the header, data table, verdict, methodology footer, and standard disclaimer.

### Step 7: Emit

Output the rendered template content. No additional commentary from the dispatcher.

## 3. Schema validation checklist for new profiles

Before committing a new profile spec:

- [ ] Frontmatter has ALL required fields listed in §1
- [ ] `profile_id` matches the filename (e.g., `buffett.md` has `profile_id: buffett`)
- [ ] `display_name` ends with "-style"
- [ ] `public_anchor.citation` is a full academic/book citation
- [ ] `public_anchor.doi_or_url` is a real URL or "N/A — book/out-of-print source"
- [ ] `tool_sequence` only contains Parallax tool names listed in `skills/_parallax/token-costs.md`
- [ ] `tool_sequence` does NOT contain `get_assessment`, `get_stock_report`, or `score_total`
- [ ] Body narrative is 300-500 words and includes "what this does not capture"
- [ ] `last_anchor_test` will be updated after the anchor test in the PR that introduces this profile

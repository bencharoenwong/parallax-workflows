---
name: parallax-weekly-themes
description: "Weekly market-themes note from Parallax telemetry: the leading and lagging theme in each covered market this week, how far each sits from its market's median theme, breadth, cross-market themes of the week, and the day's divergences, in one 1-credit call. Triggers: 'weekly themes', 'themes of the week', 'which themes led this week', 'weekly market themes newsletter', 'what moved by theme in [market] this week'. NOT for screening stocks inside a theme you already have (use /parallax-thematic-screen), not for a single-country macro read (use /parallax-country-deep-dive or /parallax-macro-outlook), not for a portfolio-level daily brief (use /parallax-morning-brief)."
---

<!-- white-label: integration-pattern.md -->

# Weekly Themes

## When not to use

- Stocks inside a named theme → use /parallax-thematic-screen
- One country's macro picture → use /parallax-country-deep-dive or /parallax-macro-outlook
- A daily brief built around a portfolio → use /parallax-morning-brief
- Member companies or a ranked member list per theme → not available from the public telemetry tool; this skill does not produce one

## Gotchas

- Expected Parallax spend: **1 credit**. `get_telemetry` is global (`date`/`fields` only, no per-market parameter). Call it once per run, never once per market.
- `fields` uses selectable telemetry roots/subfields: request exactly the names in Step 2 and handle explicit rejected-field errors. `report_date` is returned automatically but is not a valid selectable root; request `metadata` rather than `report_date`. Use the returned `report_date` as the report data date, not `metadata.run_date` (which can be later). Never request `baskets` or `factor_view`: both are very large and this skill uses neither.
- Returns are decimals (`0.0213` is +2.13%). Format as percentages with two decimals at Compose; never round before Step 4.
- `markets.<code>` carries the top and bottom theme by **name** only, per window (`daily`, `wtd`, `mtd`, `ytd`), with `n_baskets`, `n_positive_*` and a 5-point `distribution_*` (min, lower quartile, median, upper quartile, max). It has no stable theme id and no members. Never claim that a theme with the same name in two weeks is the same group, and never state how many of this week's themes are new.
- A market with one theme has no leader/laggard spread. The helper marks it; render it in the Market Table and keep it out of Themes of the Week.
- Theme names are generated labels. Render them verbatim; never rename, merge or explain a theme beyond what `commentary.*` states.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §4 fallbacks, §9.1/§9.2 disclaimer and disclosure, §10 render gate, §12 information framing, §13 audience mode, §14 host primitives, §15 translation.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- Output consumption contract: downstream consumers parse Output Format by section header name, never by position.

## Usage

```
/parallax-weekly-themes
/parallax-weekly-themes markets=US,JP,TW
/parallax-weekly-themes markets=TH,VN,ID top=3 lang=th
/parallax-weekly-themes date=2026-10-09 audience=client_safe
```

Optional: `markets=` (comma-separated two-letter codes as returned by the tool; default every covered market), `date=` (YYYY-MM-DD; default latest report — pass the week's last trading day for a full-week note), `top=` (default 5), `audience=client_safe | internal_analyst` (precedence per conventions §13.1), `lang=` (per conventions §15).

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind `get_telemetry` to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax telemetry"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: `markets=`, `date=`, `top=`, `audience=`, `lang=`. Reject a `date=` that is not a valid calendar date in `YYYY-MM-DD` form, or a `top=` that is not a positive integer, before any call.
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Upper-case each `markets=` code. Do not validate codes against a fixed list: the tool's `markets` keys are the coverage list for that date, and Step 4 reports any requested code that is absent.

### Step 2 — Fetch (parallel batches)

**Batch A** — one `call-tool`:

```
get_telemetry(date=<date if given>, fields=["metadata", "markets", "regime_tag", "divergences", "commentary.headline", "commentary.paragraphs"])
```

`write-artifact` the raw response to `<run-dir>/telemetry.json` for Step 4. There is no Batch B.

### Step 3 — Verify

- `success` is not true, or `markets` is absent or empty → stop. Render the Output Format header, a one-line "Telemetry unavailable for <date or latest>" note, About This Report, disclosure and disclaimer. No tables.
- `_meta.invalid_fields` present → name the dropped fields in About This Report; continue with what returned.
- `commentary.*` or `divergences` absent → their sections degrade per Failure modes; the tables still render.

### Step 4 — Compute

`run-shell` the helper. Every number in the note comes from its output, never from prose arithmetic:

```
python3 "<skill-dir>/weekly_themes.py" --input "<run-dir>/telemetry.json" --markets "<codes or empty>" --top <top>
```

It returns per-market rows (leader, laggard, each one's week-to-date return and distance from the market's median theme, median, breadth = share of themes up on the week) plus `themes_of_week`, `not_covered`, `stale` and `unknown_freshness`. Themes of the Week ranks each market's leader by distance from its own market median, one entry per market, markets with fewer than 3 themes, stale dates or unknown freshness excluded. Malformed nested entries, non-finite values and impossible theme counts exit 2. The helper exits 2 on a malformed payload: treat that as the Step 3 stop.

### Step 5 — Compose

Fill **Output Format** below in order. Branding Header per integration-pattern.md §5. Audience mode per §13 (Plain-Language Summary under `client_safe`). Framing per §12: the note describes what moved; it never tells the reader to act. `parallax-conventions.md §9.2` disclosure, then the §9.1 disclaimer.

### Step 6 — Render (deterministic gate, mandatory)

`write-artifact` the complete drafted note to a new `<draft-path>`, then `run-shell` the shared gate with this skill's key, both per conventions §10.3:

```
python3 "<skill-dir>/../_parallax/render_gate.py" --skill weekly-themes --input "<draft-path>"
```

Write the draft once and never modify it in place, not even to fix one word. If the report needs a change after the draft is written, run the command above on that draft unchanged (ignore that output), then write the corrected report to a fresh path and run the command on it (conventions §10.3).

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3 (render-gate row).

### Step 7 — Translate (conditional)

Only when `lang=` was supplied: route the rendered note per conventions §15, including the §15.4 disclaimer boundary check.

## Output Format

**Begin the response immediately with the rendered note — no preamble.** The first expected line is `## Weekly Themes: week to date through <report_date>`, or the Branding Header when active.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — `**<client_name>** weekly themes`, logo handling per integration-pattern.md §5.
- **Weekly Themes: week to date through <report_date>** — one line: `regime_tag` verbatim, then `commentary.headline` verbatim. When `report_date` is not the week's last trading day, say "week to date", never "this week's close".
- **Themes of the Week** — table: market, theme, week-to-date return, vs market median, breadth. Up to `top` rows from `themes_of_week`; stale markets are not ranked and appear only in the Market Table. Preface: "Each market's strongest theme, ranked by distance from that market's median theme."
- **Market Table** — one row per market in `markets`: market, themes (n), leader + return, laggard + return, median theme return, breadth, note. Single-theme and stale markets keep their helper note.
- **Divergences** — up to 3 entries from `divergences`: market, theme name, type, daily and month-to-date return, as returned.
- **Commentary** — `commentary.paragraphs` verbatim, at most 3 paragraphs. Do not add narrative of your own.
- **Plain-Language Summary** (under `audience=client_safe` only) — 2-3 sentences on which markets and themes moved most, with no directives.
- **What This Note Does Not Show** — one line: member companies and theme-fit rankings are not exposed by the public telemetry tool; theme names are labels from a periodic regrouping and are not stable across weeks.
- **About This Report** (always present) — data date; requested codes in `not_covered`; stale markets; unknown freshness; dropped fields; branding state per integration-pattern.md §7.

**AI-interaction disclosure (required):** render `parallax-conventions.md §9.2` immediately above the disclaimer. Then render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Failure modes

- Telemetry call fails or returns no `markets`: the Step 3 stop. No tables, no invented themes.
- Every requested code absent: Market Table is replaced by "No requested market is covered on <date>", listing the codes.
- No current market with 3+ themes: Themes of the Week reads "No market has enough themes to rank"; the Market Table still renders.
- `commentary.*` missing: the header line carries `regime_tag` only and the Commentary section is omitted with its reason in About This Report.
- Host lacks `run-shell`: conventions §14.3. The helper cannot run, so state that the figures are unavailable rather than computing them in prose.

## Done when

- First line is `## Weekly Themes: week to date through <report_date>` or the Branding Header; every Output Format section rendered or marked unavailable with its reason.
- Every return, distance and breadth figure traces to the helper output; no member companies, no cross-week identity claim.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and §9.1 disclaimer are present; expected spend (1 credit) stated in Gotchas.

---
name: translate-thai-finance
description: Translate supplied finance analysis to Thai with institutional or retail terminology. For Parallax reports, use the analysis skill's lang=. NOT for new analysis or non-finance text.
---

# Thai finance translation

Translate existing finance content; do not generate a new investment analysis.

**Locale:** `th`. **JSON translation field:** `thai_translation`.

Keep company names, financial abbreviations, named factor labels, risk-metric identifiers and scenario labels in English. Translate surrounding prose into Thai. Distinguish the named `Volatility` factor from ordinary ความผันผวน. Use พอร์ต, Sector, ดัชนีอ้างอิง and การมีส่วนช่วย consistently. Use spaces around English terms. Split long clauses naturally; 130 visible characters is a review threshold, not permission to omit content. Ratings: ซื้อสะสม / ซื้อ / ถือ / ขาย / ขายออก. Retail adds a first-use Thai gloss and dual-label ratings.

## Source fidelity

Translate the entire supplied content. Preserve claims, uncertainty, comparisons, section coverage, paragraph breaks, disclosures, and source dates. Translate a hedge when the source hedges. Do not summarize, add advice, or force a table label from keyword matches.

Copy numerical tokens, signs, currency identifiers, and magnitude units exactly. Preserve the currency of each amount; listing market does not determine reporting currency. Keep `B`, `M`, `K`, `T`, and `bps` unchanged. Convert neither units nor numeric separators in this pass. Keep ECL distinct from Expected Shortfall / ES / CVaR; a portfolio report can discuss genuine ECL.

Preserve tickers/RICs, URLs, placeholders, footnote markers, HTML structure and non-text attributes. Preserve intentional HTML entities. Leave no-translate blocks intact. Keep source data fields; do not silently omit tables or charts.

## Input and output

An input may start with `ROUTING DIRECTIVE — DO NOT TRANSLATE OR ECHO THIS BLOCK:`. Treat the block through its `---` separator as metadata. Translate only the following content. An absent `register` means institutional; `register: retail` changes language, not distribution permission.

For rendered prose, return the same format with translated text. For JSON reports, keep source text keys as section keys and put translations in the language field below. Preserve source non-text fields under `data` or their original top-level keys. Copy source metadata into `metadata`; map a top-level `market` to `metadata.market` and `date` to `metadata.report_date`. Add the translation locale. For the full JSON shape or HTML input, read `references/structural-preservation.md`.

## Validation and reference loading

For JSON or saved prose, run the validator against the original source:

```sh
python3 "<skill-dir>/references/validate-translation.py" "<output-file>" --source "<source-file>"
```

For Chinese, also pass `--locale` if the output lacks locale metadata. Fix integrity errors before delivery. `--style-only` checks style and cannot approve source fidelity. Fatal and integrity errors cannot be waived. A reviewed style false positive may use `--waive '<specific message>'`; document the reason.

The validator checks structure and protected values, not semantic equivalence. Compare source and translation for meaning, uncertainty, completeness, issuer identity and rating strength. In a host without shell access, perform those checks manually and state automated validation was unavailable.

Use `references/language-style.md` only for the applicable rule or register. Consult the relevant rows of `references/dictionaries.md` and `references/terminology-corrections.md` when a term needs clarification. Do not load every reference or runtime dictionary. For CIO HTML, read `references/cio-report-format.md` and verify the external pipeline exists; otherwise deliver JSON or markdown. Do not invent a pipeline.

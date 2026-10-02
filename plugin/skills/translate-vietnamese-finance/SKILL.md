---
name: translate-vietnamese-finance
description: Translate supplied finance analysis to Vietnamese (vi-VN) with precise financial terminology and source-preserving numbers.
---

# Vietnamese finance translation

Translate existing financial content into formal written Vietnamese for Vietnam-based readers. Do not generate a new investment analysis.

**Locale:** `vi-VN`. **JSON translation field:** `vietnamese_translation`.

Use natural Vietnamese economic terms alongside English finance abbreviations. Keep ticker/RIC identifiers, financial ratios, named factor labels and technical risk identifiers in English. Gloss once per document when useful. Use danh mục, vốn chủ sở hữu, chỉ số tham chiếu and hệ số thanh toán nhanh consistently. Keep ECL distinct from Expected Shortfall (ES). P/FCF must retain dòng tiền tự do, not operating cash flow.

Preserve source numeric separators even when local publications use decimal commas. Keep source currencies; Vietnamese language does not imply VND. Keep Western issuer names in English. Use verified official Vietnamese names for domestic issuers; preserve the security identifier to distinguish companies with similar names.

Use concise formal prose, without literal English idioms. Preserve source uncertainty such as có thể, dự kiến and nhiều khả năng. Retail uses plain Vietnamese explanations and dual-label ratings. Ratings and scenario translations in the dictionary are product house style. ES and operating-leverage glosses remain provisional; keep the English identifier until native finance review. Supplied HTML can be translated with its structure preserved. Generating a new CIO HTML report requires an external pipeline; otherwise deliver JSON or markdown.

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

Use `references/language-style.md` only for the applicable rule or register. Consult the relevant rows of `references/dictionaries.md` and `references/terminology-corrections.md` when a term needs clarification. Do not load every reference or runtime dictionary. For generating CIO HTML, read `references/cio-report-format.md` and verify the external pipeline exists; otherwise deliver JSON or markdown. Do not invent a pipeline.

---
name: translate-arabic-finance
description: Translate supplied finance analysis to Saudi institutional Arabic (ar-SA), preserving financial meaning and RTL text. NOT for writing new analysis (run the analysis skill first, then translate its output), not for other target languages (use the matching translate-*-finance skill), not for general non-finance translation.
---

# Saudi Arabic finance translation

Translate existing finance content; do not generate a new investment analysis.

**Locale:** `ar-SA`. **JSON translation field:** `arabic_translation`.

Use Modern Standard Arabic with Saudi market conventions. This remains a draft pending native Saudi finance review; label output unreviewed until reviewed. Keep named factor and risk identifiers and scenario identifiers in English as product house style. For financial ratios and attested macro indicators, write the Arabic term Saudi research uses with the English identifier beside it (`مكرر الربحية (P/E)`; see `references/language-style.md` §2). Ratings render dual-label in every register; HOLD = محايد; never use a broker scale for a Parallax rating. Write the riyal as the number then ريال سعودي; benchmark is المؤشر الاسترشادي. Keep Western company names in Latin script; verify official Arabic names for Saudi issuers. Preserve source numerical notation (Western digits). Never reverse RTL text or numbers; the renderer owns bidi isolation. CMA, SAMA and the Insurance Authority are distinct. Retail remains MSA with first-use glosses. Dialect and other-market variants require a separate ruleset. Native review and RTL rendering remain required before production use.

## Open decisions

Native review must confirm terminology, rating labels, numeral conventions and 3–5 translated samples. RTL HTML requires testing in the actual target renderer. No review or pipeline is implied by a passing validator.

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

Use `references/language-style.md` only for the applicable rule or register. Consult the relevant rows of `references/dictionaries.md` and `references/terminology-corrections.md` when a term needs clarification. Do not load every reference or runtime dictionary. `references/sources.md` records the Saudi broker reports and CMA/SAMA documents behind the sourced rules; load it only when a term's basis is questioned. For CIO HTML, read `references/cio-report-format.md` and verify the external pipeline exists; otherwise deliver JSON or markdown. Do not invent a pipeline.

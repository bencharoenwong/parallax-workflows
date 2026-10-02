# Source and structure contract

Read this reference for JSON, HTML, placeholders or disclosure-bearing reports.

## JSON deliverables

Translate source string fields ending in `Text`. Use the same keys under `sections`.
Each section contains `original_key` and `vietnamese_translation`. Keep every non-text source field under `data` or its original top-level key. Keep tables, charts, booleans, nulls, arrays and numbers unchanged. Copy source metadata; map a top-level `market` to `metadata.market` and `date` to `metadata.report_date`.

```json
{
  "metadata": {"market": "<source market>", "report_date": "<source date>", "translation_locale": "vi-VN"},
  "sections": {"ReportText": {"original_key": "ReportText", "vietnamese_translation": "<translation>"}},
  "data": {"charts": []}
}
```

The illustrative `charts` field represents source data; include it only if present and copy its actual value.
For a source with a `sections` object, its string values are source prose. Preserve its non-string values under `data.sections` with their original keys.
The validator checks equal section coverage, protected numerical values and passthrough fields.
It does not establish semantic equivalence. Review each translated section against its source.

## Prose and markup

Use the same format as the source for plain text, markdown or HTML. Preserve paragraph breaks, URLs, tickers/RICs, placeholders such as `{VARIABLE}`, `{{variable}}`, `${value}` and `%s`, and footnote markers.
Keep HTML tags, order, classes, IDs, styles, links and source attributes. Translate visible text and accessibility text in `alt` or `title` only. Rendering or layout changes belong in a separate reviewed step.
Preserve complete `<!-- DO NOT TRANSLATE -->` through `<!-- END NO TRANSLATE -->` blocks verbatim.
Translate ordinary disclosure prose completely; preserve entity names and registration identifiers. Use locally approved disclosure templates when an actual report pipeline requires them.

## Numerical notation and entities

Copy every numerical token, sign, currency and magnitude unit exactly. Preserve source decimal/thousands separators and numeric dates. Keep `B`, `M`, `K`, `T`, `bps` and ratio suffixes. Do not convert currency or magnitudes during translation.
A listing market does not determine reporting currency. Multi-currency comparisons are valid when the source contains them.
Keep intentional HTML entities such as `&amp;` and `&lt;` unchanged. Escape only what the output format requires; avoid double encoding. Entity presence alone is not an error.

## Validation

```sh
python3 "<skill-dir>/references/validate-translation.py" "<output-file>" --source "<source-file>"
```

Files ending in `.json` must contain valid JSON with unique keys and finite numbers. Other suffixes are treated as plain prose under `ReportText`, including HTML. Use matching source/output section keys. A leading routing directive through its `---` separator is excluded from source prose checks; never echo that directive. For Chinese prose pass `--locale zh-CN`, `zh-TW` or `zh-HK`.
`--style-only` cannot validate source fidelity. Integrity/fatal failures cannot be waived. Reviewed style false positives require a specific message and justification.
Meaning, uncertainty, rating strength, unnumbered factual statements and sentence completeness require source-by-source review even after the script passes.

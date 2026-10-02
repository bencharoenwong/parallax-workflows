# Translation skills end-to-end receipt — 2026-10-02

> **Superseded in part by the follow-up commits on this branch (after `c6a7ce8`):** Vietnamese is held out of the plugin pending native review (so the plugin-copy claims below no longer apply to Vietnamese); Vietnamese prose now localizes number separators and magnitude words, and the shared validator accepts a separator-swapped number for `vi-VN` only; Arabic conventions were corrected against Saudi sources. The test and check counts below predate those changes.

Scope: Chinese (zh-CN, zh-TW, zh-HK), Thai, Vietnamese (vi-VN), and the Arabic (ar-SA) draft. Other skills were not audited or edited in this follow-up. This receipt records verification before the translation changes were committed; no push was performed.

## Results

- 161 regression/build tests passed: 86 language/shared-validator tests and 75 bundle/manifest tests.
- 74 CLI distribution checks passed: 50 valid-output checks accepted and 24 deliberately damaged outputs rejected; zero waivers.
- Independent forward translation covered six locale variants × institutional/retail registers, plus routed Hong Kong markdown and supplied Vietnamese HTML. Reviewers received fictional English sources and skill instructions; they produced the translations before validator repair.
- Repository, installed symlink, generated plugin, and isolated `.skill` copies were exercised for Chinese, Thai, and Vietnamese. Arabic was tested from its source skill only; it remains excluded from the general-release plugin and default package build.
- Standalone packages contain a byte-identical shared validator and work through isolated Python CLI invocation without a repository-relative validator dependency.
- Lint, reference resolution, specification validation (42/42 skills), and whitespace checks passed. Review builds used a temporary Git index and left the user's actual index unstaged during verification.

The fictional report includes rating strength, possibility rather than certainty, P/FCF and ROE, ECL versus ES, relative sector allocation, signed factor scores, scenario prices, several reporting currencies, a URL, an email, a placeholder, a footnote, disclosures, a literal no-translate block, charts, booleans and nulls. The HTML sample includes link attributes and translated image accessibility text. Negative controls independently change a reported percentage or drop a null data field.

## Defects found and corrected

1. A valid routed translation failed because its source routing header was counted as report paragraphs. The validator now removes only a leading recognized source routing block through its separator, rejects an unterminated block, and rejects a routing header echoed into translated prose.
2. Non-text values nested inside source `sections` could be omitted without detection. They must now survive under `data.sections`; all four structural references document that shape.
3. Duplicate JSON keys and non-finite values were accepted by the parser. They now fail closed, including overflowing floating-point literals.
4. Named factor/risk substitutions and several international RIC suffixes escaped the existing identifier checks. Added checks preserve recognized factor labels in score/factor contexts, English technical risk names for Thai/Arabic/Vietnamese, and broader RIC coverage. Ordinary capitalized prose remains translatable.
5. Thai's long-sentence reference contradicted its main instruction. Both now treat 130 characters as a review threshold and preserve content.
6. Vietnamese's pipeline fallback could be read as forbidding supplied HTML translation. Instructions now distinguish translating existing HTML from generating a new CIO HTML report.
7. Independent Chinese cross-review identified ambiguity in a short ES gloss. Chinese instructions and the runtime prompt now require `Expected Shortfall` alongside any first-use Chinese ES gloss.

These behaviors are covered by `skills/_parallax/test_translation_validation.py` and the language-specific tests. Generated plugin files were rebuilt from source, and standalone packages were rebuilt after the corrections.

## Quality and context

Independent semantic review found no material meaning changes in the synthetic samples: uncertainty, ratio denominators, credit versus tail risk, rating strength, allocation comparisons, and disclosures were retained. Reviewers cross-checked Chinese and Vietnamese outputs in addition to their initial forward tests.

The existing Chinese/Thai/Arabic instruction entry files total 12,557 bytes, down from 54,332 bytes before this audit (about 77% smaller). Vietnamese adds a 4,722-byte entry. Detailed dictionaries/style guidance remain selectively loaded references; validators run as code rather than entering model context. Reviewers did not need to load all references or runtime dictionary snapshots.

Passing these checks establishes source-token/structure preservation and reviewed synthetic behavior, not native linguistic certification. Arabic still requires native Saudi finance review and actual RTL rendering approval before production use. Vietnamese's provisional ES/operating-leverage glosses remain qualified and retain English identifiers. No live proprietary report, external CIO rendering pipeline, or production API was exercised.

# House View Regression Corpus

Frozen set of labeled house-view documents that every extraction-prompt change must re-pass before merge. Catches prompt-regression that eyeballing a single sample cannot.

## Why this exists

Phase 0 dogfooding found Q-A/Q-B/Q-C/Q-E bugs on a **single** live walkthrough. With 1 sample + 4 desk extractions we could not falsify whether a schema change, loader change, or prompt change actually improved extraction — changes might pass the one sample by luck and regress 3 others silently.

This corpus is the ground truth. All future changes to `load-house-view/SKILL.md` (extraction prompt), `_parallax/house-view/schema.yaml` (structural constraints), or `_parallax/house-view/loader.md` (consume semantics) must run against the corpus before merge.

## Format

Each entry in `corpus.yaml` pairs a source document with a **human-labeled expected extraction**. Fields use:

- **Single values** where the source is unambiguous (e.g., `effective_date: "2026-04-01"`).
- **Ranges `[min, max]`** where the source is hedged and multiple extractions are defensible (e.g., `information_technology: [0, 1]` when the source says "constructive but selective").
- **`null`** when the field should be absent (e.g., `macro_regime.growth: null` for mandate-driven ESG views that don't speak in macro-regime terms).
- **`excludes_contains:`** lists substrings that MUST appear in the extracted `excludes` list. Avoids false-positive mismatches on wording variations.
- **`excludes_must_not_contain:`** things the extractor should NOT invent (e.g., a reflationary view has no ESG excludes).

## How to run

Proposed usage (loader not yet implemented — deferred to Phase 0 iteration):

```
python3 skills/load-house-view/regression-corpus/run_regression.py \
  --corpus skills/load-house-view/regression-corpus/corpus.yaml \
  --out /tmp/regression-report.md
```

The runner loads each source file, invokes the current `/parallax-load-house-view` extraction logic, compares against the labeled expected extraction, and emits:
- **PASS / FAIL per entry** with field-level diff
- **Aggregate stats:** mean confidence, pass rate
- **Regression delta:** vs. prior run's saved baseline

## When to extend

Add new entries when:
- A real CIO PDF surfaces a view shape not in the corpus (prose + commitments, mandate-driven, geopolitical, thematic)
- A production bug report includes a specific extraction failure
- Schema changes add new fields — update all entries to label the new field

**Target size:** 15-20 entries before Phase 1 promotion. Current: 5 seeds from the `samples/` directory.

## Labeling discipline

- **Label what you would accept from a careful human extractor, not what you personally would extract.** The corpus is a contract, not a preference statement.
- **Prefer ranges over points for hedged language.** "Constructive on AI infra but selective on software" → `information_technology: [0, 1]` (either collapses to +1 with caveat, or splits IT down and theme up).
- **Confidence scores are labels too.** If a field's source is genuinely ambiguous, label `confidence_max: 0.75` — an extractor returning 0.95 on an ambiguous field is over-confident and should fail.

## Governance

- Corpus labels are owned by the Chief Investment Office persona. Disagreements about a label go to IC review, not a unilateral edit.
- Each entry logs `labeled_by` and `labeled_at`. Re-labeling an entry bumps `version:` and keeps a provenance note.
- Do not hand-tune labels to make a failing test pass. If the extractor disagrees with a label and the label is defensible, the extractor changes, not the label.

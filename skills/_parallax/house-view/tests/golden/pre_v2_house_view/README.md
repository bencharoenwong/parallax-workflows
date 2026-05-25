# Golden Baseline: pre_v2_house_view

This directory contains the golden baseline for the `load-house-view` output (Phase B compliance audit format).

## Generation
It was generated using the script `skills/_parallax/house-view/tests/golden/generate_golden.py`.

Command used:
```bash
python3 skills/_parallax/house-view/tests/golden/generate_golden.py
```

## Regeneration Policy
This is treated as IMMUTABLE. Only regenerate this baseline when an INTENTIONAL change to ingest output shape or hashing logic is being landed. Any regeneration MUST be accompanied by a DECISIONS.md entry referencing the change in the audit chain or view formats.

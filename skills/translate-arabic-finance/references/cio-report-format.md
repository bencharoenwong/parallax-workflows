# CIO Report Format Reference (Not Yet Wired)

**Status: no pipeline exists for Arabic.** The Thai and Chinese skills each have (or are punch-listed toward) a checkpoint-script HTML pipeline living in a separate CIO-report project directory outside this repo. Arabic has neither the scripts nor the RTL-capable HTML templates yet. Until this exists, deliver CIO-report translations as translated JSON/markdown (see the Input and output section of `SKILL.md`), not as pipeline HTML.

This is a bigger lift than the Thai/Chinese case: it is not only "port the checkpoint script," it requires genuine RTL front-end work that the other two skills never needed.

---

## What the Thai/Chinese pipeline does (for reference)

1. Clears old checkpoints
2. Runs Pass 1 → Verifies output → Creates checkpoint
3. Runs Pass 2 → Verifies output → Creates checkpoint
4. Runs Pass 3/4 → Verifies output → Creates checkpoint
5. Copies final to an `output/<language>/final/` directory

See the Thai skill's `references/cio-report-format.md` for the exact command shape (`translate_cio_checkpoint.py {REPORT_NUMBER} {SOURCE_FILENAME}`) and directory layout. An Arabic pipeline should mirror that shape once built.

## Additional work an Arabic CIO pipeline needs, beyond the mechanical port

1. **HTML template direction.** The base template needs `<html dir="rtl" lang="ar">` (or a per-section `dir="rtl"` wrapper) rather than the LTR templates Thai/Chinese use.
2. **Table mirroring.** CIO reports lean heavily on tables (tactical allocation, factor scores). Column order and cell alignment need to visually mirror for RTL — this is CSS/layout work, not a translation-content change.
3. **Font stack.** The existing template's font stack needs an Arabic-script-capable font (e.g., a Noto Naskh Arabic / IBM Plex Sans Arabic pairing) alongside the Latin font already used for embedded English/numbers.
4. **Bidi-safe embedding.** Every place the template injects a ticker, an English factor label, or a number into Arabic prose needs the isolation treatment described in `references/language-style.md` section 5, not a plain string substitution — a naive `{{VARIABLE}}` swap that worked for Thai/Chinese can visually scramble in RTL context if the surrounding markup doesn't isolate it.
5. **Disclosure template.** A Saudi-market disclosure/compliance footer needs sourcing from Compliance, in Arabic, the same way the Chinese pipeline's `INTEGRATION.md` flags that the Chinese disclosure is a separate document from the Thai one — do not translate the Thai/Chinese disclosure template into Arabic and assume it is legally equivalent.

## Recommended sequencing

Do not build the HTML pipeline before the terminology and RTL rules in `SKILL.md` have gone through native review (see `SKILL.md` "Open decisions"). Building the pipeline against draft, unreviewed terminology means re-testing the whole RTL rendering path a second time once the terminology changes. Sequence: (1) native review of SKILL.md rules and dictionaries against real samples, (2) JSON-output delivery only while that happens, (3) pipeline build once (1) is stable.

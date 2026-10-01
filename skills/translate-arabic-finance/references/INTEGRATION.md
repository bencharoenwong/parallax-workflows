# Integration Punch List

Status: skill scaffold ready (SKILL.md + references drafted). Nothing downstream is wired yet, and the drafted content is unreviewed — see `SKILL.md` "Open decisions." This document is the punch list, mirroring the equivalent Chinese-skill file.

---

## 1. Central routing (`skills/_parallax/parallax-conventions.md`)

- §15.1 "Supported values" needs `ar-SA` added.
- §15.2 routing table needs a row: `ar-SA → translate-arabic-finance`.
- The `en, zh-CN, zh-TW, zh-HK, th` "not supported" message needs `ar-SA` added to its list.

Status: done as part of this scaffold — see the diff to `parallax-conventions.md`. If this file is later regenerated or hand-reverted, re-check that `ar-SA` is still present.

## 2. Perimeter classification (`skills/PERIMETER.md`)

Needs a row for `translate-arabic-finance`, same `codex-safe` classification as the other two translators (pure translation utility, no proprietary methodology, no internal schema names). Status: done as part of this scaffold.

## 3. Language-coverage notes in the sibling skills

Both `translate-chinese-finance/SKILL.md` and `translate-thai-finance/SKILL.md` currently state "Arabic requests fall back to English" in their "Language coverage" line. That line is now stale and needs updating to point at this skill instead. Status: done as part of this scaffold.

## 4. Plugin bundle

`skills/_parallax/manifest.json` is the authority for what ships. `bootstrap_manifest.py` added this skill's row with `"plugin": false` (the designed safe default for a new skill — see that script's docstring). It stays `false` deliberately: shipping an unreviewed translator in the general-release plugin bundle would hand end users draft, unreviewed Arabic finance output without any signal that it needs native review first. Flip it to `true` in `manifest.json` only after the native review in item 5 below clears, then rerun `python3 skills/_parallax/scripts/build_bundle.py plugin` so the generated `plugin/` bundle picks it up. Do not hand-edit `plugin/`.

## 5. Native review (blocks production use)

Everything in `SKILL.md`, `dictionaries.md`, `terminology-corrections.md`, and the wrong-terms dictionary inside `validate-translation.py` needs review against real, native-corrected sample output before this skill is treated as production-ready. See `SKILL.md` "Open decisions" for the specific list of unconfirmed conventions (numeral style, currency placement, date convention, stock-rating terms, RTL rendering behavior).

Process: get 3–5 real Parallax report excerpts (stock, CIO, or macro report sections) translated and corrected by the native Saudi finance reviewer. Extract the corrections into `terminology-corrections.md` and the validator's wrong-terms dictionary the same way the Thai and Chinese tables were clearly built from real observed errors, not invented ones.

## 6. CIO HTML pipeline

Out of scope for this scaffold. See `references/cio-report-format.md` for the sequencing recommendation — native review of terminology and RTL rules should land before pipeline engineering starts, to avoid re-testing RTL rendering twice.

## 7. Dialect / other-market variants (future, not now)

If a future request needs a different Arabic market (Egypt, UAE) or a genuinely colloquial register, follow the Chinese skill's `target_variant` routing-block pattern rather than overloading this skill's `ar-SA` rules. Do not assume `ar-SA` conventions transfer unchanged to another market.

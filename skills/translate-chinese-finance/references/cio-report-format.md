# CIO Report Format Reference

CIO report-specific pipeline, footer standards, and table conventions for Chinese (Simplified or Traditional) output.

---

## CIO Report Translation Pipeline

**When translating a CIO report to Chinese HTML, use the checkpoint script.**

### Setup

The checkpoint script and supporting files live in the CIO report project directory. Locate them relative to the stock report project root:

```
<project_root>/CIO report/scripts/
```

### Command

```bash
cd "<project_root>/CIO report/scripts"
python3 translate_cio_checkpoint.py {REPORT_NUMBER} {SOURCE_FILENAME} --locale zh-CN
# or --locale zh-TW for Traditional
```

### Example

```bash
python3 translate_cio_checkpoint.py 11 CIO_report_chinese_set_benchmark.html --locale zh-CN
```

### What the checkpoint script does

1. Clears old checkpoints
2. Runs Pass 1 → Verifies output → Creates checkpoint
3. Runs Pass 2 → Verifies output → Creates checkpoint
4. Runs Pass 3/4 → Verifies output → Creates checkpoint
5. Copies final to `output/chinese/zh-CN/final/` (or `zh-TW/final/`)

### Key Files

- **Checkpoint script:** `scripts/translate_cio_checkpoint.py`
- **Disclosure templates:** `scripts/Disclosure_CIO_zh-CN.html`, `scripts/Disclosure_CIO_zh-TW.html` (MUST exist for Pass 4)
- **English input:** `output/english/{N}/`
- **Chinese output:** `output/chinese/zh-CN/final/` or `output/chinese/zh-TW/final/`
- **Checkpoints:** `scripts/checkpoints/` (created automatically)

### DO NOT use batch scripts (`run_batch_*.sh`) or run passes manually — use the checkpoint script.

---

## Footer Standardization

**Standard format (zh-CN):** `CIO月报 • 机密文件`
**Standard format (zh-TW):** `CIO月報 • 機密文件`

| Wrong/Inconsistent (zh-CN) | Correct (zh-CN) |
|----------------------------|----------------|
| 来自CIO的月度报告 | CIO月报 |
| 首席投资官月度报告 | CIO月报 |
| 投资官月报 | CIO月报 |
| 月度报告 (alone) | CIO月报 |
| 机密 (alone) | 机密文件 |
| Confidential | 机密文件 |
| 内部文件 | 机密文件 |

| Wrong/Inconsistent (zh-TW) | Correct (zh-TW) |
|----------------------------|----------------|
| 來自CIO的月度報告 | CIO月報 |
| 首席投資官月度報告 | CIO月報 |
| 月度報告 (alone) | CIO月報 |
| 機密 (alone) | 機密文件 |
| Confidential | 機密文件 |

---

## Table Header Conventions

**Performance Comparison Table — first column:**
- zh-CN: `指标` (Metric)
- zh-TW: `指標`
- Do NOT use: `基准指数 / 基準指數` (that means Benchmark)

**Benchmark vs Metric distinction:**
- Benchmark (the reference index) = `基准指数` / `基準指數`
- Metric (measurement/indicator) = `指标` / `指標`

**Benchmark difference column:**
- zh-CN: `相对基准` or `超额/落后`
- zh-TW: `相對基準` or `超額/落後`
- (NOT just `差额` / `差額`)

---

## Quality Issues Found in Document Review

These patterns commonly appear and must be cleaned before finalization:

1. **Truncated/Incomplete Text** — validate all text is complete before finalizing
2. **Doubled Characters** — `的的`, `了了`, `和和`, `在在` — remove duplicates
3. **Mixed Script** — Traditional characters in a Simplified document (or vice versa)
4. **Data Inconsistencies** — same metric showing different values in different places
5. **Magnitude Errors** — `B → 亿` substitution without ×10 multiplier
6. **Table Column Width** — Chinese text usually shorter than English; verify layout still reads cleanly
7. **Footer Inconsistencies** — ensure consistent format across ALL pages
8. **Currency Mismatch** — `人民币` for non-Chinese stocks, `港元` for non-HK stocks

### Pre-Finalization Checklist

- [ ] All "Max Drawdown" instances use the same form (English with first-use Chinese gloss)
- [ ] No doubled consecutive characters
- [ ] Spaces around all English terms
- [ ] Consistent terminology for contribution / allocation / volatility
- [ ] Footer consistent across pages
- [ ] No truncated text
- [ ] Data values match across all mentions
- [ ] Script is uniformly Simplified or Traditional
- [ ] Currency matches the listing market

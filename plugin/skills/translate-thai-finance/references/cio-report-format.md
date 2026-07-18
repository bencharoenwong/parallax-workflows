# CIO Report Format Reference

CIO report-specific pipeline, footer standards, and table conventions.

---

## CIO Report Translation Pipeline

**When translating a CIO report to Thai HTML, use the checkpoint script.**

### Setup

The checkpoint script and supporting files live in the CIO report project directory. Locate them relative to the stock report project root:

```
<project_root>/CIO report/scripts/
```

### Command

```bash
cd "<project_root>/CIO report/scripts"
python3 translate_cio_checkpoint.py {REPORT_NUMBER} {SOURCE_FILENAME}
```

### Example

```bash
python3 translate_cio_checkpoint.py 11 CIO_report_thai_set_benchmark.html
```

### What the checkpoint script does

1. Clears old checkpoints
2. Runs Pass 1 → Verifies output → Creates checkpoint
3. Runs Pass 2 → Verifies output → Creates checkpoint
4. Runs Pass 3/4 → Verifies output → Creates checkpoint
5. Copies final to `output/thai/final/`

### Key Files

- **Checkpoint script:** `scripts/translate_cio_checkpoint.py`
- **Disclosure template:** `scripts/Disclosure_CIO_Thai.html` (MUST exist for Pass 4)
- **English input:** `output/english/{N}/`
- **Thai output:** `output/thai/final/`
- **Checkpoints:** `scripts/checkpoints/` (created automatically)

### DO NOT use batch scripts (`run_batch_*.sh`) or run passes manually — use the checkpoint script.

---

## Footer Standardization

**Standard format:** `รายงานประจำเดือน CIO • เอกสารลับ`

Remove possessive "ของ" before English proper nouns for more natural Thai.

| Wrong/Inconsistent | Correct |
|--------------------|---------|
| รายงานประจำเดือนของ CIO | รายงานประจำเดือน CIO |
| ข้อมูลลับ | เอกสารลับ |
| เอกสารลับเฉพาะ | เอกสารลับ |
| Confidential | เอกสารลับ |
| รายงานประจำเดือนจาก CIO | รายงานประจำเดือน CIO |
| รายงานประจำเดือนจากประธานเจ้าหน้าที่ฝ่ายการลงทุน (CIO) | รายงานประจำเดือน CIO |
| รายงานประจำเดือนของหัวหน้าเจ้าหน้าที่ฝ่ายการลงทุน | รายงานประจำเดือน CIO |
| รายงานรายเดือนของหัวหน้าฝ่ายการลงทุน | รายงานประจำเดือน CIO |
| รายงานประจำเดือนของประธานเจ้าหน้าที่ฝ่ายการลงทุน | รายงานประจำเดือน CIO |

---

## Table Header Conventions

**Performance Comparison Table — first column:**
- Use: **ตัวชี้วัด** (Metric)
- Do NOT use: ดัชนีอ้างอิง (that means Benchmark)

**Benchmark vs Metric distinction:**
- Benchmark (the reference index) = ดัชนีอ้างอิง
- Metric (measurement/indicator) = ตัวชี้วัด

**Benchmark difference column:**
- Use: เทียบดัชนีอ้างอิง or ส่วนเกิน/ส่วนขาด (NOT just ส่วนต่าง)

---

## Quality Issues Found in Document Review

These patterns were identified by comprehensive CIO report review:

1. **Truncated/Incomplete Text** — validate all text is complete before finalizing
2. **Doubled Words** — "สูงสุด สูงสุด", "ของ ของ", "และ และ" — remove duplicates
3. **Data Inconsistencies** — same metric showing different values in different places
4. **Table Column Width** — Thai text often longer than English; ensure adequate widths
5. **Footer Inconsistencies** — ensure consistent format across ALL pages

### Pre-Finalization Checklist

- [ ] All "Max Drawdown" uses same translation
- [ ] No doubled consecutive words
- [ ] Spaces around all English terms
- [ ] Consistent terminology for contribution/allocation/volatility
- [ ] Footer consistent across pages
- [ ] No truncated text
- [ ] Data values match across all mentions

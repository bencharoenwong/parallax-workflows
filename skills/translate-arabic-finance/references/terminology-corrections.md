# Terminology Corrections Reference (Seed — Pending Native Review)

Draft find→replace table for Arabic financial translation. Unlike the Thai and Chinese equivalents of this file, this table was NOT built from reviewed corrections of real translated output — no such corpus exists yet for Arabic. It is a placeholder scaffold populated with general MSA finance conventions.

**Do not treat this table as validated.** Populate it with real corrections once a native Saudi finance reviewer has checked sample output — see `SKILL.md` "Open decisions," item 7.

---

## Code-Switching Terms (Draft: Arabic phrase to avoid → Correct English)

English risk identifiers are product house style, not evidence that standard Arabic finance terminology is incorrect. Saudi CMA itself uses نسبة شارب. Use an Arabic gloss when the selected register calls for it; literal phrases that change the concept still require correction.

| English-identifier house style: Arabic gloss | Correct English |
|--------------------------|-----------------|
| خطأ التتبع | Tracking Error |
| مؤشر المخاطرة أو القيمة المعرضة للخطر | VaR |
| العائد الاستثنائي (ألفا) | Alpha |
| بيتا السهم | Beta |
| نسبة شارب alone (English identifier dropped) | Sharpe Ratio (نسبة شارب) — the Arabic term is attested (Argaam, Derayah); keep the English identifier beside it |
| الحصة النشطة | Active Share |
| نسبة الإصابة | Hit Ratio |
| الحد الأقصى للتراجع | Max Drawdown |
| المحفظة الاستثمارية (as a repeated long form) | المحفظة (short form, once introduced) |

## Structural Consistency (not corrections — pick-one-form reminders)

- Use القطاع consistently for "sector"; do not alternate with الصناعة within one document.
- Use المؤشر الاسترشادي for "benchmark" (CMA fund filings); never المؤشر المرجعي, and do not alternate with معيار الأداء.
- Use المحفظة for "portfolio" after first introducing المحفظة الاستثمارية once, if at all.

## Common Spelling-Class Errors to Watch For (categories, not confirmed instances)

No confirmed real-world instances exist yet for this language. Once native-reviewed samples arrive, populate this section the way the Thai file lists specific doubled-word artifacts (e.g., a misspelled proper noun caught in real output). Known failure categories to check against real samples:

- Hamza seat errors: أ vs إ vs ء vs ؤ vs ئ vs آ used inconsistently for the same word across a document.
- Ta marbuta / ha confusion at word end (ة vs ه).
- Alef maksura / ya confusion at word end (ى vs ي).
- Doubled consecutive words (same class of error as Thai/Chinese; no Arabic-specific example on file yet).

## HTML Entity Corruption (generic, ports directly)

Also fix: doubled consecutive words, HTML entity corruption (`&lt;` `&gt;` `&amp;` `&quot;`), extra spaces in mid-sentence — same generic classes the Thai/Chinese validators catch.

# Sources and Provenance (ar-SA source check, 2026-10-02)

The original seed was drafted from general MSA usage. This check compared it against real Saudi broker research and CMA/SAMA publications. Rules marked **(sourced)** in `SKILL.md` trace here. This record is not a substitute for native review.

## Documents read in full (extracted text)

| Id | Publisher | Document | Date | URL |
|---|---|---|---|---|
| S1 | Al Jazira Capital | Al Rajhi Bank investment update | 10/2024 | https://www.aljaziracapital.com.sa/media/jipa5bmo/al-rajhi-investment-update-ar-oct.pdf |
| S2 | Al Jazira Capital | Al Rajhi Bank Q3-2025 flash note (with ratings-definitions box) | 10/2025 | https://www.aljaziracapital.com.sa/media/zswlppvo/alrajhi-flash-note-q3-25-ar.pdf |
| S3 | Al Rajhi Capital | Daily market report | 10/10/2024 | https://www.alrajhi-capital.com/-/media/Feature/AlRajhiCapital/ResearchListing/Daily-Reports/2024/Oct/DMR-Arabic-10-October-2024.pdf |
| S4 | CMA | Saudi equity fund terms and conditions | — | https://cma.gov.sa/Market/imf/Documents/0576-1-01-011.pdf |
| S5 | CMA | Investment terminology guide (Booklet 10) | — | https://cma.gov.sa/Awareness/Publications/booklets/Booklet_10.pdf |
| S6 | CMA | Glossary of defined terms in CMA regulations | — | https://cma.gov.sa/RulesRegulations/Regulations/Documents/GlossaryOfDefinedTermsUsedintheRegulationsandRulesoftheCapitalMarketAuthorityAR.pdf |
| S9 | Argaam | Sharpe ratio explainer | — | https://www.argaam.com/ar/article/articledetail/id/1896612 |
| S10 | Derayah | Glossary entry "معدل شارب" | — | https://www.derayah.com/AR/Secure/learningportal/sharperatio.html |
| S11 | Saudi Tadawul Group | About us | — | https://tadawulgroup.sa/wps/portal/tadawulgroup/aboutus?locale=ar |
| S12 | SAMA | About SAMA | — | https://www.sama.gov.sa/ar-sa/about/pages/default.aspx |
| S13 | SAMA | Statistical report country grouping | — | https://www.sama.gov.sa/ar-sa/Publications/EconomicReports/Pages/report.aspx?cid=122 |

Weaker sources (read through a search summary, not fetched): Argaam on SNB Capital ratings (https://www.argaam.com/ar/article/articledetail/id/590556), a maaal.com Riyad Capital headline, and a CMA dual-dated announcement (https://cma.gov.sa/MediaCenter/NEWS/Pages/CMA_N_3105.aspx).

## Verdict counts on the drafted rows

14 confirmed, 13 contradicted, about 45 unsourced. Corrections applied in this change:

| Area | Draft | Finding | Source |
|---|---|---|---|
| Ratings | 5-tier شراء قوي … بيع قوي; HOLD = احتفاظ | No shared scale. Al Jazira: زيادة المراكز / محايد / تخفيض المراكز (relative to target price). Al Rajhi: وزن زائد / محايد / وزن ناقص. No "قوي" tier; no احتفاظ; محايد is universal | S2 p.2; S3 p.2 |
| Ratios | All English | Arabic in broker tables: مكرر الربحية, مكرر القيمة الدفترية, العائد على حقوق المساهمين, العائد على الأصول, ربح السهم, منذ بداية العام حتى تاريخه. EBITDA stays English | S1 p.1; S2 p.1; S3 p.2 |
| Macro indicators | All English | Arabic in the calendar: مؤشر أسعار المستهلك, مطالبات البطالة الأولية, مؤشر الدولار الأمريكي, etc. | S3 p.1 |
| Currency | `SAR 41.22` | Number then ريال سعودي in prose; currency in the table header | S1 p.1; S4 |
| Numerals | Draft Western | Confirmed Western, comma thousands, period decimal | S1–S4 |
| Benchmark | المؤشر المرجعي | المؤشر الاسترشادي in CMA fund filings | S4 |
| Sharpe Ratio | Treated as a wrong term | Argaam and Derayah use نسبة شارب / معدل شارب; written as Sharpe Ratio (نسبة شارب), which the validator accepts | S9; S10 |
| Overweight/Underweight | Keep English | وزن زائد / وزن ناقص | S3 p.2 |
| Tadawul | تداول (السوق المالية السعودية) | تداول السعودية under مجموعة تداول السعودية (post-2021); already corrected in the base change | S11; S3 p.2 |
| Dates | Gregorian unless source has Hijri | Broker research Gregorian-only; regulatory circulars Hijri first, then الموافق, then Gregorian | S1–S3; CMA announcement (weaker) |
| Scenario labels | SKILL.md English, dictionary Arabic | No source either way. Resolved: English identifiers, Arabic forms as optional glosses | — |

## Not adopted

- **Percent sign before digits.** Extracted text showed "%27.3", but PDF extraction often reorders right-to-left runs, and S3 also reads "0.83%". Left as an open decision pending a rendered-page check.

## Still unsourced

Portfolio-analytics terms (Tracking Error, Expected Shortfall, VaR, Active Share, Hit Ratio, Max Drawdown, attribution terms), most country names and months, "Contribution" (المساهمة), section headers other than those seen in S1–S3. These stay draft.

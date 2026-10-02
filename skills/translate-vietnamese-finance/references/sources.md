# Sources and Provenance (vi-VN seed)

Research pass of 2026-10-02: web search plus direct reading of public Vietnamese broker reports. Every rule in `SKILL.md` that is marked "sourced" traces to an entry here. Anything not listed here is a draft default or an open decision. This file records what was found; it is not a substitute for native review.

## Reports read directly (PDF)

| Publisher | Subject | Type | Date | URL | Read |
|---|---|---|---|---|---|
| SSI Research | TCB (bank) | Company note | 04/06/2025 | https://ftp2.ssi.com.vn/Customers/GDDT/Analyst_Report/Company_Note/TCB_2025.06.04_SSIResearch.pdf | All 10 pages, text layer |
| SSI Research | VCB (bank) | Company note | 27/05/2024 | https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/PhanTichBaoCao/VCB_31524_SSI31052024165900.pdf | Page 1, image |
| Vietcap | PC1 (power construction) | Update | 02/02/2026 | http://static1.vietstock.vn/edocs/18915/PC1_20260202_MUA.pdf | Pages 1–3, text layer |
| ACBS | KDH (real estate) | Update | 08/05/2026 | http://static1.vietstock.vn/edocs/20173/KDH_Cap_nhat_8.pdf | Pages 1–2, image |
| VNDirect | NLG (real estate) | Update | 01/12/2025 | http://static1.vietstock.vn/edocs/Files/2025/12/04/nlg-khuyen-nghi-kha-quan-voi-gia-muc-tieu-42-200-dong-co-phieu_20251204101924.pdf | Pages 1–2, image |
| Vietcap | Strategy 2026 (macro) | Strategy deck | 12/2025 | http://static1.vietstock.vn/edocs/18418/VIETCAP_STRATEGY_2026.pdf | Pages 1–10 of 394 |

Quotes from image-only pages carry higher transcription risk than those from text layers.

## Findings consistent across all six reports

- Thousands separator `.`, decimal separator `,` (e.g. `36.400`, `+15,2%`). Matches the accounting-law rule: https://thuvienphapluat.vn/chinh-sach-phap-luat-moi/vn/ho-tro-phap-luat/tu-van-phap-luat/41571/quy-dinh-chu-viet-chu-so-su-dung-trong-ke-toan
- No space before `%`.
- Dates dd/mm/yyyy.
- Analyst voice is first-person plural "Chúng tôi"; the reader is never addressed as "bạn" or "anh/chị". Hedges: "Chúng tôi cho rằng", "Chúng tôi kỳ vọng", "Chúng tôi ước tính".
- Acronyms stay in English: P/E, P/B, EV/EBITDA, ROE, ROA, ROIC, NIM, CASA, EPS, BVPS, CIR, NPL, LDR, CAGR, IPO.
- Profit lines use Vietnamese abbreviations, never English ones: LNTT (pre-tax), LNST (after-tax); revenue "doanh thu (thuần)" or "DT".
- In prose, YoY is "svck" (so với cùng kỳ) and QoQ is "so với quý trước"; table headers often keep `% YoY` / `% QoQ`.
- In prose, basis points are "điểm cơ bản".
- Large VND sums: "tỷ đồng" (10⁹), "nghìn tỷ đồng" (10¹²); "triệu đồng" for line items. English "billion/trillion" never appears.
- The rating word is capitalized and printed with target price and upside % in a header block before the narrative.

## Findings where publishers disagree (left as open decisions)

- Currency placement: SSI `36.400 đồng`; Vietcap `30.500 VND`; ACBS `Giá mục tiêu (VND): 34.100`; VNDirect `VND42.200`.
- Quarter notation: `Q1/2025` (SSI prose, ACBS); `1Q24` (SSI tables); `Q3/25` and `9T25` (VNDirect tables).

## Ratings

Broker five-tier scale (SSI legend, TCB note p.10): Mua / Khả quan / Trung lập / Kém khả quan / Bán. SSI defines Mua as expected upside at least 10 percentage points above the market over 12 months — a relative scale. Chart legend keys: `BUY: Mua, OP: Khả quan, MP: Trung lập, UP: Kém khả quan`. Other usage: "Khuyến nghị MUA với giá mục tiêu" (https://cafef.vn/du-lieu/report/tcb-khuyen-nghi-mua-voi-gia-muc-tieu-42800-dongco-phieu-6a361baa6c2160b7b428239e.chn); VNDirect "Trung lập" (https://vnbusiness.vn/vndirect-ha-khuyen-nghi-stb-xuong-trung-lap.html). "Mua mạnh" / "Strong Buy" was found only on an aggregator, not in a broker's own scale (https://vn.investing.com/equities/joint-stock-commercial-bank-consensus-estimates).

## Terminology (high confidence unless noted)

| English | Vietnamese | Source |
|---|---|---|
| Target price | Giá mục tiêu | SSI, VNDirect, ACBS reports above |
| Upside | Tiềm năng tăng giá / Tỷ lệ tăng giá | VNDirect NLG; ACBS KDH |
| Market cap | Vốn hóa thị trường | https://vnexpress.net/von-hoa-thi-truong-la-gi-4503939.html |
| Free float | Tỷ lệ free-float | https://vietnambiz.vn/ti-le-free-float-la-gi-cong-thuc-xac-dinh-ti-le-free-float-20191119120513748.htm |
| Foreign ownership limit | Room ngoại | https://vnexpress.net/cong-ty-dai-chung-khong-duoc-tu-quyet-room-ngoai-4938310.html |
| Credit quota | Room tín dụng | https://div.gov.vn/nhnn-dong-y-cho-cac-ngan-hang-du-tieu-chi-noi-room-tang-truong-tin-dung |
| Gross margin | Biên lợi nhuận gộp | SSI strategy 2025 PDF |
| Net profit after tax | Lợi nhuận sau thuế (LNST) | Circular 200/2014/TT-BTC, account 421 |
| Owners' equity | Vốn chủ sở hữu | Circular 200 balance-sheet captions |
| Cash flow from operations | Lưu chuyển tiền thuần từ hoạt động kinh doanh | Circular 200 cash-flow captions |
| NPL ratio | Tỷ lệ nợ xấu | https://vneconomy.vn/ssi-research-ty-le-no-xau-nganh-ngan-hang-tang-trong-quy-22026-bao-phu-no-xau-giam.htm |
| NPL coverage | Tỷ lệ bao phủ nợ xấu | same |
| Credit growth | Tăng trưởng tín dụng | https://kinhtechungkhoan.vn/vndirect-tang-truong-loi-nhuan-cua-cac-ngan-hang-se-cham-lai-trong-nhung-quy-toi-1051887.html |
| Deposit / lending rate | Lãi suất huy động / Lãi suất cho vay | https://baochinhphu.vn/thuc-hien-chinh-sach-tien-te-noi-long-hon-co-trong-tam-trong-diem-tiep-tuc-giam-lai-suat-cho-vay-cho-doanh-nghiep-102230715123623359.htm |
| CAR | Hệ số an toàn vốn (CAR) | Circular 41/2016/TT-NHNN via https://div.gov.vn/giam-he-so-car-8-hoan-thien-khuon-kho-phap-ly-de-thuc-hien-basel-ii |
| Monetary policy; tightening; easing | Chính sách tiền tệ; thắt chặt; nới lỏng | baochinhphu.vn above; tapchinganhang.gov.vn |
| CPI | CPI / Chỉ số giá tiêu dùng | https://www.gso.gov.vn/cpi-vi/ |
| USD/VND central rate | Tỷ giá trung tâm USD/VND | https://doanhnghiephoinhap.vn/ty-gia-usd-hom-nay-210-2026-dong-usd-tang-manh-150466.html |
| Public investment | Đầu tư công | Vietcap Strategy 2026 |
| Foreign net buying/selling | Khối ngoại mua ròng / bán ròng | https://vneconomy.vn/thanh-khoan-bung-no-vn-index-len-dinh-lich-su-moi-khoi-ngoai-ban-rong-hon-410-ty.htm |
| Liquidity | Thanh khoản | same |
| Margin lending | Giao dịch ký quỹ (margin) | Quyết định 87/QĐ-UBCK via thoibaotaichinhvietnam.vn |
| Market upgrade | Nâng hạng thị trường | https://theleader.vn/ty-le-free-float-va-nang-hang-chung-khoan-viet-nam-d45666.html |
| Overweight / Underweight | Tăng tỷ trọng / Giảm tỷ trọng | https://vietnambiz.vn/tang-ti-trong-overweight-la-gi-su-dung-tang-ti-trong-trong-xep-hang-va-khuyen-nghi-dau-tu-20200420192725676.htm |
| Portfolio; rebalancing | Danh mục; tái cân bằng danh mục | https://hdcap.vn/kien-thuc/giu-vung-huong-di-tai-chinh-tai-can-bang-danh-muc-dau-tu-de-phat-trien-ben-vung/ |
| Momentum | Momentum (often kept) / động lượng | https://www.dnse.com.vn/hoc/dau-tu-theo-momentum-la-gi |

## Documented risks

- billion/trillion: tỷ = 10⁹, nghìn tỷ = 10¹²; long- vs short-scale confusion is named in https://vi.wikipedia.org/wiki/Quy_m%C3%B4_d%C3%A0i_v%C3%A0_ng%E1%BA%AFn
- Separator inversion is named as a financial-translation error in https://dichthuatsaigon.vn/bao-cao-tai-chinh/ (a translation agency page; medium confidence).
- "nghìn" (standard, northern) and "ngàn" (southern) both mean thousand; both appear in finance press (vneconomy uses "ngàn").
- "room" is a fixed loanword; "phòng" is wrong.
- Market upgrade: FTSE Russell confirmed Vietnam's upgrade to Secondary Emerging (announced 07/10/2025, effective 2026); MSCI has not upgraded Vietnam. Do not conflate (https://www.bloomberg.com/news/articles/2025-10-07/ftse-to-upgrade-vietnam-to-emerging-market-status-from-frontier).

## Gaps (not sourced; do not treat as settled)

- A broker term for "downside" as a rating-box noun (prose uses "rủi ro giảm giá").
- The exact caption for "net profit attributable to parent" (working form: "LNST của cổ đông công ty mẹ").
- Single-source confirmation for M2 ("cung tiền M2"), FX reserves ("dự trữ ngoại hối"), PMI, trade balance ("cán cân thương mại").
- Factor-investing terms in Vietnamese: volatility ("độ biến động"), drawdown, quality, defensive, factor score. Only English-language sources were found; the skill keeps these in English.
- Disclaimer boilerplate beyond SSI.
- Validator limit: a number with one comma group (`1,234`) reads as English thousands or a Vietnamese decimal; the source check accepts it either way, so prose needs human review.

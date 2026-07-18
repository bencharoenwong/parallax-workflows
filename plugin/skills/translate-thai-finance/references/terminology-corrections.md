# Terminology Corrections Reference

Full find→replace tables for Thai financial translation. These are POST-TRANSLATION fixes — the LLM may produce wrong translations and this table corrects them.

---

## Code-Switching Terms (Wrong Thai → Correct English)

Thai finance professionals use these English terms directly. Any Thai translation sounds machine-generated.

| Wrong Thai Translation | Correct English |
|------------------------|-----------------|
| ค่าความคลาดเคลื่อนในการติดตาม | Tracking Error |
| ความคลาดเคลื่อนในการติดตาม | Tracking Error |
| ค่าความคลาดเคลื่อนจากดัชนีอ้างอิง | Tracking Error |
| ค่าเบี่ยงเบนการติดตาม | Tracking Error |
| เบี่ยงเบนการติดตาม | Tracking Error |
| จำนวนการถือครองที่มีประสิทธิภาพ | Effective Number of Holdings |
| อัตราส่วนสารสนเทศ | Information Ratio |
| อัตราส่วนชาร์ป | Sharpe Ratio |
| ส่วนแบ่งเชิงรุก | Active Share |
| อัตราถูกต้อง | Hit Ratio |
| อัลฟา / อัลฟ่า / ค่าอัลฟา / ค่าอัลฟ่า | Alpha |
| เบต้า / เบตา | Beta |
| แกมมา | Gamma |
| เดลต้า | Delta |
| ธีต้า / ทีต้า | Theta |
| เวก้า | Vega |
| โร | Rho |
| เอปไซลอน | Epsilon |
| มูลค่าความเสี่ยง | VaR |
| ค่าความเสียหายที่คาดหวัง | Expected Shortfall |
| การขาดทุนที่คาดหวัง | Expected Shortfall |
| ความเสี่ยง tail / ความเสี่ยงหาง / ความเสี่ยงด้านหาง | Tail Risk |
| เหตุการณ์หาง / เหตุการณ์ tail | เหตุการณ์หางยาว |
| การขาดทุนหาง / ขาดทุนหาง | tail loss |
| น้ำหนักมาก | Overweight |
| น้ำหนักน้อย | Underweight |
| หมุนเวียนสลับหมวดหมู่ / หมุนเวียนสายอุตสาหกรรม / การหมุนเวียนกลุ่มอุตสาหกรรม | Sector Rotation |
| พอร์ตโฟลิโอ | พอร์ต |
| สายอุตสาหกรรม / ภาคธุรกิจ / กลุ่มอุตสาหกรรม / หมวดหมู่ | Sector |
| เหตุการณ์ปลายทาง | Tail events / ความเสี่ยงเหตุการณ์สุดขั้ว |
| การสูญเสียปลายทาง | Tail loss |
| มุมมองการคาดการณ์ล่วงหน้า | Forward-looking view |
| การระบุแหล่งที่มาของผลดำเนินงาน | Performance Attribution |
| แหล่งที่มาของผลตอบแทน / ที่มาของผลตอบแทน | Return Attribution |
| การวิเคราะห์การมีContributionต่อผลการดำเนินงาน | Performance Attribution |
| การมีContribution | Contribution |
| ความเสี่ยงด้านสภาพคล่อง (when meaning ES) | Expected Shortfall (ES) |

---

## ECL vs Expected Shortfall — FACTUAL ERROR TABLE

| Wrong (ECL terms in portfolio context) | Correct |
|----------------------------------------|---------|
| Expected Credit Losses | Expected Shortfall |
| Expected Credit Loss | Expected Shortfall |
| ผลขาดทุนด้านเครดิตที่คาดว่าจะเกิดขึ้น | Expected Shortfall |
| ผลขาดทุนด้านเครดิตที่คาดการณ์ | Expected Shortfall |
| การขาดทุนด้านเครดิตที่คาดหวัง | Expected Shortfall |
| การสูญเสียเครดิตที่คาดว่าจะเกิดขึ้น | Expected Shortfall |
| ขาดทุนด้านเครดิตที่คาดว่า | Expected Shortfall |

---

## CIO Report Term Corrections

| Wrong | Correct | Notes |
|-------|---------|-------|
| การ Max Drawdown | Maximum Drawdown | Don't prefix English with การ |
| การสูญเสียสูงสุด | Maximum Drawdown | Sounds like P&L loss, not drawdown |
| การดรอดาวน์สูงสุด | Maximum Drawdown | Wrong transliteration |
| การขาดทุนสูงสุด | Maximum Drawdown | Means "maximum loss" (P&L) |
| การลดลงสูงสุด | Maximum Drawdown | Wrong translation |
| การร่วงลงสูงสุด | Maximum Drawdown | Wrong translation |
| เมตริก | ตัวชี้วัด | As table column header |
| เกณฑ์อ้างอิง | ดัชนีอ้างอิง | Standard term for benchmark |
| สินค้าจำเป็นที่จำเป็น | สินค้าจำเป็น | Remove duplicate |
| งบการเงิน | การเงิน | As Financials sector label |
| ดัชนีชี้วัด | ดัชนีอ้างอิง | In Tracking Error footnote context |
| ความประหลาดใจทางเศรษฐกิจ | Economic Surprise Index | Keep in English |
| การเคลมว่างงาน | Initial Jobless Claims | Keep in English |
| การแออัดของปัจจัย | การกระจุกตัวในปัจจัย | Factor concentration |
| สรุปสำหรับผู้บริหารใน 1 นาที | สรุปผู้บริหาร (1 นาที) | Cleaner format |
| พันธบัตร์ | พันธบัตร | Wrong spelling (no ์) |
| ไทหวัน | ไต้หวัน | Wrong spelling |

---

## Risk Metrics

| Term | Correct Usage |
|------|--------------|
| Active Risk | ความเสี่ยงเชิงรุก (NOT ความเสี่ยงที่กระตือรือร้น) |
| Active Management | การบริหารเชิงรุก |
| Active Return | ผลตอบแทนเชิงรุก |
| Passive Investment | การลงทุนเชิงรับ (NOT การลงทุนเฉื่อย) |
| Tail Risk | ความเสี่ยงเหตุการณ์สุดขั้ว (NOT ความเสี่ยงปลายทาง) |

---

## Financial Terms

| English | Correct Thai | Wrong Forms |
|---------|-------------|-------------|
| Recurring revenue | รายได้ประจำ | NOT รายได้ที่เกิดขึ้นซ้ำ |
| Operating leverage | operating leverage or การประหยัดต่อขนาด | NOT โครงสร้างต้นทุนทางการดำเนินงาน |
| High-growth segments | ภาคธุรกิจที่มีการเติบโตสูง | NOT ส่วนแบ่งการเติบโตสูง |
| Resilience | ความยืดหยุ่น | NOT ความทนทาน (market context) |
| Margin expansion | การขยายตัวของอัตรากำไร | NOT การขยายกำไรส่วนเพิ่มขึ้น |
| Sector headwinds | แรงกดดันจากภาคส่วน | NOT ลมต้านของภาคส่วน |
| Concentration | การกระจุกตัว | NOT การแออัด |
| Diversification | การกระจายความเสี่ยง | |
| Interest rate trajectory | ทิศทางอัตราดอกเบี้ย | NOT วิถีอัตราดอกเบี้ย |
| Limited upside | อัปไซด์มีจำกัด | NOT โอกาสเพิ่มขึ้นจำกัด |
| Gap (valuation) | ส่วนต่าง or ความแตกต่าง | NOT ช่องว่าง |
| Premium (pricing) | พรีเมียม or ส่วนเพิ่มราคา | NOT มูลค่าพิเศษ |
| Fundamental misunderstanding | ตลาดยังมองข้าม or ประเมินต่ำกว่าความเป็นจริง | NOT ความเข้าใจผิดพื้นฐาน |
| Momentum slowdown | โมเมนตัมที่ชะลอลง or แรงส่งที่ลดลง | NOT ภาวะโมเมนตัมชะลอตัว |

---

## Technical Analysis Terms

| English | Correct Thai |
|---------|-------------|
| Support | แนวรับ (NOT ระดับรับ) |
| Resistance | แนวต้าน (NOT ระดับต้าน) |
| Break through resistance | ทะลุแนวต้าน or เบรกแนวต้าน (NOT ถูกทำลาย) |
| Stop loss | stop loss or จุดตัดขาดทุน |
| Overbought | overbought or ซื้อมากเกินไป (NOT ภาวะซื้อ) |
| Oversold | oversold or ขายมากเกินไป (NOT ภาวะขาย) |
| Bullish signal | สัญญาณบวก or สัญญาณขาขึ้น |
| Bearish signal | สัญญาณลบ or สัญญาณขาลง |
| Bullish crossover | ตัดขึ้น or MACD ตัดเส้นสัญญาณขึ้น |

---

## Footnote Conciseness (Institutional Audience)

Thai CIOs know CAPM. Don't over-explain:

- **Alpha footnote:** "Alpha: ผลตอบแทนส่วนเกินที่ปรับด้วยความเสี่ยง วัดความสามารถในการสร้างผลตอบแทนเหนือตลาด" (no CAPM formula needed)
- **Beta footnote:** "Beta: ความเสี่ยงตลาดเชิงระบบ วัดความผันผวนเทียบกับตลาด" (no formula needed)

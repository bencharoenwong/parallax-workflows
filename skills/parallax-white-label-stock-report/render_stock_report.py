#!/usr/bin/env python3
"""Standalone white-label renderer for Parallax get_stock_report output.

Turns a get_stock_report MCP response (JSON) plus a client brand config into a
branded, white-labeled HTML stock report, and optionally a PDF.

Standalone by design: no imports of any sibling/shared module. Runtime deps are
the Python stdlib + pyyaml (for the brand config). Optional: headless Chrome for
PDF. Everything else (brand-token map, fixed semantic colors, the verbatim CGC
disclosure boilerplate, and the HTML/CSS template) is inlined below.

Usage:
    python3 render_stock_report.py <report.json> [--branding <config.yaml>]
            [--out <out.html>] [--pdf] [--client-name <name>]

- <report.json> is the full get_stock_report response ({success,symbol,report,...})
  or a bare report object; both are accepted.
- --branding defaults to ~/.parallax/client-branding/config.yaml. If it is
  missing or invalid the report still renders with the default Parallax palette.
- --pdf renders <out>.pdf via headless Chrome if Chrome is installed.

Compliance posture. Two independent choices:
- Disclosures: co-brand keeps the CGC / MAS regulatory disclosures verbatim
  (default); full white-label (full_white_label) replaces them with the client's
  own jurisdiction disclosures (voice.disclaimers[]) and refuses if none are set.
- Chicago Global credit: a "Powered by Chicago Global" line in the cover header.
  Shown by default; hidden in full white-label unless the client opts to keep it
  (powered_by_optin), pairing their own disclosures with the credit.
Brand identity (logo, palette, fonts, client name) is always the client's.
Semantic colors (positive / negative / warning) are NEVER branded.
"""
import argparse
import base64
import html as _html
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

# --------------------------------------------------------------------------- #
# Fixed semantic colors. These signal meaning, not brand identity, and are
# never overridden by client branding.
# --------------------------------------------------------------------------- #
SEMANTIC = {"pos": "#1a7f4b", "neg": "#b3261e", "warn": "#b8860b"}

DEFAULT_BRANDING = {
    "client_name": "",
    "active": False,
    "source": "default Parallax",
    "colors": {
        "primary": "#1b2a4a",
        "secondary": "#33405e",
        "tertiary": "#4c86a0",
        "neutral": "#ffffff",
        "text": "#333333",
    },
    "fonts": {"header": "Arial, Helvetica, sans-serif", "body": "Helvetica, Arial, sans-serif"},
    "logo": None,
    "client_disclaimers": [],
}

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# --------------------------------------------------------------------------- #
# CGC disclosure boilerplate, verbatim from the official report (pages 8-9).
# Pinned: re-sync from response.html_url if CGC updates the wording.
# --------------------------------------------------------------------------- #
DISCLOSURE_BLOCKS = [
    ("DISCLOSURE", [
        'The information and opinions in this report were prepared or are disseminated by Chicago Global Capital Pte. Ltd. ("CGC"), regulated by the Monetary Authority of Singapore ("MAS"). CGC is Capital Markets Services Licensed to conduct the regulated activity of fund management and is an Exempt Financial Adviser authorised to advise on and/or issue analyses/reports on investment products.',
        "This report is not intended to, and does not, constitute an offer or solicitation to buy and sell securities or engage in any investment activity. This report is for informational purposes only. Statements in this report are not made with respect to any particular investor or type of investor. Securities, financial instruments, or strategies mentioned herein may not be suitable for all investors, and this material is not intended for any specific investor and does not take into account an investor's particular investment objectives, financial situations, or needs. Chicago Global Capital recommends that investors independently evaluate particular investments and strategies, and encourages investors to seek the advice of a financial adviser.",
        "Additional information on a subject company may be available upon request. The financial products or financial services to which this research relates will only be made available to a customer who we are satisfied meets the regulatory criteria of an Accredited Investor. A distribution of the different Chicago Global Research ratings or recommendations, in percentage terms for Investments in each sector covered, is available upon request from your sales representative.",
    ]),
    ("ANALYST CERTIFICATION", [
        "The investment recommendations and market insights contained herein are produced using sophisticated AI algorithms developed by CG Parallax, incorporating machine learning and predictive analytics. The AI-generated content in this report is actively used in investment strategies for funds managed by Chicago Global Capital, with current and future holdings to be reported in accordance with regulatory requirements. While AI technologies provide comprehensive data analysis and predictive modeling, investors are advised that AI-generated recommendations should be considered alongside traditional financial analysis and professional human judgment. The AI systems and their developers receive no direct compensation based on specific investment recommendations or trading outcomes. Chicago Global Capital will provide detailed reporting of our fund's holdings that have been influenced by or derived from Parallax AI-generated insights.",
    ]),
    ("GLOBAL RESEARCH CONFLICT MANAGEMENT POLICY", [
        "Chicago Global Capital does business that relates to companies/instruments covered in Chicago Global Research, including providing research, fund management, and investment services. Chicago Global Capital sells to and buys for customers the securities/instruments of companies covered in Chicago Global Research on a principal basis. Chicago Global Capital may have a position in the equity or debt of the Company discussed in this report. Chicago Global Capital trades or may trade as principal in the debt securities (or in related derivatives). Certain disclosures listed above are also for compliance with applicable regulations in non-US jurisdictions.",
        "Our AI-driven research methodology is committed to producing clear, fair, and non-misleading evaluations that provide sufficient information to support informed investment decision-making. While utilizing advanced computational techniques, we maintain rigorous standards to ensure analytical integrity and transparency. To maintain objectivity, our algorithmic analysis is structured to prevent inappropriate influences from external financial interests. The computational models are designed to operate independently of sales, trading, or investment considerations, ensuring that the research output reflects an unbiased assessment of the subject securities. No part of the analysis is directly linked to potential transactional benefits or promotional objectives.",
        "This report includes comprehensive disclosures regarding potential conflicts of interest, limitations of the analytical approach, and the data sources utilized. The AI system certifies that the views presented accurately reflect the computational analysis without external manipulation. We acknowledge that while our advanced analytical techniques strive for high-quality insights, investors should consider this report as one of multiple inputs in their investment decision-making process. The research methodology undergoes multiple verification stages, including algorithmic cross-checking, statistical validation, and systematic review to ensure accuracy and compliance with professional research standards. Any material modifications to the analysis are documented and transparently reported.",
    ]),
    ("ANALYST STOCK RATINGS", [
        "Strong Buy - The stock's total return is expected to exceed the total return of the relevant country index or the average total return of the analyst's industry (or industry team's) coverage universe, on a risk-adjusted basis over the next 12 months, with shares rising in price on an absolute basis.",
        "Buy - The stock's total return is expected to exceed the total return of the relevant country index or the average total return of the analyst's industry (or industry team's) coverage universe, on a risk-adjusted basis over the next 12 months.",
        "Hold - The stock's total return is expected to be in line with the total return of the relevant country MSCI Index or the average total return of the analyst's industry (or industry team's) coverage universe, on a risk-adjusted basis over the next 12 months.",
        "Sell - The stock's total return is expected to be below the total return of the relevant country MSCI Index or the average total return of the analyst's industry (or industry team's) coverage universe, on a risk-adjusted basis, over the next 12-18 months.",
        "Strong Sell - The stock's total return is expected to be below the total return of the relevant country MSCI Index or the average total return of the analyst's industry (or industry team's) coverage universe, on a risk-adjusted basis, over the next 12-18 months, with shares falling in price on an absolute basis.",
        "Benchmarks for each region are as follows: North America - S&P 500; Latin America - relevant MSCI country index or MSCI Latin America Index; Europe - MSCI Europe; Japan - TOPIX; Asia - relevant MSCI country index or MSCI sub-regional index or MSCI AC Asia Pacific ex Japan Index.",
    ]),
    ("OTHER IMPORTANT DISCLOSURES", [
        "Chicago Global Research is based on public information. Chicago Global Capital makes every effort to use reliable, comprehensive information, but we make no representation that it is accurate or complete. We have no obligation to tell you when opinions or information in Chicago Global Research change apart from when we intend to discontinue equity research coverage of a subject company. Chicago Global Capital may make investment decisions that are inconsistent with the recommendations or views in this report.",
        "The value of and income from your investments may vary because of changes in interest rates, foreign exchange rates, default rates, prepayment rates, securities/instruments prices, market indexes, operational or financial conditions of companies or other factors. There may be time limitations on the exercise of options or other rights in securities/instruments transactions. Past performance is not necessarily a guide to future performance. Estimates of future performance are based on assumptions that may not be realized. If provided, and unless otherwise stated, the closing price on the cover page is that of the primary exchange for the subject company's securities/instruments.",
    ]),
]

# Statement row maps: (label, json_key, fmt). fmt 'mm' divides to millions.
INCOME_ROWS = [
    ("Total Revenue", "total_revenue", "mm"),
    ("Cost of Revenue", "cost_of_revenue_total", "mmp"),
    ("Gross Profit", "gross_profit", "mm"),
    ("SG&A Expenses", "sga_expenses_total", "mmp"),
    ("Research & Development", "research_development", "mmp"),
    ("Operating Income", "operating_income", "mm"),
    ("Income Before Tax", "net_income_before_taxes", "mm"),
    ("Income Tax", "provision_for_income_taxes", "mmp"),
    ("Net Income", "net_income", "mm"),
    ("EPS (Basic)", "basic_eps_including_extraordinary_items", "eps"),
]
BALANCE_ROWS = [
    ("Cash & Short-Term Investments", "cash_and_short_term_investments", "mm"),
    ("Total Receivables", "total_receivables_net", "mm"),
    ("Inventory", "total_inventory", "mm"),
    ("Total Current Assets", "total_current_assets", "mm"),
    ("Property, Plant & Equipment (Net)", "property_plant_equipment_total_net", "mm"),
    ("Goodwill", "goodwill_net", "mm"),
    ("Intangibles", "intangibles_net", "mm"),
    ("Total Assets", "total_assets", "mm"),
    ("Total Current Liabilities", "total_current_liabilities", "mm"),
    ("Total Long-Term Debt", "total_long_term_debt", "mm"),
    ("Total Debt", "total_debt", "mm"),
    ("Total Liabilities", "total_liabilities", "mm"),
    ("Total Equity", "total_equity", "mm"),
]
CASHFLOW_ROWS = [
    ("Operating Cash Flow", "cash_from_operating_activities", "mm"),
    ("Capital Expenditures", "capital_expenditures", "mmp"),
    ("Free Cash Flow", "__fcf__", "mm"),
    ("Investing Cash Flow", "cash_from_investing_activities", "mm"),
    ("Financing Cash Flow", "cash_from_financing_activities", "mm"),
    ("Dividends Paid", "total_cash_dividends_paid", "mm"),
    ("Net Change in Cash", "net_change_in_cash", "mm"),
]
RATIO_ROWS = [
    ("Gross Margin %", "gross_margin", "pct"),
    ("Operating Margin %", "operating_margin", "pct"),
    ("Net Margin %", "net_margin", "pct"),
    ("Return on Equity %", "return_on_equity", "pct"),
    ("Return on Assets %", "return_on_assets", "pct"),
    ("Return on Invested Capital %", "return_on_invested_capital", "pct"),
    ("P/E", "pe", "x"),
    ("P/B", "price_book_value", "x"),
    ("EV/Revenue", "enterprise_value_revenue", "x"),
    ("EV/EBIT", "enterprise_value_ebit", "x"),
    ("Dividend Yield %", "dividend_yield", "pct"),
    ("Current Ratio", "current_ratio", "x"),
    ("Quick Ratio", "quick_ratio", "x"),
    ("Cash Cycle (days)", "cash_cycle_days", "days"),
    ("Debt/Equity", "debt_equity", "x"),
    ("Net Debt/EBITDA", "net_debt_to_ebitda", "x"),
]
KEY_STATS = [
    ("P/E (TTM)", "price_to_earnings", "x"),
    ("Price / Book", "price_to_book", "x"),
    ("EPS", "earnings_per_share", "money"),
    ("Return on Equity", "return_on_equity", "pct"),
    ("Return on Assets", "return_on_assets", "pct"),
    ("Return on Investment", "return_on_investment", "pct"),
    ("Price / FCF", "price_to_fcf", "x"),
    ("EV / EBITDA", "ev_ebitda", "x"),
    ("EV / Revenue", "ev_revenue", "x"),
    ("Net Income 5Y Growth", "net_income_5y_growth", "pct"),
    ("Rev/Share 5Y Growth", "revenue_per_share_5y_growth", "pct"),
]
RETURN_COLS = [("1M", "ret_1m"), ("3M", "ret_3m"), ("YTD", "ret_ytd"),
               ("1Y", "ret_1yr"), ("5Y", "ret_5yr"), ("10Y", "ret_10yr")]
FACTORS = [("Value", "value"), ("Quality", "quality"), ("Momentum", "momentum"),
           ("Defensive", "defensive"), ("Tactical", "tactical"), ("Overall", "total")]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def esc(x):
    return _html.escape("" if x is None else str(x))


def num(x):
    if x is None:
        return None
    try:
        return float(str(x).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _hex(c, fallback):
    if isinstance(c, str) and c.startswith("#") and len(c) in (4, 7):
        return c.lower()
    return fallback


def fmt(val, kind):
    v = num(val)
    if v is None:
        return "-"
    if kind == "mm":
        v = v / 1e6
        return f"({abs(v):,.0f})" if v < 0 else f"{v:,.0f}"
    if kind == "mmp":  # expense/cost line: always parenthesised
        return f"({abs(v) / 1e6:,.0f})"
    if kind == "eps":
        return f"{v:,.2f}"
    if kind == "money":
        return f"{v:,.2f}"
    if kind == "pct":
        return f"{v:,.2f}%"
    if kind == "pctsigned":
        return f"{v:+,.1f}%"
    if kind == "x":
        return f"{v:,.2f}x"
    if kind == "days":
        return f"{v:,.1f}"
    return f"{v:,.2f}"


def fmt_bigmoney(val):
    v = num(val)
    if v is None:
        return "-"
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(v) >= div:
            return f"{v / div:,.2f}{suf}"
    return f"{v:,.0f}"


def signed_class(val):
    v = num(val)
    if v is None:
        return ""
    return "pos" if v > 0 else ("neg" if v < 0 else "")


def rating_kind(rec):
    r = (rec or "").upper()
    if "SELL" in r:
        return "neg"
    if "BUY" in r:
        return "pos"
    return "warn"


def score_kind(score):
    v = num(score)
    if v is None:
        return "warn"
    return "pos" if v >= 7 else ("neg" if v < 4 else "warn")


def data_uri(path):
    try:
        p = Path(os.path.expanduser(path))
        if not p.is_file():
            return None
        ext = p.suffix.lstrip(".").lower() or "png"
        mime = {"jpg": "jpeg", "svg": "svg+xml"}.get(ext, ext)
        return f"data:image/{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Branding
# --------------------------------------------------------------------------- #
def load_branding(path=None):
    """Read the client brand config. Always returns a complete branding dict;
    falls back to the default Parallax palette on any error (never raises)."""
    if path is None:
        path = os.path.expanduser("~/.parallax/client-branding/config.yaml")
    if yaml is None or not os.path.isfile(path):
        return dict(DEFAULT_BRANDING)
    try:
        cfg = yaml.safe_load(Path(path).read_text())
        if not isinstance(cfg, dict):
            return dict(DEFAULT_BRANDING)
    except Exception:
        return dict(DEFAULT_BRANDING)

    b = cfg.get("branding", {}) or {}
    colors = b.get("colors", {}) or {}
    typo = b.get("typography", {}) or {}
    comp = (b.get("components", {}) or {}).get("body-text", {}) or {}
    # Client jurisdiction disclaimers live in the onboard config under voice.disclaimers[]
    # ({jurisdiction, text, placement}); used only by --full-white-label (see SKILL.md).
    voice = cfg.get("voice", {}) or {}
    client_disclaimers = [x for x in (voice.get("disclaimers") or [])
                          if isinstance(x, dict) and x.get("text")]
    d = DEFAULT_BRANDING["colors"]
    primary = _hex(colors.get("primary"), d["primary"])
    branding = {
        "client_name": (cfg.get("metadata", {}) or {}).get("client_name", "") or "",
        "active": bool(colors.get("primary")),
        "source": os.path.basename(path),
        "colors": {
            "primary": primary,
            "secondary": _hex(colors.get("secondary"), primary),
            "tertiary": _hex(colors.get("tertiary"), d["tertiary"]),
            "neutral": _hex(colors.get("neutral"), d["neutral"]),
            "text": _hex(comp.get("textColor"), d["text"]),
        },
        "fonts": {
            "header": (typo.get("h1", {}) or {}).get("fontFamily")
            or DEFAULT_BRANDING["fonts"]["header"],
            "body": (typo.get("body-md", {}) or {}).get("fontFamily")
            or DEFAULT_BRANDING["fonts"]["body"],
        },
        "logo": (b.get("logos", {}) or {}).get("primary"),
        "client_disclaimers": client_disclaimers,
    }
    return branding


# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #
def build_css(branding):
    c = branding["colors"]
    f = branding["fonts"]
    return f""":root {{
  --brand-primary: {c['primary']};
  --brand-secondary: {c['secondary']};
  --brand-accent: {c['tertiary']};
  --brand-bg: {c['neutral']};
  --brand-text: {c['text']};
  --brand-heading-font: {f['header']}, Arial, sans-serif;
  --brand-body-font: {f['body']}, Helvetica, Arial, sans-serif;
  --pos: {SEMANTIC['pos']};
  --neg: {SEMANTIC['neg']};
  --warn: {SEMANTIC['warn']};
  --line: #e3e3e8;
  --muted: #6b6b72;
  --soft: #f7f7f9;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: var(--brand-body-font); color: var(--brand-text);
  background: var(--brand-bg); margin: 0; line-height: 1.55; font-size: 13.5px; }}
.page {{ max-width: 920px; margin: 0 auto; padding: 28px 46px 24px; }}
.cover-strip {{ background: var(--brand-primary); color: #fff; padding: 6px 0;
  text-align: center; font-size: 10px; letter-spacing: .18em; font-weight: 600; }}
h1, h2, h3, h4 {{ font-family: var(--brand-heading-font); color: var(--brand-primary); }}
h1 {{ font-size: 27px; margin: 6px 0 2px; }}
h2 {{ font-size: 17px; border-left: 4px solid var(--brand-secondary);
  padding-left: 11px; margin: 30px 0 10px; }}
h3 {{ font-size: 12px; color: var(--brand-secondary); text-transform: uppercase;
  letter-spacing: .08em; margin: 16px 0 4px; }}
p {{ margin: 8px 0; }}
.header {{ display: flex; align-items: flex-start; justify-content: space-between;
  padding: 14px 0 16px; border-bottom: 2px solid var(--brand-primary); }}
.header .brand img {{ height: 46px; display: block; }}
.header .brand .name {{ font-family: var(--brand-heading-font);
  font-size: 20px; font-weight: 700; color: var(--brand-primary); }}
.header .meta {{ text-align: right; font-size: 10.5px; color: var(--muted); }}
.header .meta strong {{ color: var(--brand-primary); font-family: var(--brand-heading-font);
  letter-spacing: .06em; display: block; font-size: 12px; }}
.prov {{ font-size: 9.5px; color: var(--muted); margin-top: 4px; }}
.ticker-line {{ color: var(--muted); font-size: 12px; margin: 0 0 12px; }}
.toprow {{ display: flex; gap: 14px; align-items: stretch; margin: 14px 0 6px; flex-wrap: wrap; }}
.rating-badge {{ display: inline-block; padding: 4px 14px; border-radius: 4px;
  color: #fff; font-family: var(--brand-heading-font); font-weight: 700;
  font-size: 14px; letter-spacing: .04em; }}
.rating-badge.pos {{ background: var(--pos); }}
.rating-badge.neg {{ background: var(--neg); }}
.rating-badge.warn {{ background: var(--warn); }}
.pt {{ flex: 1; min-width: 150px; border: 1px solid var(--line); border-radius: 6px;
  padding: 10px 14px; background: var(--soft); }}
.pt .label {{ font-size: 9.5px; text-transform: uppercase; letter-spacing: .1em;
  color: var(--muted); font-weight: 600; }}
.pt .val {{ font-family: var(--brand-heading-font); font-size: 19px;
  color: var(--brand-primary); font-weight: 700; }}
.pt .sub {{ font-size: 10px; color: var(--muted); }}
.scores {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin: 14px 0; }}
.chip {{ border: 1px solid var(--line); border-radius: 6px; padding: 9px 10px 11px; }}
.chip .lbl {{ font-size: 9px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); font-weight: 600; }}
.chip .sc {{ font-family: var(--brand-heading-font); font-size: 20px; font-weight: 700;
  color: var(--brand-primary); }}
.chip .sc small {{ font-size: 11px; color: var(--muted); font-weight: 400; }}
.bar {{ height: 5px; border-radius: 3px; background: #ececf0; margin-top: 6px; overflow: hidden; }}
.bar > i {{ display: block; height: 100%; }}
.bar > i.pos {{ background: var(--pos); }}
.bar > i.neg {{ background: var(--neg); }}
.bar > i.warn {{ background: var(--warn); }}
.kpi-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 12px 0; }}
.kpi {{ border: 1px solid var(--line); border-radius: 6px; padding: 10px 12px; background: #fff; }}
.kpi .label {{ font-size: 9px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); font-weight: 600; }}
.kpi .value {{ font-family: var(--brand-heading-font); font-size: 16px;
  color: var(--brand-primary); font-weight: 600; margin-top: 2px; }}
.returns {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin: 12px 0; }}
.returns .r {{ text-align: center; border: 1px solid var(--line); border-radius: 6px; padding: 8px 4px; }}
.returns .r .label {{ font-size: 9px; color: var(--muted); letter-spacing: .08em; }}
.returns .r .value {{ font-family: var(--brand-heading-font); font-weight: 700; font-size: 14px; }}
.callout {{ border-left: 4px solid var(--brand-accent); background: var(--soft);
  padding: 10px 14px; margin: 12px 0; border-radius: 0 6px 6px 0; }}
.grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
.grid3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
ul {{ margin: 6px 0; padding-left: 18px; }}
li {{ margin-bottom: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0 18px; font-size: 12px; }}
th {{ background: var(--brand-primary); color: #fff; text-align: left; padding: 7px 9px;
  font-family: var(--brand-heading-font); font-weight: 500; font-size: 10.5px;
  letter-spacing: .03em; }}
th.num, td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
td {{ padding: 6px 9px; border-bottom: 1px solid var(--line); }}
tr.peer-row.subject td {{ font-weight: 700; background: var(--soft); }}
.pos {{ color: var(--pos); }}
.neg {{ color: var(--neg); }}
.disclosures {{ margin-top: 26px; font-size: 10px; color: #555; }}
.disclosures h2 {{ font-size: 13px; }}
.disclosures h3 {{ color: var(--brand-primary); margin-top: 14px; }}
.sub {{ break-inside: avoid; }}
.header .meta .powered {{ margin-top: 5px; font-size: 9px; letter-spacing: .05em;
  text-transform: uppercase; color: var(--muted); }}
@page {{ size: A4; margin: 13mm 0 17mm; }}
@media print {{
  h1, h2, h3, h4 {{ break-after: avoid; }}
  tr, .kpi, .chip, .returns .r, .sub, .callout, .pt {{ break-inside: avoid; }}
  table {{ break-inside: auto; }}
  thead {{ display: table-header-group; }}
}}
@media screen {{ body {{ max-width: 860px; margin: 0 auto; }} }}
"""


# --------------------------------------------------------------------------- #
# Section renderers
# --------------------------------------------------------------------------- #
def paras(*vals):
    return "".join(f"<p>{esc(v)}</p>" for v in vals if v)


def bullets(items):
    items = [i for i in (items or []) if i]
    if not items:
        return ""
    return "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def g(d, *path, default=None):
    cur = d
    for k in path:
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return default
    return default if cur is None else cur


def render_cover(rep, branding):
    co = rep.get("company", {})
    name = g(rep, "company_profile", "title") or co.get("name") or rep.get("symbol", "")
    ric = co.get("ric", "")
    ccy = co.get("currency", "")
    tline = " | ".join([x for x in [ric, co.get("market"), co.get("sector"), co.get("industry")] if x])
    rec = co.get("recommendation", "")
    dcf = rep.get("dcf_valuation", {})
    vital = rep.get("vital_stats", {})

    logo_html = ""
    if branding.get("logo"):
        uri = data_uri(branding["logo"])
        if uri:
            logo_html = f'<img src="{uri}" alt="{esc(branding.get("client_name"))}">'
    if not logo_html and branding.get("client_name"):
        logo_html = f'<div class="name">{esc(branding["client_name"])}</div>'

    # Chicago Global credit in the cover header. Shown by default. In full
    # white-label it is hidden, unless the client opts to keep it (powered_by_optin),
    # which pairs their own disclosures with a "Powered by Chicago Global" credit.
    show_credit = (not branding.get("full_white_label")) or branding.get("powered_by_optin")
    powered = '<div class="powered">Powered by Chicago Global</div>' if show_credit else ""

    # factor score chips
    widths = rep.get("score_widths", {})
    chips = ""
    for label, key in FACTORS:
        sc = co.get(key)
        kind = score_kind(sc)
        w = num(widths.get(key))
        w = max(0, min(100, w)) if w is not None else (num(sc) or 0) * 10
        scval = num(sc)
        sctxt = (f"{scval:g}" if scval is not None else "-")
        chips += (
            f'<div class="chip"><div class="lbl">{esc(label)}</div>'
            f'<div class="sc">{esc(sctxt)}<small>/10</small></div>'
            f'<div class="bar"><i class="{kind}" style="width:{w:.0f}%"></i></div></div>'
        )

    # key statistics
    cr = rep.get("current_ratios", {})
    kpis = ""
    for label, key, kind in KEY_STATS:
        kpis += (f'<div class="kpi"><div class="label">{esc(label)}</div>'
                 f'<div class="value">{esc(fmt(cr.get(key), kind))}</div></div>')

    # returns strip
    pr = rep.get("period_returns", {})
    rets = ""
    for label, key in RETURN_COLS:
        v = pr.get(key)
        rets += (f'<div class="r"><div class="label">{esc(label)}</div>'
                 f'<div class="value {signed_class(v)}">{esc(fmt(v, "pctsigned"))}</div></div>')

    thesis = rep.get("investment_thesis", {})
    news = rep.get("news_analysis", {})

    return f"""
<section id="sec-cover">
  <div class="header">
    <div class="brand">{logo_html}</div>
    <div class="meta"><strong>EQUITY RESEARCH</strong>
      {esc(rep.get('generated_date', ''))} &bull; {esc(ccy)} &bull; {esc(ric)}
      {powered}
    </div>
  </div>
  <h1>{esc(name)}</h1>
  <div class="ticker-line">{esc(tline)}</div>
  <div class="toprow">
    <div class="pt"><div class="label">Rating</div>
      <div><span class="rating-badge {rating_kind(rec)}">{esc(rec or '-')}</span></div>
      <div class="sub">{esc(g(dcf, 'reconciliation_body') or g(dcf, 'reconciliation_chip') or '')}</div></div>
    <div class="pt"><div class="label">Price Target</div>
      <div class="val">{esc(fmt(dcf.get('target_value'), 'money'))} {esc(ccy)}</div>
      <div class="sub">{esc(dcf.get('target_footnote') or '')}</div></div>
    <div class="pt"><div class="label">Current Price</div>
      <div class="val">{esc(fmt(vital.get('current_price'), 'money'))} {esc(ccy)}</div></div>
    <div class="pt"><div class="label">Market Cap</div>
      <div class="val">{esc(fmt_bigmoney(co.get('mktcap')))} {esc(ccy)}</div></div>
  </div>
  <div class="scores">{chips}</div>
  <h2>Investment Thesis</h2>
  {('<p><em>' + esc(thesis.get('hook')) + '</em></p>') if thesis.get('hook') else ''}
  {paras(thesis.get('para1'), thesis.get('para2'), thesis.get('para3'), thesis.get('para4'))}
  <h2>{esc(news.get('title') or 'Recent Development')}</h2>
  {bullets([news.get('bullet1'), news.get('bullet2'), news.get('bullet3')])}
  <h2>Returns</h2>
  <div class="returns">{rets}</div>
  <h2>Key Statistics</h2>
  <div class="kpi-row">{kpis}</div>
  <p class="prov">{esc(rep.get('data_basis_note', ''))} {esc(rep.get('ratio_snapshot_note', ''))}</p>
</section>"""


def render_company(rep):
    cp = rep.get("company_profile", {})
    peers = rep.get("peers", [])
    head = ["Company", "Market", "Rating", "Mkt Cap (B)", "MTD %", "YTD %",
            "P/E", "EV/EBITDA", "ROE %", "D/E"]
    th = "".join(f'<th class="{"num" if i >= 3 else ""}">{esc(h)}</th>'
                 for i, h in enumerate(head))
    rows = ""
    for i, p in enumerate(peers):
        cls = "peer-row subject" if i == 0 else "peer-row"
        rows += (
            f'<tr class="{cls}">'
            f'<td>{esc(p.get("company_name"))}</td>'
            f'<td>{esc(p.get("market"))}</td>'
            f'<td>{esc(p.get("recommendation"))}</td>'
            f'<td class="num">{esc(fmt(p.get("mktcap_b"), "money"))}</td>'
            f'<td class="num {signed_class(p.get("mtd"))}">{esc(fmt(p.get("mtd"), "pctsigned"))}</td>'
            f'<td class="num {signed_class(p.get("ytd"))}">{esc(fmt(p.get("ytd"), "pctsigned"))}</td>'
            f'<td class="num">{esc(fmt(p.get("pe"), "x"))}</td>'
            f'<td class="num">{esc(fmt(p.get("ev_ebitda"), "x"))}</td>'
            f'<td class="num">{esc(fmt(p.get("roe"), "pct"))}</td>'
            f'<td class="num">{esc(fmt(p.get("de"), "x"))}</td>'
            f'</tr>'
        )
    return f"""
<section id="sec-company">
  <h2>Company Profile</h2>
  {paras(cp.get('para1'), cp.get('para2'), cp.get('para3'))}
  <h2>Score Analysis</h2>
  {paras(rep.get('score_analysis'))}
  <h2>Peer Analysis</h2>
  {paras(rep.get('peers_analysis'))}
  <table><thead><tr>{th}</tr></thead><tbody>{rows}</tbody></table>
</section>"""


def render_technical(rep):
    t = rep.get("technical_analysis", {})
    tt = t.get("technical_analysis", {})
    risk = t.get("risk_assessment", {})
    return f"""
<section id="sec-technical">
  <h2>Technical Analysis</h2>
  {paras(t.get('executive_summary'))}
  <div class="grid2">
    <div class="sub"><h3>Trend</h3>{paras(tt.get('trend_analysis'))}</div>
    <div class="sub"><h3>Momentum</h3>{paras(tt.get('momentum_indicators'))}</div>
    <div class="sub"><h3>Volume</h3>{paras(tt.get('volume_analysis'))}</div>
    <div class="sub"><h3>Price Action</h3>{paras(tt.get('price_action'))}</div>
    <div class="sub"><h3>Volatility</h3>{paras(tt.get('volatility_assessment'))}</div>
  </div>
  <div class="callout"><h3>Risk Assessment</h3>
    {paras(risk.get('volatility_level'), risk.get('risk_factors'))}</div>
</section>"""


def render_financial(rep):
    fa = rep.get("financial_analysis", {})
    ds = fa.get("detailedanalysis", {})
    es = fa.get("executivesummary", {})
    bs = ds.get("businessstrategy", {})
    aq = ds.get("accountingquality", {})
    pa = ds.get("prospectiveanalysis", {})
    return f"""
<section id="sec-financial">
  <h2>Financial Analysis</h2>
  {paras(rep.get('financial_summary'))}
  {('<h3>Key Highlights</h3>' + bullets(es.get('keyhighlights'))) if es.get('keyhighlights') else ''}
  <div class="grid2">
    <div class="sub"><h3>Business Strategy</h3>
      {paras(bs.get('industryposition'), bs.get('competitiveadvantage'), bs.get('businessmodel'))}
      {('<h3>Key Risks</h3>' + bullets(bs.get('keyrisks'))) if bs.get('keyrisks') else ''}</div>
    <div class="sub"><h3>Accounting Quality{(' - ' + esc(aq.get('earningsquality'))) if aq.get('earningsquality') else ''}</h3>
      {paras(aq.get('conservatismlevel'))}
      {('<h3>Key Policies</h3>' + bullets(aq.get('keypolicies'))) if aq.get('keypolicies') else ''}
      {('<h3>Red Flags</h3>' + bullets(aq.get('accountingredflags'))) if aq.get('accountingredflags') else ''}</div>
  </div>
  <div class="sub"><h3>Prospective Analysis</h3>
  {paras(pa.get('futureearnings'), pa.get('growthprospects'), pa.get('valuationassessment'))}
  {('<h3>Scenarios</h3>' + bullets(pa.get('scenarioanalysis'))) if pa.get('scenarioanalysis') else ''}</div>
</section>"""


def _stmt_table(rows_def, records):
    periods = [r.get("perenddt") or r.get("year") for r in records]
    th = '<th>Metric</th>' + "".join(
        f'<th class="num period">{esc(p)}</th>' for p in periods)
    body = ""
    for label, key, kind in rows_def:
        cells = ""
        for rec in records:
            if key == "__fcf__":
                op = num(rec.get("cash_from_operating_activities"))
                cx = num(rec.get("capital_expenditures"))
                val = (op + cx) if (op is not None and cx is not None) else None
                cells += f'<td class="num">{esc(fmt(val, "mm"))}</td>'
            else:
                cells += f'<td class="num">{esc(fmt(rec.get(key), kind))}</td>'
        body += f'<tr><td>{esc(label)}</td>{cells}</tr>'
    return f'<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def render_statements(rep):
    inc = rep.get("income_statement", [])
    bal = rep.get("balance_sheet", [])
    cf = rep.get("cash_flow", [])
    ccy = rep.get("financial_statement_currency", "USD")
    return f"""
<section id="sec-statements">
  <h2>Financial Statements</h2>
  <p class="prov">All figures in {esc(ccy)} millions except per-share data.</p>
  <h3>Income Statement</h3>
  {_stmt_table(INCOME_ROWS, inc)}
  <h3>Balance Sheet</h3>
  {_stmt_table(BALANCE_ROWS, bal)}
  <h3>Cash Flow Statement</h3>
  {_stmt_table(CASHFLOW_ROWS, cf)}
</section>"""


def render_ratios(rep):
    kr = rep.get("key_ratios", [])
    periods = [r.get("year") or r.get("perenddt") for r in kr]
    th = '<th>Ratio</th>' + "".join(f'<th class="num period">{esc(p)}</th>' for p in periods)
    body = ""
    for label, key, kind in RATIO_ROWS:
        cells = "".join(f'<td class="num">{esc(fmt(r.get(key), kind))}</td>' for r in kr)
        body += f'<tr><td>{esc(label)}</td>{cells}</tr>'
    return f"""
<section id="sec-ratios">
  <h2>Financial Ratios</h2>
  <table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>
</section>"""


def render_analyst(rep):
    pt = rep.get("price_target", {})
    return f"""
<section id="sec-analyst">
  <h2>Analyst Ratings</h2>
  {paras(rep.get('analyst_analysis'))}
  <div class="toprow">
    <div class="pt"><div class="label">Consensus Target</div>
      <div class="val">{esc(fmt(pt.get('target_mean'), 'money'))}</div></div>
    <div class="pt"><div class="label">Expected Change</div>
      <div class="val {signed_class(pt.get('exp_pct_change'))}">{esc(fmt(pt.get('exp_pct_change'), 'pctsigned'))}</div></div>
    <div class="pt"><div class="label">As Of</div>
      <div class="val">{esc(pt.get('target_calc_date') or '-')}</div></div>
  </div>
</section>"""


def render_disclosures(branding):
    if branding.get("full_white_label"):
        # Private-label: render the client's own jurisdiction disclosures verbatim
        # from the brand config (voice.disclaimers[]). No CGC boilerplate.
        blocks = ""
        for it in branding.get("client_disclaimers", []):
            heading = it.get("jurisdiction") or "Disclosures"
            blocks += f"<h3>{esc(heading)}</h3><p>{esc(it.get('text', ''))}</p>"
        return f"""
<section id="sec-disclosures" class="disclosures">
  <h2>Important Disclosures</h2>
  {blocks}
</section>"""
    # Co-brand: bundled CGC / MAS boilerplate, verbatim.
    blocks = ""
    for heading, paragraphs in DISCLOSURE_BLOCKS:
        blocks += f"<h3>{esc(heading)}</h3>" + "".join(f"<p>{esc(p)}</p>" for p in paragraphs)
    return f"""
<section id="sec-disclosures" class="disclosures">
  <h2>Important Disclosures</h2>
  {blocks}
</section>"""


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #
def render_html(response, branding):
    rep = response.get("report", response) if isinstance(response, dict) else {}
    co = rep.get("company", {})
    title = f"{co.get('name') or rep.get('symbol', 'Stock')} - Equity Research"
    if branding.get("client_name"):
        title += f" - {branding['client_name']}"
    body = (
        render_cover(rep, branding)
        + render_company(rep)
        + render_technical(rep)
        + render_financial(rep)
        + render_statements(rep)
        + render_ratios(rep)
        + render_analyst(rep)
        + render_disclosures(branding)
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{esc(title)}</title>
<style>{build_css(branding)}</style>
</head><body>
<div class="cover-strip">CONFIDENTIAL &bull; FOR THE INTENDED RECIPIENT ONLY</div>
<div class="page">
{body}
</div>
</body></html>"""


def _trim_trailing_blank(pdf_path):
    """Drop a trailing page that carries only the repeating footer (a hairline
    content overflow can spill onto an otherwise-empty final page). Best-effort;
    requires pymupdf, silently skips if unavailable."""
    try:
        import fitz  # type: ignore
    except Exception:
        return
    try:
        doc = fitz.open(pdf_path)
        changed = False
        while len(doc) > 1 and len(doc[-1].get_text().strip()) < 200:
            doc.delete_page(len(doc) - 1)
            changed = True
        if changed:
            tmp = pdf_path + ".tmp"
            doc.save(tmp)
            doc.close()
            os.replace(tmp, pdf_path)
        else:
            doc.close()
    except Exception:
        pass


def _stamp_footer(pdf_path, footer_left):
    """Stamp a per-page footer (left text + 'Page X of N') into the bottom page
    margin. Drawn in the margin, so it can never overlap content. Best-effort;
    requires pymupdf, silently skips if unavailable."""
    try:
        import fitz  # type: ignore
    except Exception:
        return
    try:
        doc = fitz.open(pdf_path)
        n = len(doc)
        gray = (0.42, 0.42, 0.45)
        mx = 36  # left/right inset in points (~aligns with content gutter)
        for i, page in enumerate(doc, 1):
            w, h = page.rect.width, page.rect.height
            y = h - 22  # inside the bottom margin, below the content box
            if footer_left:
                page.insert_text((mx, y), footer_left, fontsize=8, fontname="helv", color=gray)
            right = f"Page {i} of {n}"
            tw = fitz.get_text_length(right, fontsize=8, fontname="helv")
            page.insert_text((w - mx - tw, y), right, fontsize=8, fontname="helv", color=gray)
        tmp = pdf_path + ".tmp"
        doc.save(tmp)
        doc.close()
        os.replace(tmp, pdf_path)
    except Exception:
        pass


def to_pdf(html_path, pdf_path, footer_left=""):
    if not os.path.isfile(CHROME):
        print(f"[warn] Chrome not found at {CHROME}; skipping PDF", file=sys.stderr)
        return False
    cmd = [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={pdf_path}", f"file://{os.path.abspath(html_path)}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[warn] Chrome exit {r.returncode}: {r.stderr[:300]}", file=sys.stderr)
        return False
    _trim_trailing_blank(pdf_path)   # before stamping, so 'of N' is correct
    _stamp_footer(pdf_path, footer_left)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="White-label a Parallax stock report.")
    ap.add_argument("report_json", help="get_stock_report response JSON file")
    ap.add_argument("--branding", default=None, help="brand config.yaml path")
    ap.add_argument("--out", default=None, help="output HTML path")
    ap.add_argument("--pdf", action="store_true", help="also render a PDF via Chrome")
    ap.add_argument("--client-name", default=None, help="override client name")
    ap.add_argument("--full-white-label", action="store_true",
                    help="private-label: strip Chicago Global / Parallax attribution and use the "
                         "client's own disclosures from the brand config (voice.disclaimers[]). "
                         "Refuses to render if no client disclosures are configured.")
    ap.add_argument("--powered-by", action="store_true",
                    help="keep the 'Powered by Chicago Global' credit even with --full-white-label, "
                         "so the client's own disclosures pair with the Chicago Global credit.")
    args = ap.parse_args(argv)

    response = json.loads(Path(args.report_json).read_text())
    branding = load_branding(args.branding)
    if args.client_name:
        branding["client_name"] = args.client_name
        branding["active"] = True
    if args.powered_by:
        branding["powered_by_optin"] = True
    if args.full_white_label:
        branding["full_white_label"] = True
        if not branding.get("client_disclaimers"):
            print("ERROR: --full-white-label requires the client's own regulatory disclosures in "
                  "the brand config under voice.disclaimers[]; none found. Refusing to render "
                  "regulated research with no disclosures. Add them via the onboard config, or "
                  "render in the default co-brand mode.", file=sys.stderr)
            return 2

    symbol = (response.get("symbol") if isinstance(response, dict) else None) or "report"
    out = args.out or f"{symbol.replace('.', '_')}-white-label.html"
    html_doc = render_html(response, branding)
    Path(out).write_text(html_doc)
    print(f"HTML: {out} ({len(html_doc):,} bytes)")

    if args.pdf:
        pdf_path = os.path.splitext(out)[0] + ".pdf"
        cname = branding.get("client_name") or ""
        footer_left = f"{cname} - Confidential" if cname else "Confidential"
        if to_pdf(out, pdf_path, footer_left=footer_left):
            print(f"PDF: {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

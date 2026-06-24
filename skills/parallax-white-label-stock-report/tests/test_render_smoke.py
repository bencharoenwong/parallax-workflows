"""Smoke tests for the standalone white-label stock-report renderer.

Run: python3 -m pytest tests/ -q   (from the skill dir)
or:  python3 tests/test_render_smoke.py
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL))

import render_stock_report as r  # noqa: E402

FIXTURE = SKILL / "references" / "sample-acme.synthetic.json"
RESPONSE = json.loads(FIXTURE.read_text())
REPORT = RESPONSE["report"]

CLIENT_BRANDING = {
    "client_name": "Northwind Capital",
    "active": True,
    "source": "config.yaml",
    "colors": {
        "primary": "#2f4b7c",
        "secondary": "#b8743a",
        "tertiary": "#3a7ca5",
        "neutral": "#ffffff",
        "text": "#333333",
    },
    "fonts": {"header": "Arial", "body": "Helvetica"},
    "logo": None,
    "client_disclaimers": [],
}

SECTION_IDS = [
    "sec-cover",
    "sec-company",
    "sec-technical",
    "sec-financial",
    "sec-statements",
    "sec-ratios",
    "sec-analyst",
    "sec-disclosures",
]


def _render(branding=CLIENT_BRANDING):
    return r.render_html(RESPONSE, branding)


def test_all_sections_present():
    html = _render()
    for sid in SECTION_IDS:
        assert f'id="{sid}"' in html, f"missing section {sid}"


def test_six_factor_scores():
    html = _render()
    for label in ["Value", "Quality", "Momentum", "Defensive", "Tactical", "Overall"]:
        assert label in html, f"missing factor {label}"


def test_peer_table_has_all_rows():
    html = _render()
    n_peers = len(REPORT["peers"])
    assert n_peers == 8
    assert html.count('<tr class="peer-row') == n_peers


def test_statements_show_four_periods():
    html = _render()
    # Period columns are marked with the "period" class (th class="num period").
    # 3 statements x 4 periods = 12, plus key-ratios table 4 = 16. At minimum
    # the three statements must carry 4 period columns each: assert >= 12.
    assert html.count(' period"') >= 12


def test_brand_css_vars_applied_when_active():
    html = _render()
    assert "--brand-primary: #2f4b7c" in html
    assert "--brand-secondary: #b8743a" in html
    assert "Arial" in html and "Helvetica" in html


def test_semantic_colors_fixed_and_distinct_from_brand():
    html = _render()
    # semantic tokens present
    assert "--pos: #1a7f4b" in html
    assert "--neg: #b3261e" in html
    assert "--warn: #b8860b" in html
    # and never equal to a brand color
    brand_hexes = {v.lower() for v in CLIENT_BRANDING["colors"].values()}
    for sem in ("#1a7f4b", "#b3261e", "#b8860b"):
        assert sem not in brand_hexes


def test_disclosure_boilerplate_present():
    html = _render()
    assert "Monetary Authority of Singapore" in html
    assert "ANALYST" in html.upper()


def test_provenance_line_present():
    html = _render()
    # Co-brand: "Powered by Chicago Global" credit in the cover header. The verbose
    # research-author wording is intentionally NOT used.
    assert "Powered by Chicago Global" in html
    assert "Research and analysis by Chicago Global" not in html


def test_client_name_in_header_when_active():
    html = _render()
    assert "Northwind Capital" in html


def test_renders_with_no_branding_default():
    branding = r.load_branding("/nonexistent/path/config.yaml")
    assert branding["active"] is False
    html = r.render_html(RESPONSE, branding)
    # No client config = default Chicago Global report; the credit still applies.
    assert "Powered by Chicago Global" in html
    # core content still renders
    assert 'id="sec-cover"' in html


def test_missing_logo_does_not_crash():
    branding = dict(CLIENT_BRANDING)
    branding["logo"] = "/nope/missing-logo.png"
    html = r.render_html(RESPONSE, branding)
    assert 'id="sec-cover"' in html


# --- full private-label mode ---
FULL_WL_BRANDING = dict(CLIENT_BRANDING)
FULL_WL_BRANDING["full_white_label"] = True
FULL_WL_BRANDING["client_disclaimers"] = [
    {"jurisdiction": "Example SC", "placement": "report-end",
     "text": "Northwind Capital is licensed by the Example Securities Commission. "
             "This report is for accredited investors only."},
    {"jurisdiction": "Footer", "placement": "footer",
     "text": "Northwind Capital - Licensed by Example SC"},
]


def test_full_white_label_strips_cg_and_uses_client_disclosures():
    html = r.render_html(RESPONSE, FULL_WL_BRANDING)
    # no Chicago Global / Parallax traces
    assert "Chicago Global" not in html
    assert "Monetary Authority of Singapore" not in html
    assert "Research and analysis by Chicago Global" not in html
    # client's own disclosures rendered instead
    assert "Example Securities Commission" in html
    assert 'id="sec-disclosures"' in html


def test_full_white_label_refuses_without_disclaimers():
    # main() must refuse to render regulated research with no client disclosures
    import os
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "out.html")
    rc = r.main([str(FIXTURE), "--branding", "/nonexistent.yaml",
                 "--full-white-label", "--out", out])
    assert rc == 2
    assert not os.path.exists(out)


def test_full_white_label_with_credit_keeps_powered_by():
    # client's own disclosures, but the client opts to keep the Chicago Global credit
    branding = dict(FULL_WL_BRANDING)
    branding["powered_by_optin"] = True
    html = r.render_html(RESPONSE, branding)
    assert "Powered by Chicago Global" in html             # credit kept by opt-in
    assert "Example Securities Commission" in html          # client's own disclosures
    assert "Monetary Authority of Singapore" not in html    # not the CGC/MAS boilerplate


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)

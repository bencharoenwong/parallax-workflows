"""Smoke tests for the standalone white-label stock-report renderer.

Run: python3 -m pytest tests/ -q   (from the skill dir)
or:  python3 tests/test_render_smoke.py
"""
import json
import sys

import pytest
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
    # Checks stable anchor phrases in the pinned CGC/MAS disclosure text.
    # If these fail after a render_stock_report.py edit, re-sync DISCLOSURE_BLOCKS
    # from the official report (response.html_url). Source: DISCLOSURE_BLOCKS constant.
    html = _render()
    assert "Monetary Authority of Singapore" in html
    assert "Capital Markets Services Licensed" in html   # fund-management license sentence
    assert "Accredited Investor" in html                 # investor-classification sentence
    assert "ANALYST" in html.upper()


def test_bare_response_form_renders():
    # render_html accepts a bare report dict (no 'success'/'symbol'/'report' wrapper).
    # Protects the fallback in: rep = response.get("report", response) if isinstance(...
    html = r.render_html(REPORT, CLIENT_BRANDING)
    assert 'id="sec-cover"' in html
    assert "Monetary Authority of Singapore" in html


def test_provenance_line_present():
    html = _render()
    # Co-brand: "Powered by Parallax" credit in the cover header. The verbose
    # research-author wording is intentionally NOT used.
    assert "Powered by Parallax" in html
    assert "Research and analysis by Chicago Global" not in html


def test_client_name_in_header_when_active():
    html = _render()
    assert "Northwind Capital" in html


def test_cover_omits_price_target_box_when_dcf_valuation_absent():
    # Standard payload has no dcf_valuation; cover must omit the box, not render it blank.
    assert "dcf_valuation" not in REPORT
    html = _render()
    assert "Price Target" not in html


def test_cover_renders_price_target_box_when_dcf_valuation_present():
    # Forward-compat: if a response does carry dcf_valuation (e.g. a
    # non-standard partner pipeline), the cover should still render it.
    report_with_dcf = dict(REPORT)
    report_with_dcf["dcf_valuation"] = {
        "target_value": 142.0,
        "target_footnote": "via Peer P/E ~22.0x - 7 comps",
        "reconciliation_body": "Buy-rated; peer-multiple target sits 10.6% above current price",
        "reconciliation_chip": "Modest upside",
    }
    response_with_dcf = dict(RESPONSE, report=report_with_dcf)
    html = r.render_html(response_with_dcf, CLIENT_BRANDING)
    assert "Price Target" in html
    assert "142" in html
    assert "Modest upside" in html or "peer-multiple target" in html


def test_renders_with_no_branding_default():
    branding = r.load_branding("/nonexistent/path/config.yaml")
    assert branding["active"] is False
    html = r.render_html(RESPONSE, branding)
    # No client config = default Parallax report; the credit still applies.
    assert "Powered by Parallax" in html
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
    assert "Powered by Parallax" not in html       # credit suppressed without powered_by_optin
    # client's own disclosures rendered instead
    assert "Example Securities Commission" in html
    assert 'id="sec-disclosures"' in html


def test_full_white_label_refuses_without_disclaimers():
    # Both the CLI path (main) and the library path (render_html) must refuse to
    # render regulated research with no client disclosures.
    import os
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "out.html")
    rc = r.main([str(FIXTURE), "--branding", "/nonexistent.yaml",
                 "--full-white-label", "--out", out])
    assert rc == 2
    assert not os.path.exists(out)
    # library path: render_html must raise, not silently emit an empty section
    import pytest
    branding_no_disclaimers = dict(CLIENT_BRANDING, full_white_label=True, client_disclaimers=[])
    with pytest.raises(ValueError, match="client_disclaimers"):
        r.render_html(RESPONSE, branding_no_disclaimers)


def test_full_white_label_with_credit_keeps_powered_by():
    # client's own disclosures, but the client opts to keep the Parallax credit
    branding = dict(FULL_WL_BRANDING)
    branding["powered_by_optin"] = True
    html = r.render_html(RESPONSE, branding)
    assert "Powered by Parallax" in html                   # credit kept by opt-in
    assert "Example Securities Commission" in html          # client's own disclosures
    assert "Monetary Authority of Singapore" not in html    # not the CGC/MAS boilerplate
    assert "Chicago Global" not in html                     # no CG entity trace anywhere


def test_refuses_check_job_status_shaped_payload():
    # A raw check_job_status result has no "report" key; must refuse, not render a hollow report.
    import pytest
    job_status_payload = {
        "status": "completed",
        "result": {
            "success": True,
            "symbol": "ACME.O",
            "lang": "en",
            "pdf_url": "https://example.com/acme.pdf",
            "html_url": "https://example.com/acme.html",
            "json_url": "https://example.com/acme.json",
        },
        "success": True,
        "job_id": "11111111-1111-1111-1111-111111111111",
    }
    with pytest.raises(ValueError, match="report"):
        r.render_html(job_status_payload, CLIENT_BRANDING)


def test_bare_report_dict_still_renders():
    # The pre-existing fallback (response.get("report", response)) must still
    # accept a bare report dict with no "report" wrapper, not just the full
    # get_stock_report envelope.
    html = r.render_html(REPORT, CLIENT_BRANDING)
    assert 'id="sec-cover"' in html


# Optional config regressions exercise the real loader and renderer.

def load(tmp_path, payload):
    config = tmp_path / 'config.yaml'
    config.write_text(json.dumps(payload))
    return r.load_branding(config)


def assert_default_report(branding):
    assert branding['active'] is False
    assert branding['source'] == 'default Parallax'
    assert branding['colors'] == r.DEFAULT_BRANDING['colors']
    output = r.render_html(RESPONSE, branding)
    assert '--brand-primary: #1b2a4a' in output
    assert 'Monetary Authority of Singapore' in output
    assert 'Powered by Parallax' in output
    assert 'id="sec-cover"' in output


@pytest.mark.parametrize('payload', [
    None, [], 'not-a-config', {'branding': 'not-a-mapping'},
    {'branding': {'colors': ['#abc']}},
    {'branding': {'typography': 'broken', 'components': 'broken', 'logos': []}},
    {'branding': {'typography': {'h1': 42, 'body-md': []},
                  'components': {'body-text': False}}},
    {'metadata': ['wrong'], 'voice': 'wrong'},
    {'voice': {'disclaimers': 12}},
    {'branding': {'colors': {'primary': 'not-a-color'}}},
    {'branding': {'colors': {'primary': '#12zzzz'}}},
    {'branding': {'typography': {'h1': {'fontFamily': []}}, 'logos': {'primary': {}}}},
])
def test_malformed_optional_config_renders_defaults(tmp_path, payload):
    assert_default_report(load(tmp_path, payload))


def test_missing_and_corrupt_config_render_defaults(tmp_path):
    config = tmp_path / 'config.yaml'
    assert_default_report(r.load_branding(config))
    config.write_text('branding: [unterminated')
    assert_default_report(r.load_branding(config))
    assert_default_report(r.load_branding('\0'))


@pytest.mark.parametrize('payload, expected', [
    ({'branding': {'colors': {'primary': '#A1B2C3'}}}, '--brand-primary: #a1b2c3'),
    ({'branding': {'colors': {'secondary': '#abc'}}}, '--brand-secondary: #abc'),
    ({'branding': {'typography': {'h1': {'fontFamily': 'Courier New'}}}}, 'Courier New'),
    ({'metadata': {'client_name': 'Example Brand'}}, 'Example Brand'),
])
def test_usable_visual_input_activates_only_accepted_tokens(tmp_path, payload, expected):
    branding = load(tmp_path, payload)
    assert branding['active'] is True
    assert branding['source'] == 'config.yaml'
    output = r.render_html(RESPONSE, branding)
    assert expected in output
    assert 'Powered by Parallax' in output
    assert '--neg: #b3261e' in output


def test_malformed_branch_preserves_valid_sibling(tmp_path):
    branding = load(tmp_path, {'branding': {'colors': 'wrong',
        'components': {'body-text': {'textColor': '#123456'}}},
        'metadata': {'client_name': 'Example Brand'}, 'voice': {'disclaimers': 1}})
    output = r.render_html(RESPONSE, branding)
    assert branding['active'] is True
    assert branding['client_disclaimers'] == []
    assert '--brand-primary: #1b2a4a' in output
    assert '--brand-text: #123456' in output
    assert 'Example Brand' in output


def test_disclosures_are_separate_from_visual_activation(tmp_path):
    text = '  Example issuer approved disclosure.  '
    branding = load(tmp_path, {'voice': {'disclaimers': [
        {'text': text, 'placement': 'report-end', 'jurisdiction': 'Example'},
        {'text': ['invalid']}, {'text': '  '}, None,
    ]}})
    assert branding['active'] is False
    assert branding['source'] == 'default Parallax'
    assert len(branding['client_disclaimers']) == 1
    assert branding['client_disclaimers'][0]['text'] == text
    output = r.render_html(RESPONSE, dict(branding, full_white_label=True))
    assert 'Example issuer approved disclosure.' in output
    assert 'Monetary Authority of Singapore' not in output
    assert 'Powered by Parallax' not in output


@pytest.mark.parametrize('disclaimers', ['bad', {'text': 'wrong container'},
    [{'text': 1}], [{'text': []}], [{'text': '  '}], None])
def test_invalid_disclosure_cannot_bypass_full_white_label_gate(tmp_path, disclaimers):
    branding = load(tmp_path, {'voice': {'disclaimers': disclaimers}})
    with pytest.raises(ValueError, match='client_disclaimers'):
        r.render_html(RESPONSE, dict(branding, full_white_label=True))


def test_defaults_are_independent_between_loads(tmp_path):
    first = r.load_branding(tmp_path / 'missing.yaml')
    first['colors']['primary'] = '#000000'
    first['fonts']['header'] = 'mutated'
    first['client_disclaimers'].append({'text': 'mutated'})
    assert_default_report(r.load_branding(tmp_path / 'missing.yaml'))
    assert r.DEFAULT_BRANDING['fonts']['header'] != 'mutated'
    assert r.DEFAULT_BRANDING['client_disclaimers'] == []


def test_logo_only_activates_when_the_local_asset_can_be_loaded(tmp_path):
    branding = load(tmp_path, {'branding': {'logos': {'primary': '/missing/logo.png'}}})
    assert_default_report(branding)
    logo = tmp_path / 'logo.svg'
    logo.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>')
    branding = load(tmp_path, {'branding': {'logos': {'primary': str(logo)}}})
    assert branding['active'] is True
    assert branding['source'] == 'config.yaml'
    assert 'data:image/svg+xml;base64,' in r.render_html(RESPONSE, branding)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

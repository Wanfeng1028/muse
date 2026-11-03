import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CSS_PATH = os.path.join(ROOT, "feedflow", "static", "css", "design-v118.css")


def _v118_text():
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_v118_layer_referenced_after_v117_and_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert html.index("design-v117.css") < html.index("design-v118.css")
    css_resp = client.get("/static/css/design-v118.css")
    assert css_resp.status_code == 200


def test_v118_mismatch_bands_use_two_row_calc():
    text = _v118_text()
    assert "(min-width: 521px) and (max-width: 570px)" in text
    assert "body.is-logged-in .app-shell" in text
    assert "(min-width: 471px) and (max-width: 520px)" in text
    assert "body:not(.is-logged-in) .app-shell" in text
    assert text.count("calc(100vh - 183px - 48px)") == 2


def test_v118_mobile_only_no_important_no_gradient():
    text = _v118_text()
    assert "!important" not in text
    assert "gradient" not in text
    assert text.count("@media") == 2
    assert text.count("height:") == 2

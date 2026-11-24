from pptx import Presentation

from control_tower import golden
from control_tower.data import load_scenario
from control_tower.deck import build_deck
from control_tower.engine import find_risks
from control_tower.powerbi import export_star


def test_deck_has_eight_slides_and_synthetic_banner(tmp_path):
    data = load_scenario(golden.SCEN_DIR / "test" / "111")
    path = build_deck(data, find_risks(data), tmp_path / "d.pptx", "2026-05")
    prs = Presentation(path)
    assert len(prs.slides) == 8
    for slide in prs.slides:
        text = " ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)
        assert "SYNTHETIC" in text


def test_star_schema_tables(tmp_path):
    data = load_scenario(golden.SCEN_DIR / "test" / "111")
    paths = export_star(data, find_risks(data), tmp_path)
    names = {p.stem for p in paths}
    assert {"dim_partner", "dim_product", "dim_date", "fact_delivery", "fact_risk"} <= names
    assert (tmp_path / "DAX_measures.md").exists()

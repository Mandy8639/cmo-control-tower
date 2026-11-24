"""Recalculate the generated workbook (no Excel needed) and check it matches the Python scorecard."""

import math
import warnings

import pytest

from control_tower import golden
from control_tower.config import PARTNERS
from control_tower.data import load_scenario
from control_tower.engine import find_risks
from control_tower.excel_pack import build_workbook
from control_tower.kpis import scorecard

COLS = {"B": "deliveries", "C": "otif", "F": "rft", "H": "capa_on_time", "I": "actions_on_time", "J": "cost_variance", "K": "overdue_actions_open"}


@pytest.mark.parametrize("seed,month", [(105, "2026-05"), (110, "2026-03")])
def test_workbook_formulas_match_python(tmp_path, seed, month):
    formulas = pytest.importorskip("formulas")
    data = load_scenario(golden.SCEN_DIR / "test" / str(seed))
    path = build_workbook(data, find_risks(data), tmp_path / "wb.xlsx", month)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sol = formulas.ExcelModel().loads(str(path)).finish().calculate()
    cells = {k.split("!")[1]: v.value[0][0] for k, v in sol.items() if "]SCORECARD'!" in k.upper()}
    sc = scorecard(data).set_index(["partner", "month"])
    for row, p in enumerate(PARTNERS, start=5):
        expected = sc.loc[(p.partner_id, month)]
        for col, kpi in COLS.items():
            want, got = expected[kpi], cells.get(f"{col}{row}")
            if want is None or (isinstance(want, float) and math.isnan(want)):
                assert got in ("", None) or (isinstance(got, float) and math.isnan(got)) or p.kind == "CPO", (p.partner_id, kpi, got)
                continue
            assert got == pytest.approx(float(want), abs=1e-9), (p.partner_id, kpi, got, want)

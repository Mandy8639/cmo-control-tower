"""Baseline: a plain monthly red/amber/green scorecard, the way many teams start.

Every red cell becomes a finding for that partner and month. No data validation, no root
cause, no clustering. Loads the raw batch report, bad rows included.
"""

from __future__ import annotations

import pandas as pd

from .config import SAFETY_STOCK_WEEKS
from .data import Data
from .engine import Finding
from .kpis import scorecard

RED_TO_CATEGORY = {
    "otif_status": "late_supply",
    "rft_status": "quality_drift",
    "capa_status": "capa_overdue",
    "actions_status": "overdue_actions",
    "cost_status": "price_variance",
}


def baseline_findings(data: Data) -> list[Finding]:
    raw = Data(tables={**data.tables, "batches": data["batches_raw"]}, quarantine=data.quarantine.iloc[0:0], as_of=data.as_of)
    sc = scorecard(raw)
    out: list[Finding] = []
    for _, r in sc.iterrows():
        p = pd.Period(r.month)
        for col, cat in RED_TO_CATEGORY.items():
            if r[col] == "red":
                out.append(Finding(cat, r.partner, p.start_time.date().isoformat(), p.end_time.date().isoformat(), None, "medium", f"{col} red in {r.month}"))
    inv = data["inventory"].merge(data["products"][["material", "forecast_weekly_th"]], on="material")
    inv = inv[inv.closing_th < SAFETY_STOCK_WEEKS * inv.forecast_weekly_th]
    for (sku, month), g in inv.groupby([inv.material, inv.week_start.dt.to_period("M")]):
        out.append(
            Finding(
                "inventory_risk",
                str(sku),
                g.week_start.min().date().isoformat(),
                g.week_start.max().date().isoformat(),
                None,
                "medium",
                f"below safety stock in {month}",
            )
        )
    return out

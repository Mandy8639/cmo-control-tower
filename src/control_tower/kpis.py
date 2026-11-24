"""Delivery facts and the monthly partner scorecard (the KPI dictionary lives in docs/kpi_dictionary.md)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PARTNER_BY_ID, PARTNERS, SAFETY_STOCK_WEEKS, TOLERANCE_DAYS
from .data import Data

IN_FULL = 0.95  # delivered quantity must be at least 95% of the promised quantity
ACTION_TARGET = 0.90
COST_VARIANCE_LIMIT = 0.02
AMBER_BAND = 0.05

TOL = pd.Timedelta(days=TOLERANCE_DAYS)


def _days(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a - b).dt.days


def delivery_facts(data: Data) -> pd.DataFrame:
    """One row per delivery due by the as-of date, with OTIF flags and the delay at each stage."""
    d = data["deliveries"].copy()
    d = d[d.promised <= data.as_of]
    b = data["batches"].dropna(subset=["batch_id"]).drop_duplicates("batch_id", keep="last").set_index("batch_id")
    rec = data["material_receipts"].set_index("batch_id")
    pk = data["packaging_orders"].set_index("batch_id")
    dev = data["deviations"]
    as_of = data.as_of

    d["delivered_or_asof"] = d.delivered.fillna(as_of)
    d["late_days"] = _days(d.delivered_or_asof, d.promised).clip(lower=0)
    d["on_time"] = d.delivered.notna() & (d.delivered <= d.promised + TOL)
    d["in_full"] = d.qty_delivered.fillna(0) >= IN_FULL * d.qty_promised
    d["otif"] = d.on_time & d.in_full

    def stage(row: pd.Series) -> pd.Series:
        bid = row.batch_id
        out = {"material_delay": 0, "capacity_delay": 0, "release_delay": 0, "packaging_delay": 0, "short_qty": False, "deviation": False}
        if bid in rec.index:
            r = rec.loc[bid]
            actual = r.actual_receipt if pd.notna(r.actual_receipt) else as_of
            out["material_delay"] = max(0, (actual - r.planned_receipt).days)
        if bid in b.index:
            x = b.loc[bid]
            ready = max(
                x.planned_start, (rec.loc[bid].actual_receipt + pd.Timedelta(days=1)) if bid in rec.index and pd.notna(rec.loc[bid].actual_receipt) else x.planned_start
            )
            start = x.actual_start if pd.notna(x.actual_start) else as_of
            out["capacity_delay"] = max(0, (start - ready).days)
            if pd.notna(x.qty_made) and x.qty_made < 0.9 * x.qty_planned:
                out["short_qty"] = True
            target = PARTNER_BY_ID[x.partner].release_days_target
            if pd.notna(x.mfg_end):
                rel = x.qa_release if pd.notna(x.qa_release) else as_of
                out["release_delay"] = max(0, (rel - x.mfg_end).days - target)
            out["deviation"] = bool((dev.batch_id == bid).any())
        if bid in pk.index:
            p = pk.loc[bid]
            if pd.notna(p.received):
                done = p.completed if pd.notna(p.completed) else as_of
                out["packaging_delay"] = max(0, (done - p.due).days)
        return pd.Series(out)

    if len(d):
        d = pd.concat([d.reset_index(drop=True), d.apply(stage, axis=1).reset_index(drop=True)], axis=1)
    else:
        for c in ["material_delay", "capacity_delay", "release_delay", "packaging_delay", "short_qty", "deviation"]:
            d[c] = []
    d["month"] = d.promised.dt.to_period("M").astype(str)
    return d


def _rag(value: float | None, target: float, higher_is_better: bool = True) -> str:
    if value is None or np.isnan(value):
        return "n/a"
    if higher_is_better:
        return "green" if value >= target else ("amber" if value >= target - AMBER_BAND else "red")
    return "green" if value <= target else ("amber" if value <= target + AMBER_BAND / 2 else "red")


def _share(mask: pd.Series) -> float:
    return float(mask.mean()) if len(mask) else float("nan")


def scorecard(data: Data) -> pd.DataFrame:
    """Monthly KPIs per partner with red/amber/green status against agreement targets."""
    facts = delivery_facts(data)
    b = data["batches"]
    dev_batches = set(data["deviations"].batch_id)
    pk = data["packaging_orders"]
    capas = data["capas"]
    acts = data["actions"]
    inv = data["invoices"]
    as_of = data.as_of
    months = pd.period_range(data["inventory"].week_start.min(), as_of - pd.Timedelta(days=1), freq="M").astype(str)

    rows = []
    for p in PARTNERS:
        for m in months:
            mstart = pd.Period(m).start_time
            mend = min(pd.Period(m).end_time.normalize(), as_of)
            row: dict = {"partner": p.partner_id, "month": m}
            if p.kind == "CMO":
                f = facts[(facts.partner == p.partner_id) & (facts.month == m)]
                row["deliveries"] = len(f)
                row["otif"] = _share(f.otif)
                bb = b[(b.partner == p.partner_id) & (b.planned_start.dt.to_period("M").astype(str) == m) & b.actual_start.notna()]
                row["schedule_adherence"] = _share((bb.actual_start - bb.planned_start).dt.days.abs() <= 2)
                made = b[(b.partner == p.partner_id) & (b.mfg_end.dt.to_period("M").astype(str) == m)]
                row["rft"] = _share(~made.batch_id.isin(dev_batches))
                rel = made.dropna(subset=["qa_release"])
                row["release_days"] = float((rel.qa_release - rel.mfg_end).dt.days.mean()) if len(rel) else float("nan")
            else:
                f = pk[(pk.due.dt.to_period("M").astype(str) == m) & (pk.due <= as_of) & pk.received.notna()]
                row["deliveries"] = len(f)
                row["otif"] = _share(f.completed.notna() & (f.completed <= f.due + TOL))
                row["schedule_adherence"] = float("nan")
                row["rft"] = float("nan")
                done = f.dropna(subset=["completed"])
                row["release_days"] = float((done.completed - done.received).dt.days.mean()) if len(done) else float("nan")
            c = capas[(capas.partner == p.partner_id) & (capas.due.dt.to_period("M").astype(str) == m) & (capas.due <= as_of)]
            row["capa_on_time"] = _share(c.closed.notna() & (c.closed <= c.due))
            a = acts[(acts.partner == p.partner_id) & (acts.due.dt.to_period("M").astype(str) == m) & (acts.due <= as_of)]
            row["actions_on_time"] = _share(a.closed.notna() & (a.closed <= a.due))
            open_overdue = acts[(acts.partner == p.partner_id) & (acts.due < mend) & (acts.closed.isna() | (acts.closed > mend))]
            row["overdue_actions_open"] = int(len(open_overdue))
            i = inv[(inv.partner == p.partner_id) & (inv.invoice_date >= mstart) & (inv.invoice_date <= mend)]
            base = (i.contract_price * i.qty_th).sum()
            row["cost_variance"] = float(((i.billed_price - i.contract_price) * i.qty_th).sum() / base) if base else float("nan")

            row["otif_status"] = _rag(row["otif"], p.otif_target)
            row["rft_status"] = _rag(row["rft"], p.rft_target)
            row["release_status"] = _rag(row["release_days"], p.release_days_target, higher_is_better=False) if not np.isnan(row["release_days"]) else "n/a"
            if row["release_status"] != "n/a":
                rd, t = row["release_days"], p.release_days_target
                row["release_status"] = "green" if rd <= t else ("amber" if rd <= t + 2 else "red")
            row["capa_status"] = _rag(row["capa_on_time"], p.capa_on_time_target)
            row["actions_status"] = _rag(row["actions_on_time"], ACTION_TARGET)
            row["cost_status"] = _rag(row["cost_variance"], COST_VARIANCE_LIMIT, higher_is_better=False)
            rows.append(row)
    return pd.DataFrame(rows)


def weeks_of_supply(data: Data) -> pd.DataFrame:
    inv = data["inventory"].merge(data["products"][["material", "description", "forecast_weekly_th", "cmo"]], on="material")
    inv["weeks_of_supply"] = inv.closing_th / inv.forecast_weekly_th
    inv["below_safety_stock"] = inv.weeks_of_supply < SAFETY_STOCK_WEEKS
    return inv


def action_ageing(data: Data) -> pd.DataFrame:
    a = data["actions"]
    open_ = a[a.closed.isna()].copy()
    open_["days_overdue"] = (data.as_of - open_.due).dt.days
    open_ = open_[open_.days_overdue > 0]
    open_["bucket"] = pd.cut(open_.days_overdue, [0, 7, 14, 30, 10_000], labels=["1-7 days", "8-14 days", "15-30 days", ">30 days"])
    return open_.sort_values("days_overdue", ascending=False)

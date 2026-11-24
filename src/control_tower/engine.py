"""Risk findings with evidence and a root cause.

Each finding names a category, the partner or SKU, a date window, a root cause where one
applies, a severity, and the rows that support it. Rules were tuned on the dev split only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from .config import PARTNER_BY_ID, SAFETY_STOCK_WEEKS
from .data import Data
from .kpis import delivery_facts, weeks_of_supply

CPO_ID = "CPO-ECHO"

CAUSE_LABEL = {
    "material": "Material availability (active ingredient received late)",
    "capacity": "Capacity loss at the manufacturer (late starts, short batches)",
    "quality": "QA release held by open deviations",
    "packaging": "Packaging capacity at the contract packager",
    "demand_above_forecast": "Demand above forecast",
    "late_supply": "Late or short supply",
    "unexplained": "No supporting signal found",
}


@dataclass
class Finding:
    category: str
    entity: str
    start: str
    end: str
    cause: str | None
    severity: str
    summary: str
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _clusters(dates: pd.Series, gap_days: int) -> list[list[int]]:
    """Group row positions whose sorted dates are at most gap_days apart."""
    order = dates.sort_values()
    groups: list[list[int]] = []
    prev = None
    for idx, dt in order.items():
        if prev is None or (dt - prev).days > gap_days:
            groups.append([])
        groups[-1].append(idx)
        prev = dt
    return groups


def _iso(ts: pd.Timestamp) -> str:
    return ts.date().isoformat()


def late_supply(data: Data, facts: pd.DataFrame) -> list[Finding]:
    late = facts[~facts.otif].copy()
    if late.empty:
        return []

    def cause(r: pd.Series) -> str:
        scores = {
            "material": r.material_delay,
            "capacity": r.capacity_delay + (10 if r.short_qty else 0),
            "quality": r.release_delay + (3 if r.deviation and r.release_delay > 0 else 0),
            "packaging": r.packaging_delay,
        }
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "unexplained"

    late["cause"] = late.apply(cause, axis=1)
    late["responsible"] = late.apply(lambda r: CPO_ID if r.cause == "packaging" else r.partner, axis=1)
    out: list[Finding] = []
    for (resp, c), g in late.groupby(["responsible", "cause"]):
        for grp in _clusters(g.promised, 21):
            rows = g.loc[grp]
            if len(rows) < 2 and rows.late_days.max() < 7 and not rows.short_qty.any():
                continue
            skus = sorted(rows.material.unique())
            sev = "high" if len(rows) >= 3 or rows.late_days.max() >= 14 else "medium"
            out.append(
                Finding(
                    category="late_supply",
                    entity=resp,
                    start=_iso(rows.promised.min()),
                    end=_iso(rows.promised.max()),
                    cause=c,
                    severity=sev,
                    summary=(
                        f"{len(rows)} late or short deliveries from {resp} ({', '.join(skus)}); up to {int(rows.late_days.max())} days late. Likely cause: {CAUSE_LABEL[c]}."
                    ),
                    evidence=rows.delivery_id.tolist(),
                )
            )
    return out


def quality_drift(data: Data) -> list[Finding]:
    dev = data["deviations"].copy()
    if dev.empty:
        return []
    dev["days_open"] = (dev.closed.fillna(data.as_of) - dev.opened).dt.days
    out = []
    for partner, g in dev.groupby("partner"):
        for grp in _clusters(g.opened, 28):
            rows = g.loc[grp]
            # two or more deviations open >10 days on average, or one open 12+ days that held release
            held = rows.batch_id.isin(data["batches"][(data["batches"].qa_release - data["batches"].mfg_end).dt.days > PARTNER_BY_ID[partner].release_days_target].batch_id)
            if (len(rows) >= 2 and rows.days_open.mean() > 10) or (rows.days_open.max() >= 12 and held.any()):
                out.append(
                    Finding(
                        "quality_drift",
                        partner,
                        _iso(rows.opened.min()),
                        _iso(rows.opened.max()),
                        "quality",
                        "high" if len(rows) >= 3 else "medium",
                        f"{len(rows)} deviations opened at {partner} in {(rows.opened.max() - rows.opened.min()).days + 1} days, open {rows.days_open.mean():.0f} days on average; batch release at risk.",
                        rows.deviation_id.tolist(),
                    )
                )
    return out


def _overdue(df: pd.DataFrame, as_of: pd.Timestamp, min_days: int = 1) -> pd.DataFrame:
    """Items closed at least min_days after due, or still open that long past due."""
    df = df[df.due <= as_of]
    late_by = (df.closed.fillna(as_of) - df.due).dt.days
    return df[late_by >= min_days]


def capa_overdue(data: Data) -> list[Finding]:
    od = _overdue(data["capas"], data.as_of, min_days=10)
    out = []
    for partner, g in od.groupby("partner"):
        for grp in _clusters(g.due, 30):
            rows = g.loc[grp]
            if len(rows) >= 2:
                out.append(
                    Finding(
                        "capa_overdue",
                        partner,
                        _iso(rows.due.min()),
                        _iso(rows.due.max()),
                        None,
                        "high" if rows.closed.isna().any() or len(rows) >= 3 else "medium",
                        f"{len(rows)} CAPAs at {partner} closed late or still open past due.",
                        rows.capa_id.tolist(),
                    )
                )
    return out


def overdue_actions(data: Data) -> list[Finding]:
    od = _overdue(data["actions"], data.as_of, min_days=7)
    out = []
    for partner, g in od.groupby("partner"):
        for grp in _clusters(g.due, 21):
            rows = g.loc[grp]
            if len(rows) >= 3:
                out.append(
                    Finding(
                        "overdue_actions",
                        partner,
                        _iso(rows.due.min()),
                        _iso(rows.due.max()),
                        None,
                        "medium",
                        f"{len(rows)} action items with {partner} missed their due date ({', '.join(sorted(rows.topic.unique()))}).",
                        rows.action_id.tolist(),
                    )
                )
    return out


def price_variance(data: Data) -> list[Finding]:
    inv = data["invoices"].copy()
    inv["variance"] = inv.billed_price / inv.contract_price - 1
    over = inv[inv.variance > 0.03]
    out = []
    for partner, g in over.groupby("partner"):
        for grp in _clusters(g.invoice_date, 35):
            rows = g.loc[grp]
            if len(rows) >= 2 or rows.variance.max() > 0.05:
                extra = float(((rows.billed_price - rows.contract_price) * rows.qty_th).sum())
                out.append(
                    Finding(
                        "price_variance",
                        partner,
                        _iso(rows.invoice_date.min()),
                        _iso(rows.invoice_date.max()),
                        None,
                        "medium",
                        f"{len(rows)} invoices from {partner} billed {rows.variance.mean():.1%} above contract price on average (about ${extra:,.0f} over contract, synthetic).",
                        rows.invoice_id.tolist(),
                    )
                )
    return out


def inventory_risk(data: Data, facts: pd.DataFrame) -> list[Finding]:
    wos = weeks_of_supply(data)
    out = []
    for sku, g in wos.groupby("material"):
        g = g.sort_values("week_start").reset_index(drop=True)
        below = g[g.below_safety_stock]
        if below.empty:
            continue
        for grp in _clusters(below.week_start, 7):
            rows = below.loc[grp]
            first = rows.week_start.min()
            window = g[(g.week_start >= first - pd.Timedelta(days=28)) & (g.week_start <= first)]
            ratio = window.demand_th.sum() / (window.forecast_weekly_th.sum() or 1)
            late = facts[(facts.material == sku) & ~facts.otif & (facts.promised >= first - pd.Timedelta(days=42)) & (facts.promised <= rows.week_start.max())]
            cause = "demand_above_forecast" if ratio > 1.25 else ("late_supply" if len(late) else "unexplained")
            out.append(
                Finding(
                    "inventory_risk",
                    str(sku),
                    _iso(first),
                    _iso(rows.week_start.max()),
                    cause,
                    "high" if rows.weeks_of_supply.min() < SAFETY_STOCK_WEEKS / 2 else "medium",
                    f"{g.description.iloc[0]} fell to {rows.weeks_of_supply.min():.1f} weeks of supply (safety stock {SAFETY_STOCK_WEEKS:.0f}); "
                    f"demand ran at {ratio:.0%} of forecast in the 4 weeks before. Likely cause: {CAUSE_LABEL[cause]}.",
                    [f"{sku}@{_iso(w)}" for w in rows.week_start] + late.delivery_id.tolist(),
                )
            )
    return out


def data_quality(data: Data) -> list[Finding]:
    q = data.quarantine
    out = []
    for partner, g in q.groupby("partner"):
        out.append(
            Finding(
                "data_quality",
                partner,
                "",
                "",
                None,
                "medium",
                f"{len(g)} rows in {partner}'s batch report quarantined ({', '.join(f'{k}: {v}' for k, v in g.reason.value_counts().items())}); ask the partner to resubmit.",
                g.row_uid.tolist(),
            )
        )
    return out


def find_risks(data: Data) -> list[Finding]:
    facts = delivery_facts(data)
    findings = (
        late_supply(data, facts) + quality_drift(data) + capa_overdue(data) + overdue_actions(data) + price_variance(data) + inventory_risk(data, facts) + data_quality(data)
    )
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda f: (order[f.severity], f.category, f.entity))


def escalations(findings: list[Finding]) -> list[Finding]:
    """What goes to External Manufacturing leadership: every high-severity supply or stock risk."""
    return [f for f in findings if f.severity == "high" and f.category in ("late_supply", "inventory_risk", "quality_drift", "capa_overdue")]


def partner_name(pid: str) -> str:
    return PARTNER_BY_ID[pid].name if pid in PARTNER_BY_ID else pid

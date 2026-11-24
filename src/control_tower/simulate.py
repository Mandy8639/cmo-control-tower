"""Seeded simulator for a fictional external-manufacturing network.

It produces the files an analyst would receive from contract manufacturers (CMOs) and a
contract packager (CPO), plus a separate ground truth of the problems it planted.

Determinism rule: every random number is drawn whether or not an issue is active, so a
counterfactual run (same seed, one issue removed) differs only by that issue's effects.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import (
    CMO_BY_FAMILY,
    PARTNER_BY_ID,
    PARTNERS,
    SAFETY_STOCK_WEEKS,
    SIM_START,
    SIM_WEEKS,
)
from .products import Product, brand_portfolio, load_products

HORIZON = SIM_WEEKS * 7
START = date.fromisoformat(SIM_START)
CPO_ID = "CPO-ECHO"

ISSUE_TYPES = (
    "api_supply_delay",  # CMO: active ingredient arrives late, batches start late
    "capacity_loss",  # CMO or CPO: line down, batches late and short
    "deviation_backlog",  # CMO: deviations hold QA release
    "capa_overdue",  # any partner: CAPAs closed after due date
    "overdue_actions",  # any partner: VPT action items not closed on time
    "price_variance",  # CMO: invoices above contract price
    "demand_spike",  # SKU: demand well above forecast, stock falls below safety stock
    "bad_data",  # CMO: malformed rows in the batch report
)


@dataclass(frozen=True)
class Issue:
    issue_id: str
    type: str
    entity: str  # partner_id, or product_ndc for demand_spike
    start: int  # day offset, inclusive
    end: int  # day offset, inclusive
    magnitude: float = 1.0


@dataclass
class Scenario:
    seed: int
    tables: dict[str, pd.DataFrame]
    issues: list[Issue]
    bad_row_uids: list[str] = field(default_factory=list)


def day(d: int | float | None) -> str | None:
    if d is None or (isinstance(d, float) and np.isnan(d)):
        return None
    return (START + timedelta(days=int(d))).isoformat()


def portfolio() -> list[Product]:
    return brand_portfolio(load_products())


# ---------------------------------------------------------------- issue draw


def draw_issues(seed: int, n_min: int = 3, n_max: int = 4) -> list[Issue]:
    rng = np.random.default_rng(seed * 7919 + 17)
    cmos = [p.partner_id for p in PARTNERS if p.kind == "CMO"]
    skus = [p.product_ndc for p in portfolio()]
    n = int(rng.integers(n_min, n_max + 1))
    types = list(rng.choice(ISSUE_TYPES, size=n, replace=False))
    issues: list[Issue] = []
    used: set[tuple[str, str]] = set()
    for i, t in enumerate(types, start=1):
        for _ in range(50):
            if t == "demand_spike":
                entity = str(rng.choice(skus))
            elif t == "capacity_loss":
                entity = str(rng.choice(cmos + [CPO_ID]))
            elif t in ("capa_overdue", "overdue_actions"):
                entity = str(rng.choice(cmos + [CPO_ID]))
            else:
                entity = str(rng.choice(cmos))
            # one supply-delay type per partner, so the true cause is unambiguous
            supply = t in ("api_supply_delay", "capacity_loss", "deviation_backlog")
            key = ("supply" if supply else t, entity)
            if key not in used:
                used.add(key)
                break
        weeks = int(rng.integers(3, 5)) if t == "capacity_loss" else int(rng.integers(5, 9))
        start_week = int(rng.integers(3, SIM_WEEKS - weeks - 6))
        start = start_week * 7
        end = start + weeks * 7 - 1
        issues.append(Issue(f"I{i}", str(t), entity, start, end, round(float(rng.uniform(0.0, 1.0)), 3)))
    return issues


def _active(issues: list[Issue], kind: str, entity: str, d: int) -> Issue | None:
    for iss in issues:
        if iss.type == kind and iss.entity == entity and iss.start <= d <= iss.end:
            return iss
    return None


# ---------------------------------------------------------------- simulation


def simulate(seed: int, issues: list[Issue]) -> Scenario:
    rng = np.random.default_rng(seed)
    products = portfolio()

    product_rows = []
    demand_mean: dict[str, float] = {}
    for p in products:
        d = float(round(rng.uniform(20, 80), 1))
        demand_mean[p.product_ndc] = d
        product_rows.append(
            {
                "material": p.product_ndc,
                "description": f"{p.brand_name} ({p.generic_name})" if p.generic_name else p.brand_name,
                "dosage_form": p.dosage_form,
                "family": p.family,
                "cmo": CMO_BY_FAMILY[p.family].partner_id,
                "cpo": CPO_ID,
                "forecast_weekly_th": d,
                "safety_stock_weeks": SAFETY_STOCK_WEEKS,
            }
        )

    receipts, batches, deviations, pack, deliveries, invoices, downtime = [], [], [], [], [], [], []

    # Planned maintenance noise: one short stop per CMO, sometimes.
    for p in PARTNERS:
        u = rng.uniform(size=3)
        if u[0] < 0.5:
            s = int(u[1] * (HORIZON - 10))
            downtime.append({"partner": p.partner_id, "line": "L1", "start": s, "end": s + 1 + int(u[2] * 2), "reason": "planned maintenance"})
    for iss in issues:
        if iss.type == "capacity_loss":
            downtime.append({"partner": iss.entity, "line": "L2", "start": iss.start, "end": iss.end, "reason": "unplanned equipment failure"})

    batch_no = 0
    for p in products:
        cmo = CMO_BY_FAMILY[p.family]
        cpo = PARTNER_BY_ID[CPO_ID]
        offset = int(rng.integers(0, 28))
        starts = list(range(offset, HORIZON - 30, 28))
        for ps in starts:
            batch_no += 1
            u = rng.uniform(size=16)  # fixed draw count per batch
            batch_id = f"B{cmo.plant}{batch_no:04d}"
            po = f"45{seed:03d}{batch_no:05d}"
            qty_planned = round(4 * demand_mean[p.product_ndc], 1)

            planned_receipt = ps - 5
            late_noise = int(1 + u[0] * 6) if u[1] < 0.08 else 0
            api = _active(issues, "api_supply_delay", cmo.partner_id, ps)
            api_delay = int(8 + u[2] * 9) if api else 0
            actual_receipt = planned_receipt + late_noise + api_delay
            receipts.append(
                {
                    "partner": cmo.partner_id,
                    "po_number": po,
                    "batch_id": batch_id,
                    "component": f"API-{p.product_ndc}",
                    "planned_receipt": planned_receipt,
                    "actual_receipt": actual_receipt,
                }
            )

            actual_start = max(ps, actual_receipt + 1)
            for dt in downtime:
                if dt["partner"] == cmo.partner_id and dt["reason"] == "planned maintenance" and dt["start"] <= actual_start <= dt["end"]:
                    actual_start = dt["end"] + 1
            cap = _active(issues, "capacity_loss", cmo.partner_id, ps)
            yield_ = 0.98 + u[3] * 0.02
            if cap:
                actual_start += int(4 + u[4] * 7)
                yield_ *= 0.55 + u[5] * 0.15
            mfg_end = actual_start + 3
            qty_made = round(qty_planned * yield_, 1)

            release = mfg_end + cmo.release_days_target + int(-3 + u[6] * 4)
            backlog = _active(issues, "deviation_backlog", cmo.partner_id, mfg_end)
            dev_p = 0.75 if backlog else 0.04
            if u[7] < dev_p:
                close = mfg_end + (int(12 + u[8] * 14) if backlog else int(3 + u[8] * 5))
                deviations.append(
                    {
                        "deviation_id": f"DEV-{seed:03d}-{batch_no:04d}",
                        "partner": cmo.partner_id,
                        "batch_id": batch_id,
                        "opened": mfg_end,
                        "closed": close if close <= HORIZON else None,
                        "category": ["process", "equipment", "documentation", "environmental"][int(u[9] * 4)],
                        "severity": "major" if backlog else "minor",
                    }
                )
                release = max(release, close + 1)

            received = release + 1
            pack_due = received + cpo.release_days_target
            completed = pack_due + int(-1 + u[10] * 2)
            pcap = _active(issues, "capacity_loss", CPO_ID, received)
            if pcap:
                completed += int(5 + u[11] * 6)
            delivered = completed + 2
            promised = ps + 3 + cmo.release_days_target + 1 + cpo.release_days_target + 2
            qty_delivered = round(qty_made * (0.985 + u[12] * 0.01), 1)

            batches.append(
                {
                    "partner": cmo.partner_id,
                    "plant": cmo.plant,
                    "batch_id": batch_id,
                    "material": p.product_ndc,
                    "po_number": po,
                    "planned_start": ps,
                    "actual_start": actual_start if actual_start <= HORIZON else None,
                    "mfg_end": mfg_end if mfg_end <= HORIZON else None,
                    "qty_planned": qty_planned,
                    "qty_made": qty_made if mfg_end <= HORIZON else None,
                    "uom": "TH",
                    "qa_release": release if release <= HORIZON else None,
                }
            )
            pack.append(
                {
                    "order_id": f"PK-{seed:03d}-{batch_no:04d}",
                    "partner": CPO_ID,
                    "batch_id": batch_id,
                    "material": p.product_ndc,
                    "received": received if received <= HORIZON else None,
                    "due": pack_due,
                    "completed": completed if completed <= HORIZON else None,
                }
            )
            deliveries.append(
                {
                    "delivery_id": f"DL-{seed:03d}-{batch_no:04d}",
                    "batch_id": batch_id,
                    "partner": cmo.partner_id,
                    "material": p.product_ndc,
                    "promised": promised,
                    "delivered": delivered if delivered <= HORIZON else None,
                    "qty_promised": qty_planned,
                    "qty_delivered": qty_delivered if delivered <= HORIZON else None,
                }
            )
            if delivered <= HORIZON:
                pv = _active(issues, "price_variance", cmo.partner_id, delivered)
                bump = 1 + (0.06 + u[13] * 0.06 if pv else 0.0) + (u[14] - 0.5) * 0.016
                invoices.append(
                    {
                        "invoice_id": f"INV-{seed:03d}-{batch_no:04d}",
                        "partner": cmo.partner_id,
                        "batch_id": batch_id,
                        "invoice_date": delivered,
                        "qty_th": qty_delivered,
                        "contract_price": cmo.unit_price,
                        "billed_price": round(cmo.unit_price * bump, 2),
                    }
                )
                invoices.append(
                    {
                        "invoice_id": f"INV-{seed:03d}-{batch_no:04d}P",
                        "partner": CPO_ID,
                        "batch_id": batch_id,
                        "invoice_date": delivered,
                        "qty_th": qty_delivered,
                        "contract_price": cpo.unit_price,
                        "billed_price": round(cpo.unit_price * (1 + (u[15] - 0.5) * 0.016), 2),
                    }
                )

    capas = _capas(rng, issues, seed)
    actions = _actions(rng, issues, seed)
    inventory = _inventory(rng, issues, products, demand_mean, deliveries)

    tables = {
        "products": pd.DataFrame(product_rows),
        "partners": pd.DataFrame([asdict(p) for p in PARTNERS]),
        "material_receipts": _dates(pd.DataFrame(receipts), ["planned_receipt", "actual_receipt"]),
        "downtime": _dates(pd.DataFrame(downtime), ["start", "end"]),
        "batches": _dates(pd.DataFrame(batches), ["planned_start", "actual_start", "mfg_end", "qa_release"]),
        "deviations": _dates(
            pd.DataFrame(deviations, columns=["deviation_id", "partner", "batch_id", "opened", "closed", "category", "severity"]), ["opened", "closed"]
        ),
        "packaging_orders": _dates(pd.DataFrame(pack), ["received", "due", "completed"]),
        "deliveries": _dates(pd.DataFrame(deliveries), ["promised", "delivered"]),
        "invoices": _dates(pd.DataFrame(invoices), ["invoice_date"]),
        "capas": _dates(capas, ["opened", "due", "closed"]),
        "actions": _dates(actions, ["created", "due", "closed"]),
        "inventory": inventory,
    }
    scen = Scenario(seed=seed, tables=tables, issues=issues)
    _inject_bad_rows(scen, np.random.default_rng(seed + 50_000))
    return scen


def _dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df:
            df[c] = df[c].map(lambda v: day(v) if v is not None and not pd.isna(v) else None)
    return df


def _capas(rng: np.random.Generator, issues: list[Issue], seed: int) -> pd.DataFrame:
    rows = []
    n = 0
    for p in PARTNERS:
        for k in range(SIM_WEEKS // 2):
            n += 1
            u = rng.uniform(size=5)
            opened = k * 14 + int(u[0] * 7)
            due = opened + 30
            on_time = u[1] < 0.95
            closed = opened + int(10 + u[2] * 19) if on_time else due + int(2 + u[3] * 7)
            if _active(issues, "capa_overdue", p.partner_id, due) and u[4] < 0.85:
                closed = due + int(10 + u[3] * 30)
            rows.append(
                {
                    "capa_id": f"CAPA-{seed:03d}-{n:04d}",
                    "partner": p.partner_id,
                    "source": ["deviation", "audit", "complaint", "trend"][int(u[0] * 4)],
                    "opened": opened,
                    "due": due,
                    "closed": closed if closed <= HORIZON else None,
                }
            )
    return pd.DataFrame(rows)


def _actions(rng: np.random.Generator, issues: list[Issue], seed: int) -> pd.DataFrame:
    topics = ["recovery plan", "schedule confirmation", "material status", "deviation update", "artwork change", "capacity plan"]
    owners = ["Supplier", "External Mfg", "Quality Ops", "Tech Services", "Supply Planning"]
    rows = []
    n = 0
    for p in PARTNERS:
        for w in range(SIM_WEEKS):
            n += 1
            u = rng.uniform(size=6)
            created = w * 7 + int(u[0] * 5)
            due = created + 14
            closed = created + int(3 + u[1] * 11) if u[2] < 0.93 else due + int(1 + u[3] * 6)
            if _active(issues, "overdue_actions", p.partner_id, due) and u[4] < 0.75:
                closed = due + int(8 + u[3] * 22)
            rows.append(
                {
                    "action_id": f"ACT-{seed:03d}-{n:04d}",
                    "partner": p.partner_id,
                    "topic": topics[int(u[5] * len(topics))],
                    "owner": owners[int(u[0] * len(owners))],
                    "created": created,
                    "due": due,
                    "closed": closed if closed <= HORIZON else None,
                }
            )
    return pd.DataFrame(rows)


def _inventory(rng, issues, products, demand_mean, deliveries) -> pd.DataFrame:
    rows = []
    for p in products:
        sku = p.product_ndc
        d = demand_mean[sku]
        mine = [x for x in deliveries if x["material"] == sku]
        first = min(x["promised"] for x in mine)
        on_hand = round(d * (first / 7 + 6.5), 1)
        for w in range(SIM_WEEKS):
            u = rng.uniform(size=2)
            dem = d * (0.9 + u[0] * 0.2)
            spike = _active(issues, "demand_spike", sku, w * 7)
            if spike:
                dem *= 1.9 + u[1] * 0.3
            dem = round(dem, 1)
            rec = round(
                sum(x["qty_delivered"] for x in mine if x["delivered"] is not None and w * 7 <= x["delivered"] < w * 7 + 7 and x["delivered"] <= HORIZON), 1
            )
            opening = on_hand
            on_hand = round(max(0.0, opening + rec - dem), 1)
            rows.append(
                {
                    "week_start": day(w * 7),
                    "material": sku,
                    "opening_th": opening,
                    "receipts_th": rec,
                    "demand_th": dem,
                    "closing_th": on_hand,
                }
            )
    return pd.DataFrame(rows)


def _inject_bad_rows(scen: Scenario, rng: np.random.Generator) -> None:
    """Append malformed copies of real rows to one CMO's batch report (bad_data issue)."""
    b = scen.tables["batches"]
    b.insert(0, "row_uid", [f"R{scen.seed:03d}-{i:04d}" for i in range(len(b))])
    bad = [i for i in scen.issues if i.type == "bad_data"]
    extra = []
    for iss in bad:
        mine = b[(b.partner == iss.entity) & b.mfg_end.notna()]
        n = int(rng.integers(6, 11))
        picks = mine.sample(n=min(n, len(mine)), random_state=int(rng.integers(0, 1_000_000)))
        for j, (_, row) in enumerate(picks.iterrows()):
            r = row.to_dict()
            kind = ["duplicate", "missing_batch_id", "end_before_start", "wrong_uom", "release_before_mfg"][j % 5]
            if kind == "missing_batch_id":
                r["batch_id"] = None
            elif kind == "end_before_start":
                r["mfg_end"] = (date.fromisoformat(r["actual_start"]) - timedelta(days=2)).isoformat()
            elif kind == "wrong_uom":
                r["uom"] = "EA"
                r["qty_made"] = round(float(r["qty_made"]) * 1000, 1)
            elif kind == "release_before_mfg" and r["qa_release"]:
                r["qa_release"] = (date.fromisoformat(r["mfg_end"]) - timedelta(days=1)).isoformat()
            r["row_uid"] = f"R{scen.seed:03d}-X{len(extra):03d}"
            extra.append(r)
    if extra:
        scen.bad_row_uids = [r["row_uid"] for r in extra]
        scen.tables["batches"] = pd.concat([b, pd.DataFrame(extra)], ignore_index=True)


# ---------------------------------------------------------------- ground truth


def stock_breaches(inv: pd.DataFrame, products: pd.DataFrame) -> dict[str, list[str]]:
    fc = products.set_index("material")["forecast_weekly_th"]
    out: dict[str, list[str]] = {}
    for sku, g in inv.groupby("material"):
        weeks = g[g.closing_th < SAFETY_STOCK_WEEKS * fc[sku]].week_start.tolist()
        if weeks:
            out[str(sku)] = weeks
    return out


def ground_truth(seed: int, issues: list[Issue]) -> dict:
    full = simulate(seed, issues)
    breaches = stock_breaches(full.tables["inventory"], full.tables["products"])
    causes: dict[str, dict[str, list[str]]] = {}
    for sku, weeks in breaches.items():
        causes[sku] = {}
        for iss in issues:
            cf = simulate(seed, [i for i in issues if i.issue_id != iss.issue_id])
            cf_weeks = set(stock_breaches(cf.tables["inventory"], cf.tables["products"]).get(sku, []))
            removed = [w for w in weeks if w not in cf_weeks]
            if removed:
                causes[sku][iss.issue_id] = removed
    return {
        "seed": seed,
        "issues": [{**asdict(i), "start": day(i.start), "end": day(i.end)} for i in issues],
        "bad_row_uids": full.bad_row_uids,
        "stock_breaches": breaches,
        "breach_causes": causes,
    }

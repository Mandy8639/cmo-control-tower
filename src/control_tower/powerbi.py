"""Power BI-ready star schema: dimension and fact CSVs plus suggested DAX measures."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .data import Data
from .engine import Finding
from .kpis import delivery_facts, weeks_of_supply

DAX = """# Suggested DAX measures (Power BI)

Load every CSV in this folder, then relate fact tables to dim_partner[partner_id],
dim_product[material] and dim_date[date] (single direction, many-to-one).

```
OTIF % =
DIVIDE ( CALCULATE ( COUNTROWS ( fact_delivery ), fact_delivery[otif] = TRUE () ),
         COUNTROWS ( fact_delivery ) )

RFT % =
DIVIDE ( CALCULATE ( COUNTROWS ( fact_batch ), fact_batch[has_deviation] = FALSE () ),
         COUNTROWS ( fact_batch ) )

CAPA on time % =
DIVIDE ( CALCULATE ( COUNTROWS ( fact_capa ), fact_capa[on_time] = TRUE () ),
         COUNTROWS ( fact_capa ) )

Cost variance % =
DIVIDE ( SUMX ( fact_invoice, ( fact_invoice[billed_price] - fact_invoice[contract_price] ) * fact_invoice[qty_th] ),
         SUMX ( fact_invoice, fact_invoice[contract_price] * fact_invoice[qty_th] ) )

Weeks of supply (latest) =
VAR LastWeek = MAX ( fact_inventory[week_start] )
RETURN CALCULATE ( SUM ( fact_inventory[closing_th] ), fact_inventory[week_start] = LastWeek )
     / CALCULATE ( SUM ( dim_product[forecast_weekly_th] ) )
```

Suggested pages: network scorecard (matrix partner x month with OTIF/RFT/CAPA, conditional
formatting vs. dim_partner targets), partner deep dive (OTIF trend + late deliveries table),
supply outlook (weeks of supply by product with a 4-week safety-stock line), risks (fact_risk).

All operational data is synthetic; product names come from openFDA (public domain).
"""


def export_star(data: Data, findings: list[Finding], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    facts = delivery_facts(data)
    dev_batches = set(data["deviations"].batch_id)
    batches = data["batches"].drop(columns=["row_uid"]).assign(has_deviation=lambda d: d.batch_id.isin(dev_batches))
    capas = data["capas"].assign(on_time=lambda d: d.closed.notna() & (d.closed <= d.due))
    actions = data["actions"].assign(on_time=lambda d: d.closed.notna() & (d.closed <= d.due))
    dates = pd.date_range(data["inventory"].week_start.min() - pd.Timedelta(days=60), data.as_of + pd.Timedelta(days=60))
    tables = {
        "dim_partner": data["partners"],
        "dim_product": data["products"],
        "dim_date": pd.DataFrame({"date": dates, "month": dates.to_period("M").astype(str), "week_start": dates.to_period("W-SUN").start_time}),
        "fact_delivery": facts.drop(columns=["delivered_or_asof"]),
        "fact_batch": batches,
        "fact_packaging": data["packaging_orders"],
        "fact_deviation": data["deviations"],
        "fact_capa": capas,
        "fact_action": actions,
        "fact_invoice": data["invoices"],
        "fact_inventory": weeks_of_supply(data),
        "fact_risk": pd.DataFrame([f.to_dict() | {"evidence": ";".join(f.evidence)} for f in findings]),
        "fact_quarantine": data.quarantine,
    }
    paths = []
    for name, df in tables.items():
        p = out / f"{name}.csv"
        df.to_csv(p, index=False, date_format="%Y-%m-%d")
        paths.append(p)
    (out / "DAX_measures.md").write_text(DAX)
    return paths

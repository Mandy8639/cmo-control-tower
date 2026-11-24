"""Load one scenario's observed files and validate the partner batch report.

This module reads only data/scenarios/ (what an analyst would receive), never the
planted truth files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATE_COLS = {
    "material_receipts": ["planned_receipt", "actual_receipt"],
    "downtime": ["start", "end"],
    "batches": ["planned_start", "actual_start", "mfg_end", "qa_release"],
    "deviations": ["opened", "closed"],
    "packaging_orders": ["received", "due", "completed"],
    "deliveries": ["promised", "delivered"],
    "invoices": ["invoice_date"],
    "capas": ["opened", "due", "closed"],
    "actions": ["created", "due", "closed"],
    "inventory": ["week_start"],
}

EXPECTED_UOM = "TH"  # thousand units


@dataclass
class Data:
    tables: dict[str, pd.DataFrame]
    quarantine: pd.DataFrame
    as_of: pd.Timestamp

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]


def load_scenario(path: Path | str) -> Data:
    path = Path(path)
    tables: dict[str, pd.DataFrame] = {}
    for csv in sorted(path.glob("*.csv")):
        name = csv.stem
        df = pd.read_csv(csv, dtype={"material": str, "po_number": str})
        for col in DATE_COLS.get(name, []):
            df[col] = pd.to_datetime(df[col], errors="coerce")
        tables[name] = df
    clean, quarantine = validate_batches(tables["batches"])
    tables["batches_raw"] = tables["batches"]
    tables["batches"] = clean
    as_of = tables["inventory"].week_start.max() + pd.Timedelta(days=7)
    return Data(tables=tables, quarantine=quarantine, as_of=as_of)


def validate_batches(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Quarantine malformed rows with a reason; keep the first copy of each batch."""
    reasons: list[str | None] = []
    seen: set[str] = set()
    for _, r in df.iterrows():
        reason = None
        if pd.isna(r.batch_id) or str(r.batch_id).strip() == "":
            reason = "missing_batch_id"
        elif r.uom != EXPECTED_UOM:
            reason = "wrong_uom"
        elif pd.notna(r.mfg_end) and pd.notna(r.actual_start) and r.mfg_end < r.actual_start:
            reason = "end_before_start"
        elif pd.notna(r.qa_release) and pd.notna(r.mfg_end) and r.qa_release < r.mfg_end:
            reason = "release_before_mfg"
        elif r.batch_id in seen:
            reason = "duplicate"
        if reason is None:
            seen.add(r.batch_id)
        reasons.append(reason)
    flags = pd.Series(reasons, index=df.index)
    quarantine = df[flags.notna()][["row_uid", "partner", "batch_id"]].assign(reason=flags[flags.notna()])
    return df[flags.isna()].reset_index(drop=True), quarantine.reset_index(drop=True)

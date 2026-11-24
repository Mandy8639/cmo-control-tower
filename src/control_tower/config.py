"""Fictional partner network and the agreement targets each partner is measured against.

All partners are invented. They do not represent any real company's suppliers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Partner:
    partner_id: str
    name: str
    kind: str  # "CMO" (manufactures) or "CPO" (packages)
    family: str | None  # dosage family a CMO makes; None for CPOs
    plant: str  # SAP-style plant code
    otif_target: float  # share of deliveries on time and in full
    rft_target: float  # share of batches released without a deviation
    release_days_target: int  # manufacture -> QA release, days
    capa_on_time_target: float
    unit_price: float  # contract price per thousand units (USD, synthetic)


PARTNERS: tuple[Partner, ...] = (
    Partner("CMO-ALPHA", "CMO-Alpha (oral solids)", "CMO", "oral_solid", "EX10", 0.95, 0.97, 10, 0.90, 42.0),
    Partner("CMO-BRAVO", "CMO-Bravo (topicals)", "CMO", "topical", "EX20", 0.95, 0.96, 12, 0.90, 31.0),
    Partner("CMO-CHARLIE", "CMO-Charlie (suppositories)", "CMO", "suppository", "EX30", 0.93, 0.95, 12, 0.90, 27.0),
    Partner("CMO-DELTA", "CMO-Delta (oral liquids)", "CMO", "liquid", "EX40", 0.95, 0.96, 11, 0.90, 36.0),
    Partner("CPO-ECHO", "CPO-Echo (packaging)", "CPO", None, "EX50", 0.97, 0.98, 4, 0.90, 5.5),
)

PARTNER_BY_ID = {p.partner_id: p for p in PARTNERS}
CMO_BY_FAMILY = {p.family: p for p in PARTNERS if p.kind == "CMO"}

SIM_START = "2026-01-05"  # a Monday; synthetic calendar
SIM_WEEKS = 26
SAFETY_STOCK_WEEKS = 4.0
TOLERANCE_DAYS = 2  # up to 2 days after the promise date still counts as on time

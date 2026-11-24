"""Public product master from the openFDA NDC Directory (CC0 public domain).

Data provided by the U.S. Food and Drug Administration (https://open.fda.gov).
Only the product list is real; every operational record in this project is synthetic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "public" / "fda_ndc_products.json"
OPENFDA_URL = "https://api.fda.gov/drug/ndc.json"
LABELER_QUERY = "labeler_name:cosette"

# Dosage-form family decides which (fictional) contract manufacturer makes the product.
FORM_FAMILY = {
    "TABLET": "oral_solid",
    "CAPSULE": "oral_solid",
    "CREAM": "topical",
    "OINTMENT": "topical",
    "GEL": "topical",
    "LOTION": "topical",
    "SUPPOSITORY": "suppository",
    "SOLUTION": "liquid",
    "SUSPENSION": "liquid",
}


@dataclass(frozen=True)
class Product:
    product_ndc: str
    brand_name: str
    generic_name: str
    dosage_form: str
    marketing_category: str
    family: str


def family_for(dosage_form: str) -> str | None:
    head = dosage_form.split(",")[0].strip().upper()
    return FORM_FAMILY.get(head)


def fetch_snapshot(path: Path = SNAPSHOT) -> int:
    """Download the labeler's NDC listings once and store them (run manually)."""
    resp = httpx.get(OPENFDA_URL, params={"search": LABELER_QUERY, "limit": 100}, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    keep = [
        {
            "product_ndc": r.get("product_ndc"),
            "brand_name": r.get("brand_name"),
            "generic_name": r.get("generic_name"),
            "dosage_form": r.get("dosage_form"),
            "marketing_category": r.get("marketing_category"),
            "labeler_name": r.get("labeler_name"),
        }
        for r in body["results"]
    ]
    payload = {
        "source": "openFDA NDC Directory, https://open.fda.gov (CC0 1.0)",
        "query": LABELER_QUERY,
        "last_updated": body["meta"].get("last_updated"),
        "total": body["meta"]["results"]["total"],
        "results": keep,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return len(keep)


def load_products(path: Path = SNAPSHOT) -> list[Product]:
    raw = json.loads(path.read_text())["results"]
    seen: set[tuple[str, str]] = set()
    out: list[Product] = []
    for r in raw:
        fam = family_for(r["dosage_form"] or "")
        if fam is None:
            continue
        key = (r["brand_name"].strip().lower(), r["dosage_form"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Product(
                product_ndc=r["product_ndc"],
                brand_name=r["brand_name"].strip(),
                generic_name=(r["generic_name"] or "").strip(),
                dosage_form=r["dosage_form"],
                marketing_category=r["marketing_category"],
                family=fam,
            )
        )
    return sorted(out, key=lambda p: (p.marketing_category != "NDA", p.brand_name))


def brand_portfolio(products: list[Product], n: int = 14) -> list[Product]:
    """NDA brands first, then other products, keeping every dosage family represented."""
    chosen: list[Product] = []
    by_family: dict[str, list[Product]] = {}
    for p in products:
        by_family.setdefault(p.family, []).append(p)
    for fam in sorted(by_family):
        chosen.append(by_family[fam][0])
    for p in products:
        if len(chosen) >= n:
            break
        if p not in chosen:
            chosen.append(p)
    return sorted(chosen, key=lambda p: p.product_ndc)

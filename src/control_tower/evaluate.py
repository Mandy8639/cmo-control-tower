"""Score findings against the planted ground truth.

This is the only module besides golden.py that reads data/ground_truth/.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import golden
from .baseline import baseline_findings
from .data import load_scenario
from .engine import Finding, find_risks

# issue type -> finding categories that count as catching it, and the correct root cause
MATCH = {
    "api_supply_delay": (("late_supply",), "material"),
    "capacity_loss": (("late_supply",), "capacity"),  # "packaging" when the CPO is the entity
    "deviation_backlog": (("late_supply", "quality_drift"), "quality"),
    "capa_overdue": (("capa_overdue",), None),
    "overdue_actions": (("overdue_actions",), None),
    "price_variance": (("price_variance",), None),
    "demand_spike": (("inventory_risk",), "demand_above_forecast"),
    "bad_data": (("data_quality",), None),
}
# how far after the issue window its effects may still show (days)
LAG = {"late_supply": 45, "quality_drift": 14, "capa_overdue": 7, "overdue_actions": 7, "price_variance": 21, "inventory_risk": 49, "data_quality": 10_000}


def _overlaps(f: Finding, issue: dict) -> bool:
    if f.category == "data_quality":
        return True
    fs, fe = pd.Timestamp(f.start), pd.Timestamp(f.end)
    s, e = pd.Timestamp(issue["start"]) - pd.Timedelta(days=7), pd.Timestamp(issue["end"]) + pd.Timedelta(days=LAG[f.category])
    return fs <= e and fe >= s


def _expected_cause(issue: dict) -> str | None:
    if issue["type"] == "capacity_loss" and issue["entity"].startswith("CPO"):
        return "packaging"
    return MATCH[issue["type"]][1]


@dataclass
class ScenarioResult:
    seed: int
    caught: dict[str, bool] = field(default_factory=dict)  # issue_id -> caught
    cause_right: dict[str, bool] = field(default_factory=dict)  # supply issues only
    false_alarms: list[dict] = field(default_factory=list)
    consequences: int = 0
    findings: int = 0
    bad_rows_true: int = 0
    bad_rows_flagged: int = 0
    bad_rows_correct: int = 0


def score(findings: list[Finding], truth: dict, quarantined: list[str], products: pd.DataFrame) -> ScenarioResult:
    res = ScenarioResult(seed=truth["seed"], findings=len(findings))
    used: set[int] = set()
    for iss in truth["issues"]:
        cats, _ = MATCH[iss["type"]]
        hits = [i for i, f in enumerate(findings) if f.category in cats and f.entity == iss["entity"] and _overlaps(f, iss)]
        res.caught[iss["issue_id"]] = bool(hits)
        used.update(hits)
        if iss["type"] in ("api_supply_delay", "capacity_loss", "deviation_backlog"):
            want = _expected_cause(iss)
            res.cause_right[iss["issue_id"]] = any(findings[i].cause == want for i in hits)
    cmo_of = dict(zip(products.material, products.cmo, strict=True))
    supply_entities = {i["entity"] for i in truth["issues"] if i["type"] in ("api_supply_delay", "capacity_loss", "deviation_backlog")}
    caused = {sku for sku, c in truth["breach_causes"].items() if c}
    for i, f in enumerate(findings):
        if i in used:
            continue
        if f.category == "inventory_risk" and (f.entity in caused or cmo_of.get(f.entity) in supply_entities or "CPO-ECHO" in supply_entities):
            res.consequences += 1  # stock fell because of a planted supply problem: a true downstream signal
            continue
        res.false_alarms.append({"category": f.category, "entity": f.entity, "start": f.start, "end": f.end, "cause": f.cause, "summary": f.summary})
    truth_bad = set(truth["bad_row_uids"])
    flagged = set(quarantined)
    res.bad_rows_true, res.bad_rows_flagged, res.bad_rows_correct = len(truth_bad), len(flagged), len(truth_bad & flagged)
    return res


def run(split: str, system: str = "engine") -> dict:
    per_type: dict[str, Counter] = defaultdict(Counter)
    results = []
    for seed in golden.SPLITS[split]:
        data = load_scenario(golden.SCEN_DIR / split / str(seed))
        truth = golden.load_truth(split, seed)
        findings = find_risks(data) if system == "engine" else baseline_findings(data)
        quarantined = data.quarantine.row_uid.tolist() if system == "engine" else []
        r = score(findings, truth, quarantined, data["products"])
        results.append(r)
        for iss in truth["issues"]:
            per_type[iss["type"]]["planted"] += 1
            per_type[iss["type"]]["caught"] += int(r.caught[iss["issue_id"]])
            if iss["issue_id"] in r.cause_right:
                per_type[iss["type"]]["cause_right"] += int(r.cause_right[iss["issue_id"]])
    planted = sum(len(r.caught) for r in results)
    caught = sum(sum(r.caught.values()) for r in results)
    supply = sum(len(r.cause_right) for r in results)
    cause_ok = sum(sum(r.cause_right.values()) for r in results)
    fa = sum(len(r.false_alarms) for r in results)
    bt, bf, bc = (sum(getattr(r, a) for r in results) for a in ("bad_rows_true", "bad_rows_flagged", "bad_rows_correct"))
    return {
        "split": split,
        "system": system,
        "scenarios": len(results),
        "planted": planted,
        "caught": caught,
        "recall": caught / planted if planted else 0.0,
        "supply_issues": supply,
        "root_cause_correct": cause_ok,
        "false_alarms": fa,
        "false_alarms_per_scenario": fa / len(results),
        "consequence_findings": sum(r.consequences for r in results),
        "findings": sum(r.findings for r in results),
        "bad_rows": {"planted": bt, "quarantined": bf, "correct": bc},
        "per_type": {k: dict(v) for k, v in sorted(per_type.items())},
        "misses": [{"seed": r.seed, "issue_id": k} for r in results for k, v in r.caught.items() if not v],
        "wrong_cause": [{"seed": r.seed, "issue_id": k} for r in results for k, v in r.cause_right.items() if not v],
        "false_alarm_detail": [{"seed": r.seed, **x} for r in results for x in r.false_alarms],
    }


def write_report(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2))

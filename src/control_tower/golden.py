"""Build and verify the frozen scenario set.

Observed files (what an analyst receives) go to data/scenarios/; the planted truth goes to
data/ground_truth/ and is hashed in a manifest. The detection engine never reads
data/ground_truth/ (enforced by tests/test_boundaries.py).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .simulate import draw_issues, ground_truth, simulate

ROOT = Path(__file__).resolve().parents[2]
SCEN_DIR = ROOT / "data" / "scenarios"
TRUTH_DIR = ROOT / "data" / "ground_truth"
MANIFEST = TRUTH_DIR / "manifest.json"

SPLITS = {
    "dev": list(range(1, 11)),  # tuning: rules may be changed after looking at these
    "test": list(range(101, 116)),  # frozen: scored once per engine version
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(split: str) -> list[Path]:
    written: list[Path] = []
    for seed in SPLITS[split]:
        issues = draw_issues(seed)
        scen = simulate(seed, issues)
        out = SCEN_DIR / split / str(seed)
        out.mkdir(parents=True, exist_ok=True)
        for name, df in scen.tables.items():
            df.to_csv(out / f"{name}.csv", index=False)
        truth = ground_truth(seed, issues)
        tpath = TRUTH_DIR / split / f"{seed}.json"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text(json.dumps(truth, indent=2, default=str))
        written.append(tpath)
    return written


def freeze() -> dict:
    files: dict[str, str] = {}
    for split in SPLITS:
        for seed in SPLITS[split]:
            files[f"{split}/{seed}.json"] = sha256(TRUTH_DIR / split / f"{seed}.json")
            for csv in sorted((SCEN_DIR / split / str(seed)).glob("*.csv")):
                files[f"scenarios/{split}/{seed}/{csv.name}"] = sha256(csv)
    manifest = {"note": "Frozen before any detection code was written.", "files": files}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def verify() -> list[str]:
    """Return the files whose hash no longer matches the manifest (empty = intact)."""
    manifest = json.loads(MANIFEST.read_text())["files"]
    bad = []
    for rel, digest in manifest.items():
        path = ROOT / "data" / rel if rel.startswith("scenarios/") else TRUTH_DIR / rel
        if not path.exists() or sha256(path) != digest:
            bad.append(rel)
    return bad


def load_truth(split: str, seed: int) -> dict:
    return json.loads((TRUTH_DIR / split / f"{seed}.json").read_text())

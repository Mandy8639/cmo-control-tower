"""Command line: ct golden | ct eval | ct report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import golden


def _report(args: argparse.Namespace) -> None:
    from .data import load_scenario
    from .deck import build_deck
    from .engine import find_risks
    from .excel_pack import build_workbook
    from .powerbi import export_star

    path = Path(args.scenario) if Path(args.scenario).exists() else golden.SCEN_DIR / args.scenario
    data = load_scenario(path)
    month = args.month or (data.as_of.to_period("M") - 1).strftime("%Y-%m")
    findings = find_risks(data)
    out = Path(args.out)
    wb = build_workbook(data, findings, out / "VPT_workbook.xlsx", month)
    deck = build_deck(data, findings, out / "VPT_review.pptx", month)
    star = export_star(data, findings, out / "powerbi")
    (out / "risks.json").write_text(json.dumps([f.to_dict() for f in findings], indent=2))
    print(f"{len(findings)} findings ({sum(f.severity == 'high' for f in findings)} high), {len(data.quarantine)} rows quarantined")
    print(f"workbook: {wb}\ndeck:     {deck}\npower bi: {star[0].parent} ({len(star)} tables)")


def _eval(args: argparse.Namespace) -> None:
    from .evaluate import run

    res = [run(args.split, s) for s in ("engine", "baseline")]
    for r in res:
        print(
            f"{r['system']:8s} caught {r['caught']}/{r['planted']} ({r['recall']:.0%}), root cause {r['root_cause_correct']}/{r['supply_issues']}, "
            f"false alarms {r['false_alarms']} ({r['false_alarms_per_scenario']:.1f}/scenario), bad rows {r['bad_rows']['correct']}/{r['bad_rows']['planted']}"
        )
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=2))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="ct", description="External Manufacturing Control Tower (synthetic data)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("golden", help="build/verify the frozen scenario set")
    g.add_argument("action", choices=["build", "verify"])
    e = sub.add_parser("eval", help="score engine and baseline against planted issues")
    e.add_argument("--split", default="dev", choices=["dev", "test"])
    e.add_argument("--out")
    r = sub.add_parser("report", help="build the VPT workbook, deck and Power BI tables for one scenario")
    r.add_argument("scenario", help="e.g. test/105, or a folder of partner CSVs")
    r.add_argument("--month", help="YYYY-MM (default: last full month)")
    r.add_argument("--out", default="out")
    args = ap.parse_args(argv)
    if args.cmd == "golden":
        if args.action == "build":
            for split in golden.SPLITS:
                golden.build(split)
            golden.freeze()
            print("built and froze", sum(len(v) for v in golden.SPLITS.values()), "scenarios")
        else:
            bad = golden.verify()
            print("intact" if not bad else f"{len(bad)} files changed: {bad[:5]}")
            sys.exit(1 if bad else 0)
    elif args.cmd == "eval":
        _eval(args)
    else:
        _report(args)


if __name__ == "__main__":
    main()

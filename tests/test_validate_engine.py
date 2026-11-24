import pandas as pd

from control_tower.data import validate_batches
from control_tower.engine import _clusters, _overdue


def _row(uid, bid, start="2026-01-10", end="2026-01-13", rel="2026-01-20", uom="TH"):
    return {
        "row_uid": uid,
        "partner": "CMO-ALPHA",
        "batch_id": bid,
        "actual_start": pd.Timestamp(start),
        "mfg_end": pd.Timestamp(end),
        "qa_release": pd.Timestamp(rel),
        "uom": uom,
    }


def test_validation_quarantines_each_rule_and_keeps_first_copy():
    df = pd.DataFrame(
        [
            _row("a", "B1"),
            _row("b", "B1"),  # duplicate
            _row("c", None),  # missing id
            _row("d", "B2", uom="EA"),
            _row("e", "B3", start="2026-01-10", end="2026-01-08"),
            _row("f", "B4", end="2026-01-13", rel="2026-01-12"),
            _row("g", "B5"),
        ]
    )
    clean, q = validate_batches(df)
    assert clean.row_uid.tolist() == ["a", "g"]
    assert dict(zip(q.row_uid, q.reason, strict=True)) == {
        "b": "duplicate",
        "c": "missing_batch_id",
        "d": "wrong_uom",
        "e": "end_before_start",
        "f": "release_before_mfg",
    }


def test_clusters_split_on_gap():
    s = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-10", "2026-02-20", "2026-02-25"]))
    assert _clusters(s, 14) == [[0, 1], [2, 3]]


def test_overdue_respects_min_days_and_open_items():
    df = pd.DataFrame({"due": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-01"]), "closed": pd.to_datetime(["2026-01-03", "2026-01-20", None])})
    od = _overdue(df, pd.Timestamp("2026-02-01"), min_days=10)
    assert len(od) == 2

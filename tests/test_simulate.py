import pandas as pd

from control_tower.simulate import Issue, draw_issues, simulate


def test_same_seed_same_output():
    a = simulate(7, draw_issues(7))
    b = simulate(7, draw_issues(7))
    for name in a.tables:
        pd.testing.assert_frame_equal(a.tables[name], b.tables[name])


def test_removing_an_issue_changes_only_its_effects():
    base = simulate(3, [])
    with_price = simulate(3, [Issue("I1", "price_variance", "CMO-ALPHA", 30, 90)])
    # deliveries and inventory identical; only invoices move
    pd.testing.assert_frame_equal(base.tables["deliveries"], with_price.tables["deliveries"])
    pd.testing.assert_frame_equal(base.tables["inventory"], with_price.tables["inventory"])
    assert not base.tables["invoices"].equals(with_price.tables["invoices"])


def test_api_delay_makes_deliveries_late():
    clean = simulate(4, [])
    hit = simulate(4, [Issue("I1", "api_supply_delay", "CMO-ALPHA", 30, 90)])

    def late(df):
        d = df[df.partner == "CMO-ALPHA"].dropna(subset=["delivered"])
        return (pd.to_datetime(d.delivered) > pd.to_datetime(d.promised) + pd.Timedelta(days=2)).sum()

    assert late(hit.tables["deliveries"]) >= late(clean.tables["deliveries"]) + 3


def test_bad_rows_only_when_planted():
    assert simulate(5, []).bad_row_uids == []
    s = simulate(5, [Issue("I1", "bad_data", "CMO-ALPHA", 0, 50)])
    assert 6 <= len(s.bad_row_uids) <= 10
    assert set(s.bad_row_uids) <= set(s.tables["batches"].row_uid)

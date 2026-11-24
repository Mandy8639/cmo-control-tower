# Golden-set spot check (10 of 51 planted test issues)

Pick each row, open the named file and confirm the planted problem is visible in the data. Mark OK or WRONG. The test set was frozen (hashed) on 2026-11-23 before detection code; if anything is WRONG, the set gets rebuilt and the change is recorded in the README.

| # | Scenario | Planted issue | Entity | Window | Where to look | OK? |
|---|---|---|---|---|---|---|
| 1 | test/103 | demand_spike | 0713-0861 | 2026-04-13 to 2026-05-17 | data/scenarios/test/103/inventory.csv: demand_th ~2x forecast, closing below 4 weeks | OK: demand 2.10x forecast in window (0.99x outside); fell to 0.8 weeks of supply, 8 weeks below 4 |
| 2 | test/107 | overdue_actions | CMO-BRAVO | 2026-03-02 to 2026-04-26 | data/scenarios/test/107/actions.csv: closed after due | OK: 7 of 8 actions due in window closed late (3-27 days); 0 of 18 late outside |
| 3 | test/110 | demand_spike | 0713-0915 | 2026-02-23 to 2026-04-19 | data/scenarios/test/110/inventory.csv: demand_th ~2x forecast, closing below 4 weeks | OK: demand 2.06x forecast in window (0.98x outside); stock reached 0, 15 weeks below 4 |
| 4 | test/115 | bad_data | CMO-DELTA | 2026-03-16 to 2026-04-26 | data/scenarios/test/115/batches.csv: rows with row_uid containing X | OK: 5 extra rows (1 missing batch ID, 1 wrong unit, rest conflicting/duplicate copies of real batches) |
| 5 | test/113 | capacity_loss | CPO-ECHO | 2026-04-20 to 2026-05-17 | data/scenarios/test/113/downtime.csv L2 row; batches.csv/packaging_orders.csv late, short qty | OK: L2 unplanned downtime row for the window; all 14 packaging orders in window 5-10 days past due, none outside |
| 6 | test/103 | capa_overdue | CPO-ECHO | 2026-01-26 to 2026-03-15 | data/scenarios/test/103/capas.csv: closed well after due | WEAK: only 1 of 3 CAPAs due in window was late (11 days); the planted problem barely shows (this is test miss #2) |
| 7 | test/105 | capacity_loss | CPO-ECHO | 2026-04-13 to 2026-05-03 | data/scenarios/test/105/downtime.csv L2 row; batches.csv/packaging_orders.csv late, short qty | OK: L2 unplanned downtime row; all 12 packaging orders in window 5-10 days past due, none outside |
| 8 | test/112 | capa_overdue | CMO-CHARLIE | 2026-03-23 to 2026-05-03 | data/scenarios/test/112/capas.csv: closed well after due | OK: both CAPAs due in window closed 32 and 39 days late |
| 9 | test/112 | capacity_loss | CMO-ALPHA | 2026-03-30 to 2026-04-26 | data/scenarios/test/112/downtime.csv L2 row; batches.csv/packaging_orders.csv late, short qty | OK: L2 downtime row; all 9 batches in window started 4-10 days late at 59-68% yield |
| 10 | test/111 | deviation_backlog | CMO-BRAVO | 2026-01-26 to 2026-03-22 | data/scenarios/test/111/deviations.csv: major deviations, long open; batches.csv qa_release late | OK: 6 deviations opened in window, open 12-23 days; release took 13-24 days vs. 12-day target |

**Result (2026-11-23):** 9 clearly visible, 1 weak (#6). Checked by Claude with a script that reads the raw CSVs directly, not the engine. This confirms the planted problems are in the data; it is not an independent human review. Separately, test/102 I1 (not in this sample) is known to be invisible in the data; see reports/eval_v1.md. The frozen set was not rebuilt, so the v1 results stand as reported.

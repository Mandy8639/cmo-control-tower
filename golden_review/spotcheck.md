# Golden-set spot check (10 of 51 planted test issues)

Pick each row, open the named file and confirm the planted problem is visible in the data. Mark OK or WRONG. The test set was frozen (hashed) on 2026-11-23 before detection code; if anything is WRONG, the set gets rebuilt and the change is recorded in the README.

| # | Scenario | Planted issue | Entity | Window | Where to look | OK? |
|---|---|---|---|---|---|---|
| 1 | test/103 | demand_spike | 0713-0861 | 2026-04-13 to 2026-05-17 | data/scenarios/test/103/inventory.csv: demand_th ~2x forecast, closing below 4 weeks | |
| 2 | test/107 | overdue_actions | CMO-BRAVO | 2026-03-02 to 2026-04-26 | data/scenarios/test/107/actions.csv: closed after due | |
| 3 | test/110 | demand_spike | 0713-0915 | 2026-02-23 to 2026-04-19 | data/scenarios/test/110/inventory.csv: demand_th ~2x forecast, closing below 4 weeks | |
| 4 | test/115 | bad_data | CMO-DELTA | 2026-03-16 to 2026-04-26 | data/scenarios/test/115/batches.csv: rows with row_uid containing X | |
| 5 | test/113 | capacity_loss | CPO-ECHO | 2026-04-20 to 2026-05-17 | data/scenarios/test/113/downtime.csv L2 row; batches.csv/packaging_orders.csv late, short qty | |
| 6 | test/103 | capa_overdue | CPO-ECHO | 2026-01-26 to 2026-03-15 | data/scenarios/test/103/capas.csv: closed well after due | |
| 7 | test/105 | capacity_loss | CPO-ECHO | 2026-04-13 to 2026-05-03 | data/scenarios/test/105/downtime.csv L2 row; batches.csv/packaging_orders.csv late, short qty | |
| 8 | test/112 | capa_overdue | CMO-CHARLIE | 2026-03-23 to 2026-05-03 | data/scenarios/test/112/capas.csv: closed well after due | |
| 9 | test/112 | capacity_loss | CMO-ALPHA | 2026-03-30 to 2026-04-26 | data/scenarios/test/112/downtime.csv L2 row; batches.csv/packaging_orders.csv late, short qty | |
| 10 | test/111 | deviation_backlog | CMO-BRAVO | 2026-01-26 to 2026-03-22 | data/scenarios/test/111/deviations.csv: major deviations, long open; batches.csv qa_release late | |

# Evaluation v1 (2026-11-23)

Engine version: commit "Phases 3-4" (rules tuned on dev only). Test split scored once.

## Test split (15 scenarios, 51 planted problems)

| Problem type | Planted | Engine caught | Engine root cause right | Baseline caught |
|---|---|---|---|---|
| API supply delay | 5 | 4 | 4 | 5 |
| Capacity loss (CMO or CPO) | 6 | 6 | 6 | 6 |
| Deviation backlog | 9 | 8 | 8 | 8 |
| CAPAs overdue | 7 | 6 | – | 7 |
| Actions overdue | 5 | 5 | – | 5 |
| Price above contract | 4 | 4 | – | 4 |
| Demand spike (stock below safety) | 8 | 8 | – | 8 |
| Bad rows in partner report | 7 | 7 | – | 0 |
| **Total** | **51** | **48** | **18 / 20** | **43** |

False alarms: engine 0, baseline 166. Downstream stock-outs caused by planted supply problems
(true signals, not counted as false alarms): engine 6, baseline 6. Bad rows: 43 planted, engine
quarantined 43 (all correct), baseline 0.

## Misses (engine)

1. **test/102 I1, deviation backlog at CMO-Charlie.** CMO-Charlie makes one product, so only
   two batches fell in the window, and neither drew a deviation (the simulator's 75% chance
   missed twice). The problem is planted but invisible in the data: a golden-set flaw that the
   human spot check is meant to catch. Counted as a miss anyway.
2. **test/103 I1, CAPAs overdue at CPO-Echo.** Only one CAPA in the window was 10+ days late
   (11 days); the other was 7 days late. The rule needs two CAPAs 10+ days late within 30 days,
   set on dev to avoid flagging normal slips. The baseline caught it because one late CAPA
   turned a month red.
3. **test/113 I2, API supply delay at CMO-Delta.** The delay pushed one delivery 4 days late;
   the next late delivery was caused by packaging. The rule needs two late deliveries with the
   same cause, or one 7+ days late.

The two root-cause misses are misses 1 and 3 (no matching finding to carry a cause).

## Not changed after the test run

The thresholds stay as they are; changing them now would tune on the test set. A v2 needs a
fresh held-out set.

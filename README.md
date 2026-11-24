# External Manufacturing Control Tower

A working model of an external-manufacturing analyst's weekly routine: take the files that
contract manufacturers (CMOs) and a contract packager (CPO) send in, validate them, score
every partner against its supply and quality agreement, find supply risks and their root
cause, and build the Virtual Plant Team pack automatically: an **Excel workbook with live
formulas**, a **PowerPoint review deck** and **Power BI-ready tables**.

> **Independent demo, synthetic data.** The partner network (CMO-Alpha … CPO-Echo) is
> fictional and every operational record (batches, deliveries, deviations, CAPAs, actions,
> invoices, inventory) is simulated. Only the product list is real public data: brand names,
> NDCs and dosage forms from the openFDA NDC Directory (CC0 public domain; *Data provided by
> the U.S. Food and Drug Administration, https://open.fda.gov*). Not affiliated with, endorsed
> by, or built from the data of any pharmaceutical company or manufacturer. Nothing here says
> or implies who makes any product.

## Results (frozen test set, one scored run)

15 simulated 26-week periods with 51 planted problems, frozen and hashed before any
detection code was written. Rules were tuned on a separate 10-scenario dev split.

| | Control tower | Monthly red/amber/green scorecard (baseline) |
|---|---|---|
| Planted problems caught | **48 / 51 (94%)** | 43 / 51 (84%) |
| Root cause named correctly (supply delays) | **18 / 20** | 0 / 20 (no root cause) |
| False alarms | **0** (0.0 per period) | 166 (11.1 per period) |
| Bad rows in partner files quarantined | **43 / 43**, 0 good rows rejected | 0 / 43 (loaded as-is) |
| Findings to read | 72 | 282 |

Dev split (10 periods, 38 problems, used for tuning): 38/38 caught, 18/18 causes, 0 false
alarms; baseline 35/38 with 112 false alarms. Full detail: [`reports/eval_v1.md`](reports/eval_v1.md)
and [`reports/eval_v1.json`](reports/eval_v1.json).

**The three test misses:** a planted deviation backlog at a one-product CMO that never produced
a deviation in the data (a golden-set flaw, counted as a miss anyway); a weak CAPA slip at the
packager (one CAPA 11 days late, one 7) under the "two CAPAs 10+ days late" rule; and a supply
delay that showed up as a single 4-day-late delivery, under the "two late, or one 7+ days late"
rule. Thresholds were not changed after the test run.

**Caveats.** The same author wrote the simulator and the detector, so the benchmark tests the
logic, not real-world accuracy. Planted problems are cleaner than real ones. The baseline is a
deliberately simple monthly RAG: it catches most problems because a planted problem usually
turns a month red, but it cannot say why, and normal noise turns many other months red too.

## What it does (mapped to the job)

| Analyst task | In this repo |
|---|---|
| Collect and validate CMO/CPO data | `data.py`: loads partner files; quarantines missing batch IDs, wrong units, impossible dates and duplicates, each with a reason |
| Supplier scorecards: service, delivery, quality, cost, actions | `kpis.py`: monthly OTIF, schedule adherence, right-first-time, release days, CAPA on time, actions on time, cost variance and open overdue actions, each red/amber/green vs. agreement targets |
| Track batches, release timing, shipments, inventory | delivery facts per batch (material receipt → start → manufacture → QA release → packaging → delivery) and weeks of supply per product |
| Follow up on overdue actions, CAPAs, recovery plans | action ageing and overdue-CAPA clusters with owners |
| Coordinate on deviations, CAPAs, batch release | each late release is linked to the deviation holding it |
| Identify and escalate supply, capacity, inventory risks | `engine.py`: findings with severity and evidence; high-severity ones go on an escalation list |
| Root-cause and trend analysis | each late delivery's delay is split by stage (material, capacity, QA release, packaging); the cluster's dominant stage is the root cause |
| VPT meetings, business reviews: data, agenda, presentations, action log | `ct report` builds the deck, workbook and Power BI tables in one command |
| SAP / Power BI / Excel | SAP-style fields (PO, plant, batch, material, UoM), a star schema with DAX measures, an Excel scorecard driven by COUNTIFS / SUMIFS / SUMPRODUCT / INDEX-MATCH |
| Standardize reporting | one KPI dictionary for every partner (in the workbook) |

## Outputs

Pre-built samples (scenario test/111, May 2026) are in [`docs/demo/`](docs/demo/): the deck as
[PDF](docs/demo/VPT_review.pdf) and [PPTX](docs/demo/VPT_review.pptx), the [workbook](docs/demo/VPT_workbook.xlsx)
and the [Power BI tables](docs/demo/powerbi/).


- **`VPT_workbook.xlsx`**: a *Scorecard* sheet where every KPI is a live formula over the data
  sheets (pick a month in `B2` and everything recalculates); a *Trend* sheet with an OTIF chart;
  data sheets with helper formulas (OnTime, InFull, OTIF, RFT, weeks of supply via INDEX/MATCH);
  *Risks*, *Quarantine* and *KPI dictionary*. `tests/test_excel.py` recalculates the workbook
  without Excel and checks every scorecard cell against the Python numbers.
- **`VPT_review.pptx`**: 8 slides: agenda, network scorecard (RAG), escalations with root
  cause, partner deep dive with OTIF trend chart, supply outlook, overdue actions and CAPAs,
  data quality and decisions needed.
- **`powerbi/`**: dim_partner, dim_product, dim_date and fact tables (delivery, batch,
  packaging, deviation, CAPA, action, invoice, inventory, risk, quarantine) plus
  `DAX_measures.md`.
- **Power BI report** (built in the Power BI service on the generated tables): month slicer, partner scorecard, OTIF trend by partner, high-risk count and the risk list. Screenshot: [`docs/demo/powerbi_report.png`](docs/demo/powerbi_report.png). Relationships and measures: [`docs/demo/powerbi/model_script.tmdl`](docs/demo/powerbi/model_script.tmdl) (paste into TMDL view). For May 2026 its numbers match the Python scorecard and the Excel workbook.
- **Dashboard**: `app/dashboard.py` (Streamlit): scorecard, OTIF trend, weeks of supply, risks.

## Run it

```bash
uv sync --all-extras
uv run ct report test/111 --month 2026-05 --out out/demo   # workbook + deck + Power BI tables
uv run ct eval --split test                                 # engine vs. baseline on the frozen set
uv run ct golden verify                                     # frozen files unchanged?
uv run streamlit run app/dashboard.py
uv run pytest
```

## How the benchmark works

- `simulate.py` generates a 26-week network: 14 real products (openFDA), 4 CMOs by dosage
  form, 1 CPO, material receipts, batches, deviations, packaging orders, deliveries, invoices,
  CAPAs, VPT actions and weekly inventory. Every random draw is made whether or not a problem
  is active, so removing one problem changes only its own effects (tested).
- 8 problem types are planted: API supply delay, capacity loss (CMO or CPO), deviation
  backlog, CAPAs overdue, actions overdue, price above contract, demand spike, and bad rows in
  a partner report.
- Ground truth lives in `data/ground_truth/` and is hashed in a manifest; the engine only reads
  `data/scenarios/` (enforced by `tests/test_boundaries.py`). Stock-outs caused by a planted
  supply problem are found by counterfactual re-runs and counted as true downstream signals,
  not false alarms.
- A 10-item spot check of the frozen set, done by reading the raw files rather than through the engine, is in
  [`golden_review/spotcheck.md`](golden_review/spotcheck.md): 9 clearly visible, 1 weak (the CAPA case behind test miss #2).

## Stack

Python 3.12, pandas, openpyxl, python-pptx, Streamlit, httpx (openFDA), pytest, ruff, uv and
GitHub Actions. No AI model is used; every number is computed from the data.

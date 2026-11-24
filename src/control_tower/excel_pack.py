"""Excel workbook for the Virtual Plant Team review, with live formulas.

The Scorecard and Trend sheets are formulas over the data sheets (COUNTIFS, SUMIFS,
SUMPRODUCT, INDEX/MATCH), so changing the month in Scorecard!B2 recalculates everything,
and anyone can audit how a number was made. tests/test_excel.py recalculates the workbook
and checks it against the Python scorecard.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from .config import PARTNERS, SAFETY_STOCK_WEEKS, TOLERANCE_DAYS
from .data import Data
from .engine import Finding
from .kpis import ACTION_TARGET, COST_VARIANCE_LIMIT, IN_FULL

GREEN = PatternFill("solid", fgColor="C6EFCE")
AMBER = PatternFill("solid", fgColor="FFEB9C")
RED = PatternFill("solid", fgColor="FFC7CE")
HEAD = PatternFill("solid", fgColor="1F3864")
WHITE_BOLD = Font(bold=True, color="FFFFFF")
DATE_FMT = "yyyy-mm-dd"
MONTH_FMT = "yyyy-mm"


def _header(ws: Worksheet, cols: list[str], row: int = 1) -> None:
    for i, c in enumerate(cols, start=1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.fill, cell.font = HEAD, WHITE_BOLD
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _widths(ws: Worksheet, widths: dict[str, int]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def _v(x):
    if x is None or (isinstance(x, float) and pd.isna(x)) or x is pd.NaT:
        return None
    if isinstance(x, pd.Timestamp):
        return x.to_pydatetime()
    return x


def _data_sheet(wb: Workbook, title: str, df: pd.DataFrame, date_cols: list[str], helpers: list[tuple[str, str]]) -> tuple[Worksheet, dict[str, str], int]:
    """Write df plus helper formula columns. Returns sheet, column-letter map, last row."""
    ws = wb.create_sheet(title)
    cols = list(df.columns) + [h for h, _ in helpers]
    _header(ws, cols)
    letter = {c: get_column_letter(i) for i, c in enumerate(cols, start=1)}
    for r, rec in enumerate(df.itertuples(index=False), start=2):
        for c, val in zip(df.columns, rec, strict=True):
            cell = ws.cell(row=r, column=cols.index(c) + 1, value=_v(val))
            if c in date_cols:
                cell.number_format = DATE_FMT
        for h, tmpl in helpers:
            f = tmpl.format(r=r, **letter)
            cell = ws.cell(row=r, column=cols.index(h) + 1, value=f)
            if h.lower().startswith("month"):
                cell.number_format = MONTH_FMT
    for c in cols:
        ws.column_dimensions[letter[c]].width = max(11, min(28, len(c) + 4))
    return ws, letter, max(2, len(df) + 1)


def _rng(sheet: str, col: str, last: int) -> str:
    return f"'{sheet}'!${col}$2:${col}${last}"


def build_workbook(data: Data, findings: list[Finding], path: Path, month: str) -> Path:
    wb = Workbook()
    readme = wb.active
    readme.title = "Read me"
    as_of = data.as_of
    month_start = pd.Period(month).start_time

    # ---------------------------------------------------------------- data sheets
    dl = data["deliveries"][data["deliveries"].promised <= as_of]
    ws_d, Ld, nd = _data_sheet(
        wb,
        "Deliveries",
        dl,
        ["promised", "delivered"],
        [
            ("Month", "=DATE(YEAR({promised}{r}),MONTH({promised}{r}),1)"),
            ("OnTime", f'=IF(AND({{delivered}}{{r}}<>"",{{delivered}}{{r}}<={{promised}}{{r}}+{TOLERANCE_DAYS}),1,0)'),
            ("InFull", f"=IF({{qty_delivered}}{{r}}>={IN_FULL}*{{qty_promised}}{{r}},1,0)"),
            ("OTIF", "={OnTime}{r}*{InFull}{r}"),
        ],
    )
    pk = data["packaging_orders"]
    pk = pk[(pk.due <= as_of) & pk.received.notna()]
    ws_p, Lp, npk = _data_sheet(
        wb,
        "Packaging",
        pk,
        ["received", "due", "completed"],
        [
            ("Month", "=DATE(YEAR({due}{r}),MONTH({due}{r}),1)"),
            ("OnTime", f'=IF(AND({{completed}}{{r}}<>"",{{completed}}{{r}}<={{due}}{{r}}+{TOLERANCE_DAYS}),1,0)'),
        ],
    )
    dev = data["deviations"]
    ws_v, Lv, nv = _data_sheet(wb, "Deviations", dev, ["opened", "closed"], [])
    b = data["batches"]
    b = b[b.mfg_end.notna()].drop(columns=["row_uid"])
    ws_b, Lb, nb = _data_sheet(
        wb,
        "Batches",
        b,
        ["planned_start", "actual_start", "mfg_end", "qa_release"],
        [
            ("Month", "=DATE(YEAR({mfg_end}{r}),MONTH({mfg_end}{r}),1)"),
            ("RFT", f"=IF(COUNTIF({_rng('Deviations', Lv['batch_id'], nv)},{{batch_id}}{{r}})>0,0,1)"),
            ("ReleaseDays", '=IF({qa_release}{r}="","",{qa_release}{r}-{mfg_end}{r})'),
        ],
    )
    ws_c, Lc, nc = _data_sheet(
        wb,
        "CAPAs",
        data["capas"],
        ["opened", "due", "closed"],
        [
            ("MonthDue", "=DATE(YEAR({due}{r}),MONTH({due}{r}),1)"),
            ("OnTime", '=IF(AND({closed}{r}<>"",{closed}{r}<={due}{r}),1,0)'),
        ],
    )
    ws_a, La, na = _data_sheet(
        wb,
        "Actions",
        data["actions"],
        ["created", "due", "closed"],
        [
            ("MonthDue", "=DATE(YEAR({due}{r}),MONTH({due}{r}),1)"),
            ("OnTime", '=IF(AND({closed}{r}<>"",{closed}{r}<={due}{r}),1,0)'),
        ],
    )
    ws_i, Li, ni = _data_sheet(
        wb,
        "Invoices",
        data["invoices"],
        ["invoice_date"],
        [
            ("ContractValue", "={contract_price}{r}*{qty_th}{r}"),
            ("OverContract", "=({billed_price}{r}-{contract_price}{r})*{qty_th}{r}"),
        ],
    )
    prod = data["products"]
    ws_pr, Lpr, npr = _data_sheet(wb, "Products", prod, [], [])
    inv = data["inventory"]
    ws_w, Lw, nw = _data_sheet(
        wb,
        "Weeks of Supply",
        inv,
        ["week_start"],
        [
            ("Forecast", f"=INDEX({_rng('Products', Lpr['forecast_weekly_th'], npr)},MATCH({{material}}{{r}},{_rng('Products', Lpr['material'], npr)},0))"),
            ("WeeksOfSupply", "=IFERROR({closing_th}{r}/{Forecast}{r},0)"),
        ],
    )
    wos_col = Lw["WeeksOfSupply"]
    ws_w.conditional_formatting.add(f"{wos_col}2:{wos_col}{nw}", CellIsRule(operator="lessThan", formula=[str(SAFETY_STOCK_WEEKS)], fill=RED))

    # ---------------------------------------------------------------- scorecard (formulas)
    sc = wb.create_sheet("Scorecard", 1)
    sc["A1"] = "Network scorecard (live formulas). Change the month in B2; every KPI recalculates. SYNTHETIC DATA."
    sc["A1"].font = Font(bold=True, size=12)
    sc["A2"], sc["B2"] = "Month (first day)", month_start.to_pydatetime()
    sc["B2"].number_format = MONTH_FMT
    sc["C2"], sc["D2"] = "As of", as_of.to_pydatetime()
    sc["D2"].number_format = DATE_FMT
    sc["E2"], sc["F2"] = "Month end", "=MIN(EOMONTH(B2,0),D2)"
    sc["F2"].number_format = DATE_FMT
    months = pd.period_range(inv.week_start.min(), as_of - pd.Timedelta(days=1), freq="M")
    sc["H1"] = "Months"
    for i, m in enumerate(months, start=2):
        sc.cell(row=i, column=8, value=m.start_time.to_pydatetime()).number_format = MONTH_FMT
    dv = DataValidation(type="list", formula1=f"=$H$2:$H${len(months) + 1}", allow_blank=False)
    sc.add_data_validation(dv)
    dv.add("B2")

    cols = [
        "Partner",
        "Deliveries due",
        "OTIF",
        "OTIF target",
        "OTIF status",
        "RFT",
        "RFT target",
        "CAPA on time",
        "Actions on time",
        "Cost variance",
        "Overdue actions open",
    ]
    _header(sc, cols, row=4)
    for r, p in enumerate(PARTNERS, start=5):
        sc.cell(row=r, column=1, value=p.partner_id)
        if p.kind == "CMO":
            part, mon, otif = _rng("Deliveries", Ld["partner"], nd), _rng("Deliveries", Ld["Month"], nd), _rng("Deliveries", Ld["OTIF"], nd)
            sc.cell(row=r, column=2, value=f"=COUNTIFS({part},$A{r},{mon},$B$2)")
            sc.cell(row=r, column=3, value=f'=IFERROR(SUMIFS({otif},{part},$A{r},{mon},$B$2)/B{r},"")')
            bp, bm, brft = _rng("Batches", Lb["partner"], nb), _rng("Batches", Lb["Month"], nb), _rng("Batches", Lb["RFT"], nb)
            sc.cell(row=r, column=6, value=f'=IFERROR(SUMIFS({brft},{bp},$A{r},{bm},$B$2)/COUNTIFS({bp},$A{r},{bm},$B$2),"")')
            sc.cell(row=r, column=7, value=p.rft_target)
        else:
            mon, ot = _rng("Packaging", Lp["Month"], npk), _rng("Packaging", Lp["OnTime"], npk)
            sc.cell(row=r, column=2, value=f"=COUNTIFS({mon},$B$2)")
            sc.cell(row=r, column=3, value=f'=IFERROR(SUMIFS({ot},{mon},$B$2)/B{r},"")')
            sc.cell(row=r, column=6, value="")
            sc.cell(row=r, column=7, value="")
        sc.cell(row=r, column=4, value=p.otif_target)
        sc.cell(row=r, column=5, value=f'=IF(C{r}="","n/a",IF(C{r}>=D{r},"Green",IF(C{r}>=D{r}-0.05,"Amber","Red")))')
        cp, cm, cd, co = (_rng("CAPAs", Lc[k], nc) for k in ("partner", "MonthDue", "due", "OnTime"))
        sc.cell(row=r, column=8, value=f'=IFERROR(SUMIFS({co},{cp},$A{r},{cm},$B$2,{cd},"<="&$D$2)/COUNTIFS({cp},$A{r},{cm},$B$2,{cd},"<="&$D$2),"")')
        ap, am, ad, ao, ac = (_rng("Actions", La[k], na) for k in ("partner", "MonthDue", "due", "OnTime", "closed"))
        sc.cell(row=r, column=9, value=f'=IFERROR(SUMIFS({ao},{ap},$A{r},{am},$B$2,{ad},"<="&$D$2)/COUNTIFS({ap},$A{r},{am},$B$2,{ad},"<="&$D$2),"")')
        ip, idt, iov, icv = (_rng("Invoices", Li[k], ni) for k in ("partner", "invoice_date", "OverContract", "ContractValue"))
        sc.cell(
            row=r,
            column=10,
            value=f'=IFERROR(SUMIFS({iov},{ip},$A{r},{idt},">="&$B$2,{idt},"<="&$F$2)/SUMIFS({icv},{ip},$A{r},{idt},">="&$B$2,{idt},"<="&$F$2),"")',
        )
        sc.cell(row=r, column=11, value=f'=SUMPRODUCT(({ap}=$A{r})*({ad}<$F$2)*((({ac}="")+({ac}>$F$2))>0))')
        for c in (3, 4, 6, 7, 8, 9, 10):
            sc.cell(row=r, column=c).number_format = "0.0%"
    last = 4 + len(PARTNERS)
    sc.conditional_formatting.add(f"E5:E{last}", FormulaRule(formula=['E5="Green"'], fill=GREEN))
    sc.conditional_formatting.add(f"E5:E{last}", FormulaRule(formula=['E5="Amber"'], fill=AMBER))
    sc.conditional_formatting.add(f"E5:E{last}", FormulaRule(formula=['E5="Red"'], fill=RED))
    sc.conditional_formatting.add(f"H5:I{last}", CellIsRule(operator="lessThan", formula=[str(ACTION_TARGET)], fill=RED))
    sc.conditional_formatting.add(f"J5:J{last}", CellIsRule(operator="greaterThan", formula=[str(COST_VARIANCE_LIMIT)], fill=RED))
    _widths(sc, {"A": 16, "B": 12, "C": 10, "D": 10, "E": 11, "F": 10, "G": 10, "H": 11, "I": 11, "J": 11, "K": 12})

    # ---------------------------------------------------------------- trend + chart
    tr = wb.create_sheet("Trend", 2)
    tr["A1"] = "OTIF by month (live formulas)"
    tr["A1"].font = Font(bold=True)
    _header(tr, ["Month"] + [p.partner_id for p in PARTNERS], row=2)
    for i, m in enumerate(months, start=3):
        tr.cell(row=i, column=1, value=m.start_time.to_pydatetime()).number_format = MONTH_FMT
        for j, p in enumerate(PARTNERS, start=2):
            if p.kind == "CMO":
                part, mon, otif = _rng("Deliveries", Ld["partner"], nd), _rng("Deliveries", Ld["Month"], nd), _rng("Deliveries", Ld["OTIF"], nd)
                f = f'=IFERROR(SUMIFS({otif},{part},"{p.partner_id}",{mon},$A{i})/COUNTIFS({part},"{p.partner_id}",{mon},$A{i}),NA())'
            else:
                mon, ot = _rng("Packaging", Lp["Month"], npk), _rng("Packaging", Lp["OnTime"], npk)
                f = f"=IFERROR(SUMIFS({ot},{mon},$A{i})/COUNTIFS({mon},$A{i}),NA())"
            tr.cell(row=i, column=j, value=f).number_format = "0%"
    ch = LineChart()
    ch.title, ch.y_axis.title, ch.height, ch.width = "OTIF by partner (synthetic)", "OTIF", 8, 18
    ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0, 1
    ch.add_data(Reference(tr, min_col=2, max_col=1 + len(PARTNERS), min_row=2, max_row=2 + len(months)), titles_from_data=True)
    ch.set_categories(Reference(tr, min_col=1, min_row=3, max_row=2 + len(months)))
    tr.add_chart(ch, "H2")

    # ---------------------------------------------------------------- risks, quarantine, dictionary
    rk = wb.create_sheet("Risks", 3)
    _header(rk, ["Severity", "Category", "Partner / SKU", "From", "To", "Root cause", "Summary", "Evidence"])
    for r, f in enumerate(findings, start=2):
        for c, val in enumerate([f.severity, f.category, f.entity, f.start, f.end, f.cause or "", f.summary, ", ".join(f.evidence[:12])], start=1):
            rk.cell(row=r, column=c, value=val).alignment = Alignment(wrap_text=c in (7, 8), vertical="top")
        rk.cell(row=r, column=1).fill = RED if f.severity == "high" else AMBER
    _widths(rk, {"A": 9, "B": 15, "C": 14, "D": 11, "E": 11, "F": 20, "G": 70, "H": 40})
    q = wb.create_sheet("Quarantine")
    _header(q, ["row_uid", "partner", "batch_id", "reason"])
    for r, rec in enumerate(data.quarantine.itertuples(index=False), start=2):
        for c, val in enumerate(rec, start=1):
            q.cell(row=r, column=c, value=_v(val))
    kd = wb.create_sheet("KPI dictionary")
    _header(kd, ["KPI", "Definition", "Target"])
    for r, row in enumerate(KPI_DICTIONARY, start=2):
        for c, val in enumerate(row, start=1):
            kd.cell(row=r, column=c, value=val).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(kd, {"A": 22, "B": 90, "C": 28})

    for r, line in enumerate(
        [
            "External Manufacturing Control Tower: Virtual Plant Team workbook",
            "SYNTHETIC DATA. Partners (CMO-Alpha ... CPO-Echo) are fictional; every operational number is simulated.",
            "Product names and dosage forms: openFDA NDC Directory (public domain). Data provided by the U.S. FDA (https://open.fda.gov).",
            "Independent demo. Not affiliated with, or built from data of, Cosette Pharmaceuticals or any manufacturer.",
            f"As of {as_of.date().isoformat()}. Scorecard month: {month}.",
            "Scorecard and Trend are live formulas over the data sheets; pick a month in Scorecard!B2.",
            "Risks come from the control-tower engine (rules + root cause); Quarantine lists rows rejected by validation.",
        ],
        start=1,
    ):
        readme.cell(row=r, column=1, value=line).font = Font(bold=r == 1, size=13 if r == 1 else 11)
    readme.column_dimensions["A"].width = 120
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


KPI_DICTIONARY = [
    (
        "OTIF",
        f"Deliveries due in the month (by promise date) that arrived within {TOLERANCE_DAYS} days of the promise date and with at least {IN_FULL:.0%} of the promised quantity, divided by deliveries due. CPO: packaging orders completed within {TOLERANCE_DAYS} days of due.",
        "Per supply agreement (93-97%)",
    ),
    ("Schedule adherence", "Batches whose actual start was within 2 days of the planned start.", "Tracked, no target"),
    (
        "Right first time (RFT)",
        "Batches manufactured in the month with no deviation recorded, divided by batches manufactured.",
        "Per quality agreement (95-98%)",
    ),
    ("Release days", "QA release date minus manufacture end date, averaged over released batches.", "Per quality agreement (10-12 days)"),
    ("CAPA on time", "CAPAs due in the month (and due by the as-of date) closed on or before their due date.", "90%"),
    ("Actions on time", "VPT action items due in the month closed on or before their due date.", f"{ACTION_TARGET:.0%}"),
    (
        "Cost variance",
        "Sum of (billed price minus contract price) x quantity, divided by contract value, for invoices dated in the month.",
        f"At most {COST_VARIANCE_LIMIT:.0%}",
    ),
    ("Overdue actions open", "Action items past due and not closed at month end.", "0"),
    ("Weeks of supply", "Closing stock divided by weekly forecast demand.", f"At least {SAFETY_STOCK_WEEKS:.0f} weeks (safety stock)"),
]

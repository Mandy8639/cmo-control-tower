"""PowerPoint pack for the Virtual Plant Team / supplier business review (python-pptx)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from .config import PARTNER_BY_ID, PARTNERS
from .data import Data
from .engine import CAUSE_LABEL, Finding, escalations
from .kpis import action_ageing, scorecard, weeks_of_supply

NAVY = RGBColor(0x1F, 0x38, 0x64)
GREY = RGBColor(0x59, 0x59, 0x59)
FILL = {"green": RGBColor(0xC6, 0xEF, 0xCE), "amber": RGBColor(0xFF, 0xEB, 0x9C), "red": RGBColor(0xFF, 0xC7, 0xCE), "n/a": RGBColor(0xF2, 0xF2, 0xF2)}
BANNER = "SYNTHETIC DATA: fictional partners, simulated operations. Product names from openFDA (public domain). Independent demo."


def _slide(prs: Presentation, title: str):
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = title
    s.shapes.title.left, s.shapes.title.top, s.shapes.title.width, s.shapes.title.height = Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.9)
    tf = s.shapes.title.text_frame
    tf.paragraphs[0].alignment = PP_ALIGN.LEFT
    tf.paragraphs[0].font.size = Pt(26)
    tf.paragraphs[0].font.bold = True
    tf.paragraphs[0].font.color.rgb = NAVY
    foot = s.shapes.add_textbox(Inches(0.4), Inches(7.05), Inches(12.5), Inches(0.35)).text_frame
    foot.text = BANNER
    foot.paragraphs[0].font.size = Pt(9)
    foot.paragraphs[0].font.color.rgb = GREY
    return s


def _bullets(slide, items: list[str], top: float = 1.4, size: int = 16, height: float = 5.4) -> None:
    tf = slide.shapes.add_textbox(Inches(0.6), Inches(top), Inches(12.1), Inches(height)).text_frame
    tf.word_wrap = True
    for i, t in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"• {t}"
        p.font.size = Pt(size)
        p.space_after = Pt(6)


def _table(
    slide,
    header: list[str],
    rows: list[list[str]],
    top: float = 1.4,
    col_w: list[float] | None = None,
    fills: list[list[str | None]] | None = None,
    size: int = 12,
):
    shape = slide.shapes.add_table(len(rows) + 1, len(header), Inches(0.5), Inches(top), Inches(12.3), Inches(0.4 * (len(rows) + 1)))
    t = shape.table
    for j, h in enumerate(header):
        c = t.cell(0, j)
        c.text = h
        c.text_frame.paragraphs[0].font.size = Pt(size)
        c.text_frame.paragraphs[0].font.bold = True
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.text = str(val)
            c.text_frame.paragraphs[0].font.size = Pt(size)
            if fills and fills[i - 1][j]:
                c.fill.solid()
                c.fill.fore_color.rgb = FILL[fills[i - 1][j]]
    if col_w:
        for j, w in enumerate(col_w):
            t.columns[j].width = Inches(w)
    return t


def _pct(x) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:.0%}"


def build_deck(data: Data, findings: list[Finding], path: Path, month: str) -> Path:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    sc = scorecard(data)
    cur = sc[sc.month == month].set_index("partner")
    esc = escalations(findings)

    # 1 title
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "External Manufacturing: Virtual Plant Team review"
    s.shapes.title.left, s.shapes.title.top, s.shapes.title.width, s.shapes.title.height = Inches(0.8), Inches(2.0), Inches(11.7), Inches(1.4)
    s.shapes.title.text_frame.paragraphs[0].font.size = Pt(40)
    s.shapes.title.text_frame.paragraphs[0].font.color.rgb = NAVY
    sub = s.placeholders[1]
    sub.left, sub.top, sub.width, sub.height = Inches(0.8), Inches(3.6), Inches(11.7), Inches(1.8)
    sub.text = f"Scorecard month {month} · data as of {data.as_of.date().isoformat()}\n{BANNER}"
    sub.text_frame.paragraphs[0].font.size = Pt(22)
    sub.text_frame.paragraphs[1].font.size = Pt(14)

    # 2 agenda
    s = _slide(prs, "Agenda")
    _bullets(
        s,
        [
            "Network scorecard: service, quality, CAPA, actions, cost by partner",
            f"Escalations for External Manufacturing leadership ({len(esc)})",
            "Partner deep dive: the weakest partner this month",
            "Supply outlook: products below safety stock",
            "Overdue actions and CAPAs, with owners",
            "Data quality: rows rejected from partner reports",
            "Decisions and asks",
        ],
        size=20,
    )

    # 3 scorecard
    s = _slide(prs, f"Network scorecard, {month}")
    header = ["Partner", "Deliveries", "OTIF", "Target", "RFT", "CAPA on time", "Actions on time", "Cost var.", "Overdue actions"]
    rows, fills = [], []
    for p in PARTNERS:
        r = cur.loc[p.partner_id]
        rows.append(
            [
                PARTNER_BY_ID[p.partner_id].name,
                int(r.deliveries),
                _pct(r.otif),
                _pct(p.otif_target),
                _pct(r.rft),
                _pct(r.capa_on_time),
                _pct(r.actions_on_time),
                "–" if pd.isna(r.cost_variance) else f"{r.cost_variance:+.1%}",
                int(r.overdue_actions_open),
            ]
        )
        fills.append([None, None, r.otif_status, None, r.rft_status, r.capa_status, r.actions_status, r.cost_status, None])
    _table(s, header, rows, col_w=[3.0, 1.0, 1.0, 0.9, 1.0, 1.3, 1.4, 1.1, 1.6], fills=fills)
    _bullets(
        s, ["Green meets the agreement target; amber is within 5 points; red is below that. Definitions: KPI dictionary in the workbook."], top=4.4, size=12
    )

    # 4 escalations
    s = _slide(prs, "Escalations for leadership")
    if esc:
        rows = [
            [f.severity.upper(), f.category.replace("_", " "), f.entity, f"{f.start} → {f.end}", CAUSE_LABEL.get(f.cause or "", "–"), f.summary]
            for f in esc[:6]
        ]
        _table(s, ["Sev.", "Type", "Partner / SKU", "Window", "Root cause", "What we see"], rows, col_w=[0.7, 1.3, 1.4, 2.0, 2.4, 4.5], size=10)
    else:
        _bullets(s, ["No high-severity supply or stock risks this period."])

    # 5 deep dive: lowest OTIF CMO this month (or overall)
    cmos = [p.partner_id for p in PARTNERS]
    worst = cur.loc[cmos].otif.astype(float).fillna(1).idxmin()
    s = _slide(prs, f"Partner deep dive: {PARTNER_BY_ID[worst].name}")
    trend = sc[sc.partner == worst]
    cd = CategoryChartData()
    cd.categories = trend.month.tolist()
    cd.add_series("OTIF", [None if pd.isna(v) else round(float(v), 3) for v in trend.otif])
    cd.add_series("Target", [PARTNER_BY_ID[worst].otif_target] * len(trend))
    chart = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.5), Inches(1.4), Inches(6.6), Inches(4.6), cd).chart
    chart.has_legend, chart.legend.position, chart.legend.include_in_layout = True, XL_LEGEND_POSITION.BOTTOM, False
    chart.value_axis.maximum_scale, chart.value_axis.minimum_scale = 1.0, 0.0
    chart.value_axis.tick_labels.number_format, chart.value_axis.tick_labels.number_format_is_linked = "0%", False
    mine = [f for f in findings if f.entity == worst]
    _bullets(s, [f.summary for f in mine[:5]] or ["No open findings for this partner."], top=1.4, size=13, height=4.8)
    s.shapes[-1].left = Inches(7.3)
    s.shapes[-1].width = Inches(5.6)

    # 6 supply outlook
    s = _slide(prs, "Supply outlook: weeks of supply vs. safety stock")
    wos = weeks_of_supply(data)
    latest = wos[wos.week_start == wos.week_start.max()].sort_values("weeks_of_supply")
    rows, fills = [], []
    for r in latest.head(8).itertuples():
        risk = next((f for f in findings if f.category == "inventory_risk" and f.entity == r.material), None)
        rows.append([r.material, r.description.split(" (")[0], r.cmo, f"{r.weeks_of_supply:.1f}", "4.0", CAUSE_LABEL.get(risk.cause, "–") if risk else "–"])
        fills.append([None, None, None, "red" if r.below_safety_stock else "green", None, None])
    _table(
        s,
        ["NDC", "Product", "Manufacturer", "Weeks of supply", "Safety stock", "Cause of last breach"],
        rows,
        col_w=[1.2, 4.0, 1.6, 1.5, 1.3, 2.7],
        fills=fills,
        size=11,
    )

    # 7 overdue actions / CAPAs: everything that ran past due in the scorecard month
    s = _slide(prs, f"Overdue actions and CAPAs, {month}")
    mend = min(pd.Period(month).end_time.normalize(), data.as_of)
    mstart = pd.Period(month).start_time
    rows = []
    for kind, df, idc in (("Action", data["actions"], "action_id"), ("CAPA", data["capas"], "capa_id")):
        late = df[(df.due >= mstart) & (df.due <= mend) & (df.closed.isna() | (df.closed > df.due))]
        for r in late.itertuples():
            closed = r.closed.date().isoformat() if pd.notna(r.closed) else "open"
            days = ((r.closed if pd.notna(r.closed) else data.as_of) - r.due).days
            topic = getattr(r, "topic", None) or getattr(r, "source", "")
            owner = getattr(r, "owner", "Partner QA")
            rows.append([kind, getattr(r, idc), r.partner, topic, owner, r.due.date().isoformat(), closed, days])
    rows.sort(key=lambda x: -x[-1])
    if rows:
        _table(
            s,
            ["Type", "ID", "Partner", "Topic / source", "Owner", "Due", "Closed", "Days late"],
            [x[:-1] + [str(x[-1])] for x in rows[:9]],
            col_w=[0.9, 1.9, 1.6, 2.0, 1.7, 1.4, 1.4, 1.4],
            size=11,
        )
    else:
        _bullets(s, ["Nothing ran past due this month."])
    open_now = action_ageing(data)
    _bullets(
        s,
        [
            f"Still open past due today: {len(open_now)} action items."
            + (f" Oldest: {open_now.iloc[0].action_id} ({int(open_now.iloc[0].days_overdue)} days)." if len(open_now) else "")
        ],
        top=5.9,
        size=13,
        height=0.8,
    )

    # 8 data quality + asks
    s = _slide(prs, "Data quality and decisions needed")
    q = data.quarantine
    dq = [
        f"{len(g)} rows rejected from {p}'s batch report: " + ", ".join(f"{k} ({v})" for k, v in g.reason.value_counts().items())
        for p, g in q.groupby("partner")
    ]
    asks = []
    for f in esc[:4]:
        if f.category == "late_supply" and f.cause == "material":
            asks.append(f"{f.entity}: request a recovery plan and confirmed API receipt dates; consider expediting or a second API source.")
        elif f.category == "late_supply" and f.cause in ("capacity", "packaging"):
            asks.append(f"{f.entity}: confirm restored capacity and a catch-up schedule; review allocation across products.")
        elif f.category in ("late_supply", "quality_drift"):
            asks.append(f"{f.entity}: joint review with Quality Ops on open deviations blocking release; agree investigation timelines.")
        elif f.category == "inventory_risk":
            asks.append(f"{f.entity}: align with Supply Planning on demand vs. forecast and pull-in options for the next batch.")
        elif f.category == "capa_overdue":
            asks.append(f"{f.entity}: escalate overdue CAPAs to the partner's site head with new committed dates.")
    asks = list(dict.fromkeys(asks))
    _bullets(
        s,
        ["Data quality: " + x for x in (dq or ["all partner reports passed validation."])]
        + ["Ask: " + a for a in (asks or ["no decisions needed this period."])],
        size=14,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(path)
    return path

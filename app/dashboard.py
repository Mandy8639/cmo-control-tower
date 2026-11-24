"""Streamlit dashboard: uv run --extra dashboard streamlit run app/dashboard.py

Synthetic data only. Reads the observed scenario files, never the planted truth.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from control_tower.data import load_scenario
from control_tower.engine import CAUSE_LABEL, find_risks
from control_tower.golden import SCEN_DIR
from control_tower.kpis import scorecard, weeks_of_supply

st.set_page_config(page_title="External Manufacturing Control Tower", layout="wide")
st.title("External Manufacturing Control Tower")
st.caption("SYNTHETIC DATA: fictional partners and simulated operations. Product names from openFDA (public domain). Independent demo.")

scenarios = sorted(f"{p.parent.name}/{p.name}" for p in SCEN_DIR.glob("*/*") if p.is_dir())
choice = st.sidebar.selectbox("Scenario", scenarios, index=scenarios.index("test/111") if "test/111" in scenarios else 0)
data = load_scenario(SCEN_DIR / choice)
sc = scorecard(data)
months = sorted(sc.month.unique())
month = st.sidebar.selectbox("Scorecard month", months, index=max(0, len(months) - 3))
findings = find_risks(data)

st.subheader(f"Network scorecard, {month}")
cur = sc[sc.month == month].set_index("partner")
show = cur[["deliveries", "otif", "rft", "release_days", "capa_on_time", "actions_on_time", "cost_variance", "overdue_actions_open"]].astype(float)
status = cur[["otif_status", "rft_status", "release_status", "capa_status", "actions_status", "cost_status"]]
colors = {"green": "#C6EFCE", "amber": "#FFEB9C", "red": "#FFC7CE", "n/a": ""}


def paint(col: pd.Series) -> list[str]:
    key = {
        "otif": "otif_status",
        "rft": "rft_status",
        "release_days": "release_status",
        "capa_on_time": "capa_status",
        "actions_on_time": "actions_status",
        "cost_variance": "cost_status",
    }.get(col.name)
    return [f"background-color: {colors[status.loc[i, key]]}" if key else "" for i in col.index]


st.dataframe(
    show.style.apply(paint).format(
        {"otif": "{:.0%}", "rft": "{:.0%}", "capa_on_time": "{:.0%}", "actions_on_time": "{:.0%}", "cost_variance": "{:+.1%}", "release_days": "{:.1f}"},
        na_rep="–",
    ),
    width="stretch",
)

left, right = st.columns(2)
with left:
    st.subheader("OTIF trend")
    st.line_chart(sc.pivot(index="month", columns="partner", values="otif"))
with right:
    st.subheader("Weeks of supply (safety stock = 4)")
    wos = weeks_of_supply(data)
    st.line_chart(wos.pivot(index="week_start", columns="material", values="weeks_of_supply"))

st.subheader(f"Risks and escalations ({len(findings)})")
for f in findings:
    window = f" · {f.start} → {f.end}" if f.start else ""
    with st.expander(f"[{f.severity.upper()}] {f.category.replace('_', ' ')} · {f.entity}{window}"):
        st.write(f.summary)
        if f.cause:
            st.write(f"**Root cause:** {CAUSE_LABEL[f.cause]}")
        st.caption("Evidence: " + ", ".join(f.evidence[:20]))

st.subheader("Quarantined rows")
st.dataframe(data.quarantine, width="stretch")

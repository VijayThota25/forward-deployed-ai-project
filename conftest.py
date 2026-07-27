import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# --- palette (validated categorical order; see dataviz skill reference) ---
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQUENTIAL_BLUE = "#2a78d6"
STATUS_COLORS = {"LOW": "#0ca30c", "MEDIUM": "#fab219", "HIGH": "#ec835a", "CRITICAL": "#d03b3b"}
STATUS_ICONS = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
MUTED = "#898781"
GRIDLINE = "#e1e0d9"

st.set_page_config(page_title="Cloud Cost Optimizer", layout="wide", page_icon="💰")


def api_get(path, params=None):
    try:
        resp = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API error calling GET {path}: {e}")
        return None


def api_post(path, params=None):
    try:
        resp = requests.post(f"{API_BASE_URL}{path}", params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API error calling POST {path}: {e}")
        return None


def fixed_color_map(categories):
    return {cat: CATEGORICAL[i % len(CATEGORICAL)] for i, cat in enumerate(sorted(categories))}


def base_layout(fig, height=340):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="#fcfcfb",
        paper_bgcolor="#fcfcfb",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color="#0b0b0b"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRIDLINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(showgrid=True, gridcolor=GRIDLINE, zeroline=False, tickfont=dict(color=MUTED))
    return fig


# --- sidebar: environment controls ---
with st.sidebar:
    st.header("⚙️ Environment")
    st.caption(f"API: {API_BASE_URL}")

    health = api_get("/api/health")
    if health and health.get("status") == "ok":
        st.success("Backend connected")
    else:
        st.error("Backend unreachable — start the API with `uvicorn app.main:app --reload`")

    st.divider()
    st.caption("Mock/simulated cloud provider — no real credentials used.")
    if st.button("🔄 Regenerate synthetic fleet", width='stretch'):
        with st.spinner("Generating synthetic resources + running analysis..."):
            result = api_post("/api/simulate/generate")
        if result:
            st.success(f"Created {result['resources_created']} resources, "
                       f"{result['analysis']['recommendations_created']} recommendations.")
            st.rerun()

    if st.button("▶️ Re-run analysis engine", width='stretch'):
        with st.spinner("Scanning resources for waste..."):
            result = api_post("/api/recommendations/run-analysis")
        if result:
            st.success(f"Scanned {result['resources_scanned']} resources, "
                       f"{result['recommendations_created']} new recommendations.")
            st.rerun()

st.title("💰 Cloud Cost Optimizer & Remediation Engine")
st.caption("API-first waste detection and one-click remediation for a simulated cloud fleet.")

summary = api_get("/api/costs/summary")

if summary is None:
    st.stop()

if summary["resource_count"] == 0:
    st.info("No resources yet. Click **Regenerate synthetic fleet** in the sidebar to seed the environment.")
    st.stop()

# --- KPI row ---
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Monthly Cost", f"${summary['total_monthly_cost']:,.2f}")
k2.metric("Potential Savings", f"${summary['total_potential_savings']:,.2f}")
k3.metric("Realized Savings", f"${summary['total_realized_savings']:,.2f}")
k4.metric("Open Recommendations", summary["open_recommendations"])
k5.metric("Tracked Resources", summary["resource_count"])

st.divider()

# --- cost trend + breakdowns ---
c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("Daily Cost Trend (30d)")
    trend = api_get("/api/costs/trend", params={"days": 30})
    if trend:
        df = pd.DataFrame(trend)
        df["date"] = pd.to_datetime(df["date"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["total_cost"], mode="lines",
            line=dict(color=SEQUENTIAL_BLUE, width=2, shape="spline"),
            fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
            hovertemplate="%{x|%b %d}<br>$%{y:,.2f}<extra></extra>",
        ))
        base_layout(fig)
        st.plotly_chart(fig, width='stretch')

with c2:
    st.subheader("Cost by Resource Type")
    type_df = pd.DataFrame(
        [{"type": k, "cost": v} for k, v in summary["cost_by_type"].items()]
    ).sort_values("cost", ascending=True)
    colors = fixed_color_map(type_df["type"].tolist())
    fig2 = go.Figure(go.Bar(
        x=type_df["cost"], y=type_df["type"], orientation="h",
        marker_color=[colors[t] for t in type_df["type"]],
        hovertemplate="%{y}<br>$%{x:,.2f}<extra></extra>",
    ))
    base_layout(fig2, height=340)
    fig2.update_layout(showlegend=False)
    st.plotly_chart(fig2, width='stretch')

st.subheader("Cost by Region")
region_df = pd.DataFrame(
    [{"region": k, "cost": v} for k, v in summary["cost_by_region"].items()]
).sort_values("cost", ascending=False)
colors_r = fixed_color_map(region_df["region"].tolist())
fig3 = go.Figure(go.Bar(
    x=region_df["region"], y=region_df["cost"],
    marker_color=[colors_r[r] for r in region_df["region"]],
    hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
))
base_layout(fig3, height=280)
fig3.update_layout(showlegend=False)
st.plotly_chart(fig3, width='stretch')

st.divider()

# --- recommendations ---
st.subheader("📋 Recommendations")

f1, f2, f3 = st.columns([1, 1, 2])
status_choice = f1.selectbox("Status", ["OPEN", "REMEDIATED", "DISMISSED", "ALL"], index=0)
severity_choice = f2.selectbox("Severity", ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"], index=0)

params = {}
if status_choice != "ALL":
    params["status_filter"] = status_choice
if severity_choice != "ALL":
    params["severity"] = severity_choice

recommendations = api_get("/api/recommendations", params=params) or []
f3.markdown(f"**{len(recommendations)}** recommendation(s) match filters")

if not recommendations:
    st.caption("No recommendations match the current filters.")
else:
    header = st.columns([3, 1.4, 1.6, 1, 1, 1])
    for col, label in zip(header, ["Recommendation", "Resource", "Action", "Savings/mo", "Severity", ""]):
        col.markdown(f"**{label}**")

    for rec in recommendations:
        row = st.columns([3, 1.4, 1.6, 1, 1, 1])
        row[0].markdown(f"**{rec['title']}**  \n<span style='color:#898781;font-size:0.85em'>{rec['description']}</span>", unsafe_allow_html=True)
        resource = rec.get("resource") or {}
        row[1].write(resource.get("name", "—"))
        row[2].write(rec["suggested_action"].replace("_", " ").title())
        row[3].write(f"${rec['estimated_monthly_savings']:,.2f}")
        sev = rec["severity"]
        row[4].markdown(f"{STATUS_ICONS.get(sev,'')} :{('red' if sev in ('HIGH','CRITICAL') else 'orange' if sev=='MEDIUM' else 'green')}[{sev}]")

        if rec["status"] == "OPEN":
            with row[5]:
                bc1, bc2 = st.columns(2)
                if bc1.button("✅", key=f"remediate-{rec['id']}", help="Remediate"):
                    result = api_post(f"/api/recommendations/{rec['id']}/remediate")
                    if result:
                        st.toast(f"Remediated: saved ${result['savings_realized_monthly']:,.2f}/mo")
                        st.rerun()
                if bc2.button("✖️", key=f"dismiss-{rec['id']}", help="Dismiss"):
                    result = api_post(f"/api/recommendations/{rec['id']}/dismiss")
                    if result:
                        st.rerun()
        else:
            row[5].caption(rec["status"].title())

        if rec.get("cli_command"):
            label = "AWS CLI command" if rec["status"] == "OPEN" else "AWS CLI command (executed)"
            with st.expander(label, icon="⌨️"):
                st.code(rec["cli_command"], language="bash")

st.divider()

# --- resources table ---
with st.expander("🖥️ All Tracked Resources"):
    resources = api_get("/api/resources") or []
    if resources:
        df = pd.DataFrame(resources)[
            ["name", "resource_type", "region", "status", "instance_size", "avg_cpu_utilization",
             "size_gb", "attached", "monthly_cost"]
        ]
        st.dataframe(df, width='stretch', hide_index=True)

# --- remediation action log ---
with st.expander("🗂️ Remediation Action Log"):
    actions = api_get("/api/actions") or []
    if actions:
        df = pd.DataFrame(actions)[
            ["performed_at", "action_type", "status", "savings_realized_monthly", "cli_command", "notes"]
        ]
        st.dataframe(df, width='stretch', hide_index=True)
    else:
        st.caption("No remediation actions performed yet.")

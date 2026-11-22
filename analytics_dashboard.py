"""Private pandas summaries and Plotly charts for AI MatchLab."""

from datetime import datetime, time, timedelta
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import psycopg
import streamlit as st

from owner_analytics import (
    DIRECT, MODES, SOURCES, AnalyticsDatabaseError, check_connections,
    failure_code, is_owner, read_events,
)

SGT = ZoneInfo("Asia/Singapore")
PERIODS = {"Today": 1, "Last 7 Days": 7, "Last 30 Days": 30, "All Time": None}
COLORS = ["#6958a6", "#557797", "#bb6a72"]
COLUMNS = ("kind", "session_id", "mode", "source", "occurred_at", "completed")
CONNECTION_HELP = {
    "MISSING_SETTING": "Add this key under [owner_analytics] in Streamlit Secrets.",
    "INVALID_DSN": "Use a quoted PostgreSQL connection string with an explicit host and user.",
    "POOLER_ROUTE": "Copy the Session pooler host and project ref from the same Supabase Connect dialog. Use ROLE.PROJECT_REF on port 5432.",
    "LOGIN_REJECTED": "Check that the role can log in and use that role's database password.",
    "TLS_VERIFY_FAILED": "Check the exact Session pooler hostname and the Supabase root CA in owner_analytics.ssl_root_cert_pem.",
    "TLS_HANDSHAKE_FAILED": "Check that host and port point to the Supabase Session pooler. Check Pooler Logs for the failed handshake.",
    "INVALID_CA": "Paste the complete Supabase PEM certificate into owner_analytics.ssl_root_cert_pem.",
    "DNS_FAILURE": "Replace host in this setting with the exact hostname from Supabase Connect → Session pooler.",
    "CONNECT_TIMEOUT": "The connection attempt timed out. Confirm the Session pooler host and port 5432, then check project status and database network restrictions.",
    "CONNECTION_REFUSED": "The endpoint refused the connection. Verify the Session pooler host and port 5432, then check whether Supabase blocked the Streamlit app's IP.",
    "NETWORK_ROUTE": "Streamlit could not route to this address. Use the shared Session pooler endpoint on port 5432 for IPv4 connectivity.",
    "CONNECTION_CLOSED": "The connection closed during startup. Check Supabase Pooler Logs at the time of the attempt.",
    "DATABASE_NOT_FOUND": "Use the database name from the Supabase Session pooler connection details, normally postgres.",
    "CONNECTION_LIMIT": "The database or pooler is at its connection limit.",
    "DATABASE_UNAVAILABLE": "Check whether the Supabase project is paused, starting, or recovering.",
    "CONNECT_UNCLASSIFIED": "Connection startup failed with an unrecognized response. Check Supabase Pooler Logs at the time of the attempt.",
    "WRONG_ROLE": "Use the restricted matchlab_writer or matchlab_reader role for its respective key.",
    "ACCESS_DENIED": "Check the schema usage grant, table grant and role policy in the analytics migration.",
    "SCHEMA_MISSING": "Check that this connection targets the Supabase project where the analytics migration ran.",
    "SCHEMA_MISMATCH": "Check the table columns against the analytics migration.",
    "READER_POLICY": "Check that RLS is enabled and the migration's matchlab_read SELECT policy is in effect.",
    "QUERY_TIMEOUT": "The database connected, but the query timed out. Check for locks or Supabase load.",
    "DATABASE_ERROR": "The database operation failed. Check the Supabase Postgres logs for this time.",
}
CSS = """
<style>
.matchlab-kpis { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; }
.matchlab-kpi { color:#282438; background:#fff9f3; border:1px solid #e7def6;
  border-radius:18px; padding:1rem 1.25rem; box-shadow:0 4px 16px #39305312;
  transition:transform 160ms ease, box-shadow 160ms ease; overflow-wrap:anywhere; }
.matchlab-kpi:nth-child(3n+2) { background:#f1edf9; }
.matchlab-kpi:nth-child(3n+3) { background:#eef4fa; }
.matchlab-kpi small { display:block; color:#4d4568; font-size:.9rem; }
.matchlab-kpi strong { font-size:clamp(1.15rem,3vw,1.85rem); }
@media (hover:hover) {
  .matchlab-kpi:hover { transform:translateY(-2px); box-shadow:0 8px 20px #39305320; }
}
@media (max-width:680px) {
  .matchlab-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); gap:.6rem; }
  .matchlab-kpi { padding:.75rem; }
}
@media (prefers-reduced-motion:reduce) {
  .matchlab-kpi { transition:none; }
  .matchlab-kpi:hover { transform:none; }
}
</style>
"""


def date_window(period, now):
    today = now.astimezone(SGT).date()
    days = PERIODS[period]
    start = datetime.combine(today - timedelta(days=days - 1), time.min, SGT) if days else None
    return start, datetime.combine(today + timedelta(days=1), time.min, SGT)


def summarize(rows, start, end):
    events = pd.DataFrame.from_records(rows, columns=COLUMNS)
    visits = events.loc[events.kind == "visit"].copy()
    rounds = events.loc[events.kind == "game_started"]
    traffic = visits.groupby("source").size().reindex([*SOURCES.values(), DIRECT], fill_value=0)
    modes = (rounds.groupby("mode")
             .agg(started=("kind", "size"), completed=("completed", "sum"))
             .reindex(MODES, fill_value=0))
    dates = pd.to_datetime(visits.occurred_at, utc=True).dt.tz_convert(SGT).dt.normalize()
    daily = visits.groupby(dates).size()
    if len(daily):
        first = start or daily.index.min()
        daily = daily.reindex(pd.date_range(first, end - timedelta(days=1)), fill_value=0)
    return len(visits), visits.session_id.nunique(), traffic, daily, modes


def show_chart(fig, key):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=12, r=12, t=15, b=12), height=320,
        legend=dict(orientation="h", y=-0.24),
    )
    st.plotly_chart(fig, key=key, width="stretch", config={"displayModeBar": False, "scrollZoom": False})


def render_dashboard():
    if not is_owner():
        st.error("Owner authentication is required.")
        return

    st.title("AI MatchLab — Owner Analytics")
    period = st.selectbox("Date range · Singapore time", list(PERIODS), index=2)
    st.button("Refresh Analytics", icon=":material/refresh:")
    with st.expander("Database diagnostics"):
        st.caption("Tests both connections. The writer test rolls back its event.")
        if st.button("Check reader and writer"):
            for key, code in check_connections().items():
                if code == "OK":
                    st.success(f"owner_analytics.{key} · OK")
                else:
                    st.warning(f"owner_analytics.{key} · {code}. {CONNECTION_HELP[code]}")
    now = datetime.now(SGT)
    start, end = date_window(period, now)
    try:
        visits, sessions, traffic, daily, modes = summarize(read_events(start, end), start, end)
    except (psycopg.Error, AnalyticsDatabaseError) as error:
        code = failure_code(error)
        st.error(f"Analytics could not load. owner_analytics.read_dsn · {code}. {CONNECTION_HELP[code]}")
        return
    except PermissionError:
        st.error("Owner authentication is required.")
        return
    except (RuntimeError, ValueError):
        st.error("Analytics could not load. The database results could not be summarized.")
        return

    st.caption(f"Last updated {datetime.now(SGT):%d %b %Y, %I:%M:%S %p} SGT")
    started, completed = map(int, modes.sum())
    rate = f"{completed / started:.1%}" if started else "—"
    leaders = modes.index[modes.started == modes.started.max()]
    popular = ("Tie" if len(leaders) > 1 else leaders[0]) if started else "—"
    labels = (
        ("◉", "Total Visits", f"{visits:,}"), ("◈", "Unique Sessions", f"{sessions:,}"),
        ("▷", "Games Started", f"{started:,}"), ("✓", "Games Completed", f"{completed:,}"),
        ("↗", "Completion Rate", rate), ("✦", "Most Popular Mode", popular),
    )
    cards = "".join(
        f'<div class="matchlab-kpi"><small><span aria-hidden="true">{icon}</span> {label}'
        f'</small><strong>{escape(value)}</strong></div>' for icon, label, value in labels
    )
    st.html(f'{CSS}<div class="matchlab-kpis">{cards}</div>')
    if not visits and not started:
        st.info("No activity was recorded in this date range. History begins when tracking is enabled.")
        return

    left, right = st.columns(2)
    with left:
        st.subheader("Traffic Sources")
        if visits:
            show_chart(go.Figure(go.Pie(
                labels=traffic.index.tolist(), values=traffic.tolist(), hole=.63, sort=False,
                marker_colors=COLORS, textinfo="percent",
                hovertemplate="%{label}<br>%{value:,} visits · %{percent}<extra></extra>",
            )), "traffic_sources")
            st.caption(" · ".join(f"{source} {count:,} ({count / visits:.1%})"
                                 for source, count in traffic.items()))
        else:
            st.info("No visits recorded in this date range.")
    with right:
        st.subheader("Daily Visitor Trends")
        if visits:
            fig = go.Figure(go.Scatter(
                x=daily.index.strftime("%Y-%m-%d"), y=daily.values, mode="lines+markers",
                line=dict(color=COLORS[0], width=3),
                hovertemplate="%{x|%d %b %Y}<br>%{y:,} visits<extra></extra>",
            ))
            fig.update_xaxes(type="date")
            fig.update_yaxes(rangemode="tozero", dtick=1 if daily.max() < 6 else None)
            show_chart(fig, "daily_visits")
        else:
            st.info("No daily visit data for this date range.")

    left, right = st.columns(2)
    with left:
        st.subheader("Game Popularity")
        if started:
            fig = go.Figure()
            for name, color in zip(("Started", "Completed"), COLORS):
                fig.add_bar(name=name, x=modes.index, y=modes[name.lower()].tolist(),
                            marker_color=color, texttemplate="%{y:,}", textposition="outside",
                            hovertemplate="%{x}<br>%{y:,}<extra>%{fullData.name}</extra>")
            fig.update_layout(barmode="group", showlegend=True)
            fig.update_yaxes(rangemode="tozero", dtick=1 if modes.started.max() < 6 else None)
            show_chart(fig, "game_modes")
        else:
            st.info("No games started in this date range.")
    with right:
        st.subheader("Game Completion")
        if started:
            st.progress(completed / started, text=f"{completed:,} of {started:,} rounds completed · {rate}")
        else:
            st.info("Completion rate is available once a game starts.")
    st.caption("Visits and unique sessions count one arrival per recorded Streamlit session. "
               "Traffic sources reflect tagged arrivals to AI MatchLab. "
               "Game metrics follow rounds started in the selected dates through to their outcome.")

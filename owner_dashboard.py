"""Private pandas summaries and Plotly charts for AI MatchLab."""

from datetime import datetime, time, timedelta
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import psycopg
import streamlit as st

from match_history import read_dashboard, read_private_details
from owner_analytics import (
    DIRECT, MODES, SOURCES, AnalyticsDatabaseError, check_connections,
    failure_code, is_owner,
)

SGT = ZoneInfo("Asia/Singapore")
PERIODS = {"Today": 1, "Last 7 Days": 7, "Last 30 Days": 30, "All Time": None}
COLORS = ["#7857b1", "#4e78a3", "#c47479", "#478779"]
DETAIL_COLUMNS = ("round_id", "finished_at", "overall", "scores", "prompts")
FILTER_DEFAULTS = {"lab_period": "Last 30 Days", "lab_mode": "All modes", "lab_source": "All sources"}
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


def filter_events(events, mode, source):
    if source != "All sources":
        events = events.loc[events.source == source]
    if mode != "All modes":
        matching = events.loc[(events.kind == "game_started") & (events["mode"] == mode)]
        visits = events.loc[(events.kind == "visit") & events.session_id.isin(matching.session_id)]
        events = pd.concat([visits, matching])
    return events


def score_summary(rounds):
    scored = rounds.loc[rounds.overall.notna()].copy()
    if scored.empty:
        return scored, pd.Series(dtype=float), pd.Series(dtype=float)
    dates = pd.to_datetime(scored.finished_at, utc=True).dt.tz_convert(SGT).dt.normalize()
    trend = scored.groupby(dates).overall.mean().sort_index()
    questions = scored[["prompts", "scores"]].explode(["prompts", "scores"])
    averages = questions.groupby("prompts").scores.mean()
    return scored, trend, averages


def top(series):
    if not series.sum():
        return "—"
    winners = series.index[series == series.max()]
    return str(winners[0]) if len(winners) == 1 else "Tie"


def percentage(completed, started):
    return f"{completed / started:.1%}" if started else "—"


def score_label(score):
    return f"{score:.1f} / 100" if pd.notna(score) else "—"


def cards(items, animate=False):
    content = "".join(
        f'<div class="lab-card"><span class="lab-icon" aria-hidden="true">{icon}</span>'
        f'<div class="lab-card-label">{escape(label)}</div>'
        f'<strong class="{"lab-word-value" if value in (*MODES, DIRECT) else ""}">{escape(value)}</strong>'
        f'<small>{escape(description)}</small></div>'
        for icon, label, value, description in items
    )
    animation = " lab-enter" if animate else ""
    st.html(f'<div class="lab-cards{animation}">{content}</div>')


def panel(key):
    return st.container(key=f"lab_panel_{key}", border=True)


def show_chart(fig, key, height=295):
    fig.update_layout(
        template="plotly_white", font=dict(color="#393249", family="system-ui"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=12, t=18, b=18), height=height,
        legend=dict(orientation="h", y=-.2),
        hoverlabel=dict(bgcolor="#332548", font_color="white", bordercolor="#332548"),
    )
    fig.update_yaxes(gridcolor="#eee8f2", zerolinecolor="#e5deee", automargin=True)
    fig.update_xaxes(automargin=True, fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    st.plotly_chart(fig, key=key, width="stretch",
                    config={"displayModeBar": False, "scrollZoom": False, "responsive": True})


def time_chart(data, unit, color, fill=False):
    fig = go.Figure(go.Scatter(
        x=data.index.strftime("%Y-%m-%d"), y=data.tolist(), mode="lines+markers",
        line=dict(color=color, width=3, shape="spline", smoothing=.55),
        marker=dict(size=6, line=dict(color="white", width=1)),
        fill="tozeroy" if fill else None, fillcolor="rgba(120,87,177,.11)",
        hovertemplate=f"%{{x|%d %b %Y}}<br>%{{y:{',d' if fill else '.1f'}}} {unit}<extra></extra>",
    ))
    fig.update_xaxes(type="date")
    fig.update_yaxes(rangemode="tozero" if fill else "normal", range=None if fill else [0, 100],
                     dtick=1 if fill and data.max() < 6 else None)
    return fig


def show_traffic(traffic, daily, visits):
    left, right = st.columns([1, 1.55])
    with left, panel("sources"):
        st.subheader("Traffic Sources")
        if visits:
            show_chart(go.Figure(go.Pie(
                labels=traffic.index.tolist(), values=traffic.tolist(), hole=.69, sort=False,
                marker=dict(colors=COLORS[:3], line=dict(color="white", width=2)),
                textinfo="percent", showlegend=False,
                hovertemplate="%{label}<br>%{value:,} visits · %{percent}<extra></extra>",
            )).add_annotation(text=f"<b>{visits:,}</b><br>visits", showarrow=False, font_size=17),
                "traffic_sources")
            st.caption(" · ".join(f"{source} {count:,} ({count / visits:.1%})"
                                 for source, count in traffic.items()))
        else:
            st.info("Traffic sources will appear when visits match these filters.")
    with right, panel("daily"):
        st.subheader("Daily Visitors")
        if len(daily):
            show_chart(time_chart(daily, "visits", COLORS[0], fill=True), "daily_visits")
        else:
            st.info("No daily visits match these filters.")


def show_games(modes, started, completed):
    left, right = st.columns(2)
    with left, panel("modes"):
        st.subheader("Bestie vs Couple")
        if started:
            fig = go.Figure()
            rates = [percentage(row.completed, row.started) for row in modes.itertuples()]
            for name, color in zip(("Started", "Completed"), COLORS):
                fig.add_bar(name=name, x=modes.index.tolist(), y=modes[name.lower()].tolist(),
                            marker_color=color, customdata=rates,
                            hovertemplate="%{x}<br>%{y:,} %{fullData.name}<br>"
                                          "%{customdata} completion<extra></extra>")
            fig.update_layout(barmode="group", barcornerradius=5)
            fig.update_yaxes(rangemode="tozero", dtick=1 if modes.started.max() < 6 else None)
            show_chart(fig, "game_modes")
            st.caption(" · ".join(f"{mode} {rate}" for mode, rate in zip(modes.index, rates)))
        else:
            st.info("Mode comparisons will appear when a game starts.")
    with right, panel("funnel"):
        st.subheader("Game Completion Funnel")
        if started:
            show_chart(go.Figure(go.Funnel(
                y=["Started", "Completed"], x=[started, completed], textinfo="value+percent initial",
                marker=dict(color=[COLORS[0], COLORS[3]]),
                hovertemplate="%{y}<br>%{x:,} rounds · %{percentInitial:.1%}<extra></extra>",
            )), "completion_funnel")
            st.progress(completed / started, text=f"{percentage(completed, started)} of started games completed")
        else:
            st.info("Completion rate is available once a game starts.")


def show_scores(scored, trend):
    left, right = st.columns(2)
    with left, panel("distribution"):
        st.subheader("Match Score Distribution")
        if scored.empty:
            st.info("No recorded scores match these filters.")
        else:
            bands = ["0–20", "21–40", "41–60", "61–80", "81–100"]
            counts = pd.cut(scored.overall.round(), [-1, 20, 40, 60, 80, 100], labels=bands)
            totals = counts.value_counts(sort=False)
            fig = go.Figure(go.Bar(
                x=bands, y=totals.tolist(), marker_color=[*COLORS, "#9b76ba"],
                hovertemplate="%{x} / 100<br>%{y:,} scored matches<extra></extra>",
            ))
            fig.update_layout(barcornerradius=5)
            fig.update_yaxes(rangemode="tozero", dtick=1 if totals.max() < 6 else None)
            show_chart(fig, "distribution")
            st.caption("Scores are rounded to the nearest whole point for these ranges.")
    with right, panel("trend"):
        st.subheader("Average Matching Score Trend")
        if trend.empty:
            st.info("Score trends will appear as scored games finish.")
        else:
            show_chart(time_chart(trend, "/ 100", COLORS[1]), "score_trend")
            st.caption("Averages are grouped by completion day in Singapore time.")


def show_insights(scored, averages, modes, completed):
    st.header("AI Matching Insights")
    stats = scored.overall.agg(["mean", "max", "min"])
    mode_cards = [
        ("◈", f"{mode} completion", percentage(row.completed, row.started),
         f"{row.completed:,} of {row.started:,} games finished")
        for mode, row in modes.iterrows()
    ]
    cards((
        ("◒", "Average compatibility", score_label(stats["mean"]), "Across scored matches"),
        ("↑", "Highest compatibility", score_label(stats["max"]), "Highest overall score"),
        ("↓", "Lowest compatibility", score_label(stats["min"]), "Lowest overall score"),
        ("◇", "Most selected mode", top(modes.started), "Based on games started"),
        ("✓", "Total completed matches", f"{completed:,}", "Includes rounds without recorded scores"),
        *mode_cards,
    ))
    with panel("question_insights"):
        st.subheader("How questions scored")
        if averages.empty:
            st.info("Question averages will appear as scores are recorded.")
        else:
            high, low = averages.max(), averages.min()
            for label, value in (("Highest average", high), ("Lowest average", low)):
                prompts = " · ".join(averages.index[averages == value])
                st.text(f"{label} · {score_label(value)}")
                st.write(prompts)


def show_round_details(row, available):
    with panel("round_detail"):
        st.subheader("Match details")
        st.text(f"{row.mode} · Finished {format_date(row.finished_at)}")
        if pd.isna(row.overall):
            st.info("No score snapshot was recorded for this round.")
            return

        st.metric("Overall compatibility", score_label(row.overall))
        strongest = max(range(len(row.scores)), key=row.scores.__getitem__)
        weakest = min(range(len(row.scores)), key=row.scores.__getitem__)
        st.text(f"Strongest question · Q{strongest + 1}")
        st.text(f"Weakest question · Q{weakest + 1}")
        if strongest == weakest:
            st.caption("All five recorded scores are tied.")
        show_chart(go.Figure(go.Bar(
            x=[f"Q{i}" for i in range(1, 6)], y=row.scores,
            marker_color=[COLORS[0]] * 5, customdata=row.prompts,
            hovertemplate="%{customdata}<br>%{y:.1f} / 100<extra></extra>",
        )).update_yaxes(range=[0, 100]), "round_question_scores", height=200)

        private = None
        if available:
            try:
                private = read_private_details(row.name)
            except (psycopg.Error, AnalyticsDatabaseError, PermissionError):
                st.warning("Shared answers are temporarily unavailable.")
        if private:
            names, first_answers, second_answers = private
            st.caption("Both players opted in to share these details.")
        else:
            st.caption("There are no shared names or answers available for this round.")
        for index, (prompt, score) in enumerate(zip(row.prompts, row.scores, strict=True)):
            with st.expander(f"{index + 1}. {prompt} · {score:.1f} / 100"):
                if private:
                    for name, answer in zip(names, (first_answers[index], second_answers[index])):
                        st.text(name)
                        st.text(answer)
                else:
                    st.caption("Only the anonymous question score is available.")


def format_date(timestamp):
    return pd.Timestamp(timestamp).tz_convert(SGT).strftime("%d %b %Y, %I:%M %p SGT")


def show_recent(rounds, available):
    st.header("Recent Games & Match Details")
    if rounds.empty:
        st.info("Games matching your filters will appear here.")
        return
    recent = rounds.sort_values(["occurred_at", "round_id"], ascending=False).head(50).copy()
    recent["Session"] = recent.session_id.astype(str).str[:8]
    recent["Started (SGT)"] = recent.occurred_at.map(format_date)
    recent["Status"] = recent.completed.map({True: "Completed", False: "Started"})
    recent["Score"] = recent.overall.map(score_label)
    table = recent.rename(columns={"mode": "Mode", "source": "Traffic source"})
    st.dataframe(table[["Session", "Mode", "Started (SGT)", "Traffic source", "Status", "Score"]],
                 hide_index=True, width="stretch", key="lab_recent_games")
    st.caption(f"Showing the latest {len(recent):,} of {len(rounds):,} matching rounds.")
    completed = recent.loc[recent.completed].set_index("round_id")
    if not completed.empty:
        selected = st.selectbox(
            "Open a completed game", completed.index.tolist(), index=None,
            format_func=lambda key: (f"{completed.at[key, 'Session']} · {completed.at[key, 'mode']} · "
                                     f"{completed.at[key, 'Started (SGT)']} · {str(key)[:6]}"),
            key="lab_selected_round",
        )
        if selected is not None:
            show_round_details(completed.loc[selected], available)


def clear_filters():
    st.session_state.update(FILTER_DEFAULTS)
    st.session_state.pop("lab_custom", None)
    st.session_state.pop("lab_selected_round", None)


def render_dashboard():
    if not is_owner():
        st.session_state.pop("lab_snapshot", None)
        st.error("Owner authentication is required.")
        return

    with st.container(key="owner_dashboard"):
        st.html(Path(__file__).with_name("analytics_dashboard.css"))
        dashboard_body()


def dashboard_body():
    st.title("AI MatchLab — Owner Analytics")
    st.caption("Private dashboard · Singapore time")
    now = datetime.now(SGT)
    with panel("filters"):
        first, second, third = st.columns(3)
        period = first.selectbox("Date range", [*PERIODS, "Custom date range"], index=2, key="lab_period")
        mode = second.selectbox("Game mode", ["All modes", *MODES], key="lab_mode")
        source = third.selectbox("Traffic source", ["All sources", *SOURCES.values(), DIRECT], key="lab_source")
        refresh, clear = st.columns(2)
        reload_data = refresh.button("Refresh Analytics", icon=":material/refresh:", type="primary")
        clear.button("Clear Filters", on_click=clear_filters)
        if period == "Custom date range":
            custom = st.date_input("Start and end dates", (now.date() - timedelta(days=6), now.date()),
                                   max_value=now.date(), key="lab_custom")
            if len(custom) < 2:
                st.info("Select both dates to see your results.")
                return
            start = datetime.combine(custom[0], time.min, SGT)
            end = datetime.combine(custom[1] + timedelta(days=1), time.min, SGT)
        else:
            start, end = date_window(period, now)

    snapshot = st.session_state.get("lab_snapshot")
    first_load = snapshot is None and not st.session_state.get("lab_has_animated")
    if reload_data or snapshot is None or snapshot[:2] != (start, end):
        try:
            with st.spinner("Loading analytics…", show_time=False):
                rows, available = read_dashboard(start, end)
            snapshot = start, end, datetime.now(SGT), rows, available
            st.session_state.lab_snapshot = snapshot
        except (psycopg.Error, AnalyticsDatabaseError) as error:
            code = failure_code(error)
            st.error(f"Analytics could not load. owner_analytics.read_dsn · {code}. {CONNECTION_HELP.get(code, '')}")
            if snapshot is None or snapshot[:2] != (start, end):
                diagnostics()
                return
            st.warning("Showing the last successful refresh for this date range.")
        except PermissionError:
            st.session_state.pop("lab_snapshot", None)
            st.error("Owner authentication is required.")
            return

    _, _, updated, rows, available = snapshot
    st.caption(f"Last updated {updated:%d %b %Y, %I:%M:%S %p} SGT")
    events = filter_events(pd.DataFrame.from_records(rows, columns=COLUMNS + DETAIL_COLUMNS), mode, source)
    visits, sessions, traffic, daily, modes = summarize(
        events.loc[:, list(COLUMNS)].itertuples(index=False, name=None), start, end
    )
    rounds = events.loc[events.kind == "game_started"]
    scored, trend, averages = score_summary(rounds)
    started, completed = map(int, modes.sum())
    cards((
        ("◉", "Total Visits", f"{visits:,}", "Tracked arrivals"),
        ("◈", "Unique Sessions", f"{sessions:,}", "Distinct visitor sessions"),
        ("▷", "Games Started", f"{started:,}", "Rounds opened"),
        ("✓", "Games Completed", f"{completed:,}", "Rounds that reached results"),
        ("↗", "Completion Rate", percentage(completed, started), "Share of started rounds"),
        ("✦", "Average Match Score", score_label(scored.overall.mean()), f"{len(scored):,} scored rounds"),
        ("◇", "Most Popular Mode", top(modes.started), "Based on games started"),
        ("→", "Most Popular Traffic Source", top(traffic), "Based on tracked arrivals"),
    ), animate=first_load)
    st.session_state.lab_has_animated = True
    if not available:
        st.info("Score history will begin after migration 002 is applied. Existing usage analytics remain available.")
    st.caption("Game counts follow rounds started in the selected dates through to their outcome. "
               "With a mode filter, visits include sessions that started that mode within the date range.")
    tab_traffic, tab_play, tab_scores = st.tabs(["Traffic", "Gameplay", "Scores"])
    with tab_traffic:
        show_traffic(traffic, daily, visits)
    with tab_play:
        show_games(modes, started, completed)
    with tab_scores:
        show_scores(scored, trend)
    show_insights(scored, averages, modes, completed)
    show_recent(rounds, available)
    diagnostics()


def diagnostics():
    with st.expander("Database diagnostics"):
        st.caption("Tests both connections. The writer test rolls back its event.")
        if st.button("Check reader and writer"):
            for key, code in check_connections().items():
                if code == "OK":
                    st.success(f"owner_analytics.{key} · OK")
                else:
                    st.warning(f"owner_analytics.{key} · {code}. {CONNECTION_HELP.get(code, '')}")

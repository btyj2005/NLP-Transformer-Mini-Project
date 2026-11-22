"""Anonymous event recording and the verified owner-only read boundary."""

from contextlib import contextmanager
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

import psycopg
import streamlit as st

GITHUB_SUBJECT = "github|247741615"
SOURCES = {"linkedin": "LinkedIn", "github": "GitHub"}
DIRECT = "Direct / Other"
MODES = ("Bestie Mode", "Couple Mode")


def settings(section):
    try:
        return st.secrets.get(section, {})
    except (FileNotFoundError, ValueError):
        return {}


def owner_login_configured():
    auth = settings("auth")
    return all(auth.get(key) for key in ("redirect_uri", "cookie_secret", "client_id",
                                         "client_secret", "server_metadata_url")) and bool(
        settings("owner_analytics").get("issuer")
    )


def is_owner():
    if not owner_login_configured() or not st.user.is_logged_in:
        return False
    expires = st.user.get("exp")
    return (
        st.user.get("iss") == settings("owner_analytics")["issuer"]
        and st.user.get("sub") == GITHUB_SUBJECT
        and isinstance(expires, (int, float))
        and expires > datetime.now(timezone.utc).timestamp()
    )


def source_for(value):
    return SOURCES.get(value.strip().casefold(), DIRECT)


def initialize_visit():
    state = st.session_state
    if "analytics_session" in state or is_owner() or not settings("owner_analytics").get("write_dsn"):
        return
    headers = st.context.headers
    agent = headers.get("User-Agent", "").lower()
    purpose = (headers.get("Sec-Purpose", "") + headers.get("Purpose", "")).lower()
    if not agent or "prefetch" in purpose or any(
        marker in agent for marker in ("bot", "crawler", "spider", "headlesschrome")
    ):
        return
    state.analytics_session = uuid4()
    values = st.query_params.get_all("utm_source")
    state.analytics_source = source_for(values[0]) if len(values) == 1 else DIRECT
    record("visit")


def record(kind, round_id=None, mode=None):
    state = st.session_state
    session_id = state.get("analytics_session")
    if not session_id or is_owner():
        return
    pending = state.setdefault("analytics_pending", {})
    scope = round_id or session_id
    # Keep the first timestamp if a callback runs again before a successful write.
    if len(pending) < 100:
        pending.setdefault((kind, scope), (
            kind, scope, session_id, round_id, mode, state.analytics_source,
            datetime.now(timezone.utc),
        ))


@contextmanager
def connect(dsn):
    with psycopg.connect(dsn, connect_timeout=2, sslmode="verify-full",
                         prepare_threshold=None) as conn:
        conn.execute("SET LOCAL statement_timeout = '2500ms'")
        yield conn


def flush_events():
    state = st.session_state
    pending = state.get("analytics_pending")
    if is_owner():
        if pending:
            pending.clear()
        return
    dsn = settings("owner_analytics").get("write_dsn")
    if not pending or not dsn or monotonic() < state.get("analytics_retry_after", 0):
        return
    try:
        with connect(dsn) as conn, conn.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO matchlab_analytics.events
                   (kind, scope_id, session_id, round_id, mode, source, occurred_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                list(pending.values()),
            )
    except (psycopg.Error, ValueError):
        state.analytics_retry_after = monotonic() + 30
    else:
        pending.clear()


def read_events(start, end):
    """Read a visit window and the lifetime outcomes of rounds started in it."""
    if not is_owner():
        raise PermissionError("Owner authentication required.")
    dsn = settings("owner_analytics").get("read_dsn")
    if not dsn:
        raise RuntimeError("Analytics database is not configured.")
    with connect(dsn) as conn:
        return conn.execute(
            """SELECT event.kind, event.session_id, event.mode, event.source,
                      event.occurred_at, completion.round_id IS NOT NULL AS completed
               FROM matchlab_analytics.events AS event
               LEFT JOIN matchlab_analytics.events AS completion
                 ON event.kind = 'game_started'
                AND completion.kind = 'game_completed'
                AND completion.scope_id = event.scope_id
                AND completion.session_id = event.session_id
                AND completion.mode = event.mode
                AND completion.occurred_at >= event.occurred_at
               WHERE event.kind IN ('visit', 'game_started')
                 AND (%s::timestamptz IS NULL OR event.occurred_at >= %s)
                 AND event.occurred_at < %s""",
            (start, start, end),
        ).fetchall()

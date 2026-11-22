"""Anonymous event recording and the verified owner-only read boundary."""

from contextlib import contextmanager
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from time import monotonic
from uuid import uuid4

import psycopg
import streamlit as st
from psycopg.conninfo import conninfo_to_dict

GITHUB_SUBJECT = "github|247741615"
SOURCES = {"linkedin": "LinkedIn", "github": "GitHub"}
DIRECT = "Direct / Other"
MODES = ("Bestie Mode", "Couple Mode")
LOGGER = getLogger(__name__)
INSERT_EVENT = """INSERT INTO matchlab_analytics.events
    (kind, scope_id, session_id, round_id, mode, source, occurred_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING"""
CONNECT_SQLSTATES = {
    "28P01": "LOGIN_REJECTED",
    "28000": "LOGIN_REJECTED",
    "3D000": "DATABASE_NOT_FOUND",
    "53300": "CONNECTION_LIMIT",
    "57P03": "DATABASE_UNAVAILABLE",
}
POOLER_ROUTE_MESSAGES = ("tenant or user not found", "tenant/user", "(enotfound)", "worker_not_found")
# When libpq tried multiple addresses, prefer a failure from the furthest
# stage reached. Inspect driver text locally and emit only these fixed codes.
CONNECT_MESSAGES = (
    ("LOGIN_REJECTED", (
        "authentication failed", "no password supplied", "sasl authentication",
        "eauthquery", "no pg_hba.conf entry", "is not permitted to log in",
    )),
    ("DATABASE_NOT_FOUND", ("database does not exist",)),
    ("CONNECTION_LIMIT", (
        "too many connections", "too many clients", "max client connections reached",
        "remaining connection slots", "maxclientsinsessionmode",
    )),
    ("DATABASE_UNAVAILABLE", (
        "database system is starting up", "database system is shutting down",
        "database system is in recovery mode", "database is paused",
    )),
    ("TLS_VERIFY_FAILED", (
        "certificate verify failed", "certificate verification failed", "server certificate",
        "root certificate", "self-signed certificate", "unknown ca", "certificate has expired",
        "could not load ssl certificate",
    )),
    ("TLS_HANDSHAKE_FAILED", (
        "ssl error:", "tls alert", "ssl is required", "does not support ssl",
        "ssl negotiation", "tls handshake", "invalid response to gssapi negotiation",
    )),
    ("CONNECTION_CLOSED", (
        "server closed the connection unexpectedly", "connection reset by peer",
        "ssl connection has been closed unexpectedly", "eof detected",
    )),
    ("CONNECT_TIMEOUT", (
        "timeout expired", "timed out", "connection timeout", "connection attempt timed out",
    )),
    ("CONNECTION_REFUSED", ("connection refused", "actively refused")),
    ("NETWORK_ROUTE", ("network is unreachable", "no route to host", "network is down")),
    ("DNS_FAILURE", (
        "could not translate host name", "getaddrinfo failed", "name or service not known",
        "temporary failure in name resolution", "no such host", "nodename nor servname provided",
    )),
)


class AnalyticsDatabaseError(RuntimeError):
    """Carries a fixed diagnostic code suitable for the owner UI and server logs."""


def failure_code(error):
    if isinstance(error, AnalyticsDatabaseError):
        return str(error)
    return {
        "42501": "ACCESS_DENIED",
        "42P01": "SCHEMA_MISSING",
        "3F000": "SCHEMA_MISSING",
        "42703": "SCHEMA_MISMATCH",
        "57014": "QUERY_TIMEOUT",
    }.get(getattr(error, "sqlstate", None), "DATABASE_ERROR")


def connection_failure(error):
    # Supavisor can report a routing failure as an authorization error.
    message = str(error).casefold()
    if any(marker in message for marker in POOLER_ROUTE_MESSAGES):
        return "POOLER_ROUTE"
    sqlstate = CONNECT_SQLSTATES.get(error.sqlstate)
    if sqlstate:
        return sqlstate
    if re.search(r'(?:role|user) "[^"\n]+" does not exist', message):
        return "LOGIN_REJECTED"
    if re.search(r'database "[^"\n]+" does not exist', message):
        return "DATABASE_NOT_FOUND"
    for code, markers in CONNECT_MESSAGES:
        if any(marker in message for marker in markers):
            return code
    return "CONNECT_UNCLASSIFIED"


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
    if "prefetch" in purpose or any(
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
def connect(dsn, ca_path=None):
    try:
        options = conninfo_to_dict(dsn)
    except (psycopg.Error, TypeError, ValueError):
        raise AnalyticsDatabaseError("INVALID_DSN") from None
    if not options.get("host") or not options.get("user"):
        raise AnalyticsDatabaseError("INVALID_DSN")
    try:
        conn = psycopg.connect(
            dsn, connect_timeout=5, sslmode="verify-full",
            sslrootcert=ca_path or options.get("sslrootcert") or "system",
            prepare_threshold=None,
        )
    except psycopg.Error as error:
        raise AnalyticsDatabaseError(connection_failure(error)) from None
    with conn:
        conn.execute("SET LOCAL statement_timeout = '2500ms'")
        yield conn


@contextmanager
def database_connection(key):
    config = settings("owner_analytics")
    dsn, ca = config.get(key), config.get("ssl_root_cert_pem")
    if not dsn:
        raise AnalyticsDatabaseError("MISSING_SETTING")
    if not isinstance(dsn, str):
        raise AnalyticsDatabaseError("INVALID_DSN")
    if ca is None:
        with connect(dsn) as conn:
            yield conn
        return
    if not isinstance(ca, str) or not ca.strip().startswith("-----BEGIN CERTIFICATE-----"):
        raise AnalyticsDatabaseError("INVALID_CA")
    try:
        with TemporaryDirectory(prefix="matchlab-ca-") as folder:
            path = Path(folder) / "root.crt"
            path.write_text(ca, encoding="ascii")
            with connect(dsn, str(path)) as conn:
                yield conn
    except (OSError, UnicodeError):
        raise AnalyticsDatabaseError("INVALID_CA") from None


def check_role(conn, role):
    matches = conn.execute(
        """SELECT current_user = %s AND NOT (rolsuper OR rolbypassrls)
           FROM pg_catalog.pg_roles WHERE rolname = current_user""",
        (role,),
    ).fetchone()
    if matches != (True,):
        raise AnalyticsDatabaseError("WRONG_ROLE")


def check_reader_policy(conn):
    if conn.execute(
        """SELECT row_security_active('matchlab_analytics.events'),
                  EXISTS (
                      SELECT 1 FROM pg_catalog.pg_policies
                      WHERE schemaname = 'matchlab_analytics' AND tablename = 'events'
                        AND policyname = 'matchlab_read' AND cmd = 'SELECT'
                        AND current_user = ANY(roles) AND qual = 'true'
                  )"""
    ).fetchone() != (True, True):
        raise AnalyticsDatabaseError("READER_POLICY")


def check_connections():
    """Probe both roles on demand. The writer's test event is rolled back."""
    if not is_owner():
        raise PermissionError("Owner authentication required.")
    results = {}
    for key, role in (("write_dsn", "matchlab_writer"), ("read_dsn", "matchlab_reader")):
        try:
            with database_connection(key) as conn:
                check_role(conn, role)
                if key == "write_dsn":
                    session = uuid4()
                    with conn.transaction(force_rollback=True):
                        conn.execute(INSERT_EVENT, (
                            "visit", session, session, None, None, DIRECT, datetime.now(timezone.utc),
                        ))
                else:
                    check_reader_policy(conn)
                    conn.execute("SELECT 1 FROM matchlab_analytics.events LIMIT 1").fetchone()
        except (AnalyticsDatabaseError, psycopg.Error) as error:
            results[key] = failure_code(error)
        else:
            results[key] = "OK"
    return results


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
        with database_connection("write_dsn") as conn, conn.cursor() as cursor:
            check_role(conn, "matchlab_writer")
            cursor.executemany(INSERT_EVENT, list(pending.values()))
    except (AnalyticsDatabaseError, psycopg.Error) as error:
        LOGGER.warning("Analytics write failed [%s]", failure_code(error))
        state.analytics_retry_after = monotonic() + 30
    else:
        pending.clear()


def read_events(start, end):
    """Read a visit window and the lifetime outcomes of rounds started in it."""
    if not is_owner():
        raise PermissionError("Owner authentication required.")
    with database_connection("read_dsn") as conn:
        check_role(conn, "matchlab_reader")
        check_reader_policy(conn)
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

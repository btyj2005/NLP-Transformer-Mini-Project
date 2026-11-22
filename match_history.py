"""Anonymous score history and separately retained, explicitly consented details."""

from hashlib import sha256
from json import dumps
from uuid import UUID, uuid4

import psycopg
import streamlit as st

from owner_analytics import (
    AnalyticsDatabaseError, LOGGER, check_reader_policy, check_role, database_connection,
    failure_code, is_owner,
)

SCORES_SQL = """
    INSERT INTO matchlab_analytics.match_scores (round_id, overall, scores, prompts)
    VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
"""
DETAILS_SQL = """
    INSERT INTO matchlab_analytics.private_match_details
        (round_id, names, first_answers, second_answers, deletion_hash)
    VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
"""


def consent_marker(round_id, name, answers):
    """Bind an affirmative choice to one player’s exact final content and round."""
    return round_id, sha256(dumps([name, answers], ensure_ascii=False).encode()).digest()


def joint_consent(round_id, choices, names, answers):
    return bool(round_id) and all(
        choices.get(index) == consent_marker(round_id, names[index], answers[index])
        for index in range(2)
    )


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def _sharing_available():
    try:
        with database_connection("write_dsn") as conn:
            check_role(conn, "matchlab_writer")
            return match_history_available(conn)
    except (psycopg.Error, AnalyticsDatabaseError):
        return False


def sharing_available():
    return bool(st.session_state.get("analytics_session")) and not is_owner() and _sharing_available()


def save_match(round_id, result, prompts, private=None):
    """Write one snapshot. Return a deletion code only for a committed private insert."""
    if not round_id or not st.session_state.get("analytics_session") or is_owner():
        return None
    code = None
    try:
        with database_connection("write_dsn") as conn:
            check_role(conn, "matchlab_writer")
            if not match_history_available(conn):
                return None
            inserted = conn.execute(
                SCORES_SQL, (round_id, result.overall, list(result.scores), list(prompts))
            ).rowcount
            if inserted and private:
                names, answers = private
                candidate = uuid4()
                try:
                    with conn.transaction():
                        written = conn.execute(
                            DETAILS_SQL, (round_id, list(names), list(answers[0]), list(answers[1]),
                                          sha256(str(candidate).encode()).digest()),
                        ).rowcount
                        if written:
                            code = candidate
                except psycopg.Error as error:
                    LOGGER.warning("Private match save failed [%s]", failure_code(error))
    except (psycopg.Error, AnalyticsDatabaseError) as error:
        LOGGER.warning("Match score save failed [%s]", failure_code(error))
        return None
    return code


def delete_private_details(value):
    """Holder of a round’s random receipt may remove its private data."""
    try:
        code = UUID(value.strip())
    except (ValueError, AttributeError):
        return False
    try:
        with database_connection("write_dsn") as conn:
            check_role(conn, "matchlab_writer")
            conn.execute("SELECT matchlab_analytics.delete_private_match(%s)", (code,))
    except (psycopg.Error, AnalyticsDatabaseError) as error:
        LOGGER.warning("Private match deletion failed [%s]", failure_code(error))
        return False
    return True


def read_private_details(round_id):
    if not is_owner():
        raise PermissionError("Owner authentication required.")
    with database_connection("read_dsn") as conn:
        check_role(conn, "matchlab_reader")
        if conn.execute(
            "SELECT row_security_active('matchlab_analytics.private_match_details')"
        ).fetchone() != (True,):
            raise AnalyticsDatabaseError("READER_POLICY")
        return conn.execute(
            """SELECT names, first_answers, second_answers
               FROM matchlab_analytics.private_match_details WHERE round_id = %s""",
            (round_id,),
        ).fetchone()


def match_history_available(conn):
    return conn.execute(
        """SELECT to_regclass('matchlab_analytics.match_scores') IS NOT NULL
              AND to_regclass('matchlab_analytics.private_match_details') IS NOT NULL"""
    ).fetchone()[0]


def read_dashboard(start, end):
    """Read visits and the lifetime outcomes of rounds started in the window."""
    if not is_owner():
        raise PermissionError("Owner authentication required.")
    with database_connection("read_dsn") as conn:
        check_role(conn, "matchlab_reader")
        check_reader_policy(conn)
        available = match_history_available(conn)
        columns = "score.overall, score.scores, score.prompts" if available else "NULL, NULL, NULL"
        score_join = ""
        if available:
            score_join = """
                LEFT JOIN matchlab_analytics.match_scores score ON score.round_id = completion.scope_id
            """
        rows = conn.execute(
            f"""SELECT event.kind, event.session_id, event.mode, event.source,
                       event.occurred_at, completion.round_id IS NOT NULL AS completed,
                       event.round_id, completion.occurred_at, {columns}
                FROM matchlab_analytics.events AS event
                LEFT JOIN matchlab_analytics.events AS completion
                  ON event.kind = 'game_started'
                 AND completion.kind = 'game_completed'
                 AND completion.scope_id = event.scope_id
                 AND completion.session_id = event.session_id
                 AND completion.mode = event.mode
                 AND completion.occurred_at >= event.occurred_at
                {score_join}
                WHERE event.kind IN ('visit', 'game_started')
                  AND (%s::timestamptz IS NULL OR event.occurred_at >= %s)
                  AND event.occurred_at < %s""",
            (start, start, end),
        ).fetchall()
    return rows, available

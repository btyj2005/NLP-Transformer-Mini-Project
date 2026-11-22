from datetime import datetime, timezone
from uuid import uuid4

import pytest
import psycopg
from streamlit.testing.v1 import AppTest

import owner_analytics as analytics
from owner_dashboard import date_window, summarize
from test_game import APP, click


class User(dict):
    @property
    def is_logged_in(self):
        return bool(self)


@pytest.fixture
def configure(monkeypatch):
    issuer = "https://example.eu.auth0.com/"
    monkeypatch.setattr(analytics, "owner_login_configured", lambda: True)
    monkeypatch.setattr(analytics, "settings", lambda _: {
        "issuer": issuer, "write_dsn": "test", "read_dsn": "test",
    })
    monkeypatch.setattr(analytics.st.context.__class__, "headers", property(
        lambda _: {"User-Agent": "Mozilla/5.0"}
    ))
    return issuer


@pytest.mark.parametrize("identity,allowed", [
    ({}, False),
    ({"sub": "github|99", "preferred_username": "btyj2005"}, False),
    ({"sub": "github|247741615", "exp": 0}, False),
    ({"sub": "github|247741615", "iss": "https://other.example/"}, False),
    ({"sub": "github|247741615"}, True),
])
def test_server_authorization(configure, monkeypatch, identity, allowed):
    user = User({"iss": configure, "exp": 4102444800, **identity} if identity else {})
    monkeypatch.setattr(analytics.st, "user", user)
    accesses = []

    def unavailable(dsn):
        accesses.append(dsn)
        raise psycopg.OperationalError()

    monkeypatch.setattr(analytics, "connect", unavailable)
    assert analytics.is_owner() is allowed
    expected = psycopg.OperationalError if allowed else PermissionError
    with pytest.raises(expected):
        analytics.read_events(None, datetime.now(timezone.utc))
    assert accesses == (["test"] if allowed else [])
    if not allowed:
        with pytest.raises(PermissionError):
            analytics.check_connections()
        assert accesses == []


def test_missing_user_agent_still_tracks_visit(configure, monkeypatch):
    monkeypatch.setattr(analytics.st, "user", User())
    monkeypatch.setattr(analytics.st.context.__class__, "headers", property(lambda _: {}))
    monkeypatch.setattr(analytics, "connect", lambda _: (_ for _ in ()).throw(psycopg.OperationalError()))
    app = AppTest.from_file(str(APP)).run().run()
    assert not app.exception
    assert [row[0] for row in app.session_state.analytics_pending.values()] == ["visit"]


@pytest.mark.parametrize("driver_message,code", [
    ("FATAL: Tenant or user not found", "POOLER_ROUTE"),
    ("FATAL: (ENOTFOUND) tenant/user private not found", "POOLER_ROUTE"),
    ("FATAL: password authentication failed", "LOGIN_REJECTED"),
    ('FATAL: role "private" does not exist', "LOGIN_REJECTED"),
    ("fe_sendauth: no password supplied", "LOGIN_REJECTED"),
    ("SSL error: certificate verify failed", "TLS_VERIFY_FAILED"),
    ("server does not support SSL, but SSL was required", "TLS_HANDSHAKE_FAILED"),
    ("timeout expired", "CONNECT_TIMEOUT"),
    ("Connection refused", "CONNECTION_REFUSED"),
    ("Network is unreachable", "NETWORK_ROUTE"),
    ('could not translate host name "ssl-private.example" to address: Name or service not known',
     "DNS_FAILURE"),
    ("connection refused\nFATAL: password authentication failed", "LOGIN_REJECTED"),
    ("SSL SYSCALL error: EOF detected", "CONNECTION_CLOSED"),
    ('FATAL: database "private" does not exist', "DATABASE_NOT_FOUND"),
    ("FATAL: remaining connection slots are reserved", "CONNECTION_LIMIT"),
    ("FATAL: the database system is starting up", "DATABASE_UNAVAILABLE"),
    ("unexpected startup response", "CONNECT_UNCLASSIFIED"),
])
def test_connection_errors_report_safe_codes(monkeypatch, driver_message, code):
    def fail(*args, **kwargs):
        assert kwargs["sslmode"] == "verify-full"
        assert kwargs["sslrootcert"] == "system"
        assert kwargs["connect_timeout"] == 5
        raise psycopg.OperationalError(f"{driver_message} host=private.example password=private")

    monkeypatch.setattr(analytics.psycopg, "connect", fail)
    with pytest.raises(analytics.AnalyticsDatabaseError) as detail:
        with analytics.connect("host=private.example user=matchlab_writer password=private"):
            pytest.fail("Unexpected connection")
    assert str(detail.value) == code
    assert detail.value.__suppress_context__


def test_connection_sqlstate_and_pooler_routing():
    assert analytics.connection_failure(psycopg.errors.InvalidPassword("private")) == "LOGIN_REJECTED"
    error = psycopg.errors.InvalidAuthorizationSpecification("Tenant or user not found")
    assert analytics.connection_failure(error) == "POOLER_ROUTE"


def test_dashboard_reports_reader_and_writer_independently(configure, monkeypatch):
    monkeypatch.setattr(analytics.st, "user", User(
        iss=configure, sub=analytics.GITHUB_SUBJECT, exp=4102444800,
    ))
    monkeypatch.setattr(analytics, "settings", lambda _: {
        "issuer": configure, "write_dsn": "bad=private-password",
    })
    app = AppTest.from_file(str(APP)).run()
    click(app, "Owner Analytics")
    click(app, "Check reader and writer")
    assert all("private-password" not in item.value for item in [*app.error, *app.warning])
    assert "owner_analytics.read_dsn · MISSING_SETTING" in app.error[0].value
    assert any("owner_analytics.write_dsn · INVALID_DSN" in item.value for item in app.warning)


@pytest.mark.parametrize("tag,source", [("linkedin", "LinkedIn"), ("GitHub", "GitHub"),
                                       (None, analytics.DIRECT), ("other", analytics.DIRECT)])
def test_session_events(configure, monkeypatch, tag, source):
    import nlp_model
    from scoring import MatchResult

    monkeypatch.setattr(analytics.st, "user", User())
    monkeypatch.setattr(analytics, "connect", lambda _: (_ for _ in ()).throw(psycopg.OperationalError()))
    monkeypatch.setattr(nlp_model, "compare_round", lambda *_: (MatchResult((.7,) * 5), None))
    app = AppTest.from_file(str(APP))
    app.query_params["view"] = "owner_analytics"
    if tag is not None:
        app.query_params["utm_source"] = tag
    app.run()
    assert not app.exception
    assert all(b.label != "Owner Analytics" for b in app.button)
    app.session_state.view = "owner_analytics"
    app.query_params["utm_source"] = "linkedin"
    app.run()
    assert app.session_state.view == "home"
    app.radio[0].set_value("Couple Mode").run()
    click(app, "Start Game →")
    app.session_state.screen = "ready"
    app.run()
    click(app, "Reveal our match →")
    app.run()
    pending = list(app.session_state.analytics_pending.values())
    assert [row[0] for row in pending] == ["visit", "mode_selected", "game_started", "game_completed"]
    assert {row[5] for row in pending} == {source}
    assert len({row[2] for row in pending}) == 1
    assert len({row[3] for row in pending[1:]}) == 1
    assert {row[4] for row in pending[1:]} == {"Couple Mode"}
    click(app, "Play Again")
    assert len(app.session_state.analytics_pending) == 6


def test_singapore_window_and_summaries():
    before = datetime(2026, 11, 21, 15, 59, tzinfo=timezone.utc)
    after = datetime(2026, 11, 21, 16, tzinfo=timezone.utc)
    start, end = date_window("Last 7 Days", after)
    assert start.day == 16 and end.day == 23
    session_a, session_b = uuid4(), uuid4()
    rows = [
        ("visit", session_a, None, "LinkedIn", before, False),
        ("visit", session_b, None, "GitHub", after, False),
        ("game_started", session_a, "Bestie Mode", "LinkedIn", before, True),
        ("game_started", session_b, "Couple Mode", "GitHub", after, False),
    ]
    visits, unique, traffic, daily, modes = summarize(rows, start, end)
    assert (visits, unique) == (2, 2)
    assert traffic.tolist() == [1, 1, 0]
    assert daily.tolist() == [0, 0, 0, 0, 0, 1, 1]
    assert modes.values.tolist() == [[1, 1], [1, 0]]
    assert summarize([], None, end)[0] == 0


def test_owner_navigation_and_charts(configure, monkeypatch):
    from types import SimpleNamespace
    import owner_dashboard as dashboard

    monkeypatch.setattr(analytics.st, "user", User(
        iss=configure, sub=analytics.GITHUB_SUBJECT, exp=4102444800,
    ))
    at = datetime(2026, 11, 21, 16, tzinfo=timezone.utc)
    monkeypatch.setattr(dashboard, "datetime", SimpleNamespace(now=lambda _: at,
                                                             combine=datetime.combine))
    session = uuid4()
    round_id = uuid4()
    rows = [
        ("visit", session, None, "GitHub", at, False, None, None, None, None, None),
        ("game_started", session, "Bestie Mode", "GitHub", at, True, round_id, at,
         60, [20, 40, 60, 80, 100], ["A", "B", "C", "D", "E"]),
    ]
    calls = []

    def read(start, end):
        calls.append((start, end))
        return rows, True

    monkeypatch.setattr(dashboard, "read_dashboard", read)
    monkeypatch.setattr(dashboard, "read_private_details", lambda key: None)
    app = AppTest.from_file(str(APP)).run()
    click(app, "Owner Analytics")
    assert len(app.get("plotly_chart")) == 6
    assert '"values":[0,1,0]' in app.get("plotly_chart")[0].proto.spec
    assert any("100.0%" in item.proto.body for item in app.get("html"))
    app.selectbox[0].set_value("Today").run()
    assert not app.exception
    assert calls[-1][0].day == 22
    click(app, "Refresh Analytics")
    assert len(calls) == 3
    assert "analytics_session" not in app.session_state

    app.selectbox(key="lab_selected_round").set_value(round_id).run()
    assert not app.exception
    assert any(item.label == "Overall compatibility" for item in app.metric)
    assert len(app.get("plotly_chart")) == 7
    app.selectbox(key="lab_mode").set_value("Couple Mode").run()
    assert not app.exception
    assert not app.get("plotly_chart")
    click(app, "Clear Filters")
    app.selectbox(key="lab_source").set_value("LinkedIn").run()
    assert not app.exception
    assert not app.get("plotly_chart")
    app.selectbox(key="lab_period").set_value("Custom date range").run()
    app.date_input[0].set_value((at.date(), at.date())).run()
    assert not app.exception
    assert calls[-1][0].day == 21

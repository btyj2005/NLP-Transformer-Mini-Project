from datetime import datetime, timezone
from uuid import uuid4

import pytest
import psycopg
from streamlit.testing.v1 import AppTest

import owner_analytics as analytics
from analytics_dashboard import date_window, summarize
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
    import analytics_dashboard as dashboard

    monkeypatch.setattr(analytics.st, "user", User(
        iss=configure, sub=analytics.GITHUB_SUBJECT, exp=4102444800,
    ))
    at = datetime(2026, 11, 21, 16, tzinfo=timezone.utc)
    monkeypatch.setattr(dashboard, "datetime", SimpleNamespace(now=lambda _: at,
                                                             combine=datetime.combine))
    session = uuid4()
    rows = [("visit", session, None, "GitHub", at, False),
            ("game_started", session, "Bestie Mode", "GitHub", at, True)]
    calls = []

    def read(start, end):
        calls.append((start, end))
        return rows

    monkeypatch.setattr(dashboard, "read_events", read)
    app = AppTest.from_file(str(APP)).run()
    click(app, "Owner Analytics")
    assert len(app.get("plotly_chart")) == 3
    assert '"values":[0,1,0]' in app.get("plotly_chart")[0].proto.spec
    assert any("100.0%" in item.proto.body for item in app.get("html"))
    app.selectbox[0].set_value("Today").run()
    assert not app.exception
    assert calls[-1][0].day == 22
    click(app, "Refresh Analytics")
    assert len(calls) == 3
    assert "analytics_session" not in app.session_state

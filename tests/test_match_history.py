from uuid import uuid4

import pytest
from streamlit.testing.v1 import AppTest

import match_history
import nlp_model
from scoring import MatchResult
from test_game import APP, click


def test_consent_bound_to_round_and_final_content():
    round_id = uuid4()
    names = ("A", "B")
    answers = [["first"] * 5, ["second"] * 5]
    choices = {i: match_history.consent_marker(round_id, names[i], answers[i]) for i in range(2)}
    assert match_history.joint_consent(round_id, choices, names, answers)
    assert not match_history.joint_consent(uuid4(), choices, names, answers)
    assert not match_history.joint_consent(round_id, choices, ("C", "B"), answers)
    answers[0][2] = "edit"
    assert not match_history.joint_consent(round_id, choices, names, answers)


@pytest.mark.parametrize("first,second", [(False, False), (True, False), (False, True), (True, True)])
def test_game_shares_only_with_both_choices(monkeypatch, first, second):
    monkeypatch.setattr(match_history, "sharing_available", lambda: True)
    monkeypatch.setattr(nlp_model, "compare_round", lambda *_: (MatchResult((.2, .4, .6, .8, 1)), None))
    saves = []
    code = uuid4()

    def save(round_id, result, prompts, private):
        saves.append((round_id, result.overall, prompts, private))
        return code if private else None

    monkeypatch.setattr(match_history, "save_match", save)
    app = AppTest.from_file(str(APP)).run()
    click(app, "Start Game →")
    app.session_state.names = ("first", "second")
    app.session_state.answers = [["first answer"] * 5, ["second answer"] * 5]
    app.session_state.screen = "question"
    app.session_state.question = 4
    app.run()
    assert not app.checkbox[0].value
    app.checkbox[0].set_value(first)
    click(app, "Finish turn →")
    assert not app.checkbox
    click(app, "I’m ready →")
    app.session_state.question = 4
    app.run()
    assert not app.checkbox[0].value
    app.checkbox[0].set_value(second)
    click(app, "Finish turn →")
    assert not app.checkbox
    click(app, "Reveal our match →")
    assert not app.exception
    assert len(saves) == 1
    assert saves[0][0] == app.session_state.analytics_round
    assert saves[0][1] == 60
    assert len(saves[0][2]) == 5
    assert bool(saves[0][3]) is (first and second)
    assert (app.session_state.deletion_code == code) is (first and second)


def test_private_queries_reject_visitor_before_connecting(monkeypatch):
    monkeypatch.setattr(match_history, "is_owner", lambda: False)
    monkeypatch.setattr(match_history, "database_connection", lambda _: pytest.fail("connected"))
    with pytest.raises(PermissionError):
        match_history.read_private_details(uuid4())

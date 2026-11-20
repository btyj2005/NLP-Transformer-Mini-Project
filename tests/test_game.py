from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import nlp_model
from questions import QUESTIONS
from scoring import MatchResult

APP = Path(__file__).resolve().parents[1] / "app.py"


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


@pytest.mark.parametrize("mode", QUESTIONS)
def test_game_navigation(mode, monkeypatch):
    received = []

    def compare(left, right):
        received.append((left.copy(), right.copy()))
        return MatchResult((0.8, 0.2, 0.4, 0.7, 0.5)), ([[1, 0]] * 5, [[0, 1]] * 5)

    def encode_replacement(answers):
        assert answers == ["My replacement answer."]
        return [[1, 0]]

    monkeypatch.setattr(nlp_model, "compare_round", compare)
    monkeypatch.setattr(nlp_model, "answer_tokens", lambda _: [["[CLS]", "edited", "[SEP]"]] * 2)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio[0].set_value(mode).run()
    click(app, "Start Game →")
    click(app, "Continue →")
    assert "both players" in app.error[0].value
    app.text_input[0].set_value("Alex")
    app.text_input[1].set_value("Jordan")
    click(app, "← Back")
    click(app, "Start Game →")
    assert [entry.value for entry in app.text_input] == ["Alex", "Jordan"]
    click(app, "Continue →")
    click(app, "Next →")
    assert "short answer" in app.error[0].value

    app.text_area[0].set_value("My first draft.")
    click(app, "Next →")
    click(app, "← Back")
    assert app.text_area[0].value == "My first draft."

    for player in range(2):
        for index, (prompt, _) in enumerate(QUESTIONS[mode]):
            assert any(prompt in entry.value for entry in app.markdown)
            if player == 1:
                assert app.text_area[0].value == ""
            app.text_area[0].set_value(f"Player {player + 1}, answer {index + 1}.")
            click(app, "Finish turn →" if index == 4 else "Next →")
        assert not app.text_area
        if player == 0:
            click(app, "I’m ready →")

    click(app, "Edit Player 1 answers")
    assert not app.text_area
    click(app, "I’m ready →")
    assert app.text_area[0].value == "Player 1, answer 1."
    app.text_area[0].set_value("My edited first answer.")
    for index in range(5):
        click(app, "Finish turn →" if index == 4 else "Next →")

    click(app, "Reveal our match →")
    assert app.session_state.screen == "results"
    assert app.session_state.result.overall == 52
    assert received[0][0][0] == "My edited first answer."
    assert received[0][1][0] == "Player 2, answer 1."
    original_answers = [answers.copy() for answers in app.session_state.answers]
    original_result = app.session_state.result
    monkeypatch.setattr(nlp_model, "encode_answers", encode_replacement)

    app.selectbox(key="simulation_player").set_value(1).run()
    app.selectbox(key="simulation_question").set_value(2).run()
    click(app, "Try This Answer")
    assert "short answer" in app.error[0].value
    app.text_area(key="simulation_answer").set_value("My replacement answer.")
    click(app, "Try This Answer")
    assert app.session_state.simulation.similarities == (0.8, 0.2, 1, 0.7, 0.5)
    assert app.session_state.simulation.overall == 64
    assert [metric.value for metric in app.metric] == ["52.0%", "64.0%"]
    assert len(app.get("plotly_chart")) == 1
    assert len(app.table) == 3
    assert app.session_state.answers == original_answers
    assert app.session_state.result == original_result

    app.selectbox(key="explanation_question").set_value(0).run()
    assert not app.exception
    assert app.metric[-1].value == "0.800"
    click(app, "Reset simulation")
    assert app.session_state.simulation is None
    assert app.text_area(key="simulation_answer").value == ""
    assert not app.get("plotly_chart")
    assert not app.table
    assert [metric.value for metric in app.metric] == ["0.800"]
    assert app.session_state.answers == original_answers
    assert app.session_state.result == original_result
    click(app, "Switch Mode")
    assert app.session_state.screen == "welcome"
    assert not any(any(player) for player in app.session_state.answers)


def test_failed_inference_preserves_answers_and_allows_retry(monkeypatch):
    def unavailable(*_answers):
        raise OSError("Model unavailable")

    monkeypatch.setattr(nlp_model, "compare_round", unavailable)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.session_state.screen = "ready"
    app.session_state.answers = [["A good answer."] * 5, ["Another answer."] * 5]
    app.run()
    click(app, "Reveal our match →")
    assert "could not finish" in app.error[0].value
    assert app.session_state.result is None
    assert app.session_state.answers[0][0] == "A good answer."
    monkeypatch.setattr(nlp_model, "compare_round", lambda *_: (MatchResult((0.5,) * 5), None))
    click(app, "Try AI analysis again")
    assert app.session_state.screen == "results"
    click(app, "Play Again")
    assert app.session_state.screen == "setup"
    assert not any(any(player) for player in app.session_state.answers)


def test_header_navigation_saves_unsubmitted_drafts():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    click(app, "Start Game →")
    app.text_input[0].set_value("Alex")
    app.text_input[1].set_value("Jordan")
    click(app, "✦ AI MatchLab")
    click(app, "Resume round →")
    assert [entry.value for entry in app.text_input] == ["Alex", "Jordan"]

    click(app, "Continue →")
    click(app, "Next →")
    assert (app.session_state.player, app.session_state.question) == (0, 0)

    app.text_area[0].set_value("A draft worth keeping.")
    click(app, "About")
    assert app.session_state.view == "about"
    assert any("About AI MatchLab" in entry.value for entry in app.markdown)
    assert any("grouped bar chart" in entry.value and "percentage points" in entry.value for entry in app.markdown)
    assert not app.text_area
    click(app, "← Back to Home")
    click(app, "Resume round →")
    assert app.text_area[0].value == "A draft worth keeping."
    click(app, "Next →")
    assert app.session_state.question == 1
    click(app, "← Back")
    assert app.session_state.question == 0
    assert app.text_area[0].value == "A draft worth keeping."

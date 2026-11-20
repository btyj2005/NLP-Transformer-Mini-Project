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
        return MatchResult((0.8, 0.2, 0.4, 0.7, 0.5))

    monkeypatch.setattr(nlp_model, "compare_answers", compare)
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
    click(app, "Switch Mode")
    assert app.session_state.screen == "welcome"
    assert not any(any(player) for player in app.session_state.answers)


def test_failed_inference_preserves_answers_and_allows_retry(monkeypatch):
    def unavailable(*_answers):
        raise OSError("Model unavailable")

    monkeypatch.setattr(nlp_model, "compare_answers", unavailable)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.session_state.screen = "ready"
    app.session_state.answers = [["A good answer."] * 5, ["Another answer."] * 5]
    app.run()
    click(app, "Reveal our match →")
    assert "could not finish" in app.error[0].value
    assert app.session_state.result is None
    assert app.session_state.answers[0][0] == "A good answer."
    monkeypatch.setattr(nlp_model, "compare_answers", lambda *_: MatchResult((0.5,) * 5))
    click(app, "Try AI analysis again")
    assert app.session_state.screen == "results"
    click(app, "Play Again")
    assert app.session_state.screen == "setup"
    assert not any(any(player) for player in app.session_state.answers)

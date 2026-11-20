import pytest

from match_insights import (
    CHANGE_COLORS, ORIGINAL_COLOR, category_averages, compare_scores, comparison_chart,
    comparison_table, question_scores, score_statistics,
)
from questions import QUESTIONS
from scoring import MatchResult


@pytest.mark.parametrize(("mode", "experience_scores"), [
    ("Bestie Mode", (55, 50)),
    ("Couple Mode", (45, 45)),
])
def test_comparison_and_aggregations(mode, experience_scores):
    original = question_scores(mode, MatchResult((0.2, 0.4, 0.4, 0.7, -0.1)))
    comparison = compare_scores(original, MatchResult((0.2, 0.4, 0.3, 0.7, -0.1)))
    assert list(original["Question"]) == [prompt for prompt, _ in QUESTIONS[mode]]
    assert list(original.columns) == ["Question", "Category", "Original"]
    assert list(comparison["Change"]) == [0, 0, -10, 0, 0]
    assert score_statistics(comparison[["Original", "Simulated"]]).to_dict() == {
        "Original": {"Average": 34, "Minimum": 0, "Maximum": 70},
        "Simulated": {"Average": 32, "Minimum": 0, "Maximum": 70},
    }
    assert tuple(category_averages(comparison).loc["Experiences", ["Original", "Simulated"]]) == experience_scores


@pytest.mark.parametrize("mode", QUESTIONS)
@pytest.mark.parametrize(("replacement_cosine", "direction", "label"), [
    (0.57, "Increase", "+17 pp"),
    (0.2, "Decrease", "−20 pp"),
    (0.4, "Unchanged", "0 pp"),
])
def test_chart_and_table_use_all_five_scores(mode, replacement_cosine, direction, label):
    original = MatchResult((0.2, 0.4, 0.8, 1, -0.1))
    simulated = MatchResult((0.2, replacement_cosine, 0.8, 1, -0.1))
    comparison = compare_scores(question_scores(mode, original), simulated)
    figure = comparison_chart(comparison, question=1)
    before, after = figure.data
    assert figure.layout.barmode == "group"
    assert before.name == "Original"
    assert after.name == "Simulated"
    assert tuple(before.y) == tuple(after.y) == ("Q1", "Q2*", "Q3", "Q4", "Q5")
    assert tuple(before.x) == original.scores
    assert tuple(after.x) == simulated.scores
    assert before.marker.color == ORIGINAL_COLOR
    assert tuple(after.marker.color) == (
        CHANGE_COLORS["Unchanged"], CHANGE_COLORS[direction], *[CHANGE_COLORS["Unchanged"]] * 3,
    )
    assert tuple(after.text) == ("0 pp", label, "0 pp", "0 pp", "0 pp")
    table = comparison_table(comparison, question=1)
    assert list(table.data.columns) == ["Question", "Category", "Original Score", "Simulated Score", "Change"]
    markup = table.to_html()
    assert f"Q2 · Modified — {QUESTIONS[mode][1][0]}" in markup
    assert label in markup

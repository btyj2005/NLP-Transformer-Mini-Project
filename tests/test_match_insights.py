import pytest

from match_insights import category_averages, compare_scores, question_scores, score_statistics
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

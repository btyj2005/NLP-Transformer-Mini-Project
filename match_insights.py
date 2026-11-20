"""Build the shared question score table and its summaries."""

import pandas as pd

from questions import QUESTION_CATEGORIES, QUESTIONS


def question_scores(mode, result):
    return pd.DataFrame({
        "Question": [prompt for prompt, _ in QUESTIONS[mode]],
        "Category": QUESTION_CATEGORIES[mode],
        "Original": result.scores,
    })


def compare_scores(original, simulated):
    comparison = original.assign(Simulated=simulated.scores)
    return comparison.assign(Change=comparison["Simulated"] - comparison["Original"])


def score_statistics(scores):
    return scores.agg(["mean", "min", "max"]).rename(
        index={"mean": "Average", "min": "Minimum", "max": "Maximum"}
    )


def category_averages(scores):
    return scores.groupby("Category", sort=False).mean(numeric_only=True)

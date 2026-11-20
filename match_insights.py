"""Build the shared question score table and its summaries."""

from html import escape

import pandas as pd
import plotly.express as px

from questions import QUESTION_CATEGORIES, QUESTIONS

ORIGINAL_COLOR = "#6382a7"
CHANGE_COLORS = {"Increase": "#4e8267", "Decrease": "#ae5962", "Unchanged": "#9a81bf"}
CHANGE_TEXT_COLORS = {"Increase": "#326047", "Decrease": "#903d48", "Unchanged": "#624989"}


def question_scores(mode, result):
    return pd.DataFrame({
        "Question": [prompt for prompt, _ in QUESTIONS[mode]],
        "Category": QUESTION_CATEGORIES[mode],
        "Original": result.scores,
    })


def compare_scores(original, simulated):
    comparison = original.assign(Simulated=simulated.scores)
    return comparison.assign(Change=comparison["Simulated"] - comparison["Original"])


def change_direction(change):
    if change > 0:
        return "Increase"
    if change < 0:
        return "Decrease"
    return "Unchanged"


def change_label(change):
    if not change:
        return "0"
    if abs(change) < 0.05:
        return "↑ <0.1" if change > 0 else "↓ <0.1"
    sign = "+" if change > 0 else "−"
    return sign + f"{abs(change):.1f}".removesuffix(".0")


def comparison_chart(comparison, question):
    question_labels = [f"Q{index + 1}{'*' if index == question else ''}" for index in comparison.index]
    chart_data = comparison.assign(Prompt=question_labels).melt(
        id_vars=["Prompt", "Question"], value_vars=["Original", "Simulated"],
        var_name="Result", value_name="Score",
    )
    figure = px.bar(
        chart_data, x="Score", y="Prompt", color="Result", orientation="h", barmode="group",
        custom_data=["Question"], category_orders={"Prompt": question_labels},
        color_discrete_map={"Original": ORIGINAL_COLOR, "Simulated": CHANGE_COLORS["Unchanged"]},
    )
    figure.update_traces(
        textposition="outside", textangle=0, textfont_size=12,
        hovertemplate="%{customdata[0]}<br>%{fullData.name} %{x:.1f}/100<extra></extra>",
    )
    figure.update_traces(texttemplate="%{x:.1f}", selector={"name": "Original"})
    figure.update_traces(
        marker_color=[CHANGE_COLORS[change_direction(change)] for change in comparison["Change"]],
        text=[f"{escape(change_label(change))} pp" for change in comparison["Change"]],
        texttemplate="%{x:.1f} (%{text})",
        selector={"name": "Simulated"},
    )
    figure.update_xaxes(
        title="Similarity score out of 100", range=[0, 165], tickvals=[0, 25, 50, 75, 100],
        fixedrange=True, gridcolor="#e6dff0",
    )
    figure.update_yaxes(
        title=None, categoryorder="array", categoryarray=question_labels[::-1], fixedrange=True,
    )
    figure.update_layout(
        showlegend=False, height=372, margin={"l": 34, "r": 4, "t": 8, "b": 48},
        paper_bgcolor="#faf8f5", plot_bgcolor="#faf8f5", font_color="#292936",
        bargap=0.23, bargroupgap=0.1,
    )
    return figure


def comparison_table(comparison, question):
    table = comparison.rename(columns={"Original": "Original Score", "Simulated": "Simulated Score"})
    labels = [
        f"Q{index + 1}{' · Modified' if index == question else ''} — {prompt}"
        for index, prompt in table["Question"].items()
    ]
    table = table.assign(Question=labels)
    return (
        table.style.hide(axis="index")
        .format({"Original Score": "{:.1f}", "Simulated Score": "{:.1f}", "Change": lambda change: f"{change_label(change)} pp"})
        .apply(lambda row: ["background-color: #f2edfb; font-weight: 650" if row.name == question else ""] * len(row), axis=1)
        .map(lambda change: f"color: {CHANGE_TEXT_COLORS[change_direction(change)]}; font-weight: 700", subset=["Change"])
    )


def score_statistics(scores):
    return scores.agg(["mean", "min", "max"]).rename(
        index={"mean": "Average", "min": "Minimum", "max": "Maximum"}
    )


def category_averages(scores):
    return scores.groupby("Category", sort=False).mean(numeric_only=True)

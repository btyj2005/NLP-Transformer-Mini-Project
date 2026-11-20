import pytest

from questions import QUESTION_COUNT, QUESTIONS
from scoring import clean_answer, cosine_similarity, score_embeddings, validate_answers


@pytest.mark.parametrize("answer", ["", " \n\t ", "...", "x" * 241])
def test_invalid_answers(answer):
    with pytest.raises(ValueError):
        clean_answer(answer)


def test_answer_count_and_whitespace():
    assert validate_answers(["  Go hiking.  "] * 5) == ["Go hiking."] * 5
    with pytest.raises(ValueError, match="5 answers"):
        validate_answers(["Go hiking."])


@pytest.mark.parametrize("mode", QUESTIONS)
def test_modes_have_five_distinct_prompts(mode):
    assert len({prompt for prompt, _ in QUESTIONS[mode]}) == QUESTION_COUNT


def test_cosine_examples():
    assert cosine_similarity([2, 0], [9, 0]) == 1
    assert cosine_similarity([2, 0], [0, 9]) == 0
    assert cosine_similarity([2, 0], [-9, 0]) == -1
    assert cosine_similarity([1, 2], [3, 4]) == cosine_similarity([3, 4], [1, 2])


@pytest.mark.parametrize("right", [[], [1], [0, 0], [float("nan"), 1]])
def test_invalid_embeddings(right):
    with pytest.raises(ValueError):
        cosine_similarity([1, 0], right)


def test_game_score_and_reproducibility():
    left = [[1, 0]] * 5
    right = [[1, 0], [0, 1], [-1, 0], [1, 1], [1, 0]]
    result = score_embeddings(left, right)
    assert result.scores == pytest.approx((100, 0, 0, 70.7107, 100), abs=0.0001)
    assert result.overall == pytest.approx(54.1421, abs=0.0001)
    assert result.biggest_match == 0
    assert result.biggest_difference == 2
    assert result == score_embeddings(left, right)


def test_embedding_count():
    with pytest.raises(ValueError, match="5 embeddings"):
        score_embeddings([[1, 0]], [[1, 0]])

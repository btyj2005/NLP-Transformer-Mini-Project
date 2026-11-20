import os

import pytest

from nlp_model import answer_tokens, compare_answers, compare_round, simulate_answer

pytestmark = pytest.mark.skipif(
    os.environ.get("MATCHLAB_TEST_MODEL") != "1",
    reason="Set MATCHLAB_TEST_MODEL=1 to use the real model (first run downloads weights).",
)


def test_real_model_similarity_and_reproducibility():
    left = [
        "I enjoy watching movies at home.",
        "I like growing orchids.",
        "I love camping in the forest.",
        "Take a train through Switzerland.",
        "Make time to check in on each other.",
    ]
    right = [
        "I love relaxing with films on weekends.",
        "The city has a new metro line.",
        "I hate camping in the forest.",
        "Take a train through Switzerland.",
        "Remember to check in and listen.",
    ]
    result = compare_answers(left, right)
    assert result == compare_answers(left, right)
    assert result.similarities[0] > result.similarities[1]
    assert result.scores[3] == pytest.approx(100, abs=0.001)
    assert result.biggest_match == 3
    assert all(0 <= score <= 100 for score in result.scores)

    answers = [left, right]
    original, embeddings = compare_round(*answers)
    replacement = "The new metro line opened in the city."
    simulated = simulate_answer(original, answers, embeddings, 0, 1, replacement)
    full = compare_answers([left[0], replacement, *left[2:]], right)
    assert simulated.similarities == pytest.approx(full.similarities, abs=1e-6)
    assert simulated.similarities[:1] + simulated.similarities[2:] == (
        original.similarities[:1] + original.similarities[2:]
    )
    assert simulated.overall > original.overall
    assert simulate_answer(original, answers, None, 0, 1, replacement).similarities == pytest.approx(
        simulated.similarities, abs=1e-6
    )
    assert simulate_answer(original, answers, embeddings, 0, 1, left[1]) is original


def test_real_model_tokens_include_word_pieces_and_exclude_padding():
    assert answer_tokens(["Gaming!", "Tokenization is useful."]) == [
        ["[CLS]", "gaming", "!", "[SEP]"],
        ["[CLS]", "token", "##ization", "is", "useful", ".", "[SEP]"],
    ]

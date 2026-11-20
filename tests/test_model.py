import os

import pytest

from nlp_model import compare_answers

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

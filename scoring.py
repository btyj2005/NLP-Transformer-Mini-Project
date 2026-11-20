"""Input validation and cosine scoring independent of Streamlit and PyTorch."""

from dataclasses import dataclass
from math import fsum, hypot, isfinite

from questions import QUESTION_COUNT

MAX_ANSWER_LENGTH = 240


class AnswerError(ValueError):
    """An answer needs editing before it can be scored."""


def clean_answer(text: str) -> str:
    answer = text.strip()
    if not answer or not any(character.isalnum() for character in answer):
        raise AnswerError("Write a short answer before continuing.")
    if len(answer) > MAX_ANSWER_LENGTH:
        raise AnswerError(f"Keep your answer within {MAX_ANSWER_LENGTH} characters.")
    return answer


def validate_answers(answers: list[str]) -> list[str]:
    if len(answers) != QUESTION_COUNT:
        raise AnswerError(f"Each player needs {QUESTION_COUNT} answers.")
    return [clean_answer(answer) for answer in answers]


def cosine_similarity(left, right) -> float:
    """Compare vector directions using their dot product and lengths."""
    if len(left) != len(right) or len(left) == 0:
        raise ValueError("Embeddings must have the same nonzero dimension.")
    left_length, right_length = hypot(*left), hypot(*right)
    if not left_length or not right_length or not isfinite(left_length * right_length):
        raise ValueError("Embeddings must have finite, nonzero lengths.")
    dot_product = fsum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    return max(-1.0, min(1.0, dot_product / (left_length * right_length)))


@dataclass(frozen=True)
class MatchResult:
    similarities: tuple[float, ...]

    @property
    def scores(self) -> tuple[float, ...]:
        return tuple(100 * max(0.0, value) for value in self.similarities)

    @property
    def overall(self) -> float:
        return fsum(self.scores) / len(self.scores)

    @property
    def biggest_match(self) -> int:
        return max(range(len(self.similarities)), key=self.similarities.__getitem__)

    @property
    def biggest_difference(self) -> int:
        return min(range(len(self.similarities)), key=self.similarities.__getitem__)


def score_embeddings(left, right) -> MatchResult:
    if len(left) != QUESTION_COUNT or len(right) != QUESTION_COUNT:
        raise ValueError(f"Expected {QUESTION_COUNT} embeddings per player.")
    return MatchResult(tuple(cosine_similarity(a, b) for a, b in zip(left, right, strict=True)))

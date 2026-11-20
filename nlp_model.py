"""Load and reuse one pretrained sentence encoder for the app."""

from threading import Lock

import streamlit as st

from questions import QUESTION_COUNT
from scoring import MatchResult, clean_answer, cosine_similarity, score_embeddings, validate_answers

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_URL = f"https://huggingface.co/{MODEL_NAME}"


@st.cache_resource(show_spinner=False)
def load_model():
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(1)
    model = SentenceTransformer(
        MODEL_NAME,
        revision=MODEL_REVISION,
        device="cpu",
        trust_remote_code=False,
        model_kwargs={"use_safetensors": True},
    )
    model.eval()
    # One shared encoder and lock keep concurrent sessions from spiking CPU memory.
    return model, Lock()


def encode_answers(answers):
    model, inference_lock = load_model()
    with inference_lock:
        # encode tokenizes the text, runs the Transformer, then pools token
        # representations into one embedding per answer. No weights are updated.
        return model.encode(answers, batch_size=5, show_progress_bar=False)


def compare_round(left: list[str], right: list[str]):
    vectors = encode_answers(validate_answers(left) + validate_answers(right))
    players = (vectors[:QUESTION_COUNT], vectors[QUESTION_COUNT:])
    return score_embeddings(*players), players


def compare_answers(left: list[str], right: list[str]) -> MatchResult:
    result, _ = compare_round(left, right)
    return result


def simulate_answer(result, answers, embeddings, player, question, replacement):
    replacement = clean_answer(replacement)
    if replacement == answers[player][question]:
        return result

    other = 1 - player
    if embeddings is None:
        # A round scored before the simulator was added has no saved vectors.
        updated, counterpart = encode_answers([replacement, answers[other][question]])
    else:
        updated, = encode_answers([replacement])
        counterpart = embeddings[other][question]
    similarities = list(result.similarities)
    similarities[question] = cosine_similarity(updated, counterpart)
    return MatchResult(tuple(similarities))


def answer_tokens(answers):
    """Show the tokens fed to the Transformer, including its boundary markers."""
    model, inference_lock = load_model()
    answers = [clean_answer(answer) for answer in answers]
    with inference_lock:
        batch = model.tokenize(answers)
        return [
            model.tokenizer.convert_ids_to_tokens(ids[mask.bool()].tolist())
            for ids, mask in zip(batch["input_ids"], batch["attention_mask"], strict=True)
        ]

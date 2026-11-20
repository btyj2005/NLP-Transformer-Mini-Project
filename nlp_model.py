"""Load and reuse one pretrained sentence encoder for the app."""

from threading import Lock

import streamlit as st

from questions import QUESTION_COUNT
from scoring import MatchResult, score_embeddings, validate_answers

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


def compare_answers(left: list[str], right: list[str]) -> MatchResult:
    answers = validate_answers(left) + validate_answers(right)
    model, inference_lock = load_model()
    with inference_lock:
        # encode tokenizes the text, runs the Transformer, then pools token
        # representations into one embedding per answer. No weights are updated.
        vectors = model.encode(answers, batch_size=5, show_progress_bar=False)
    return score_embeddings(vectors[:QUESTION_COUNT], vectors[QUESTION_COUNT:])

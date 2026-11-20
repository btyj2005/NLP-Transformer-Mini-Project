"""The AI MatchLab game and its Streamlit screens."""

from base64 import b64encode
from html import escape
from pathlib import Path

import streamlit as st

from nlp_model import MODEL_NAME, MODEL_URL, compare_answers
from questions import QUESTION_COUNT, QUESTIONS
from scoring import MAX_ANSWER_LENGTH, AnswerError, MatchResult, clean_answer

ROOT = Path(__file__).parent
st.set_page_config(page_title="AI MatchLab", page_icon="✦", layout="wide")
st.html(ROOT / "style.css")
state = st.session_state


def new_round(screen="setup"):
    state.update(screen=screen, player=0, question=0,
                 answers=[[""] * QUESTION_COUNT for _ in range(2)],
                 editing=False, error="", result=None)


if "screen" not in state:
    state.update(mode="Bestie Mode", names=("", ""), view="game")
    new_round("welcome")

state.setdefault("view", "game")


def change_screen(screen, **fields):
    state.update(screen=screen, error="", **fields)


def start_round():
    state.update(mode=state.mode_choice, view="game")
    new_round()


def open_view(view, draft=None):
    """Save the current form before opening Home or About."""
    if draft == "setup":
        state.names = (state.setup_name_1.strip(), state.setup_name_2.strip())
    elif draft:
        state.answers[state.player][state.question] = state[draft]
    state.view = view


def header(draft=None):
    with st.container(key="lab_header"):
        brand, nav = st.columns([2, 1], vertical_alignment="center", gap="small")
        for column, label, key, destination in (
            (brand, "✦ AI MatchLab", "home_nav", "home"),
            (nav, "About", "about_nav", "about"),
        ):
            with column:
                button = st.form_submit_button if draft else st.button
                button(label, key=key, type="tertiary", on_click=open_view, args=(destination, draft))


def welcome():
    left, right = st.columns([1.15, 1], vertical_alignment="center", gap="small")
    with left:
        st.html('''<div class="hero-copy"><h1>AI MatchLab</h1>
            <p class="tagline">Discover how well<br>your vibes match.</p>
            <p class="muted">Take turns answering five questions with a friend or partner.
            Then see where your answers overlap and what you could talk about next.</p></div>''')
    with right:
        hero = b64encode((ROOT / "assets" / "speech-bubbles.webp").read_bytes()).decode("ascii")
        st.html(f'<img class="hero-art" src="data:image/webp;base64,{hero}" alt="" width="960" height="640">')

    with st.container(key="mode_picker"):
        st.markdown("### Choose your mode")
        st.radio(
            "Game mode", list(QUESTIONS), index=list(QUESTIONS).index(state.mode),
            key="mode_choice", horizontal=True, label_visibility="collapsed", width="stretch",
            captions=("How well do you know your bestie?", "How well do your vibes match?"),
        )
    with st.container(key="start_game"):
        paused = state.screen != "welcome"
        if paused:
            st.button("Resume round →", type="primary", width="stretch", on_click=open_view, args=("game",))
        label = "Start a new round" if paused else "Start Game →"
        st.button(label, type="secondary" if paused else "primary", width="stretch", on_click=start_round)
    st.html('<p class="center muted fine">An AI-powered game for entertainment and conversation.</p>')


def stage_label(text):
    mode_class = "couple" if state.mode == "Couple Mode" else "bestie"
    symbol = "♡" if mode_class == "couple" else "✦"
    st.html(f'<div class="stage-label {mode_class}"><span aria-hidden="true">{symbol}</span> '
            f'{state.mode}<span class="stage-detail">{escape(text)}</span></div>')


def progress_bar(value, label):
    return (f'<div class="track" role="progressbar" aria-label="{escape(label)}" '
            f'aria-valuenow="{value:.1f}" aria-valuemin="0" aria-valuemax="100">'
            f'<span style="width:{value:.6f}%"></span></div>')


def save_names(destination):
    state.names = (state.setup_name_1.strip(), state.setup_name_2.strip())
    if destination == "question" and not all(state.names):
        state.error = "Enter a name for both players."
    else:
        state.update(screen=destination, error="")


def setup():
    state.setup_name_1, state.setup_name_2 = state.names
    with st.form("player_setup_form", border=False, enter_to_submit=False):
        header("setup")
        stage_label("Player setup")
        setup_fields()


def setup_fields():
    with st.container(key="setup_panel", border=True):
        st.markdown("## Who’s playing?")
        st.markdown("Use names or nicknames. You’ll answer separately on this device.")
        left, right = st.columns(2)
        left.text_input("Player 1 name", key="setup_name_1", max_chars=32, placeholder="e.g. Alex")
        right.text_input("Player 2 name", key="setup_name_2", max_chars=32, placeholder="e.g. Jordan")
        back, forward = st.columns(2)
        back.form_submit_button("← Back", width="stretch", on_click=save_names, args=("welcome",))
        forward.form_submit_button("Continue →", type="primary", width="stretch",
                                   on_click=save_names, args=("question",))
        if state.error:
            st.error(state.error)


def save_answer(player, index, widget_key, advance):
    # A delayed submit from an earlier screen must never advance this question.
    if state.screen != "question" or (player, index) != (state.player, state.question):
        return
    answer = state[widget_key]
    state.answers[player][index] = answer
    state.error = ""
    if not advance:
        if index > 0:
            state.question -= 1
        else:
            state.screen = "setup" if player == 0 and not state.editing else "handoff"
        return
    try:
        state.answers[player][index] = clean_answer(answer)
    except AnswerError as error:
        state.error = str(error)
        return
    if index < QUESTION_COUNT - 1:
        state.question += 1
    else:
        state.screen = "ready" if player == 1 or state.editing else "handoff"


def question_screen():
    player, index = state.player, state.question
    prompt, hint = QUESTIONS[state.mode][index]
    widget_key = f"answer_{player}_{index}"
    # The game owns drafts even after Streamlit removes old form widgets.
    state[widget_key] = state.answers[player][index]
    step = player * QUESTION_COUNT + index + 1
    theme = "couple" if state.mode == "Couple Mode" else "bestie"
    # Keep the form, card and native progress bar mounted between questions.
    with st.form("question_form", border=False, enter_to_submit=False):
        header(widget_key)
        with st.container(key=f"question_stage_{theme}"):
            status = f"Player {player + 1} of 2 · Question {index + 1} of {QUESTION_COUNT}"
            stage_label(status)
            st.progress(step / (2 * QUESTION_COUNT))
            question_fields(player, index, prompt, hint, widget_key)
        st.html('<p class="center muted fine">Keep your screen to yourself while you answer.</p>')


def question_fields(player, index, prompt, hint, widget_key):
    with st.container(key="question_panel", border=True):
        st.text(f"{state.names[player]}’s turn")
        st.markdown(f"## {prompt}")
        st.caption(hint)
        st.text_area(
            "Your answer", key=widget_key, max_chars=MAX_ANSWER_LENGTH,
            placeholder="Write one or two short sentences in English…", height=115,
        )
        left, right = st.columns(2)
        left.form_submit_button("← Back", key=f"back_{widget_key}", width="stretch", on_click=save_answer,
                                args=(player, index, widget_key, False))
        label = "Finish turn →" if index == QUESTION_COUNT - 1 else "Next →"
        right.form_submit_button(label, key=f"advance_{widget_key}", type="primary", width="stretch",
                                 on_click=save_answer, args=(player, index, widget_key, True))
        if state.error:
            st.error(state.error)


def handoff():
    stage_label("Pass the screen")
    with st.container(key="handoff_panel", border=True):
        target = state.player if state.editing else 1
        st.html(f'<h2>{escape(state.names[target])}, it’s your turn.</h2>')
        st.markdown("Pass the device to the player named above. Their answers will open when they’re ready.")
        left, right = st.columns(2)
        if state.editing:
            left.button("← Back to review", width="stretch", on_click=change_screen, args=("ready",))
        else:
            left.button("← Player 1: Edit", width="stretch", on_click=change_screen,
                        args=("question",), kwargs={"player": 0, "question": QUESTION_COUNT - 1})
        right.button("I’m ready →", type="primary", width="stretch", on_click=change_screen,
                     args=("question",), kwargs={"player": target, "question": 0})


def ready():
    stage_label("Both turns complete")
    with st.container(key="ready_panel", border=True):
        st.markdown("## Ready to compare?")
        st.markdown("Reveal your scores together. The answer comparisons stay folded until you choose to open them.")
        if state.error:
            st.error(state.error)
        st.button("Try AI analysis again" if state.error else "Reveal our match →",
                  type="primary", width="stretch", on_click=change_screen, args=("analysis",))
        for player, column in enumerate(st.columns(2)):
            column.button(f"Edit Player {player + 1} answers", width="stretch",
                          on_click=change_screen, args=("handoff",), kwargs={"player": player, "editing": True})


def analysis():
    stage_label("AI analysis")
    st.markdown("## Comparing your answers")
    try:
        with st.spinner("Creating sentence embeddings. The first round may need to download the model…"):
            state.result = compare_answers(*state.answers)
    except AnswerError as error:
        state.update(screen="ready", error=f"Check your answers and try again. {error}")
        st.rerun()
    except Exception:
        # Keep user text and service internals out of the UI and application logs.
        state.update(screen="ready", error="The AI model could not finish. Check the connection and try again.")
        st.rerun()
    change_screen("results")
    st.rerun()


def highlight(title, index, result: MatchResult, column):
    with column:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.write(QUESTIONS[state.mode][index][0])
            st.caption(f"Question {index + 1} · {result.scores[index]:.1f}/100 · Cosine {result.similarities[index]:.3f}")
            with st.expander("Compare your answers together"):
                for name, answers in zip(state.names, state.answers, strict=True):
                    st.text(name)
                    st.html(f'<div class="answer-quote">{escape(answers[index])}</div>')
                if state.answers[0][index] == state.answers[1][index]:
                    st.caption("You entered the same text for this question.")
                elif title == "Your Biggest Match":
                    st.caption("The embeddings for these two answers had the closest directions in this round. Read both to see which ideas overlap.")
                else:
                    st.caption("These two answers had the least aligned embeddings in this round. Read both to see where your answers took different directions.")


def results():
    result = state.result
    left, right = (escape(name) for name in state.names)
    title = "On the same wavelength" if result.overall >= 65 else (
        "A little overlap, a little surprise" if result.overall >= 35 else "Lots to swap stories about"
    )
    stage_label("Round complete")
    theme = "couple" if state.mode == "Couple Mode" else "bestie"
    st.html(f'''<div class="score-panel {theme}">
        <div><p class="score-label">Your Match Score</p><p class="score-number">{result.overall:.1f}<small> / 100</small></p></div>
        <div><h2>{left} &amp; {right}</h2><p>{title}</p></div>
        </div>''')
    st.markdown("## Vibe breakdown")
    for index, ((prompt, _), score) in enumerate(zip(QUESTIONS[state.mode], result.scores, strict=True)):
        label = f"{index + 1}. {prompt} · {score:.1f}/100"
        st.html(f'<div class="score-row"><p>{escape(label)}</p>'
                f'{progress_bar(score, prompt)}</div>')
    if result.biggest_match == result.biggest_difference:
        st.caption("All five cosine scores tied. Both highlights show the first question.")
    left, right = st.columns(2)
    highlight("Your Biggest Match", result.biggest_match, result, left)
    highlight("Your Biggest Difference", result.biggest_difference, result, right)
    st.caption("This entertainment score measures text similarity. The model can miss negation, context and tone. Your friendship or relationship can’t be measured by five answers.")
    again, switch = st.columns(2)
    again.button("Play Again", type="primary", width="stretch", on_click=new_round)
    switch.button("Switch Mode", width="stretch", on_click=new_round, args=("welcome",))


def how_ai_works():
    st.divider()
    st.html('<h2 id="how-ai-works">How AI works</h2>')
    with st.expander("From your answers to a match score"):
        concepts = (
            ("Natural language processing", "NLP is the area of computing that works with human language, including the short answers you write here."),
            ("Tokenization", "The tokenizer splits an answer into small pieces, such as whole words or parts of words, and turns them into numbers the model can read."),
            ("Transformer", "A Transformer uses attention to link tokens to other tokens in a sentence. This gives each token a representation that reflects its context."),
            ("Inference", "Inference means running a trained model on new input. Each answer passes through the same pretrained model with its weights fixed."),
            ("Embeddings", "The model pools the token representations into a list of 384 numbers for each answer. This list is an embedding."),
            ("Cosine similarity", "Cosine similarity compares the directions of two embeddings. A value near 1 means they point in nearly the same direction. The game maps negative values to zero and averages the five question scores."),
        )
        for heading, description in concepts:
            st.markdown(f"**{heading}**\n\n{description}")
        st.markdown("### Different words, related ideas")
        st.html('''<div class="example-pair"><div><strong>Person A</strong><br>I enjoy watching movies at home.</div>
            <div><strong>Person B</strong><br>I love relaxing with films on weekends.</div></div>''')
        st.write("Movies and films refer to a similar activity, and both answers describe ways to unwind. The model can place the answers near each other even when their wording differs.")
        st.markdown("### Where similarity falls short")
        st.write("‘I love camping’ and ‘I hate camping’ share a topic and may score highly even though they disagree. Unrelated answers usually score lower. English works best for this model, and local slang, jokes, and context can change how it interprets an answer.")
        st.markdown(f"**Model** · [{MODEL_NAME}]({MODEL_URL})")
        st.write("MiniLM is a compact, pretrained English sentence encoder. It runs on CPU and suits short answers, so the game can run without a paid AI API.")


def about():
    st.markdown("# About AI MatchLab")
    st.write("Two people answer five questions, then the game compares how similar their written answers are. It’s a way to start a conversation and see a real AI model at work.")
    st.markdown("## From answers to a score")
    st.html('''<ol class="about-flow">
        <li>Write your answers</li><li>Split the text into tokens</li>
        <li>Make an embedding</li><li>Compare answers</li><li>See the game score</li>
        </ol>''')
    with st.container(key="about_topics"):
        left, right = st.columns(2, gap="small")
        with left:
            with st.expander("What is NLP?"):
                st.write("Natural language processing, or NLP, is how computers work with human language. A model can pick up on similar ideas even when two people use different words.")
            with st.expander("What is a Transformer?"):
                st.write("A Transformer is a way to build a language model. It uses attention to weigh how different parts of a sentence relate to each other. That helps it tell a river bank from a bank that handles money.")
            with st.expander("What is BERT?"):
                st.write("BERT stands for Bidirectional Encoder Representations from Transformers. It’s a related language model that uses context from both sides of a word. AI MatchLab uses the pretrained MiniLM sentence encoder described below. [Read the BERT paper](https://aclanthology.org/N19-1423/)")
        with right:
            with st.expander("What are embeddings?"):
                st.write("The app first splits each answer into smaller pieces called tokens. MiniLM reads those pieces in context and combines them into one list of 384 numbers, called an embedding. You can think of it as an arrow that represents the answer.")
            with st.expander("How does the real model score my answers?"):
                st.write("The game uses cosine similarity to see how closely the two arrows point in the same direction. It turns negative values into zero, multiplies each similarity by 100, and averages the five question scores. The model was already trained when this project started.")
                st.markdown(f"**Model** · [{MODEL_NAME}]({MODEL_URL})")
            with st.expander("What does the score tell me?"):
                st.write("The score describes similarity in what you wrote. Shared topics can score highly even when the answers disagree. Friendship, love and relationship success are outside what this score can measure.")
    st.html('''<div class="example-pair"><div><strong>Person A</strong><br>I love watching movies.</div>
        <div><strong>Person B</strong><br>I enjoy films.</div></div>''')
    st.caption("Different words can point to the same idea. Both answers are about enjoying movies.")
    st.markdown("## About the project")
    st.write("Bryan Tock built AI MatchLab as an independent mini-project while studying for a Diploma in Applied AI & Analytics at Republic Polytechnic. It applies concepts from NVIDIA’s Building Transformer-Based Natural Language Processing Applications certification.")
    st.button("← Back to Home", on_click=open_view, args=("home",))


screen = {"home": "welcome", "about": "about"}.get(state.view, state.screen)
if screen not in {"setup", "question"}:
    header()
render = {
    "welcome": welcome, "about": about, "setup": setup, "question": question_screen,
    "handoff": handoff, "ready": ready, "analysis": analysis, "results": results,
}[screen]
render()
if screen != "about":
    how_ai_works()

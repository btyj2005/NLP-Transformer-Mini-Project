# AI MatchLab

**Discover how well your vibes match.**

[Play AI MatchLab on Streamlit Community Cloud](https://btyj2005-nlp-transformer-mini-project-app-d2788k.streamlit.app/?utm_source=github)

AI MatchLab is a two-player Streamlit game and student portfolio project. Friends or partners take turns answering five open-ended questions, then see how closely a pretrained language model groups their answers.

![AI MatchLab welcome screen showing Bestie and Couple modes](assets/welcome.webp)

## Play a round

- **Bestie Mode** asks about weekends, interests, food, holidays and friendship.
- **Couple Mode** asks about dates, time together, appreciation, holidays and relationship values.
- Each player answers privately on the same device. A handoff screen keeps the outgoing player’s answers out of view. Both players can revisit and edit their own answers before comparing.
- The results show all five scores and the questions with the highest and lowest cosine values. Open a highlight together to read the two answers side by side.
- **What If?** lets you try a replacement answer and compare the question score and overall match. Reset the experiment anytime. Your round answers and scores are kept intact.
- **How did AI compare our answers?** shows the selected answers, their real model tokens, how sentence embeddings work and the question’s cosine similarity.
- **About** explains NLP, Transformers, BERT and the MiniLM model behind the game. The AI MatchLab header button returns home, where you can resume a round with your draft intact.
- The question card stays visible as you move through the round, and the progress bar updates in a single step.

![AI MatchLab results with a real model score and five question scores using fictional answers](assets/results.webp)

## From the NVIDIA courses to the app

- **Building Transformer-Based Natural Language Processing Applications.** The game tokenizes answers, runs pretrained MiniLM inference on CPU, turns each answer into a sentence embedding and compares embeddings for semantic similarity.
- **Fundamentals of Accelerated Data Science.** Match Insights organizes the five scores in a pandas DataFrame, calculates the change from a replacement answer, aggregates the average, minimum and maximum, and uses GroupBy to compare category averages. Tables and bars visualize the original and simulated results.

## Model and scoring

The app uses a compact, 6-layer English sentence encoder. Sentence Transformers and PyTorch tokenize each answer, run the pretrained Transformer, and pool token representations into a 384-number embedding. The app uses the same model revision and settings for both players. It runs inference on CPU without updating the weights. Answers are capped at 240 characters for quick rounds. The encoder can read up to 256 word pieces per answer. [all-MiniLM-L6-v2 model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)

For each question, the app finds the cosine similarity `c` between the two embeddings by dividing their dot product by the product of their lengths. The displayed game score is `100 × max(0, c)`, with `c` bounded to `[-1, 1]` for floating-point safety. Each question has equal weight. The overall score is the arithmetic mean of the five unrounded game scores, displayed to one decimal place. The highlights use raw cosine, including negative values. Ties use the first matching question.

For example, *I enjoy watching movies at home* and *I love relaxing with films on weekends* can produce embeddings that point in similar directions. Both refer to watching films as a way to unwind. Negated answers like *I love camping* and *I hate camping* can also score highly because they share a topic. Slang, very short answers, sarcasm and text outside the model’s English training focus can affect the result. Treat the 0–100 score as a conversation starter about these answers. It has no statistical validation as a measure of relationship compatibility.

**Privacy.** Names, answers and results use Streamlit’s session state. Inference runs in the app server process. Analytics storage excludes names, answers, results and IP addresses. Answers stay in the app server process and are never sent to Hugging Face. Hugging Face supplies the model and tokenizer files. A new round clears answers and scores. Use nicknames if you prefer, and keep both players’ consent in mind when opening highlights or sharing screenshots.

## Run locally

Use Python 3.11 on Windows or Linux x86-64, or on macOS with Apple Silicon. Run these commands from the project root, after activating the virtual environment.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux shell: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The first scoring request downloads about 91 MB of model weights plus tokenizer files. The welcome and question screens open before the model loads. Later rounds reuse the model in memory. The CPU encoder uses small batches and a single inference thread to keep resource use down.

## Tests

```bash
python -m pip install pytest==8.4.2
python -m pytest -q
```

The default tests cover scoring, both modes, answer editing, inference recovery, simulator reset and the Match Insights calculations. Set `MATCHLAB_TEST_MODEL=1` and rerun pytest to check real MiniLM inference, tokenization and simulation. In PowerShell, use `$env:MATCHLAB_TEST_MODEL = '1'`.

## Deploy on Streamlit Community Cloud

In [Streamlit Community Cloud](https://share.streamlit.io/), choose **Create app**, select `btyj2005/NLP-Transformer-Mini-Project`, branch `main`, and main file `app.py`. Choose Python **3.11** in **Advanced settings** and deploy. The public game runs with or without analytics secrets. After launch, play a full round to exercise the first model download and a second round to check reuse. Cloud start-up time and memory depend on the hosting instance. [Deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)

## Owner Analytics

The owner dashboard shows visits, unique sessions, arrival sources, daily trends and game outcomes. pandas groups real events stored in Supabase PostgreSQL and Plotly draws the charts. Dates use Singapore time. Game metrics follow rounds started in the selected date range, including rounds completed later.

A visit is recorded once per Streamlit session. A reload, new tab or reconnect can create a new session. The app uses random IDs and does not link sessions across browsers or devices. Known crawler, prefetch and headless clients are skipped where detectable, and signed-in owner activity is excluded. Visits made before signing in as owner may still count. Outages can leave gaps if a session ends before a write succeeds. History begins when tracking is enabled.

- [LinkedIn share link](https://btyj2005-nlp-transformer-mini-project-app-d2788k.streamlit.app/?utm_source=linkedin)
- [GitHub share link](https://btyj2005-nlp-transformer-mini-project-app-d2788k.streamlit.app/?utm_source=github)

Use the LinkedIn link to replace the app URL in your LinkedIn post manually. The app counts tagged arrivals at AI MatchLab. Untagged or unsupported sources appear as Direct / Other. Views of the LinkedIn post and GitHub repository pages are outside these counts.

### Enable GitHub sign-in

1. In Auth0, create a **Regular Web Application**. Set its **Allowed Callback URLs** to `https://btyj2005-nlp-transformer-mini-project-app-d2788k.streamlit.app/oauth2callback`. Keep its client ID and client secret for Streamlit.
2. In GitHub **Settings → Developer settings → OAuth Apps**, create an OAuth App. Use the live app as the homepage and `https://YOUR_AUTH0_DOMAIN/login/callback` as the Authorization callback URL. Generate the GitHub client secret.
3. In Auth0 **Authentication → Social**, create a GitHub connection using the GitHub OAuth App credentials. Enable it for the Regular Web Application, and disable other connections for that application. The owner check uses the signed Auth0 issuer and the GitHub account ID `github|247741615` for `btyj2005`. Keep this as an unlinked GitHub identity so Auth0 issues that subject.
4. Generate a random cookie secret locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Add the Auth0 application credentials and cookie secret to Streamlit **Manage app → Settings → Secrets** using the format below. GitHub OAuth credentials belong in Auth0 only. Sign in from the footer, then select **Owner Analytics** from the sidebar. Logout clears the Streamlit app session.

### Enable persistent storage

1. Create a Supabase project and run [the analytics migration](migrations/001_owner_analytics.sql) in the SQL Editor as the project administrator. The migration preserves existing event rows. Keep `matchlab_analytics` outside the exposed Data API schemas.
2. In the SQL Editor set long, distinct random passwords for the new roles using `ALTER ROLE matchlab_writer PASSWORD 'WRITE_PASSWORD';` and `ALTER ROLE matchlab_reader PASSWORD 'READ_PASSWORD';`. Generate separate passwords, store them securely and avoid saving or sharing the password-setting query. The writer can insert only and the reader can select only. Use these roles for the app instead of using `postgres` or a Supabase service key.
3. In Supabase **Connect**, copy the host and region for the IPv4-compatible **Session pooler** on port 5432. Use usernames `matchlab_writer.PROJECT_REF` and `matchlab_reader.PROJECT_REF`. Configure both DSNs in Streamlit Secrets. The example uses PostgreSQL keyword/value syntax. Alphanumeric passwords work without extra DSN escaping. The application enforces TLS hostname and certificate validation.

```toml
[auth]
redirect_uri = "https://btyj2005-nlp-transformer-mini-project-app-d2788k.streamlit.app/oauth2callback"
cookie_secret = "YOUR_RANDOM_COOKIE_SECRET"
client_id = "YOUR_AUTH0_APPLICATION_CLIENT_ID"
client_secret = "YOUR_AUTH0_APPLICATION_CLIENT_SECRET"
server_metadata_url = "https://YOUR_AUTH0_DOMAIN/.well-known/openid-configuration"

[auth.client_kwargs]
scope = "openid"

[owner_analytics]
issuer = "https://YOUR_AUTH0_DOMAIN/"
write_dsn = "host=YOUR_POOLER_HOST port=5432 dbname=postgres user=matchlab_writer.PROJECT_REF password=WRITE_PASSWORD sslrootcert=system"
read_dsn = "host=YOUR_POOLER_HOST port=5432 dbname=postgres user=matchlab_reader.PROJECT_REF password=READ_PASSWORD sslrootcert=system"
```

For local use, place these values in the ignored `.streamlit/secrets.toml` and register the matching local callback URL in Auth0. Restart the app after saving secrets. With no writer configured, the game keeps working without recording events. The dashboard reports a load failure if the reader cannot connect.

4. Verify with a staging database before sharing the tracked links. Open the public app in a separate browser session and complete a round. In an owner session, confirm the visit source and game counts, reboot the Streamlit app and verify the same records still appear. Try a second GitHub account to confirm it cannot open the dashboard. Use a staging project to keep those test visits out of production statistics.

Analytics retain minimal anonymous event records indefinitely for the All Time view. There is no automatic deletion on deployment. Backups and any future deletion policy are managed by the Supabase project owner. Do not commit real secrets.

## What I learned

- Comparing embeddings helps find related ideas even when there are few shared words.
- A high similarity score can reflect a shared topic, even when the two answers disagree.
- Loading the model once and reusing it makes a small CPU app more practical.
- A clear handoff screen and saved drafts matter as much to the game as the model does.

## About the project

AI MatchLab is a student mini-project that brings together what I learned from both NVIDIA courses through a two-player game.

# DropRead

![CI](https://github.com/R0GUE-A5H/DropRead/actions/workflows/deploy.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Live](https://img.shields.io/badge/live-dropread.site-brightgreen)

DropRead is an autonomous AI agent pipeline that researches, synthesizes, and schedules weekly newsletters on any highly specific topic. Subscribe to any topic and it lands in your inbox on a schedule.

This project is written in **Python** and **FastAPI**, uses **LangGraph** for the agent pipeline, **Groq (Llama 3.3 70B)** for synthesis, **BAAI/bge-reranker-base** for cross-encoder reranking, **pgvector** for semantic caching, and **Serper + crawl4ai** for live web research.

**Live Website**: https://dropread.site/

<img width="1920" height="1982" alt="Home Page" src="https://github.com/user-attachments/assets/0aca2d52-c039-4147-9147-e4f54103788a" />

---

## How it Works

![Architecture](docs/Arch.png)

The core is a **LangGraph** pipeline with 6 nodes and **PostgreSQL** _checkpointing_ for resumable execution:

query_generation → search → web_crawl → validation → rerank → synthesis

1. Query generation — rewrites the user's topic into an optimized Serper search query
2. Search — fetches top 20 organic results via Serper API
3. Web crawl — tiered fetching: `curl_cffi` (TLS fingerprint spoofing) → `crawl4ai` (Playwright/Chromium for JS-heavy sites) → `Serper snippet fallback`. WAF detection skips challenge pages automatically.
4. Validation — LLM filters crawled pages to only those genuinely relevant to the topic
5. Rerank — `BAAI/bge-reranker-base` cross-encoder scores each page against the topic; top-N kept
6. Synthesis — `Llama 3.3 70B` synthesizes a readable newsletter from the surviving sources

- Semantic cache: Topics are embedded with **BAAI/bge-small-en-v1.5** and compared against a `pgvector` HNSW index (cosine similarity ≥ 0.82 = cache hit, 3-day TTL). Similar topics like "rust async" and "async rust programming" reuse the same digest, skipping the pipeline entirely.

- Scheduler: **APScheduler** fires every 15 minutes inside **FastAPI**'s lifespan. _next_delivery_ is bumped before pipeline execution — a failed run never causes infinite retries.

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI + async SQLAlchemy + PostgreSQL (Supabase) |
| AI pipeline | LangGraph + LangChain + Groq (Llama 3.3 70B) |
| ML models | `BAAI/bge-small-en-v1.5` (embeddings), `BAAI/bge-reranker-base` (cross-encoder) |
| Vector search | pgvector with HNSW index |
| Web crawling | `curl_cffi` + `crawl4ai` (Playwright/Chromium) + `trafilatura` |
| Frontend | HTMX + AlpineJs + Jinja2 |
| Email | Resend |
| Deployment | AWS EC2 (t3.small) + Docker + Caddy (auto HTTPS) |
| CI/CD | GitHub Actions |
| Observability | CloudWatch |

## Features

1. Live pipeline status - HTMX polls every 2s; triggers a digest-done event when ready
2. Email subscriptions - per-digest schedule (day + time), stored in UTC, displayed in local timezone
3. Digest archive - all past emailed digests preserved and browsable per topic
4. Semantic cache - similar topics return cached results instantly, no LLM call
5. Security - double-submit cookie `CSRF`, `SSRF` protection, `SlowAPI` rate limiting, `DOMPurify XSS` sanitization
6. Kill switch - synthesis node checks if digest was deleted mid-run before spending tokens

---

# Installation & Setup

## 1. Configure Environment Variables

Create `.env.local` in root directory with following variables:

```bash
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_HOST=
POSTGRES_PORT=
POSTGRES_DB=
SECRET_KEY=
GROQ_API_KEY=
SERPER_API_KEY=
RESEND_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
RESEND_FROM_EMAIL=onboarding@resend.dev
APP_ENV=local
APP_URL=http://127.0.0.1:8000
ALLOWED_ORIGINS=*
```

For `SECRET_KEY`, run:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 2. Prepare the Database

- **Option 1 - Supabase (recommended)** - it comes with `pgvector` enabled

  Create a free project at [supabase.com](https://supabase.com). Grab connection details from **Settings → Database** and fill in the `POSTGRES_*` vars.

- **Option 2 — Local PostgreSQL (15+ with pgvector installed):**

  Install pgvector first:
  ```bash
  # Mac
  brew install pgvector
  # Ubuntu
  apt install postgresql-15-pgvector
  ```

  Then create the database:
  ```bash
  psql -U postgres -c "CREATE DATABASE dropread;"
  ```

  Set `POSTGRES_HOST=localhost` and `POSTGRES_DB=dropread` in `.env.local`.

_Note: Supabase recommended for local dev too, free tier is sufficient. Migrations in step 5 handle the vector extension and HNSW index automatically._

## 3. Setup Google OAuth

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project → APIs & Services → Credentials → Create OAuth 2.0 Client ID
3. Add `http://127.0.0.1:8000/auth/google/callback` to Authorized redirect URIs
4. Copy client ID and secret into `.env.local`

## 4. Grab other API keys

- Groq: [console.groq.com](https://console.groq.com)
- Serper: [serper.dev](https://serper.dev)
- Resend: [resend.com](https://resend.com)

Note: for local dev, Resend allows sending from `onboarding@resend.dev` 
to your registered email only. Set `RESEND_FROM_EMAIL=onboarding@resend.dev` 
in `.env.local`. For production, use your verified domain.

## 5. Install dependencies and run

```bash
uv sync
uv run playwright install chromium
uv run alembic upgrade head
uv run uvicorn src.ai_newsletter.app:app --reload
```

> **Note:** The first time you generate a topic, it will take 1-2 minutes to download ~500MB of ML models.

> Linux users should run  `uv run playwright install-deps chromium` 

Open `http://127.0.0.1:8000`

## 6. Running tests

```bash
uv run pytest tests/ -v
```

20 tests across 4 classes: delivery time logic, semantic cache (mocked DB, threshold 0.82), pipeline route auth + validation, and email dispatch.

## 7. CI/CD

`build-base → test → migrate → deploy`

- build-base skips if `pyproject.toml` / `uv.lock` unchanged (hash-based)
- migrate runs `alembic upgrade head` against production `Supabase` before deploy
- deploy SSH into EC2, pulls base image from GHCR, rebuilds app layer only

Note: Base image (~650MB) includes Chromium, PyTorch CPU, and both ML models pre-downloaded. App layer rebuilds in seconds on code-only changes.

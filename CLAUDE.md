# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

넉넉 (nokknok) — an AI cash-flow management service for a Korean fintech AI hackathon (2026 금융 AI Challenge, Team BankWay). It computes a user's actual available balance (account balance minus already-committed spending like subscriptions/installments/loans), simulates 6-month balance trajectories, and recommends which owned card to pay with, when, to optimize card benefit qualification — with the terms-and-conditions clause backing each recommendation.

Monorepo: `backend/` (FastAPI, Python 3.11) deploys to Render, `frontend/` (React + TypeScript + Vite) deploys to Vercel, as independent builds from one repo.

## Core architecture: calculation vs. explanation are separate paths

This is the load-bearing design decision of the whole codebase — read this before touching `engine/`, `rag/`, or `api/`.

```
Terms PDF ──[batch] LLM converts → human review → rule table
                                          │
User query ──[LLM] extracts parameters ──→ rule engine (owns all money math)
                                          │
                                    result ──[LLM] generates explanation
```

- **LLM never computes amounts.** It only: (1) converts clause text to rule-table rows during batch ingestion (human-reviewed before use), (2) extracts structured parameters from a user's natural-language query, (3) narrates an already-computed result. `src/engine/` must never import the LLM client or `src/rag/`.
- **If the LLM call fails, the numeric result still ships.** `explanation` becomes `null`; the computed numbers are never withheld. Frontend must render cards/results even when `explanation` is `null` — see `frontend/README.md`.
- **No vector search anywhere**, runtime or batch. Evidence clauses are located by an exact join on `card_benefit_rule.clause_id` → `clause_source`, never by similarity search. The batch ingestion pipeline is intentionally single-stage: it inserts a clause section, gets its `id`, extracts rules from that same section, and stores the `clause_id` immediately — so there is never a "match rules back to clauses later" step that would need search. Full rationale in [docs/decisions/001](docs/decisions/001-no-vector-search.md) and [002](docs/decisions/002-llm-provider-and-pipeline.md); don't reintroduce `pgvector`, `pg_trgm`, or an embedding column without reopening that decision.
- **Rule precedence is single-select, never additive.** When a spend category has both a category-specific rule and an `ALL` wildcard rule in the same performance bracket, exactly one applies (specific wins, `ALL` is the fallback) — they are never summed. This is enforced by the SQL pattern in `backend/README.md` (`ORDER BY ... LIMIT 1`), not by summing matched rows. Getting this wrong produces a plausible-looking but wrong discount number, which is the failure mode this whole system is designed to prevent.
- **Two independent LLM call profiles, never share config**: batch (terms conversion) tolerates 5 retries / 15s timeout and resumes from a progress file on failure; runtime (query parsing, explanation) is budgeted on **total elapsed time**, not retry count (`tenacity.stop_after_delay`, 3.5s total budget; there is deliberately **no** runtime retry-count setting — `stop_after_delay` only looks at elapsed time, so a count would be dead config that looks live) — on budget exhaustion it gives up mid-retry and returns `explanation=null`. Using batch settings on the runtime path is a real failure mode: it stalls the UI for up to a minute during a demo.

## Contracts — the cross-team interface boundary

`contracts/` is the single source of truth shared by backend, frontend, and the DB. **Changes require agreement from all contributors** and must land in the same commit as any migration:

| File | Owner | Content |
|---|---|---|
| `contracts/schema.sql` | @seohee-P | table definitions (canonical; run directly against Postgres) |
| `contracts/api-spec.yaml` | @fanfanduck | endpoint & response shapes |
| `contracts/types.ts` | @fanfanduck | frontend data types |
| `contracts/ui-system.md` | all | design tokens, class conventions |

When generating code with an AI assistant, the relevant contract file(s) must be included as context. FastAPI's auto-generated OpenAPI docs (`/docs`) must be kept in sync with `contracts/api-spec.yaml` when response models change — update both in the same commit. Frontend copies `contracts/types.ts` to `src/types/contract.ts` in `prebuild`; don't hand-edit that copy.

## Repo layout

```
backend/src/
├── adapter/     data-source abstraction (mango606)
├── rag/         terms parsing → clause+rule ingestion, single-stage pipeline (mango606)
├── engine/      card-combination optimizer, benefit-qualification logic (seohee-P) — currently unimplemented (stub __init__.py only)
├── forecast/    variable-spend time-series forecasting (fanfanduck) — currently unimplemented
├── repository/  DB access — persona.py only (fanfanduck); card/rule queries pending (seohee-P)
├── api/         endpoints, response assembly (fanfanduck) — main.py app factory,
│                /api/health, /api/personas, /api/balance; simulate/route pending
└── common/      config, logging, exceptions, LLM client (shared)
frontend/src/    React 19 + TS + Vite 8 + Tailwind 4 + Recharts 3 scaffold; App.tsx is a shell, no screens or router yet (see frontend/README.md)
contracts/       cross-team interface contract (see above)
data/            seed SQL for cards, clauses, personas + generated batch output
scripts/         generate_persona.py, ingest_clauses.py (see Data pipeline commands below)
docs/decisions/  ADRs — read before revisiting search/LLM-provider/pipeline-structure decisions
```

`src/adapter/` implements a `TransactionProvider` protocol with swappable backends — `MockProvider` (demo personas, needs DB session), `FileProvider` (user-uploaded card-issuer export, no DB), and a not-yet-built `MyDataProvider` (real 마이데이터 integration, requires a license nokknok doesn't have yet). Code above the adapter layer must not know which implementation is active; select via `src/adapter/factory.py`.

`src/common/llm.py` wraps the LLM call behind an `LlmProvider` protocol so the provider is swappable via `LLM_PROVIDER`. **Gemini is the decided and implemented provider** ([docs/decisions/002](docs/decisions/002-llm-provider-and-pipeline.md)), chosen for its structured-output/response-schema support; `GeminiProvider` builds the REST body directly and uses the `google-genai` SDK only to construct `responseSchema`. Anthropic/OpenAI adapters remain as fallbacks behind the same protocol — don't add provider-specific branching in call sites.

**Error responses**: every endpoint returns `ErrorResponse {code, message}` from `src/api/errors.py`; FastAPI's default `{"detail": ...}` bodies for validation failures and unhandled exceptions are converted by handlers registered in `create_app()`. `message` is user-facing copy — never put exception text or field names in it (`contracts/ui-system.md` forbids showing raw errors). `ErrorCode` must stay in sync with the `enum` in `contracts/api-spec.yaml`; `tests/test_api_errors.py` asserts this.

**Settings injection**: `create_app(settings)` stores settings on `app.state.settings`; `lifespan` reads them from there rather than calling `get_settings()` again, so a test that injects settings actually exercises them. Startup logs which `.env` paths were read (paths only, never values) — pydantic-settings merges the root and `backend/` files **key by key**, so a stale key left in one file silently overrides the other.

## Commands

### Setup
```bash
cp .env.example .env      # DATABASE_URL must be the pooled connection string
psql $DATABASE_URL -f contracts/schema.sql
psql $DATABASE_URL -f data/cards.seed.sql
psql $DATABASE_URL -f data/clauses.seed.sql
psql $DATABASE_URL -f data/personas.seed.sql
```

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000            # API docs at :8000/docs
```

### Tests (backend only — frontend has no test setup yet)
```bash
cd backend
pytest                              # runs tests/ (pytest.ini: testpaths=tests, pythonpath=.)
pytest tests/test_rag.py            # single file
pytest tests/test_rag.py::TestRuleExtractor::test_name   # single test
pytest -k "성능 or Extractor"        # by keyword (test names are Korean in places)
```
Tests are pure unit tests (no live DB or network) — `test_adapter.py` covers `FileProvider`/category classification/installment detection, `test_rag.py` covers rule/exclusion validation, JSON-response parsing, and the rule extractor against a stub LLM client (`_StubClient`).

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Data pipeline (mango606's domain)
```bash
# Synthetic 6-month transaction history per persona, with realistic seasonality
# (payday effects, day-of-week variance, category volatility) — not random.
python scripts/generate_persona.py --months 6 --seed 42
psql $DATABASE_URL -f data/generated/transactions.sql

# Terms PDF → clause+rule ingestion, single-stage (see architecture section above)
python scripts/ingest_clauses.py --card-id 1 --pdf data/clauses/a.pdf --dry-run --limit 5   # dry-run first, no DB needed
python scripts/ingest_clauses.py --card-id 1 --pdf data/clauses/a.pdf                        # then ingest for real
```
- Interrupted ingestion (rate limit/network) resumes automatically from `data/generated/ingest_progress.json` — don't restart from scratch, it double-spends LLM budget.
- LLM responses are cached in `data/generated/llm_cache.json`; re-running after a prompt change requires `--no-cache`.
- Ingested rules land with `verified=false` and are excluded from qualification logic until a human reviews and flips them to `true` (query in `scripts/README.md`).
- Both scripts close their DB connection in `finally` (`dispose_engine()`) — the free-tier connection limit is shared with the API server.

## Conventions

- **Commits**: Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`). Branches: `feat/<domain>`, `fix/<domain>`, `refactor/<domain>`.
- **DB connections**: always the pooled connection string (Neon `-pooler` host / Supabase Supavisor port 6543), never direct — free tier has a low concurrent-connection cap. App-side pool capped around 5 (`DB_POOL_MAX`, `max_overflow=0` must be explicit or the cap isn't actually enforced).
- **No hardcoded enums that mirror DB data.** `spend_category` codes and similar fixed-but-DB-owned value sets must be read from the DB and used to build the LLM structured-output schema dynamically — duplicating the list in code means two places to update and a silent mismatch when one is missed.
- **`spend_category` (and similarly-typed fields) are validated at the DB/schema boundary**, not left as free text — a category typo should fail loudly at ingestion, not silently zero out a discount calculation at runtime.
- No comments explaining *what* code does; comments are reserved for *why* (a non-obvious constraint, a past incident, a tradeoff) — this convention is followed consistently throughout the existing codebase (see `exceptions.py`, `llm.py`, `schema.sql` for the style).

## 절대 규칙
- 금액 계산에 LLM을 쓰지 않는다. 규칙 엔진이 전담한다.
- contracts/ 의 스키마·타입을 임의로 바꾸지 않는다. 필요하면 먼저 알린다.
- 카테고리 코드는 spend_category 마스터에 있는 값만 쓴다.
- 카테고리 전용 규칙이 ALL보다 우선하며 합산하지 않는다.
- 배치는 stop_after_attempt, 런타임은 stop_after_delay를 쓴다.
- 배치 스크립트는 종료 시 dispose_engine()을 호출한다.

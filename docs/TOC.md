# Creonnect Documentation — Table of Contents

Complete reference for Creonnect project documentation.

## Getting Started

- **[QUICKSTART.md](#quickstart)** — 5-minute setup guide (local development)
- **[README.md](#readme)** — Project overview and features
- **[INFRASTRUCTURE.md](INFRASTRUCTURE.md)** — Environment setup, Docker, cloud deployment

## Architecture & Design

- **[CREDITS_AND_USAGE_MODEL.md](CREDITS_AND_USAGE_MODEL.md)** â€” Usage metering, credit deduction, and guardrail design

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — High-level system design, components, data flows
- **[AI_ANALYTICS_PIPELINES.md](AI_ANALYTICS_PIPELINES.md)** — AI modules, analytics, data transformation

## Backend Development

- **[BACKEND_SERVICES.md](BACKEND_SERVICES.md)** — Service orchestrators and business logic
- **[API_ENDPOINTS.md](API_ENDPOINTS.md)** — Complete API reference with examples
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Code style, testing, PR process

## Frontend Development

- **[FRONTEND.md](FRONTEND.md)** — Vite SPA setup, pages, API integration

## Operations & Tools

- **[INTERNAL_TOOLS.md](INTERNAL_TOOLS.md)** — Diagnostic and utility scripts

## Quick Links

| Topic | Document |
|-------|----------|
| How do I run the app locally? | [QUICKSTART.md](#quickstart) |
| What is the architecture? | [ARCHITECTURE.md](ARCHITECTURE.md) |
| How do I call the API? | [API_ENDPOINTS.md](API_ENDPOINTS.md) |
| How do services work? | [BACKEND_SERVICES.md](BACKEND_SERVICES.md) |
| How do I deploy? | [INFRASTRUCTURE.md](INFRASTRUCTURE.md) |
| How do I debug with scripts? | [INTERNAL_TOOLS.md](INTERNAL_TOOLS.md) |
| How do I contribute code? | [CONTRIBUTING.md](CONTRIBUTING.md) |
| How does the AI layer work? | [AI_ANALYTICS_PIPELINES.md](AI_ANALYTICS_PIPELINES.md) |
| How should credits and usage billing work? | [CREDITS_AND_USAGE_MODEL.md](CREDITS_AND_USAGE_MODEL.md) |

---

## Index of Files

### Documentation

```
docs/
├── ARCHITECTURE.md              ← System overview
├── BACKEND_SERVICES.md          ← Service layer
├── AI_ANALYTICS_PIPELINES.md    ← AI and analytics
├── API_ENDPOINTS.md             ← API reference
├── FRONTEND.md                  ← Frontend SPA
├── INFRASTRUCTURE.md            ← Deployment
├── INTERNAL_TOOLS.md            ← Scripts and tools
├── CONTRIBUTING.md              ← Contribution guide
├── QUICKSTART.md                ← Quick start
└── TOC.md                       ← This file
```

### Core Backend

```
backend/
├── main.py                      ← FastAPI entry point
├── app/
│   ├── api/                     ← API routers
│   │   ├── dashboard.py
│   │   ├── instagram_auth_routes.py
│   │   ├── post_analysis_routes.py
│   │   └── ... (other routers)
│   ├── services/                ← Business logic
│   │   ├── dashboard_service.py
│   │   ├── post_insights_service.py
│   │   ├── ai_analysis_service.py
│   │   └── ... (other services)
│   ├── ai/                      ← AI and ML
│   │   ├── llm_client.py
│   │   ├── rag.py
│   │   ├── post_insights.py
│   │   ├── cringe_analysis.py
│   │   └── ... (other AI modules)
│   ├── analytics/               ← Analytics
│   │   ├── content_score.py
│   │   ├── benchmark_engine.py
│   │   ├── account_health_engine.py
│   │   └── ... (other analytics)
│   ├── ingestion/               ← Data ingestion
│   │   ├── instagram_oauth.py
│   │   └── instagram_mapper.py
│   ├── infra/                   ← Infrastructure
│   │   ├── database.py
│   │   ├── redis_client.py
│   │   ├── models.py
│   │   └── token_store.py
│   └── utils/                   ← Utilities
│       └── logger.py
├── tests/                       ← Test suite
└── requirements.txt             ← Python dependencies
```

### Frontend

```
frontend/
├── index.html                   ← HTML entry
├── src/
│   ├── main.js                  ← JS entry
│   ├── components/              ← Reusable components
│   ├── pages/                   ← Page-level components
│   ├── services/                ← API helpers
│   └── assets/                  ← Styles, images, fonts
├── vite.config.js               ← Build config
└── package.json                 ← Dependencies
```

### Internal Tools

```
internal_tools/
├── run_smoke_test.py            ← Smoke test
├── run_creator_analysis.py      ← Account analysis
├── post_analysis_diag.py        ← Post diagnostics
├── vision_diag.py               ← Vision API test
└── ... (20+ scripts)
```

### Infrastructure

```
infra/
├── terraform/                   ← IaC (AWS, GCP, etc.)
│   └── main.tf
├── docker-compose.yml           ← Local dev
└── Dockerfile                   ← Container image
```

---

## Common Tasks

### I want to...

| Task | Reference |
|------|-----------|
| Get started locally | [QUICKSTART.md](#quickstart) |
| Understand the system design | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Write a new API endpoint | [BACKEND_SERVICES.md](BACKEND_SERVICES.md) + [API_ENDPOINTS.md](API_ENDPOINTS.md) |
| Add a new service | [BACKEND_SERVICES.md](BACKEND_SERVICES.md) → "Adding a New Service" |
| Modify AI scoring | [AI_ANALYTICS_PIPELINES.md](AI_ANALYTICS_PIPELINES.md) |
| Debug a feature | [INTERNAL_TOOLS.md](INTERNAL_TOOLS.md) |
| Deploy to production | [INFRASTRUCTURE.md](INFRASTRUCTURE.md) |
| Contribute code | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Call the API from frontend | [API_ENDPOINTS.md](API_ENDPOINTS.md) |
| Configure environment | [INFRASTRUCTURE.md](INFRASTRUCTURE.md) → "Environment Configuration" |

---

## Documentation Standards

- **Architecture docs** explain high-level design and data flows.
- **API docs** include request/response schemas, status codes, examples.
- **Service docs** explain responsibilities, dependencies, and usage.
- **Infrastructure docs** provide setup, deployment, and troubleshooting.
- **Code comments** in source files explain complex logic; avoid obvious comments.

---

## Keeping Docs in Sync

When you modify code:

1. If you change an API endpoint → update [API_ENDPOINTS.md](API_ENDPOINTS.md)
2. If you add a service → update [BACKEND_SERVICES.md](BACKEND_SERVICES.md)
3. If you change AI logic → update [AI_ANALYTICS_PIPELINES.md](AI_ANALYTICS_PIPELINES.md)
4. If you add an internal tool → update [INTERNAL_TOOLS.md](INTERNAL_TOOLS.md)
5. Update this TOC if you add major new docs.

---

# QUICKSTART

## Local Development (5 minutes)

### Prerequisites

- Python 3.10+, Node.js 16+, PostgreSQL 13+, Redis 6+
- Git

### 1. Clone & Setup Backend

```bash
git clone https://github.com/yourorg/creonnect.git
cd creonnect

# Create virtualenv and install
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Copy env config
cp .env.example .env

# Edit .env:
# - DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/creonnect
# - REDIS_URL=redis://localhost:6379/0
# - OPENAI_API_KEY=sk-...
# - INSTAGRAM_APP_ID=...
```

### 2. Start Databases

```bash
# Terminal 1: PostgreSQL
createdb creonnect
# (or ensure it's running via service)

# Terminal 2: Redis
redis-server
```

### 3. Start Backend

```bash
# Terminal 3: Backend API
cd creonnect
source .venv/bin/activate
uvicorn backend.main:app --reload --factory
```

Visit `http://localhost:8000/docs` for API docs.

### 4. Start Frontend

```bash
# Terminal 4: Frontend
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` in your browser.

### 5. Test

```bash
# Terminal 5: Test script
source .venv/bin/activate
python internal_tools/run_smoke_test.py
```

Expected output: `✓ All tests passed`

### Done!

You now have:
- Backend API running on `http://localhost:8000`
- Frontend on `http://localhost:5173`
- Database: PostgreSQL (creonnect)
- Cache: Redis

Next: Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system, or jump to [API_ENDPOINTS.md](API_ENDPOINTS.md) to explore endpoints.

---

# README

## Creonnect

**Creator Intelligence Platform**

Creonnect analyzes Instagram creator accounts and posts to provide actionable growth insights, content recommendations, and brand safety scoring.

### Features

- 📊 **Creator Dashboard** — Profile metrics, growth score, niche detection
- 🎬 **Post Analysis** — Engagement metrics, visual quality (S1–S6), cringe detection
- 🤖 **AI Intelligence** — LLM-powered recommendations, RAG-based action plans
- 👤 **Account Health** — AHS scoring, engagement signals, content breakdown
- 🔐 **Brand Safety** — Cringe/adult content detection via vision API
- 🔗 **OAuth Integration** — Seamless Instagram authentication

### Quick Start

See [QUICKSTART](#quickstart) above.

### Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — System design
- [API_ENDPOINTS.md](API_ENDPOINTS.md) — API reference
- [CONTRIBUTING.md](CONTRIBUTING.md) — Contributing guidelines
- [INFRASTRUCTURE.md](INFRASTRUCTURE.md) — Deployment guide

### Tech Stack

- **Backend:** FastAPI (Python async)
- **Frontend:** Vite (Vue/React)
- **Database:** PostgreSQL + pgvector
- **Cache:** Redis
- **AI/ML:** OpenAI, Google Gemini, sentence-transformers

### License

Proprietary (Creonnect, Inc.)


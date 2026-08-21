# Creonnect Developer & Agent Guidelines

## 🌟 Engineering Standard & Philosophy
Write all code, architecture, docstrings, and tests to **Staff / Principal Engineer standards** (modeled after best-in-class engineering systems at Google, Stripe, and Anthropic).

### Core Tenets:
1. **Zero Trivial Comments**: Never comment the syntax (e.g., `# loop over items`). Always explain the *why*, mathematical invariants, architectural tradeoffs, failure modes, and concurrency guarantees.
2. **First-Class Typing & Contracts**: All Python functions must have explicit type hints (Pydantic / typing) and Google-style docstrings. All React components/hooks must have JSDoc/TSDoc.
3. **Graceful Degradation & Guardrails**: Any external network call (OpenAI, Azure, Instagram, Gemini, Redis) must have explicit retry, timeout, fallback, and error containment semantics.
4. **Boundary Integrity**:
   - `backend/app/api/`: Request validation, routing, HTTP response status codes.
   - `backend/app/services/`: Application orchestration, business workflows, background job dispatches.
   - `backend/app/analytics/`: Pure, deterministic mathematical scoring engines (no LLM hallucinations).
   - `backend/app/ai/`: Multi-provider LLM prompts, structured outputs, RAG embeddings, and safety filters.
   - `backend/app/infra/`: Database pools, Redis connections, queue managers, raw storage.
   - `frontend/src/`: Clean component hierarchy, responsive UI, decoupled API clients.

---

## 🛠️ Code Craftsmanship Checklist

When writing or modifying any file in this repository:

### 1. Python Docstring Standard (Google Style)
Every module, class, and public function must have:
- **Module Header**: Explaining the architecture layer, upstream callers, downstream dependencies, and invariants.
- **Function Docstring**:
  - Clear 1-sentence summary + detailed system explanation.
  - `Args:` with types and domain constraints (e.g., `Must sum to 1.0`, `UUID v4 format`).
  - `Returns:` with container types and semantic meaning.
  - `Raises:` listing all domain exceptions and conditions.
  - `Complexity:` (Time/Space) when algorithmic or data-intensive.

### 2. Architectural Tagging
Use explicit annotations for non-obvious engineering decisions:
- `# NOTE(arch):` Architectural rationale or design tradeoff.
- `# INVARIANT:` Critical conditions that must hold true across execution.
- `# PERF:` Performance considerations (caching, batching, vectorization).
- `# FALLBACK:` Handling for downstream failures or rate limits.
- `# SECURITY:` Authentication, sanitization, and data privacy safeguards.

### 3. Frontend Standards (React + Vite)
- Component TSDoc / JSDoc with `@param`, `@returns`, and accessibility/telemetry notes.
- Memoize expensive calculations (`useMemo`) and callbacks (`useCallback`) in data-heavy dashboard views.
- Strict error boundary handling around API-fed charts and tables.

---

## 🚀 Key Commands & Workflows

| Task | Command |
|---|---|
| **Run Targeted Tests** | `pytest backend/app/tests/test_<feature>.py -v` |
| **Check API Keys & Services** | `python check_api_keys.py` |
| **Create DB Migration** | `alembic revision --autogenerate -m "<description>"` |
| **Apply DB Migrations** | `alembic upgrade head` (or `python run_migration.py`) |
| **Run Background Worker** | `python -m backend.app.workers.rq_worker` |
| **Frontend Dev Server** | `cd frontend && npm run dev` |
| **Frontend Build Check** | `cd frontend && npm run build` |

---

## 📁 Custom Codex Commands
- `/document-code <path>`: Transforms any file into pristine, Staff Engineer-grade documented code with module contracts, Google docstrings, and architectural tags.
- `/document-sweep <path>`: Systematically documents an entire directory file-by-file to avoid context truncation.
- `/test-loop <path>`: Enters an autonomous loop to run tests and fix code until green.
- `/remember <lesson>`: Adds a new permanent rule to the Persistent Memory section below.

---

## 🧠 Persistent Memory & Lessons Learned
*(This section is automatically managed by the `/remember` command. Codex will check here to avoid repeating past mistakes.)*

- **Example Rule:** All background worker jobs must log failures to Redis so the frontend can display exact failure reasons.

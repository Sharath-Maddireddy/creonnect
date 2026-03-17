# Creonnect

Creator Intelligence Backend - AI-powered analytics and insights for social media creators.

## Features

- **Niche Classification**: Automatically detect creator's content niche
- **Growth Scoring**: Calculate growth potential (0-100) based on engagement metrics
- **Post Analysis**: Analyze individual post performance
- **AI Explanations**: Generate natural language insights using RAG + LLM

## Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Mac/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Set environment variables
set OPENAI_API_KEY=your_key_here  # Windows
export OPENAI_API_KEY=your_key_here  # Mac/Linux

# Run demo
python -m backend.app.demo

# Run API server
uvicorn backend.main:app --reload
```

## Instagram OAuth (Recommended)

This project now supports the official Instagram OAuth flow via the Meta Graph API.

1. Create a Meta app with Instagram Basic Display or Graph API access.
2. Set the OAuth redirect URI to:
   `http://localhost:8000/api/auth/instagram/callback`
3. Configure environment variables (see `.env.example` and `backend/.env.example`):

```bash
INSTAGRAM_APP_ID=your_facebook_app_id_here
INSTAGRAM_APP_SECRET=your_facebook_app_secret_here
INSTAGRAM_REDIRECT_URI=http://localhost:8000/api/auth/instagram/callback
```

Note: `INSTAGRAM_SESSION_ID` is deprecated and only used for legacy dev scraper tooling.

## Demo Data

- Synthetic creator data lives under `backend/app/demo/`
- Generator script: `backend/app/demo/generate_fake_instagram.py`
- Output file: `backend/app/demo/synthetic_creator.json`

## Dev Fixture Tools (Instagram Scraper)

These scripts are `dev-only` for fixture generation/testing and are not part of production ingestion.

### Compliance and Acceptable Use

- This scraper workflow is intended for development and testing only.
- Use it only for accounts you own or accounts you have explicit permission to access.
- Accessing Instagram data by scraping may violate Instagram Terms of Service and applicable platform policies.
- Production ingestion must use official APIs where possible.
- You are responsible for ensuring lawful and policy-compliant use; this project disclaims responsibility for misuse.

**⚠️ Warning:** This dev scraper relies on a session cookie and should be used only in approved, compliant testing contexts.

#### Security Note: `INSTAGRAM_SESSION_ID`

- `INSTAGRAM_SESSION_ID` is a highly sensitive authentication credential and can provide full access to the associated Instagram account if exposed.
- Never commit session IDs to version control. Store them in local `.env` files and ensure those files are ignored in `.gitignore`.
- Rotate session credentials regularly, and rotate immediately if you suspect any leakage.
- Use separate test accounts for fixture generation; do not use personal accounts.
- For shared/local-prod-like environments, prefer secret management tools (for example, secret vaults or CI/CD secret stores) over hardcoded values.
- Windows note: CMD does not support `\` line continuation. Use a single line (recommended), or `^` in CMD / `` ` `` in PowerShell.

```bash
# Required session for dev scraper calls
set INSTAGRAM_SESSION_ID=your_instagram_session_id   # Windows
export INSTAGRAM_SESSION_ID=your_instagram_session_id  # Mac/Linux

# Generate raw Instagram fixture JSON from scraper output (Windows single-line)
python -m backend.app.tools.generate_ig_raw_fixtures --username <name> --limit 30 --out fixtures/ig_<name>_raw.json

# Generate raw Instagram fixture JSON from scraper output
# (Mac/Linux with line continuation)
python -m backend.app.tools.generate_ig_raw_fixtures \
  --username <name> \
  --limit 30 \
  --out fixtures/ig_<name>_raw.json

# Enqueue account-analysis from a generated fixture
python -m backend.app.tools.enqueue_account_analysis_from_fixture \
  --fixture fixtures/ig_<name>_raw.json
```

If `INSTAGRAM_SESSION_ID` is missing, fixture generation exits with:
`Set INSTAGRAM_SESSION_ID to run fixture generator.`

## API Endpoints

- `GET /health` - Health check endpoint
- `POST /api/account-analysis` - Enqueue account-level analysis background job
- `GET /api/account-analysis/{job_id}` - Poll job status/result

## Account Analysis Jobs (RQ + Redis)

```bash
# Start Redis
docker run --rm -p 6379:6379 redis

# Start API
uvicorn backend.main:app --reload

# Start RQ worker (new terminal)
python -m backend.app.workers.rq_worker

# Enqueue account analysis (Windows single-line)
curl -X POST http://localhost:8000/api/account-analysis -H "Content-Type: application/json" -d "{\"account_id\":\"demo\",\"post_limit\":30}"

# Enqueue account analysis (Mac/Linux with line continuation)
curl -X POST http://localhost:8000/api/account-analysis \
  -H "Content-Type: application/json" \
  -d "{\"account_id\":\"demo\",\"post_limit\":30}"

# Poll status
curl http://localhost:8000/api/account-analysis/<job_id>
```

## Project Structure

```
backend/
|-- app/
|   |-- ai/           # AI modules (niche, growth, explain)
|   |-- api/          # FastAPI routers
|   |-- demo/         # Demo data + synthetic loader
|   |-- ingestion/    # Data ingestion and mapping
|   |-- knowledge/    # RAG knowledge base
|   |-- services/     # Orchestration layer
|   `-- utils/        # Logging and utilities
`-- main.py           # FastAPI application
```



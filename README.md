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

## API Endpoints

- `GET /health` - Health check endpoint

## Project Structure

```
backend/
├── app/
│   ├── ai/           # AI modules (niche, growth, explain)
│   ├── ingestion/    # Data ingestion and mapping
│   ├── knowledge/    # RAG knowledge base
│   └── utils/        # Logging and utilities
└── main.py           # FastAPI application
```

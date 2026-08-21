"""
Creonnect API Keys Health Check
Tests: Azure OpenAI, Gemini, Tavily, Supabase DB, Redis
"""
import asyncio
import os
import sys
from pathlib import Path

# Load env files
from dotenv import load_dotenv
repo_root = Path(__file__).resolve().parent
load_dotenv(repo_root / "backend" / ".env", override=True)

results = []

def ok(name, detail=""):
    results.append(("OK", name, detail))
    print(f"  [OK]  {name}" + (f" — {detail}" if detail else ""))

def fail(name, detail=""):
    results.append(("FAIL", name, detail))
    print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))

def skip(name, detail=""):
    results.append(("SKIP", name, detail))
    print(f"  [SKIP] {name}" + (f" — {detail}" if detail else ""))


print("\n=== Creonnect API Key Health Check ===\n")

# ── 1. Azure OpenAI ─────────────────────────────────────────────────────
print("1. Azure OpenAI (gpt-5.6-terra)")
try:
    from openai import AzureOpenAI
    client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    )
    resp = client.chat.completions.create(
        model=os.getenv("LLM_MODEL_NAME", "gpt-5.6-terra"),
        messages=[{"role": "user", "content": "Reply with OK only"}],
        max_completion_tokens=5,
    )
    ok("Azure OpenAI Chat", resp.choices[0].message.content.strip())
except Exception as e:
    fail("Azure OpenAI Chat", str(e)[:120])

# ── 2. Azure Embeddings ──────────────────────────────────────────────────
print("\n2. Azure Embeddings (text-embedding-3-small)")
try:
    from openai import AzureOpenAI
    client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    )
    emb = client.embeddings.create(
        model=os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
        input="health check",
    )
    dims = len(emb.data[0].embedding)
    ok("Azure Embeddings", f"{dims} dims")
except Exception as e:
    fail("Azure Embeddings", str(e)[:120])

# ── 3. Gemini Vision ─────────────────────────────────────────────────────
print("\n3. Google Gemini (gemini-2.5-flash-lite)")
try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-flash-lite")
    resp = model.generate_content("Reply with OK only")
    ok("Gemini Vision", resp.text.strip()[:40])
except Exception as e:
    fail("Gemini Vision", str(e)[:120])

# ── 4. Tavily Search ─────────────────────────────────────────────────────
print("\n4. Tavily Search API")
try:
    from tavily import TavilyClient
    t = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    r = t.search("test", max_results=1)
    ok("Tavily Search", f"{len(r.get('results', []))} result(s)")
except Exception as e:
    fail("Tavily Search", str(e)[:120])

# ── 5. Supabase / PostgreSQL ─────────────────────────────────────────────
print("\n5. Supabase PostgreSQL")
try:
    import asyncpg
    db_url = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    async def test_db():
        conn = await asyncpg.connect(db_url, timeout=10)
        val = await conn.fetchval("SELECT 1")
        await conn.close()
        return val
    result = asyncio.run(test_db())
    ok("Supabase PostgreSQL", f"SELECT 1 = {result}")
except Exception as e:
    fail("Supabase PostgreSQL", str(e)[:120])

# ── 6. Redis ─────────────────────────────────────────────────────────────
print("\n6. Redis")
try:
    import redis
    r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_connect_timeout=3)
    r.ping()
    ok("Redis", "PONG received")
except Exception as e:
    fail("Redis", str(e)[:120])


# ── Summary ──────────────────────────────────────────────────────────────
print("\n" + "=" * 40)
passed = sum(1 for s, *_ in results if s == "OK")
failed = sum(1 for s, *_ in results if s == "FAIL")
skipped = sum(1 for s, *_ in results if s == "SKIP")
print(f"PASSED: {passed}  FAILED: {failed}  SKIPPED: {skipped}")
print("=" * 40 + "\n")
sys.exit(0 if failed == 0 else 1)

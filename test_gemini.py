import os
import asyncio
from pathlib import Path
from urllib.parse import urlparse

env_path = Path("backend/.env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

api_key = os.getenv("GEMINI_API_KEY")
print("API Key starts with:", api_key[:10] if api_key else "None")

import google.generativeai as genai

async def test_vision():
    media_url = "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=800"
    instruction = "Hello, what is in this image?"
    print("Testing vision against URL:", media_url)
    
    try:
        def call_gemini():
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-flash-latest")
            # Wait, google.generativeai GenerateContent requires either PIL Image or a list of parts. 
            # Can we just pass an HTTP URL as part of the list? Let's trace how ai_analysis_service does it.
            response = model.generate_content([instruction, media_url])
            return response.text
        
        text = await asyncio.wait_for(asyncio.to_thread(call_gemini), timeout=30.0)
        print("Success:", text)
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e))
        import traceback
        traceback.print_exc()

asyncio.run(test_vision())

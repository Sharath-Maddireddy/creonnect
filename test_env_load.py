#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from pathlib import Path

# Load .env from backend directory or root fallback
from dotenv import load_dotenv
_backend_env = Path(__file__).parent / "backend" / ".env"
_root_env = Path(__file__).parent / ".env"
_env_file = _backend_env if _backend_env.exists() else _root_env
load_dotenv(_env_file, override=False)

import os
key = os.getenv('GEMINI_API_KEY', '').strip()
print(f'GEMINI_API_KEY loaded: {bool(key)}')
print(f'Key length: {len(key)}')
if key:
    print(f'Key starts with: {key[:10]}')
    print(f'Key ends with: {key[-10:]}')

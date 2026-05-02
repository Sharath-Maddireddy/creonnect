# Contributing to Creonnect

Thank you for contributing! This document outlines standards, testing expectations, and the PR process.

## Code of Conduct

Be respectful, inclusive, and professional. If issues arise, contact the maintainers.

---

## Development Setup

See [QUICKSTART.md](TOC.md#quickstart) for local development setup.

---

## Code Style

### Python (Backend)

**Standard:** PEP 8 with type hints.

```python
# Good
def analyze_post(post: SinglePostInsights, include_ai: bool = False) -> dict[str, Any]:
    """Analyze a single post.
    
    Args:
        post: Post data model.
        include_ai: Whether to run AI analysis.
    
    Returns:
        Analysis result dictionary.
    """
    result = {}
    if include_ai:
        result["ai_analysis"] = analyze_single_post_ai(post)
    return result

# Bad
def analyze_post(post, include_ai=False):
    # no type hints, no docstring
    result = {}
    if include_ai:
        result["ai_analysis"] = analyze_single_post_ai(post)
    return result
```

**Guidelines:**
- Use type hints for function arguments and return values.
- Write docstrings for all public functions (Google or NumPy style).
- Keep functions under 50 lines where possible.
- Use descriptive variable names; avoid single-letter vars except in loops/math.
- One import per line (except `from X import a, b, c` for related imports).
- Sort imports: stdlib, third-party, local.

**Example:**
```python
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel

from backend.app.utils.logger import logger
```

### JavaScript/TypeScript (Frontend)

**Standard:** ES6+, functional components, no `var`.

```javascript
// Good
async function fetchDashboard(userId) {
  const response = await fetch(`/api/creator/dashboard?user_id=${userId}`);
  if (!response.ok) {
    throw new Error(`Dashboard fetch failed: ${response.status}`);
  }
  return response.json();
}

// Bad
var fetchDashboard = function(userId) {
  // old style, no error handling
  return fetch(`/api/creator/dashboard?user_id=${userId}`).then(r => r.json());
}
```

**Guidelines:**
- Use `const` by default; `let` for reassignment; never `var`.
- Use async/await over `.then()` chains.
- Handle errors explicitly.
- Use template literals for string interpolation.
- Comment why, not what; code should be self-explanatory.

### Markdown Documentation

- Use ATX headings (`#`, `##`, `###`), not underlines.
- Code blocks with language tag (` ```python`, ` ```bash`, etc.).
- Links: relative paths for local docs, absolute URLs for external.
- Lists: use `-` for unordered; `1.`, `2.` for ordered.

---

## Testing

### Backend Tests

**Location:** `backend/app/tests/`

**Framework:** pytest

**Run tests:**
```bash
pytest
# or verbose
pytest -v
# or specific test
pytest backend/app/tests/test_dashboard.py::test_build_creator_dashboard
```

**Guidelines:**
- Write tests for all public functions.
- Use fixtures from `conftest.py` (DB, Redis, API client mocks).
- Test happy path and error cases.
- Mock external APIs (Instagram, OpenAI, Gemini).
- Name tests descriptively: `test_<function>_<scenario>`.

**Example:**
```python
def test_build_single_post_insights_with_ai(post_fixture, capsys):
    """Test post insights pipeline with AI enabled."""
    result = build_single_post_insights(
        target_post=post_fixture,
        historical_posts=[],
        run_ai=True
    )
    
    assert result["post"].media_id == post_fixture.media_id
    assert result["ai_analysis"] is not None
    assert "summary" in result["ai_analysis"]
```

### Frontend Tests

**Framework:** Vitest or Jest (depends on setup)

**Run tests:**
```bash
npm run test
npm run test:coverage
```

**Guidelines:**
- Test component rendering and user interactions.
- Mock API calls.
- Use descriptive test names.

---

## Commits & Git

### Commit Messages

**Format:** `<type>: <subject>`

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`

**Examples:**
```
feat: add cringe detection to brand safety score
fix: handle null engagement rate in benchmark calculation
docs: update API endpoints reference
refactor: extract metric computation into helper function
test: add tests for action plan generation
```

**Guidelines:**
- Keep commit messages concise and descriptive.
- One logical change per commit.
- Reference issue numbers: `Fixes #123` in description.

### Branching

- `main` — production-ready code
- `develop` — integration branch for features
- `feature/<name>` — feature branches
- `hotfix/<name>` — urgent production fixes

**Workflow:**
```bash
# Create feature branch from develop
git checkout develop
git pull origin develop
git checkout -b feature/my-new-feature

# Make changes, commit, push
git add .
git commit -m "feat: add new feature"
git push origin feature/my-new-feature

# Create pull request on GitHub
```

---

## Pull Request Process

### Before Submitting

1. **Test locally:**
   ```bash
   pytest
   npm run test
   npm run build  # frontend
   ```

2. **Check code style:**
   ```bash
   # Python (optional, if using linter)
   pylint backend/app/services/my_service.py
   # or
   flake8 backend/
   ```

3. **Update docs** if you changed behavior (API, services, config).

4. **Keep commit history clean:**
   ```bash
   # Rebase if needed
   git rebase -i develop
   ```

### PR Template

```markdown
## Description
Brief summary of changes.

## Changes
- List of specific changes
- One per line

## Testing
- How was this tested?
- Test cases added?

## Checklist
- [ ] Tests added/updated
- [ ] Docs updated
- [ ] No breaking changes (or documented)
- [ ] Commit messages follow format
- [ ] All tests passing
```

### Review Process

- PRs require at least 1 approval.
- CI/CD must pass (tests, linting, build).
- Address review comments.
- Keep PRs focused (one feature per PR when possible).

---

## Architecture Guidelines

### Adding a New Service

1. Create `backend/app/services/my_service.py`.
2. Define public function(s) with clear inputs/outputs.
3. Add docstrings and type hints.
4. Log progress with `logger.info()`.
5. Raise `HTTPException` or custom exceptions for errors.
6. Write tests in `backend/app/tests/test_my_service.py`.
7. Document in [BACKEND_SERVICES.md](BACKEND_SERVICES.md).

### Adding a New API Endpoint

1. Create router in `backend/app/api/my_router.py`.
2. Define route with clear path, method, docstring.
3. Use Pydantic models for request/response validation.
4. Call services for business logic.
5. Return appropriate HTTP status codes.
6. Add tests in `backend/app/tests/test_my_router.py`.
7. Document in [API_ENDPOINTS.md](API_ENDPOINTS.md).

### Adding a New AI Module

1. Create `backend/app/ai/my_module.py`.
2. Define pure functions where possible.
3. Use pydantic schemas for inputs.
4. Handle errors gracefully (fallback to deterministic rules).
5. Log LLM/vision API calls.
6. Write tests with mocked API responses.
7. Document in [AI_ANALYTICS_PIPELINES.md](AI_ANALYTICS_PIPELINES.md).

---

## Common Mistakes to Avoid

1. **Missing type hints** — Always add them.
2. **No docstrings** — Document public functions.
3. **Hardcoding values** — Use environment variables or config.
4. **Not testing** — Write tests for new code.
5. **Ignoring error cases** — Handle errors explicitly.
6. **Committing secrets** — Use `.env`, never commit API keys.
7. **Large PRs** — Keep PRs focused; split large changes.
8. **Stale docs** — Update docs when behavior changes.

---

## Performance Considerations

- **Database:** Use indexes for frequently queried columns. Prefer async queries.
- **LLM Calls:** Cache responses in Redis. Implement timeouts.
- **Vision API:** Handle large images; consider compression.
- **Frontend:** Lazy-load routes, optimize images, use CDN.
- **Caching:** Cache hot data (creator profiles, post snapshots).

---

## Security Checklist

- [ ] No secrets in code or git history.
- [ ] Input validation on all API endpoints.
- [ ] CORS configured correctly.
- [ ] SQL injection prevented (use ORM).
- [ ] Auth checks on protected endpoints.
- [ ] Error messages don't leak sensitive info.
- [ ] Dependencies have no critical vulnerabilities (`pip audit`, `npm audit`).

---

## Debugging Tips

### Backend

```bash
# Print logs
python -c "from backend.app.utils.logger import logger; logger.info('test')"

# Database query
from backend.app.infra.database import get_sync_sessionmaker
session = get_sync_sessionmaker()()
creators = session.query(Creator).all()
print(creators)

# Redis inspection
from backend.app.infra.redis_client import get_redis
redis = get_redis()
print(redis.get('my_key'))
```

### Frontend

```javascript
// Console logging
console.log("Dashboard data:", dashboard);

// API debugging
fetch('/api/creator/dashboard').then(r => r.json()).then(d => console.log(d));
```

---

## Useful Links

- [FastAPI Docs](https://fastapi.tiangolo.com)
- [Pydantic Docs](https://docs.pydantic.dev)
- [SQLAlchemy Docs](https://docs.sqlalchemy.org)
- [pytest Docs](https://docs.pytest.org)
- [Vite Docs](https://vitejs.dev)
- [PEP 8 Style Guide](https://pep8.org)

---

## Questions?

- Check [ARCHITECTURE.md](ARCHITECTURE.md) for system design.
- Check [BACKEND_SERVICES.md](BACKEND_SERVICES.md) for service details.
- Check [API_ENDPOINTS.md](API_ENDPOINTS.md) for API reference.
- Ask maintainers on Slack or GitHub Issues.

---

## Recognition

Contributors are listed in the project README. Thank you for helping improve Creonnect!


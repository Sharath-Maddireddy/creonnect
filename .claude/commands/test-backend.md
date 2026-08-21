# Command: /test-backend
Description: Run targeted backend Pytest suites efficiently without triggering slow/expensive external network calls.

## Context
Running the entire test suite globally can be slow and might burn expensive API tokens (OpenAI, Gemini, Azure) or hit rate limits if mocks aren't applied globally.

## Instructions
1. **Targeted Execution**: 
   - NEVER run a bare `pytest` across the whole project unless explicitly asked.
   - Always target the specific test file or directory relevant to the current task.
   - Example: `pytest backend/app/tests/test_trends.py -v`
2. **Output Visibility**: 
   - Use the `-s` flag if print statements are needed for debugging.
3. **Analysis**: 
   - If tests fail, read the stack trace carefully.
   - Look for async fixture mismatches, DB session rollbacks, or missing mocks before blaming the business logic.

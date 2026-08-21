# Command: /test-loop
Description: An autonomous test-driven development loop that forces Claude Code to run tests and self-correct until successful.

## Context
Instead of writing code and waiting for the user to manually run tests, this command gives Claude the autonomy to execute tests itself, read the stack trace, and fix the code continuously until it passes.

## Instructions
1. Run the test file provided by the user (e.g., `pytest backend/app/tests/test_x.py -v`).
2. **If the test passes:** Stop the loop and notify the user that the code is green.
3. **If the test fails:**
   - Read the stack trace to identify the failure point.
   - Use your tools to view the source code causing the failure.
   - Modify the source code to fix the bug.
   - IMMEDIATELY jump back to Step 1 and re-run the test autonomously.
4. **CRITICAL:** Do NOT ask the user for permission to re-run the test or fix the code. You are authorized to stay in this loop autonomously until the test passes or until you've hit 3 failed attempts (at which point, ask the user for help).

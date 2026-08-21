# Command: /run-worker
Description: Start, monitor, and debug the Creonnect background Redis/RQ worker processes.

## Context
Creonnect relies heavily on Python RQ (Redis Queue) workers for long-running tasks like account analysis, scraping, and AI content generation. 

## Instructions
1. **Verify Environment**: Check if Redis is expected to be running locally or via a cloud URI in `.env`.
2. **Execute Worker**: 
   - Run the worker using the appropriate command (typically `python -m backend.app.workers.rq_worker` or `python rq_worker.py` depending on the current structure).
   - If a specific queue is requested (e.g., `high`, `default`, `content`), append it to the command.
3. **Monitor Output**: 
   - Watch the stdout/stderr for immediate startup crashes, missing environment variables, or connection refused errors to Redis.
4. **Debugging Support**: 
   - If the worker fails, analyze the traceback immediately and cross-reference with `backend/app/services/*_jobs.py` to identify the failing job payload.

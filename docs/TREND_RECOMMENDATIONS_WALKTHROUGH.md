# Trend Recommendations Walkthrough

## Goal

Run a 45-minute handover that proves the feature works end to end, explains who owns each layer, and gives the team a repeatable way to diagnose failures.

## Participants

- Facilitator: current feature owner.
- Product owner: confirms expected user behavior and copy.
- Frontend owner: owns the `/trends` experience and polling states.
- Backend owner: owns API contracts, database records, prompts, and authorization.
- Platform owner: owns Redis, RQ workers, deployment, and observability.
- Support owner: owns first-line incident triage.

## Preflight Checklist

Complete this 15 minutes before the meeting.

- Use a non-production creator account with a completed account analysis and trend-analysis result.
- Sign in as that same account so account-scoped requests are authorized.
- Start the API, Redis, `worker`, and `worker-content`.
- Confirm `worker-content` starts with `RQ_QUEUES=trend-analysis,content-suggestions`.
- Confirm the database schema is current with `alembic upgrade head`.
- Have one reel, one carousel, and one photo idea available, or generate them beforehand.
- Open three windows: the app at `/trends`, `worker-content` logs, and API logs.
- Prepare a safe non-production environment for the queue-failure demonstration. Do not stop production workers during the walkthrough.

## Agenda

| Time | Topic | Outcome |
| --- | --- | --- |
| 0-5 min | Context and architecture | Team understands what the feature owns and depends on. |
| 5-13 min | Explore recommendations | Team sees creator-specific recommendations and sidebar signals. |
| 13-23 min | Generate full ideas | Team sees asynchronous queue processing and persisted results. |
| 23-33 min | Execute an idea | Team sees format-specific generation, saving, and scheduling. |
| 33-40 min | Failure and recovery | Team can diagnose a stopped or unavailable content worker. |
| 40-45 min | Ownership and questions | Owners accept responsibilities and record follow-ups. |

## Facilitator Script

### 1. Context and Architecture: 0-5 Minutes

Say:

> Trend Recommendations converts completed creator analysis plus trend signals into content angles. It does not generate ideas synchronously in the web request. The API creates a job, Redis holds the queue, and `worker-content` produces and persists the final ideas.

Show:

- [TrendRecommendations.jsx](../frontend/src/pages/TrendRecommendations.jsx)
- [content_suggestion_routes.py](../backend/app/api/content_suggestion_routes.py)
- [content_suggestion_jobs.py](../backend/app/services/content_suggestion_jobs.py)
- [docker-compose.prod.yml](../docker-compose.prod.yml)

Point out:

- The frontend route is `/trends`.
- The content-suggestion API prefix is `/api/v1/accounts`.
- `worker-content`, not the standard worker, handles `trend-analysis` and `content-suggestions`.
- The database records both generated ideas and their job status.

### 2. Explore Recommendations: 5-13 Minutes

Steps:

1. Open `/trends` while signed in.
2. Search for the prepared creator account.
3. Explain the Weekly Opportunity summary and opportunity score.
4. Explain the recommendation-card fields: title, hook, rationale, opportunity score, difficulty, and content type.
5. Show the right-side data panels: Today's Insights, Analysis Pipeline, Niche Detected, Trending Topics, Content Gaps, and Trending Audio.
6. Open Trending Topics and Trending Audio where data is present.

Say:

> The sidebar reports available analysis and trend data. It must never make up a trend metric or an Instagram track title when a verified source has not supplied it.

Expected outcome:

- Recommendation cards are visible.
- Sidebar panels contain data or an honest empty-state explanation.

### 3. Generate Full Ideas: 13-23 Minutes

Steps:

1. Click **Generate Full Ideas**.
2. Show the initial queued/progress state in the UI.
3. In `worker-content` logs, locate the new job ID and show the job being picked up.
4. Explain the generation stages: content analysis, trend research, audience analysis, competitor checks, and high-potential idea generation.
5. Wait for completion, then show the new cards under Generated Ideas.
6. Refresh the browser only if the polling state does not update; it should normally update automatically.

Say:

> The UI is polling the job-status endpoint. A completed job writes persisted ideas, which is why downstream actions can use a stable idea ID instead of an in-memory recommendation card.

Expected outcome:

- Job moves from queued to processing to completed.
- Generated idea cards appear with stored IDs.

### 4. Execute, Save, and Schedule: 23-33 Minutes

Demonstrate one action for each format:

| Idea type | Primary action | Secondary action |
| --- | --- | --- |
| Reel | Generate Script | Generate Caption |
| Carousel | Generate Slides | Generate Caption |
| Photo | Generate Photo Brief | Generate Caption |

Steps:

1. Use a reel idea and click **Generate Script**. Explain that it creates a video/reel script.
2. Use a carousel idea and click **Generate Slides**. Explain that a carousel should not be presented as a reel script.
3. Use a photo idea and click **Generate Photo Brief**.
4. Generate a caption for one idea.
5. Click **Save Idea**, add it to a collection if relevant, then click **Schedule**.
6. Open **View Content Calendar** and confirm the scheduled item is present.

Say:

> Recommendation cards can be persisted before downstream generation. If a user encounters "Idea not found in the database yet," the idea has not completed persistence; save it or generate full ideas first.

Expected outcome:

- Each action matches the content type.
- A saved and scheduled idea appears in the calendar.

### 5. Prompt Assistant: 33-35 Minutes

Steps:

1. Enter a concrete prompt such as `Give me three educational carousel angles for my niche`.
2. Send the prompt and show the response.
3. Explain that it uses the same account-scoped context and must return a clear error if its provider or data dependency is unavailable.

Expected outcome:

- The assistant responds or displays an actionable failure state.

### 6. Failure and Recovery: 35-40 Minutes

Only perform this in a non-production environment.

Steps:

1. Stop `worker-content` while leaving API and Redis up.
2. Queue a full-idea generation request.
3. Show the job remaining queued or the recorded queue-unavailable failure, depending on the failure point.
4. Start `worker-content` again with:

```powershell
$env:RQ_QUEUES = 'trend-analysis,content-suggestions'
python -m backend.app.workers.rq_worker
```

5. Show the worker connecting to Redis and processing the queued job.
6. If the job is marked failed due to enqueue failure, submit a new request after recovery; failed jobs are intentionally not executed in the API process.

Say:

> The recovery is to restore Redis connectivity and the content worker, then submit a new generation request. We do not fall back to synchronous LLM work because that would block API requests and hide an operational outage.

## Incident Triage Exercise

Ask the support owner to answer these questions from the logs and database record:

1. What is the `account_id` and job ID?
2. Is Redis reachable from API and `worker-content`?
3. Is `worker-content` subscribed to `content-suggestions`?
4. What is the job's persisted `status`, `step_label`, and `error_message`?
5. Did the LLM provider return an error or rate-limit response?
6. Does the creator have completed account and trend analysis data?

## Acceptance Checklist

By the end of the meeting, confirm all items aloud:

- The team knows that `worker-content` is required for idea generation.
- The team can identify the API, worker, Redis queue, and database record for one generated idea.
- The team understands that actions differ for reels, carousels, and photos.
- The team knows the recovery path for stuck or failed jobs.
- Each layer has a named owner.
- Follow-up tasks and unresolved limitations are recorded in the team tracker.

## References

- [Trend Recommendations Handover](TREND_RECOMMENDATIONS_HANDOVER.md)
- [TrendRecommendations.jsx](../frontend/src/pages/TrendRecommendations.jsx)
- [content_suggestion_routes.py](../backend/app/api/content_suggestion_routes.py)
- [content_suggestion_jobs.py](../backend/app/services/content_suggestion_jobs.py)
- [trend_recommendation_engine.py](../backend/app/analytics/trend_recommendation_engine.py)
- [docker-compose.prod.yml](../docker-compose.prod.yml)

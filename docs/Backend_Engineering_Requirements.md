# Creonnect — Backend Engineering Requirements
## Creator Discovery Infrastructure Upgrade


## 1. Overview

This document outlines the production-ready infrastructure requirements for the Creonnect Creator Discovery system. The core discovery logic (Semantic Matching, Audience Authenticity Scoring, Brand Match Engine) has already been implemented and fully validated at the PoC stage. This document describes what the backend team must build to bring these into a scalable, production-grade deployment.

---

## 2. Background — What Has Already Been Built

The following modules are complete and production-ready at the **logic layer**. Backend has no responsibilities for these files, only for the data infrastructure they depend on.

| Module | File | Status |
|---|---|---|
| Brand Campaign AI Parser | `backend/app/services/campaign_prompt_service.py` | DONE |
| Creator Pool Service | `backend/app/services/creator_pool_service.py` | DONE |
| Semantic Scoring Engine | `backend/app/analytics/brand_match_engine.py` | DONE |
| Audience Authenticity Scoring | `backend/app/analytics/audience_quality.py` | DONE |
| LLM Embedding Client | `backend/app/ai/llm_client.py embed()` | DONE |
| Semantic Search API Endpoint | `backend/app/api/campaign_routes.py` | DONE |
| Lookalike API Endpoint | `backend/app/api/campaign_routes.py` | DONE |
| Authenticity Pre-Compute Job | `backend/app/workers/nightly_jobs.py` | DONE |

---

## 3. Production Requirements

### 3.1 REQ-001 — Vector Database Setup

**Priority:** HIGH
**Rationale:** stores creator embeddings in a Python dictionary in server RAM. This is only viable for small pools (< 1,000 creators) and will fail in production.

**What is required:**
- Select and provision a Vector Database. Recommended options (in order of preference):
  - **`pgvector`** extension on the existing PostgreSQL DB (cheapest, no new infrastructure)
  - **Pinecone** (managed cloud Vector DB, easiest to set up)
  - **Milvus** or **Qdrant** (self-hosted, open source)

**Specific tasks:**
1. Create a `creator_vectors` table (if using `pgvector`) with the following schema:
   - `account_id` (TEXT, Primary Key, linked to the main creator table)
   - `embedding` (VECTOR(1536)) — the 1,536-dimension OpenAI embedding
   - `created_at` (TIMESTAMP)
   - `updated_at` (TIMESTAMP)
2. Add a metadata table `creator_discovery_meta` with pre-computed filter fields:
   - `account_id` (FK)
   - `follower_count` (INTEGER)
   - `creator_dominant_category` (TEXT)
   - `authenticity_score` (FLOAT, pre-computed)
   - `avg_visual_quality_score` (FLOAT)
   - `avg_brand_safety_score` (FLOAT)
   - `adult_content_detected` (BOOLEAN)
   - `predicted_engagement_rate` (FLOAT)

---

### 3.2 REQ-002 — Asynchronous Embedding Ingestion Worker

**Priority:** HIGH
**Rationale:** Creator embeddings must never be generated in real-time during a live search. They must be pre-computed and stored offline.

**What is required:**
- An RQ/Celery background worker task called `generate_creator_embedding`.
- This task must be **triggered automatically** whenever:
  - A new creator profile is created in the platform.
  - An existing creator profile's bio, category, or niche tags are updated.
- The task should:
  1. Combine `creator_dominant_category` + `niche_tags` + `bio` into a single text string.
  2. Call `LLMClient().embed(text)` (already implemented in `llm_client.py`) to get the embedding vector.
  3. Store the resulting 1,536-dimension vector in the `creator_vectors` table / Pinecone index.
  4. Pre-compute the `authenticity_score` using `calculate_authenticity_score()` (already implemented in `audience_quality.py`) and store it in `creator_discovery_meta`.

**Important:** The existing `_load_creator_pool()` generates embeddings synchronously on the first server request. This is acceptable ONLY for the PoC/demo environment. In production, `_load_creator_pool()` must be replaced with a query to the Vector DB.

---



## 4. Data Requirements from Existing Creator Snapshots

The scoring engine requires the following fields from the creator database for each candidate. Confirm these are available in the existing schema.

| Field | Type | Required For |
|---|---|---|
| `account_id` | TEXT | Primary Key / Lookup |
| `follower_count` | INTEGER | Audience Size Fit, Auth Score pre-filter |
| `creator_dominant_category` | TEXT | Semantic Fit Fallback |
| `avg_views` | INTEGER | Authenticity Score |
| `avg_likes` | INTEGER | Authenticity Score |
| `avg_comments` | INTEGER | Authenticity Score |
| `ahs_score` | FLOAT | Engagement Quality Score |
| `avg_visual_quality_score` | FLOAT | Content Quality Score (S1) |
| `avg_brand_safety_score` | FLOAT | Brand Safety Score (S6) |
| `predicted_engagement_rate` | FLOAT | Engagement Quality Score |
| `adult_content_detected` | BOOLEAN | Hard Disqualification |

---

## 5. Embedding Cost Estimate

Using **OpenAI `text-embedding-3-small`** (the current implementation):

| Scale | Estimated Cost (One-Time Ingestion) |
|---|---|
| 1,000 creators | ~$0.003 |
| 10,000 creators | ~$0.03 |
| 100,000 creators | ~$0.30 |
| 1,000,000 creators | ~$3.00 |

**Search cost:** Each brand search prompt embeds one short string (~50–100 tokens). At $0.02/1M tokens, this is essentially $0 per search.

---

## 6. Acceptance Criteria

| Requirement | Acceptance Test |
|---|---|
| REQ-001 (Vector DB) | A new creator can be stored and retrieved by vector similarity. |
| REQ-002 (Ingestion Worker) | Creating a new creator profile automatically triggers the embedding job. |

---

*This document was prepared by the Creonnect Core Team. For questions, contact the product / AI team.*

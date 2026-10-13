# Day Plan: Ticket API & AI Triage Service

## Overview

This plan covers the complete lifecycle of **Task 2 (Read, Debug, Own)** and **Task 3 (Build with AI, Own Every Line)**.

---

## 1. Task 2: Read, Debug, Own

### Objective
Stabilize, correct, document, and connect the inherited `ticket-api` service so that any new engineer can run, test, and maintain it without assistance.

### Steps
1. **Try to Run It (Document Exact Behavior)**:
   - Follow `ticket-api/README.md` as written (`pip install -r requirements.txt`, `uvicorn main:app --reload`).
   - Record exact failures:
     - `KeyError: 'TICKETS_DATA_PATH'` due to missing default path.
     - `ModuleNotFoundError: No module named 'main'` because `main.py` is in `app/main.py`.
2. **Get It Running**:
   - Provide safe fallback default path `data/tickets_sample.csv` when `TICKETS_DATA_PATH` is unset.
   - Fix README instruction to `uvicorn app.main:app --reload`.
   - Fix frontend month indexing bug in `web/index.html` (`d.getMonth() + 1`).
3. **Make It Correct (Test-Driven)**:
   - Write failing test for pagination: `GET /tickets?page=1&size=10` must start at index 0 (`TCK-1001`), fixing `start = (page - 1) * size + 1`.
   - Write failing test for average resolution calculation in `/summary`: average must be computed strictly across resolved tickets (`len(resolved_tickets)`), not total tickets (`len(TICKETS)`).
   - Fix both defects and ensure tests pass.
4. **Document It**:
   - Update `README.md` with complete setup, environment configuration, and test instructions.
   - Create `docs/ROOT_CAUSE.md` detailing every bug, discovery method, and applied solution.
5. **Connect Day 1 Work**:
   - Integrate Day 1's `python-ticket-summary` calculation engine into `/summary`.
   - Preserve backward-compatible keys (`total`, `by_category`, `average_resolution_hours`) while exposing extended metrics (`category_averages`, `skipped_tickets`).
   - Add comprehensive tests validating `/summary` against `tickets_sample.csv`.

---

## 2. Task 3: Build with AI, Own Every Line

### Approach for /triage and Retrieval (3 to 5 lines)
We will build `POST /triage` by pairing a lightweight BM25/keyword retrieval step over the 6 KB markdown articles with a structured Google Gemini Flash function call returning category, priority, grounded reply, and article IDs.
The model call will be isolated behind a single swappable interface so it can be tested with offline mocks without incurring costs or network latency.
What could go wrong: retrieval might pull irrelevant articles for ambiguous tickets, prompt injection or unusual inputs (empty or 6KB repetitions) could disrupt parsing, and external API rate limits or network timeouts could cause unhandled 500 errors unless gracefully caught and routed to human review.

### Steps
1. **Knowledge Base Ingestion & Retrieval**:
   - Place 6 help articles in `kb/`.
   - Implement `app/retrieval.py` using keyword/BM25 token-matching to score and select the top relevant articles.
2. **Backend Triage Endpoint (`POST /triage`)**:
   - Implement structured output schema via Pydantic (`category`, `priority`, `suggested_reply`, `article_ids`).
   - Encapsulate LLM calls in `app/triage_ai.py` with mockable interface.
   - Enforce edge case policies:
     - Empty/whitespace input -> HTTP 422.
     - Very long input (>4,000 characters) -> truncate cleanly.
     - Out-of-scope query -> human follow-up reply, no hallucinated policies.
     - Prompt injection attempt -> isolate user input as untrusted content.
     - Model failure/timeout -> graceful degradation fallback marked for human review.
   - Write unit tests mocking the model and verifying all edge cases (S1–S10).
3. **Small TypeScript Screen (`frontend/`)**:
   - Scaffold Vite + React + TypeScript in `frontend/`.
   - Provide form, submission button, loading state, error alerts, and result card.
   - Read API endpoint from `VITE_API_BASE_URL`.
   - Add Vitest component test.
   - Configure CORS in FastAPI.
4. **Deployment & Environment Security**:
   - Maintain `.env.example` with mock values only.
   - Configure `Dockerfile` and `render.yaml` for Render.com deployment.
   - Validate live deployment with a real request and verify in Render logs.
5. **Live Demo and Defense Prep**:
   - Prepare 3-minute demo script and code walkthrough covering empty inputs and error fallbacks.

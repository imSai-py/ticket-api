# AI Use Log

This document records the transparent usage of AI assistance across Task 2 and Task 3 development.

---

## 1. Tools and Models Used

- **Development Assistant**: Google Antigravity Agentic Assistant powered by Gemini models for code generation, test authoring, refactoring, and code review.
- **Runtime Inference Models**: Google Gemini API via `google-genai` SDK (`gemini-3.1-flash-lite` primary model with low-latency fallback cascade to `gemini-3.5-flash-lite` and `gemini-3.8-flash`).

---

## 2. Tasks Accelerated with AI

### Task 2: Codebase Investigation & Bug Remediation
- **Assistance**:
  - Analyzed stack traces and identified missing `TICKETS_DATA_PATH` environment variable handling in `app/main.py`.
  - Identified off-by-one pagination formula in `GET /tickets` skipping ticket `TCK-1001`.
  - Diagnosed zero-indexed JavaScript `getMonth()` bug in `web/index.html`.
  - Aligned `/summary` endpoint calculation with Day 1 logic (resolved tickets vs. total tickets).
- **Human Verification**:
  - Wrote reproducible failing unit tests before implementing each fix.
  - Verified outputs against raw `data/tickets_sample.csv` rows.

### Task 3: AI Ticket Triage Feature Implementation
- **Assistance**:
  - Scaffolded BM25 ranking algorithm in `app/retrieval.py` for tokenized retrieval across the 6 knowledge base articles.
  - Structured the Pydantic output schema (`category`, `priority`, `suggested_reply`, `article_ids`) with strict field validations.
  - Implemented multi-stage Docker build separating Node 20 frontend compilation from lightweight Python 3.11 runtime.
- **Human Verification**:
  - Enforced 4,000 character length budget and empty/whitespace input validation (`422 Unprocessable Entity`).
  - Added hallucination guardrails to filter out ungrounded article IDs.
  - Tested 10 real sample tickets (S1–S10), including prompt injection defenses (S7) and Spanish cross-lingual requests (S8).
### Task 4: Helpdesk Schema Ingestion & Production Basics
- **Assistance**:
  - Normalized daily helpdesk schema variations (`labels`, `customer_email`, `assigned_to`, `refund_amount`).
  - Added production health check endpoint (`GET /health`), input validations, and error handlers.
  - Implemented `DD/MM/YYYY` date formatting and USD refund normalization.
- **Human Verification**:
  - Verified unit test suite with offline mocks and zero test regressions.
  - Validated edge cases: missing `resolved_at` dates and Excel file lock contention.

### Task 5: Peer Code Review (Escalation Export)
- **Assistance**:
  - Ran parallel standards and spec reviews on Sam's pull request diff.
  - Identified critical schema mismatches (`tags` vs. `labels`) and non-rectangular CSV footer rows.
- **Human Verification**:
  - Re-verified all line numbers directly against source diff.
  - Provided kind, specific, actionable feedback in plain language following `review_template.md`.

---

## 3. Engineering Guardrails Enforced

1. **Deterministic Test Suite**: All unit and integration tests use offline mock responses.
2. **Zero Secret Leakage**: API keys remain strictly in environment variables; `.env` is ignored by git and verified by pre-commit checks.
3. **Multi-Model Fallback Cascade**: Automatic graceful degradation if primary free-tier models encounter upstream 503 high-demand spikes.


# 3-Minute Live Demo & Q&A Defense Guide

This guide prepares you for the live demo and technical defense.

---

## 1. 3-Minute Live Demo Script

### Minute 1: The Problem & Backend Core (0:00 - 1:00)
- **Show Swagger UI** at `http://localhost:8000/docs`.
- **Explain `/summary` endpoint**:
  - Show how it calculates the true resolution average (**25.27 hours**) strictly over the 42 resolved tickets, excluding the 18 open tickets.
  - Show how it exposes Day 1 category breakdowns (`category_averages`) and tracked open tickets (`skipped_tickets`).
- **Explain `/tickets` endpoint**:
  - Show that pagination begins at index 0, returning `TCK-1001` on page 1.

### Minute 2: AI Triage Architecture & Retrieval (1:00 - 2:00)
- **Show Knowledge Base Ingestion**:
  - Point to `kb/` containing the 6 curated markdown articles.
  - Explain `app/retrieval.py`: pure-Python BM25 scoring extracts the most relevant articles (up to top 3) without heavy vector database overhead.
- **Show `/triage` Endpoint**:
  - Post a sample ticket (e.g., *Subject: "Cannot log in", Body: "Reset email never arrives"*).
  - Show the returned structured JSON:
    - `category`: `Login`
    - `priority`: `high`
    - `suggested_reply`: grounded in `KB-001`
    - `article_ids`: `["KB-001"]`

### Minute 3: Interactive Frontend & Edge Cases (2:00 - 3:00)
- **Open Frontend** at `http://localhost:5173`.
- **Demonstrate Normal Ticket**: Paste sample ticket S1 -> Click Triage -> Show color-coded badges, reply blockquote, and cited sources.
- **Demonstrate Edge Cases**:
  1. *Empty Input (Sample S4)*: Submit empty fields -> Show clear validation alert (HTTP 422).
  2. *Out-of-Scope (Sample S6)*: Ask about Bitcoin payment -> Show that the model states a human agent will follow up and cites no articles (no hallucinations).
  3. *Adversarial Injection (Sample S7)*: Paste prompt injection -> Show that system instructions safely ignore customer override commands.

---

## 2. Technical Defense Q&A

### Question 1: "What happens when someone sends an empty input?"
**Your Answer**:
> "We handle empty input at the Pydantic schema validation boundary before any model or retrieval logic runs. In `app/schemas.py`, the `TriageRequest` model uses a validator (`validate_content_not_empty`) that checks whether both `subject.strip()` and `text.strip()` are empty. If so, it raises a validation error, and FastAPI automatically returns `HTTP 422 Unprocessable Entity` with a clear message. In the React frontend, we also have client-side validation that stops the submission before making the network request."

### Question 2: "What happens when the model call fails or times out?"
**Your Answer**:
> "We designed the service for graceful degradation so the customer support agent is never blocked. In `app/triage_ai.py`, the external model call is wrapped in a `try...except` block. If the API key is missing, network times out, or the provider encounters a 500/rate-limit error, we catch the exception and immediately return `get_fallback_triage()`. This returns an `HTTP 200` response with category `Technical`, priority `normal`, suggested reply stating a human specialist will review the request, and empty article IDs `[]`. The ticket stays in the queue for manual review without crashing the application."

### Question 3: "Why did you choose a pure-Python BM25 retriever instead of a vector database like ChromaDB or Pinecone?"
**Your Answer**:
> "We have exactly 6 short help articles totaling around 3 KB. Installing heavy vector frameworks like PyTorch or ChromaDB would add hundreds of megabytes to our Docker image, increase cold-start latency, and risk exceeding memory limits on free-tier platforms like Render. Pure-Python BM25 with token-overlap and title boosting runs in less than 5 milliseconds, uses negligible memory, requires zero external dependencies, and is 100% deterministic and offline testable."

### Question 4: "How did you connect your Day 1 work to the `/summary` endpoint?"
**Your Answer**:
> "The original endpoint had a mathematical defect: it accumulated hours for resolved tickets, but divided by total tickets (60 instead of 42), which skewed the average down to 17.69 hours. I ported the Day 1 calculation engine into `ticket_summary.py` and `app/summary_service.py` to calculate the average strictly across resolved tickets (yielding the true 25.27 hours). To ensure existing web UI callers didn't break, I preserved the root keys `total`, `by_category`, and `average_resolution_hours`, while also attaching the Day 1 extended metrics `category_averages` and `skipped_tickets`."

---

## 3. Render Live Deployment Verification & Platform Logs Evidence

### Live Verification Workflow
1. **Container Build and Local Verification**:
   ```bash
   docker build -t ticket-api .
   docker run -p 8000:8000 -e GEMINI_API_KEY="<REDACTED>" ticket-api
   ```
2. **Frontend Pointing to Deployed Endpoint**:
   Configure `frontend/.env`:
   ```bash
   VITE_API_BASE_URL=https://ticket-api.onrender.com
   ```
3. **Send Real Request & Verify Platform Log**:
   ```bash
   curl -X POST https://ticket-api.onrender.com/triage \
     -H "Content-Type: application/json" \
     -d '{"subject": "Cannot login", "text": "Password reset email not received"}'
   ```
   **Captured Render Platform Log Output**:
   ```text
   ==> Starting service with 'uvicorn app.main:app --host 0.0.0.0 --port 8000'
   INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
   INFO:     10.0.12.34:52180 - "POST /triage HTTP/1.1" 200 OK
   ```

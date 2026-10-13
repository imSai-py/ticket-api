# ticket-api

A support ticket analytics service and AI-powered ticket triage platform.

Requires Python 3.8+ and Node.js 18+.

---

## 1. Quick Start

### Backend (Python FastAPI)

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables (optional):
   ```bash
   cp .env.example .env
   # Edit .env and supply GEMINI_API_KEY if testing live AI calls
   ```

3. Run the development server:
   ```bash
   uvicorn app.main:app --reload
   ```
   - Web overview: http://localhost:8000/
   - Interactive API docs (Swagger): http://localhost:8000/docs
   - Triage endpoint: `POST http://localhost:8000/triage`

### Frontend (React + TypeScript)

1. Install frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Run frontend development server:
   ```bash
   npm run dev
   ```
   - Triage UI: http://localhost:5173/

---

## 2. Approach: AI Ticket Triage & Retrieval

We build `POST /triage` by pairing a lightweight BM25/keyword retrieval step over the 6 KB markdown articles with a structured Google Gemini Flash function call returning category, priority, grounded reply, and article IDs.
The model call is isolated behind a single swappable interface so it can be tested with offline mocks without incurring costs or network latency.
What could go wrong: retrieval might pull irrelevant articles for ambiguous tickets, prompt injection or unusual inputs (empty or 6KB repetitions) could disrupt parsing, and external API rate limits or network timeouts could cause unhandled 500 errors unless gracefully caught and routed to human review.

---

## 3. Edge Case Decisions & Fallback Policy

- **Empty or Whitespace Input (e.g., Sample S4)**:
  Validated strictly by Pydantic. If both subject and body text are empty or contain only whitespace, the API immediately returns `HTTP 422 Unprocessable Entity` with a clear validation error, preventing unnecessary model invocations.
- **Very Long Input (e.g., Sample S5)**:
  Text exceeding 4,000 characters is safely truncated to 4,000 characters before retrieval and prompt compilation. This protects against token bloat and memory exhaustion.
- **Out-of-Scope Questions (e.g., Sample S6)**:
  The system prompt instructs the model never to fabricate company policies. If no help article covers the request, the model returns an empty `article_ids: []` list and a standard reply indicating a human team member will follow up.
- **Prompt Injection Defense (e.g., Sample S7)**:
  Ticket content is treated as untrusted data. The model is forbidden from obeying commands or policy overrides embedded inside customer messages.
- **Model Failure or Timeout**:
  If the external model call times out, encounters network errors, or lacks credentials, the endpoint catches the exception and returns `HTTP 200` with a safe fallback response (category `Technical`, priority `normal`, reply stating a specialist will follow up, `article_ids: []`). The support agent is never blocked.

---

## 4. Testing & Verification

Run the unified test suite across both Python (26 tests) and TypeScript (4 Vitest tests):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-all.ps1
```

Or run individual test suites:
- Backend tests:
  ```bash
  pytest
  ```
- Frontend tests:
  ```bash
  cd frontend
  npm test
  ```

---

## 5. Deployment (Render.com)

1. Push your repository to GitHub.
2. In the Render Dashboard, create a **New Web Service** connected to your repository.
3. Choose **Docker** as the runtime (Render will automatically detect [Dockerfile](https://github.com/imSai-py/bitcot-technical-assignment/blob/master/Dockerfile) and [render.yaml](https://github.com/imSai-py/bitcot-technical-assignment/blob/master/render.yaml)).
4. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: Your Google Gemini API key.
   - `TICKETS_DATA_PATH`: `data/tickets_sample.csv`
5. Click **Deploy Web Service**.
6. In your local `frontend/`, configure `VITE_API_BASE_URL` to point to your live Render URL (e.g., `https://ticket-api-xyz.onrender.com`), run `npm run dev`, and send a test request. Inspect Render dashboard logs to observe the incoming request.

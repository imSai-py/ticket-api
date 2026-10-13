## Problem Statement

Support agents receive hundreds of customer requests across billing, technical issues, refunds, and account access. Currently, the team lacks an automated triage mechanism. Agents must manually inspect every ticket, search through separate help documentation, categorize the urgency, and draft replies from scratch. This process creates delays, inconsistent customer guidance, and ticket backlogs. Furthermore, the existing prototype API contains pagination errors, inaccurate average resolution calculations, startup configuration defects, and cannot connect to existing analytics logic.

## Solution

A robust, self-contained Python FastAPI service that:
1. Fixes existing API defects, providing reliable ticket retrieval, accurate pagination, and Day 1 summary metrics.
2. Provides a `POST /triage` endpoint that automatically retrieves relevant knowledge base articles, determines ticket category and priority, drafts grounded responses using a structured AI model, and handles edge cases safely without hallucinations.
3. Provides a clean TypeScript frontend application where support agents can paste customer tickets and inspect triage recommendations in real time.
4. Deploys cleanly to cloud infrastructure with strict environment variable secret isolation.

## User Stories

1. As a support agent, I want to paste an incoming customer ticket into a web interface, so that I receive an immediate triage recommendation.
2. As a support agent, I want the system to categorize tickets into one of six standard categories (Billing, Login, Shipping, Refunds, Technical, Account), so that tickets route to the correct team.
3. As a support agent, I want the system to assign an urgency level (urgent, high, normal, low), so that critical customer blockages receive immediate attention.
4. As a support agent, I want the system to draft a suggested reply grounded in verified help articles, so that I can respond accurately without writing messages from scratch.
5. As a support agent, I want to see the specific article identifiers (such as KB-001) used to construct the answer, so that I can verify policy details.
6. As a support agent, I want the system to state that a human agent will follow up when a customer asks a question outside existing documentation, so that customers do not receive fabricated policies.
7. As a support agent, I want clear visual loading states while the AI processes a ticket, so that I know the system is active.
8. As a support agent, I want clear error messages when network or service requests fail, so that I understand what went wrong.
9. As an API client, I want `GET /tickets` to start from index 0 on page 1, so that I do not miss the first ticket in the dataset.
10. As an API client, I want `GET /tickets` to support custom page and size parameters, so that I can page through tickets efficiently.
11. As an API client, I want `GET /tickets/{ticket_id}` to return 404 with a clear message when a ticket does not exist, so that missing records are handled cleanly.
12. As an operations lead, I want `GET /summary` to compute average resolution time strictly across resolved tickets, so that pending tickets do not distort operational metrics.
13. As an operations lead, I want `GET /summary` to provide per-category resolution averages and skipped ticket identifiers from the Day 1 module, so that I have complete visibility into department performance.
14. As an operations lead, I want `GET /summary` to maintain backward compatibility with existing dashboard fields (`total`, `by_category`, `average_resolution_hours`), so that existing web displays do not break.
15. As a system administrator, I want the backend service to start cleanly without crashing when environment variables are unset, using sensible local defaults.
16. As a system administrator, I want all sensitive credentials (such as API keys) loaded strictly through environment variables, so that secrets never leak into source control.
17. As an API client, I want `POST /triage` to reject empty or whitespace-only submissions with HTTP 422, so that resources are not wasted on blank requests.
18. As a security engineer, I want customer input to be safely truncated if it exceeds length limits (e.g., 4,000 characters), so that the service is protected from memory exhaustion or denial of service.
19. As a security engineer, I want the AI prompt to treat customer input as untrusted data, so that prompt injection attempts (such as instructions to ignore previous rules) cannot manipulate system policies.
20. As a support engineer, I want the system to degrade gracefully to a safe human-escalation payload when the external AI provider is unreachable or times out, so that agent workflows never freeze.
21. As a developer, I want the external model interface encapsulated behind a single swappable function, so that the underlying model provider can be changed or mocked easily.
22. As a DevOps engineer, I want a containerized deployment configuration, so that the service runs reliably on free-tier cloud platforms such as Render.

## Implementation Decisions

- **Architectural Seams and Boundaries**: The application will maintain a single HTTP boundary for all backend capability testing via FastAPI test client. Model interactions will sit behind an abstract boundary interface to allow direct substitution.
- **Data Persistence and Initialization**: The dataset path will default to `data/tickets_sample.csv` when environment variables are not supplied. Data loading will convert dates into native datetime objects with ISO-8601 UTC compliance.
- **Summary Metrics Computation**: The summary engine will incorporate Day 1 logic. Resolution durations will be computed solely for tickets with valid resolved timestamps and statuses matching `resolved` or `closed`.
- **Knowledge Retrieval Engine**: A pure-Python keyword and token-overlap matching algorithm will evaluate incoming ticket subjects and bodies against the 6 local markdown knowledge base articles. Only the highest-ranking relevant articles will be supplied to the prompt. Includes cross-lingual keyword normalization to support multilingual customer queries (such as Spanish ticket S8 in the test samples).
- **Triage Output Contract**:
  - `category`: String restricted to `Billing`, `Login`, `Shipping`, `Refunds`, `Technical`, `Account`.
  - `priority`: String restricted to `urgent`, `high`, `normal`, `low`.
  - `suggested_reply`: Non-empty grounded text.
  - `article_ids`: List of strings matching referenced articles (e.g., `["KB-001"]`).
- **Edge-Case Policies**:
  - Input with zero non-whitespace characters returns HTTP 422.
  - Input exceeding 4,000 characters is trimmed to 4,000 characters prior to retrieval and prompt construction.
  - Unhandled topics or conflicting instructions produce a canned response stating a human agent will review the issue.
  - AI timeouts or connection failures catch exceptions and return a fallback categorization marked for human review.
- **Frontend Stack**: Single-page application built with Vite, React, and TypeScript. Uses environment variable configuration for target API base URL.
- **Deployment**: Standard multi-stage container configuration suitable for Render.com free-tier deployment.
- **Workflow Automation & Verification Scripts**: Multi-platform verification runners (`scripts/verify-all.ps1`, `scripts/verify-all.sh`) enforce automated testing gates across environments.

## Testing Decisions

- **Black-Box External Verification**: Tests will exercise HTTP entrypoints and public contract interfaces (such as KBRetriever and API endpoints). Internal helper functions will not be tested in isolation.
- **Determinism and Offline Execution**: Unit test suites must run without internet access. Model calls must be intercepted at the function boundary.
- **Test Scenarios**:
  - Pagination zero-index alignment and boundary enforcement.
  - Summary metric precision against known CSV data.
  - Rejection of invalid or missing ticket IDs.
  - Empty ticket input rejection (HTTP 422).
  - Triage response schema compliance across all sample edge cases (S1 through S10).
  - Model failure and timeout fallback behavior.
  - Frontend component rendering, user submission, and error handling via Vitest.

## Out of Scope

- User authentication, login credentials, and user permissions for support agents.
- Real-time database writing or mutation of tickets on the server (dataset remains read-only sample).
- Direct automated email or SMS dispatch to customers.
- Training or fine-tuning custom machine learning models.

## Further Notes

- The 6 knowledge base articles are static markdown documents located in `kb/`.
- The sample tickets dataset contains 60 records (61 CSV rows including header) with various completion states.

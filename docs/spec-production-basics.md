# Specification: Production Basics and Resilience for Billing Ops Sync

## Daily Approach Plan

1. Analyze Day 4 Part 1 requirements and draft stakeholder update for Mara.
2. Formulate GitHub issues and technical specification for production basics slice.
3. Implement `GET /health` diagnostic endpoint checking storage, ticket data, and knowledge base.
4. Enforce strict input validation, domain enums, and centralized exception handlers for client errors.
5. Document clean-machine environment setup in README and verify full test suite.

## Problem Statement

The billing operations sync service, batch approval digest, and one-click approval workflows are functionally complete. However, running these services in production environments introduces operational risks:
1. Malformed or boundary client payloads (such as negative dollar amounts, blank customer names, or non-existent approval statuses) can trigger unexpected 500 errors or corrupt data records if not strictly validated.
2. Automated health monitoring and uptime probes have no lightweight endpoint (`GET /health`) to verify system availability, storage accessibility, and subsystem readiness.
3. New team members and automated deployment runners lack a single comprehensive, clean-machine onboarding guide in the README that works reliably from scratch.

## Solution

Harden the application by implementing production foundations:
1. Provide a comprehensive system health probe (`GET /health`) returning structured diagnostics across storage, seed data, and knowledge base subsystems.
2. Add strict schema validation (Pydantic field constraints, non-negative amounts, required non-empty customer names, valid priority enumerations) and centralized exception handlers that convert bad inputs and file conflicts into descriptive, client-friendly error responses instead of application crashes.
3. Overhaul `README.md` with foolproof, step-by-step clean-machine execution instructions, environment variable setup, verification commands, and full endpoint documentation.

## User Stories

1. As a platform monitoring agent or load balancer, I want to call `GET /health`, so that I can automatically verify if the service, file storage, and knowledge base are available.
2. As a support operations manager, I want bad or incomplete ticket sync payloads rejected with clear error explanations, so that corrupted data is never written to the tracking sheet.
3. As a support operations manager, I want one-click approval links with missing or invalid parameters to return clear guidance, so that I understand why an action failed.
4. As a new software engineer, I want clean-machine onboarding instructions in the README, so that I can clone the repository and run all services without missing dependencies or undocumented setup steps.
5. As an operations team member, I want to understand what the system does and how to run it without encountering technical jargon.

## Implementation Decisions

1. **Health Check Endpoint (`GET /health`)**:
   - Implemented as a lightweight route returning HTTP 200 with JSON payload:
     `{"status": "healthy", "version": "1.0.0", "storage": "accessible", "tickets_data": "loaded", "knowledge_base": "indexed"}`.
   - If tracking storage is inaccessible or read/write fails, returns `status: "degraded"` with HTTP 503 Service Unavailable.
2. **Schema & Input Validation**:
   - `SyncTicketRequest`:
     - Disallow negative or NaN amounts (`amount >= 0.0`).
     - Disallow blank or whitespace-only `customer_name` (must contain at least one non-whitespace character).
     - Validate `priority` against allowed enumerations (`urgent`, `high`, `normal`, `low`).
   - One-Click Approval Action (`GET /ops/approvals/{ticket_id}/action`):
     - Strip whitespace and validate `ticket_id`; return HTTP 400 if empty.
     - Validate `status` query parameter; return HTTP 400 if not `Approved` or `Rejected`.
3. **Centralized Error Handling**:
   - Add a custom exception handler for `RequestValidationError` returning readable validation messages: `{"detail": "..."}`.
   - Retain `SpreadsheetLockedError` returning HTTP 423 with clear advice.
   - Add a catch-all handler for unexpected internal exceptions returning HTTP 500 with logged incident context without leaking internal stack traces.
4. **Clean-Machine Documentation**:
   - Update `ticket-api/README.md` to provide full copy-paste terminal workflows for Python virtual environments, dependency installation, `.env` setup, dev server launch, frontend launch, test suite verification, and ops endpoint usage.
5. **Configurable Storage & Domain Enumerations**:
   - Support `OPS_TRACKING_PATH` environment variable in `get_ops_tracking_path()` to ensure configurable file storage path resolution across test and deployment environments.
   - Define `ApprovalStatusEnum` (`Pending`, `Approved`, `Rejected`) to model ticket lifecycle states without string primitive obsession.

## Testing Decisions

- Test external HTTP behavior and contract compliance, avoiding mocks where real local files can be exercised.
- Cover all edge cases: negative amounts, whitespace customer names, malformed ticket IDs, file lock errors, and healthy vs degraded health checks.
- Maintain existing 76 Python tests and 4 TypeScript tests, adding new regression tests to reach full green verification.

## Out of Scope

- Multi-tenant cloud database migration (CSV delimited storage remains the single source of truth for this iteration).
- Authentication/OAuth token validation (reserved for enterprise authorization phase).
- Dynamic SMS notification gateways.

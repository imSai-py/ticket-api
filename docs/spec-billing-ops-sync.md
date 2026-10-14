## Child Tickets (Execution Frontier)

- [x] #16 - feat: core billing sync and tracking storage slice (Blocked by: None)
- [x] #17 - feat: instant escalation alert notification slice (Blocked by: #16)
- [x] #18 - feat: consolidated batch approval digest slice (Blocked by: #16)
- [x] #19 - feat: one-click approval action and receipt slice (Blocked by: #18)

---
## Problem Statement

Support operations staff spend multiple hours every week manually copying customer and ticket information between the help desk and an internal operations tracking spreadsheet. Billing tickets cause the most delay because they require manager approvals before customer refunds or adjustments can proceed. 

Operations managers work almost entirely out of their email inbox and refuse to adopt or log into a new software tool. However, sending individual approval emails for every billing request causes severe inbox clutter and decision fatigue (approaching 100 emails per day). Furthermore, when urgent escalations occur, the team currently lacks an automated mechanism to immediately alert leadership, risking customer churn and missed service-level agreements.

## Solution

An automated operations workflow integrated into the ticket service that:
1. Automatically synchronizes billing tickets from the help desk directly into the tracking spreadsheet without human copy-pasting.
2. Extracts billing amounts when present, safely recording a verified fallback flag when amounts are omitted in customer text.
3. Consolidates all pending billing approvals into a single, scheduled batch email digest (delivered at 9:00 AM, with an on-demand manual trigger), containing a summary table, one-click action links, and an attached CSV.
4. Allows managers to approve or reject requests directly from the digest email with a single click that opens a clean, one-line receipt and requires zero login credentials.
5. Sends instant escalation alerts directly to the designated manager's personal inbox the moment an urgent ticket is identified.

## User Stories

1. As a support operations specialist, I want incoming billing tickets to automatically record in the operations tracking spreadsheet, so that I never have to manually copy-paste ticket details between two tools.
2. As a support operations specialist, I want tickets categorized as Billing during automated triage to immediately register in the tracking sheet, so that the operations backlog is always up to date.
3. As a support operations specialist, I want a direct API endpoint to submit a billing ticket to the tracking sheet, so that tickets from external help desk webhooks sync seamlessly.
4. As a support operations specialist, I want missing dollar amounts in ticket descriptions to default to $0.00 with a verification flag, so that missing text details do not crash the sync pipeline.
5. As an operations manager, I want to receive a single consolidated batch email digest of all pending billing approvals at 9:00 AM, so that my inbox is not flooded with dozens of individual emails throughout the day.
6. As an operations manager, I want the batch digest email to show customer name, ticket ID, requested amount, agent name, and reason in a clean table, so that I have all necessary context to make quick approval decisions.
7. As an operations manager, I want each ticket in the digest email to include one-click "Approve" and "Reject" links, so that I can process approvals directly from my email client without logging into a separate dashboard.
8. As an operations manager, I want clicking an approval link to display a simple, one-line confirmation receipt (e.g., "Ticket TCK-1001 marked Approved"), so that I can close the browser tab immediately without entering credentials.
9. As an operations manager, I want the digest email to include a direct link to the tracking spreadsheet, so that I can perform bulk edits when reviewing many tickets at once.
10. As an operations manager, I want the digest email to attach a CSV file containing all pending tickets, so that I can inspect the data offline or in spreadsheet software.
11. As an operations manager, I want the system to remain silent at 9:00 AM when there are zero pending billing approvals, so that I am not interrupted by empty notification emails.
12. As an operations manager, I want an immediate alert sent to my personal inbox the moment a ticket is flagged as urgent or escalated, so that critical issues receive instant executive attention regardless of the digest schedule.
13. As an operations manager, I want urgent escalation emails to clearly display the customer name, amount, reason, and urgency banner, so that I can prioritize emergency escalations over normal tasks.
14. As an operations lead, I want to trigger the batch digest email on-demand via an API endpoint, so that I can send unscheduled midday reviews or verify the workflow during demonstrations.
15. As an operations lead, I want an endpoint to view all currently pending approvals, so that I can audit outstanding requests at any time.
16. As an operations lead, I want the system to track status updates (Pending, Approved, Rejected) and timestamps in the tracking sheet, so that our team maintains a clean audit trail.
17. As an engineer, I want the manager recipient email addresses to be configurable via environment variables, so that production recipient addresses remain decoupled from source code.
18. As an engineer, I want operations tracking tests to run offline against isolated temporary fixtures, so that tests remain deterministic and fast.

## Implementation Decisions

- **Architectural Seam**: Testing will occur at the highest application boundary: the FastAPI HTTP interface (`TestClient`). No internal sub-functions will be tested in isolation when their behavior can be asserted through HTTP requests and resulting data fixtures.
- **Storage Layer**: The operational tracking spreadsheet is represented as a structured CSV data store (`data/ops_tracking_sheet.csv`). All record creation, status updates, and queries operate on this canonical source of truth with schema headers:
  `ticket_id`, `customer_name`, `category`, `priority`, `amount`, `reason`, `agent`, `status`, `escalated`, `created_at`, `updated_at`, `notes`.
- **Amount Extraction & Normalization**:
  - Regular expression and text parsing will detect currency patterns (e.g., `$XX.XX`, `XX USD`).
  - If no currency pattern is found in the ticket text, `amount` defaults to `0.00` and `notes` appends `"Needs amount verification"`.
- **Triage Pipeline Integration**:
  - The existing `POST /triage` route will be hooked: when `category == "Billing"`, the system automatically invokes the tracking sync.
  - If `priority == "urgent"`, the system immediately triggers the single-inbox escalation alert.
- **Digest Batch Dispatch Contract**:
  - Endpoint `POST /ops/approvals/send-digest` generates the digest payload.
  - When pending count is zero, the service returns `{"has_pending": false, "dispatched": false}` and suppresses outbound email.
  - When pending count > 0, formats an ASCII/Markdown summary table and attached CSV string.
- **One-Click Approval Web Action**:
  - Endpoint `GET /ops/approvals/{ticket_id}/action?status={Approved|Rejected}` acts as the destination for email hyperlinks.
  - Returns a minimal HTML response: `<html><body><h3>✓ Ticket {ticket_id} marked {status}. You may close this tab.</h3></body></html>`.
- **Escalation Notification Contract**:
  - Instant dispatch triggers strictly when `priority == "urgent"` or `escalated == true`.
  - Recipient defaults to environment variable `ESCALATION_MANAGER_EMAIL`, falling back to `manager@company.com`.

## Testing Decisions

- **Good Test Standard**: Tests must assert observable external behavior: HTTP status codes, response payloads, file contents on disk, and email payload generation. Tests will not mock internal helpers unless required to isolate network or clock side effects.
- **Modules Covered**:
  - Tracking sheet synchronization and status updating.
  - Immediate escalation alert dispatch for urgent priority versus suppression for normal priority.
  - Batch digest compilation (pending tickets, table formatting, CSV payload attachment, and empty queue suppression).
  - One-click approval link execution and HTML receipt generation.
  - End-to-end integration through `POST /triage` auto-sync.
- **Prior Art**: Follows patterns established in `tests/test_api.py` and `tests/test_triage.py` using `pytest`, `tmp_path` fixtures for file isolation, and FastAPI `TestClient`.

## Out of Scope

- Synchronization for departments other than Billing (Technical, Login, Shipping, Account) for the Friday release.
- A multi-page manager web dashboard requiring password authentication.
- Multi-tier approval workflows (e.g., requiring secondary VP approval for refunds over $1,000).
- Live third-party SMTP/SendGrid network calls during unit test runs.

## Further Notes

- Configuration settings:
  - `ESCALATION_MANAGER_EMAIL`: Target address for urgent alerts.
  - `DIGEST_MANAGER_EMAIL`: Target address for daily batch digests.
  - `BASE_URL`: Base URL used to construct one-click approval links in email bodies (defaults to `http://localhost:8000`).
- The tracking CSV file will be initialized automatically if it does not already exist.


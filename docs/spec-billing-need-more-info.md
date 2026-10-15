# Specification: Billing Escalation Workflow with "Need More Info" & Refund Verification

## Child Tickets (Execution Frontier)

- [ ] #48 - feat: expand approval status enum and tracking state to support `needs_info` (Blocked by: None)
- [ ] #49 - feat: add "Need More Info" button to digest emails and action receipt endpoint (Blocked by: #48)
- [ ] #50 - feat: implement agent notification dispatch on "Need More Info" status change (Blocked by: #49)
- [ ] #51 - feat: support ticket re-submission and refund legitimacy verification details (Blocked by: #50)
- [ ] #52 - feat: update scheduler for dual daily digests at 9:00 AM and 3:00 PM (Blocked by: #49)

---

## Problem Statement

During our operational prototype walkthrough with Mara, she identified critical gaps in the refund escalation workflow:
1. **Binary Decision Deadlock**: Currently, managers only have "Approve" and "Reject" options. When a billing ticket lacks sufficient context (e.g. proof of double-billing, cancellation history, or transaction IDs), managers are forced to reject legitimate customer requests outright or approve unverified payouts.
2. **Financial Risk on Unverified Refunds**: Customer refund transfers carry real financial liability. Disbursing company funds requires verifying legitimacy (valid reason, customer transaction details, and agent verification notes). Without a structured way to pause payout and ask for more information, the business faces financial loss or customer dissatisfaction.
3. **Billing Operational Bottleneck**: Billing escalations are the single biggest point of friction for Mara's support team. Support agents need a closed-loop mechanism where manager requests for additional information trigger an immediate notification back to the assigned agent, allowing them to collect more details and re-submit the ticket for final manager approval.
4. **Digest Cadence Alignment**: The previous schedule only fired at 9:00 AM. Mara requires an afternoon digest at 3:00 PM so morning requests do not wait overnight for approval.

---

## Solution

A closed-loop billing escalation and verification lifecycle that adds a third manager decision option:
1. **Three-Way Manager Action**: Digest emails and alerts provide three distinct, one-click options: **Approve**, **Reject**, and **Need More Info**.
2. **`needs_info` State Transition**: Clicking "Need More Info" transitions the ticket from `pending` to `needs_info` in `data/ops_tracking_sheet.csv`, recording an audit timestamp and prompt note.
3. **Agent Notification Loop**: When a manager selects "Need More Info", the system dispatches an automatic notification to the support agent (via `assigned_to` / `customer_email`), informing them that additional verification or customer details are required.
4. **Re-submission Flow**: Support agents can supplement the ticket with additional context or evidence via `POST /ops/sync-ticket`, moving the ticket back to `pending` status for the next digest.
5. **Refund Legitimacy Capture**: Enforce capturing clear operational justification and refund amounts, ensuring tickets with zero or missing amounts require explicit verification notes.
6. **Twice-Daily Digest Cadence**: Update the automated schedule to trigger batch approval digests at both **9:00 AM** and **3:00 PM**.

---

## User Stories

1. As an operations manager, I want to see three distinct action options ("Approve", "Reject", and "Need More Info") in my approval emails, so that I am not forced to reject customer refunds when simple details are missing.
2. As an operations manager, I want clicking "Need More Info" to display a clean, one-line confirmation receipt (e.g. *"Ticket TCK-1001 marked as needing more info. Support agent notified."*), so that I can process requests with a single click without logging into a dashboard.
3. As an operations manager, I want tickets marked as "Need More Info" to be excluded from pending approval counts, so that my digest only highlights actionable requests.
4. As an operations manager, I want to receive digest emails twice a day—at 9:00 AM and 3:00 PM—so that urgent billing queries submitted during the morning are reviewed before end of day.
5. As an operations manager, I want the system to require a clear operational refund reason (e.g., double charge, canceled plan), so that financial payouts are verified as legitimate before transfer.
6. As a support agent, I want an automatic email notification when a manager flags my ticket for "Need More Info", so that I know exactly which customer needs follow-up without checking a spreadsheet.
7. As a support agent, I want the notification to specify the ticket ID, customer name, refund amount, and instructions to gather further context, so that I can resolve the inquiry efficiently.
8. As a support agent, I want to re-submit an updated ticket with supplemental context through the web UI or API, so that it seamlessly returns to the manager's pending queue for the next 9:00 AM or 3:00 PM digest.
9. As a support agent, I want the tracking spreadsheet to record an audit trail of previous manager notes and re-submission comments, so that history is preserved across multiple back-and-forth reviews.
10. As a support team lead, I want to query `GET /ops/approvals/pending` and see distinct counts for `pending` vs `needs_info`, so that I can monitor agent follow-up bottlenecks.
11. As a finance officer, I want all approved refunds to retain the verified operational reason and agent sign-off in the tracking CSV, so that accounting audits pass compliance checks.
12. As a platform monitoring service, I want `GET /health` to verify tracking store access and digest scheduling readiness, ensuring high uptime for billing approvals.

---

## Implementation Decisions

- **Architectural Seam**:
  - The feature will be tested at the highest application boundary: the FastAPI HTTP interface (`TestClient`).
  - No internal helper functions will be tested in isolation when their behavior can be asserted through HTTP requests and resulting tracking fixtures.
- **State Machine Extension in `app/tracking_sync.py` & `app/schemas.py`**:
  - `ApprovalStatus` enum expanded from `("pending", "approved", "rejected")` to include `"needs_info"`.
  - State transitions:
    - `pending` -> `approved` (Terminal)
    - `pending` -> `rejected` (Terminal)
    - `pending` -> `needs_info` (Actionable by Agent)
    - `needs_info` -> `pending` (Upon Agent Re-submission with updated context)
- **Email Action Links & Minimal HTML Contract**:
  - In `app/batch_digest.py` and `app/escalation.py`, render three styled buttons:
    - `Approve`: Green (`#28a745`)
    - `Reject`: Red (`#dc3545`)
    - `Need More Info`: Amber/Blue (`#ffc107` or `#17a2b8`)
  - Link format: `/ops/approvals/action?ticket_id={id}&status=needs_info`
- **Agent Notification Dispatch**:
  - In `app/escalation.py`, add `send_agent_info_request_email(ticket_id, customer_name, amount, reason, agent_email)`.
  - When status changes to `needs_info`, dispatch notification immediately to the assigned agent.
- **Digest Scheduler Cadence**:
  - Update `app/scheduler.py` to trigger digests at both **09:00** and **15:00** (3:00 PM).
- **Audit Log & History in CSV**:
  - Append audit notes in the existing `notes` column: e.g. `Manager requested more info at 2026-10-15 15:30:00; Agent updated invoice #1024 at 2026-10-15 16:15:00`.
  - Flat-file safety: All notes must continue passing through `sanitize_cell()` to prevent CSV row splitting.

---

## Testing Decisions

- **High-Seam Verification**:
  - Use `fastapi.testclient.TestClient` exclusively for all new test cases.
  - Assert HTTP responses, status codes, and the resulting single-line rows in `data/ops_tracking_sheet.csv`.
- **Key Scenarios to Test**:
  1. *Action Endpoint*: `GET /ops/approvals/action?ticket_id=...&status=needs_info` returns `200 OK`, outputs a friendly HTML receipt, updates tracking status to `needs_info`, and updates `updated_at`.
  2. *Digest Rendering*: `send_batch_digest()` contains all three action URLs (`approved`, `rejected`, `needs_info`).
  3. *Agent Notification*: Executing `needs_info` triggers outbound email dispatch to the assigned agent.
  4. *Re-submission*: Calling `POST /ops/sync-ticket` for a ticket currently in `needs_info` resets status back to `pending` and preserves audit history in `notes`.
  5. *Dual Schedule*: `scheduler.should_trigger_digest()` returns `True` at 09:00 and 15:00, and `False` at other hours.
  6. *Offline Determinism*: Mock all outbound SMTP/email calls so test suite runs in under 15 seconds without external dependencies.

---

## Out of Scope

- Non-billing ticket category automation (shipping, technical, login) — scheduled for next week.
- Replacing the flat-file CSV storage with Google Sheets or SQL database (decided in meeting to keep current Excel file-locking behavior).
- Live interactive agent chat/commenting system (email notifications and CSV notes suffice).

---

## Further Notes

- Mara explicitly called the core tool "amazing" and wants this billing slice hardened and deployed.
- Once the user verifies this plan and the testing seams, execution will proceed slice by slice with full test verification.

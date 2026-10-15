# Specification: Helpdesk Export Schema Adaptation and Ingestion Resilience

## Problem Statement

The upstream IT team has altered how the helpdesk export is produced and delivered:
1. **Delivery Process Change**: Exports are no longer accessed via automated live database queries; IT now dispatches a daily CSV export via email each morning.
2. **Column Renaming**:
   - The column previously named `tags` is now named `labels`.
   - The column previously named `requester_email` is now named `customer_email`.
3. **Schema Variations**:
   - The incoming export file (`helpdesk_export_new_format.csv`) introduces new operational fields (`assigned_to`, `refund_amount`) but omits historical fields such as `resolved_at`.
   - The current application ingestion pipeline in `app/main.py` strictly accesses `row["resolved_at"]`, which immediately triggers unhandled `KeyError` exceptions when pointed to the new helpdesk export file.
   - Ticket summary metrics in `ticket_summary.py` require defensive handling when `resolved_at` timestamps are missing on unresolved tickets.
   - Operations synchronization logic in `app/tracking_sync.py` and `app/schemas.py` must reliably detect escalations from the new `labels` column and map `customer_email` and `refund_amount` correctly.

## Solution

Harden the application to ingest and process the client's daily helpdesk export format reliably:
1. Implement a schema-agnostic, backward-compatible ticket normalization layer that supports both the new export format (`labels`, `customer_email`, `assigned_to`, `refund_amount`) and the legacy format (`tags`, `requester_email`, `resolved_at`).
2. Preserve the default date formatting exactly as supplied in the incoming export file (`%Y-%m-%d %H:%M`) without destructive format conversions.
3. Provide robust dictionary extraction in `load_tickets()` and `to_public_ticket_dict()` so that optional columns (`resolved_at`, `refund_amount`, `labels`) never cause runtime key errors.
4. Update ticket analytics in `ticket_summary.py` to seamlessly aggregate volume and category breakdowns even when tickets lack resolution timestamps.
5. Ensure operational synchronization (`app/tracking_sync.py`) parses semicolon-delimited `labels` for escalation triggers (`escalated`, `esc`, `Escalated;vip`) and automatically captures `customer_email` and `refund_amount`.

## User Stories

1. As a support operations manager, I want the system to load the new helpdesk export file delivered each morning by IT, so that our operational triage and analytics reflect current ticket activity.
2. As a support operations manager, I want the system to preserve the default date format from the export file, so that audit timestamps remain consistent with upstream IT records.
3. As an operations team member, I want tickets with the renamed `labels` column to be recognized accurately, so that ticket categories and tags are not lost during ingestion.
4. As an operations team member, I want tickets with `escalated` or `esc` inside the `labels` column to trigger our escalation alerts, so that urgent customer issues receive immediate attention.
5. As an operations team member, I want customer contact information from the renamed `customer_email` column to be correctly ingested, so that support agents can reach out to customers without manual copy-pasting.
6. As a support agent, I want tickets containing a `refund_amount` in the new export to automatically populate the refund amount in the operations tracking sheet, so that manual data entry is eliminated.
7. As a platform monitoring service, I want calling `GET /health` to verify the accessibility of the helpdesk export data without failing on schema changes, so that service uptime is accurately reported.
8. As a backend API consumer, I want calling `GET /tickets` to return public ticket information without encountering a 500 error when `resolved_at` is omitted, so that frontend dashboards display ticket lists reliably.
9. As a backend API consumer, I want calling `GET /tickets/{ticket_id}` to retrieve individual ticket details from the new export format, so that agents can inspect specific tickets by ID.
10. As a business analyst, I want calling `GET /summary` to compute ticket counts and category distributions from the new export file without crashing on missing resolution dates, so that daily ticket volume metrics are always available.
11. As a DevOps engineer, I want the ability to configure the helpdesk export file location using the `TICKETS_DATA_PATH` environment variable, so that daily email exports can be mounted or updated without code deployments.
12. As a software developer, I want the ingestion parser to remain backward-compatible with legacy sample files containing `tags` and `requester_email`, so that existing test suites and historical archives do not break.

## Implementation Decisions

1. **Ticket Ingestion Normalization Layer**:
   - Modify `load_tickets(path)` in `app/main.py` to safely extract fields using dictionary fallbacks:
     - `labels`: reads `row.get("labels")` with fallback to `row.get("tags", "")`.
     - `customer_email`: reads `row.get("customer_email")` with fallback to `row.get("requester_email", "")`.
     - `resolved_at`: reads `row.get("resolved_at")`; if absent or empty, parses to `None` without raising `KeyError`.
     - `created_at`: preserves the default incoming timestamp string directly (`row.get("created_at", "")`).
     - `refund_amount`: safely parses numeric string if present (`float(val)` if `val` else `0.0`).
     - `assigned_to`: reads `row.get("assigned_to", "")`.
2. **Date Representation Preservation**:
   - Retain the incoming date format (`%Y-%m-%d %H:%M`) as the canonical string representation.
   - Avoid converting timestamps to alternative formats, honoring the client's default format specification.
3. **Public Ticket Representation (`to_public_ticket_dict`)**:
   - Update `to_public_ticket_dict(ticket)` to safely extract `ticket_id`, `created_at`, `category`, `priority`, `status`, and optionally `resolved_at`, `customer_email`, `labels`, and `refund_amount` if present.
4. **Summary and Metric Calculation Resilience**:
   - Ensure `compute_metrics(TICKETS)` in `ticket_summary.py` counts all tickets toward category totals and overall volume even when `resolved_at` is `None`.
   - Skip resolution duration calculation only for records that lack a resolved timestamp, adding them to tracked skipped tickets without failing the request.
5. **Operational Sync & Escalation Detection**:
   - Extend `app/tracking_sync.py` to parse `labels` (and legacy `tags`) using case-insensitive tokenization for `escalated` and `esc`.
   - Map `customer_email` directly to customer contact fields in ticket records.
   - Pre-populate monetary amounts from `refund_amount` if provided in the export.
6. **Data Source Configuration**:
   - Maintain `TICKETS_DATA_PATH` environment variable support with default path pointing to `data/helpdesk_export.csv` or `data/tickets_sample.csv`.
7. **Sam's PR Deferred**:
   - Review and modification of Sam's prototype PR (`feature/escalation-export`) are explicitly held and deferred to a later iteration per user instructions.

## Testing Decisions

- A good test verifies external observable HTTP behavior and data contracts rather than internal implementation details.
- **Ingestion & Metric Tests**:
  - Verify `load_tickets()` successfully loads all 120 rows from `helpdesk_export_new_format.csv` without errors.
  - Verify `GET /tickets` returns HTTP 200 with 10 records and handles pagination cleanly.
  - Verify `GET /tickets/{ticket_id}` returns specific tickets (e.g. `TCK-5007`, `TCK-5039`).
  - Verify `GET /summary` returns accurate category counts across all 120 tickets.
  - Verify backward compatibility by testing against legacy `tickets_sample.csv`.
- **Operational Sync Tests**:
  - Verify tickets with `labels: "escalated"` or `labels: "Escalated;vip"` are flagged as escalated.
  - Verify `customer_email` and `refund_amount` are persisted into tracking records.
- Prior art: existing tests in `tests/test_api.py` and `tests/test_tracking_sync.py`.

## Out of Scope

- Reviewing, refactoring, or integrating Sam's proposed PR (`feature/escalation-export`).
- Direct SMTP/IMAP mailbox polling or email attachment extraction.
- Automatic database migrations (the service continues using flat CSV storage).

## Further Notes

- The sample export `helpdesk_export_new_format.csv` contains 120 tickets, 34 escalated tickets, and $7,283.00 in escalated refund values.
- All 88 existing backend tests and 4 frontend tests must continue to pass cleanly.

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
4. **Lead Feedback & Client Specifics**:
   - **Date Format Requirement**: Dates must be formatted as `DD/MM/YYYY` (Day/Month/Year) in client-facing representations, converting incoming timestamps into the standard readable `DD/MM/YYYY` format.
   - **Priority Precedence (`escalated` vs `vip`)**: In the `labels` column, `escalated` (or `esc`) represents critical customer issues/refund disputes and must be assigned highest priority (`urgent`), taking precedence over `vip` (which maps to `high` priority).
   - **Refund Currency**: Numeric values in `refund_amount` without currency indicators must default strictly to US Dollars (USD / `$`).
   - **5:00 PM Client Demo on Render**: The final demonstration to the client at 5:00 PM will be hosted on Render (not localhost), requiring full verification, local testing, and GitHub synchronization before deployment. (Deployment execution is explicitly held until user approval).

## Solution

Harden the application to ingest and process the client's daily helpdesk export format reliably:
1. Implement a schema-agnostic, backward-compatible ticket normalization layer that supports both the new export format (`labels`, `customer_email`, `assigned_to`, `refund_amount`) and the legacy format (`tags`, `requester_email`, `resolved_at`).
2. Provide standard `DD/MM/YYYY` date formatting across public ticket representations, converting incoming ISO/space timestamps into readable Day/Month/Year formats.
3. Establish clear priority hierarchy in `app/tracking_sync.py`: tickets with `escalated` / `esc` in `labels` map to `urgent` priority and set `escalated=True`; tickets with `vip` map to `high` priority unless also escalated.
4. Normalize `refund_amount` entries to standard USD currency values (defaulting to `$0.00` if absent).
5. Provide robust dictionary extraction in `load_tickets()` and `to_public_ticket_dict()` so that optional columns (`resolved_at`, `refund_amount`, `labels`) never cause runtime key errors.
6. Update ticket analytics in `ticket_summary.py` to seamlessly aggregate volume and category breakdowns even when tickets lack resolution timestamps.
7. Prepare the project for seamless Render cloud deployment for the 5:00 PM client demonstration, maintaining deployment steps on hold until explicitly authorized by the user.

## User Stories

1. As a support operations manager, I want the system to load the new helpdesk export file delivered each morning by IT, so that our operational triage and analytics reflect current ticket activity.
2. As a client or stakeholder, I want dates displayed in `DD/MM/YYYY` format, so that ticket timestamps are easily readable and match our local business convention.
3. As an operations team member, I want tickets with `escalated` or `esc` labels to receive top `urgent` priority, so that critical disputes and dissatisfied customers are addressed first.
4. As an operations team member, I want tickets labeled `vip` to receive `high` priority, so that high-value customers receive expedited service while allowing critical escalations to take precedence.
5. As an operations manager, I want unlabeled numeric refund amounts in the export to be treated as US Dollars (USD), so that financial records and adjustments have unambiguous currency values.
6. As an operations team member, I want customer contact information from the renamed `customer_email` column to be correctly ingested, so that support agents can reach out to customers without manual copy-pasting.
7. As a support agent, I want tickets containing a `refund_amount` in the new export to automatically populate the refund amount in the operations tracking sheet, so that manual data entry is eliminated.
8. As a platform monitoring service, I want calling `GET /health` to verify the accessibility of the helpdesk export data without failing on schema changes, so that service uptime is accurately reported.
9. As a backend API consumer, I want calling `GET /tickets` to return public ticket information without encountering a 500 error when `resolved_at` is omitted, so that frontend dashboards display ticket lists reliably.
10. As a backend API consumer, I want calling `GET /tickets/{ticket_id}` to retrieve individual ticket details from the new export format, so that agents can inspect specific tickets by ID.
11. As a business analyst, I want calling `GET /summary` to compute ticket counts and category distributions from the new export file without crashing on missing resolution dates, so that daily ticket volume metrics are always available.
12. As a DevOps engineer, I want the ability to configure the helpdesk export file location using the `TICKETS_DATA_PATH` environment variable, so that daily email exports can be mounted or updated without code deployments.
13. As a software developer, I want the ingestion parser to remain backward-compatible with legacy sample files containing `tags` and `requester_email`, so that existing test suites and historical archives do not break.
14. As an engineering lead, I want all changes verified locally and deployed to Render for the 5:00 PM client demonstration only after explicit user confirmation, ensuring a stable presentation.

## Implementation Decisions

1. **Ticket Ingestion Normalization Layer**:
   - Modify `load_tickets(path)` in `app/main.py` to safely extract fields using dictionary fallbacks:
     - `labels`: reads `row.get("labels")` with fallback to `row.get("tags", "")`.
     - `customer_email`: reads `row.get("customer_email")` with fallback to `row.get("requester_email", "")`.
     - `resolved_at`: reads `row.get("resolved_at")`; if absent or empty, parses to `None` without raising `KeyError`.
     - `created_at`: reads `row.get("created_at", "")`.
     - `refund_amount`: safely parses numeric string if present (`float(val)` if `val` else `0.0`), defaulting currency to USD ($).
     - `assigned_to`: reads `row.get("assigned_to", "")`.
2. **Date Format Normalization (`DD/MM/YYYY`)**:
   - Provide helper `format_display_date(timestamp_str)` converting ISO/space dates (`%Y-%m-%d %H:%M` or ISO-8601) into standard `DD/MM/YYYY` representation (e.g. `05/10/2026`).
   - Retain parsed ISO timestamps internally for sorting and metrics while presenting `DD/MM/YYYY` in public client representations.
3. **Priority Precedence Rules (`escalated` > `vip`)**:
   - When synchronizing tickets or evaluating priority from `labels`:
     - If `labels` contains `escalated` or `esc` (case-insensitive): `priority = "urgent"`, `escalated = True`.
     - Else if `labels` contains `vip` (case-insensitive): `priority = "high"`, `escalated = False`.
     - Else retain ticket's assigned priority (`normal`, `low`, etc.).
4. **Currency Defaulting**:
   - Default all numeric refund amounts to USD ($). Format outputs with two decimal places (e.g. `$100.00` or float `100.00` USD).
5. **Public Ticket Representation (`to_public_ticket_dict`)**:
   - Update `to_public_ticket_dict(ticket)` to safely extract `ticket_id`, formatted `created_at` (`DD/MM/YYYY`), `category`, `priority`, `status`, and optionally `resolved_at`, `customer_email`, `labels`, and `refund_amount` without `KeyError`.
6. **Summary and Metric Calculation Resilience**:
   - Ensure `compute_metrics(TICKETS)` in `ticket_summary.py` counts all tickets toward category totals and overall volume even when `resolved_at` is `None`.
   - Skip resolution duration calculation only for records that lack a resolved timestamp, adding them to tracked skipped tickets without failing the request.
7. **Operational Sync & Escalation Detection**:
   - Extend `app/tracking_sync.py` to parse `labels` (and legacy `tags`) implementing the `escalated` > `vip` priority hierarchy.
   - Map `customer_email` directly to customer contact fields in ticket records.
   - Pre-populate monetary amounts from `refund_amount` in USD.
8. **Data Source Configuration**:
   - Maintain `TICKETS_DATA_PATH` environment variable support with default path pointing to `data/helpdesk_export.csv` or `data/tickets_sample.csv`.
9. **5:00 PM Render Demo Deployment (HELD)**:
   - Configuration files (`Dockerfile`, `render.yaml`) are prepared for Render deployment.
   - Pushing to GitHub production branch (`master`) and triggering live Render deployment will **NOT** execute automatically; this step is strictly held until explicit confirmation by the user following complete verification.
10. **Sam's PR Deferred**:
    - Review and modification of Sam's prototype PR (`feature/escalation-export`) remain held and deferred per user instructions.

## Testing Decisions

- A good test verifies external observable HTTP behavior and data contracts rather than internal implementation details.
- **Ingestion & Metric Tests**:
  - Verify `load_tickets()` successfully loads all 120 rows from `helpdesk_export_new_format.csv` without errors.
  - Verify `created_at` renders in `DD/MM/YYYY` format in ticket endpoints.
  - Verify `GET /tickets` returns HTTP 200 with 10 records and handles pagination cleanly.
  - Verify `GET /tickets/{ticket_id}` returns specific tickets (e.g. `TCK-5007`, `TCK-5039`).
  - Verify `GET /summary` returns accurate category counts across all 120 tickets.
  - Verify backward compatibility by testing against legacy `tickets_sample.csv`.
- **Priority & Currency Sync Tests**:
  - Verify ticket labeled `escalated` is assigned `urgent` priority and `escalated=True`.
  - Verify ticket labeled `vip` is assigned `high` priority.
  - Verify compound label `Escalated;vip` gives precedence to `urgent` escalation.
  - Verify raw refund amounts (e.g. `480`) are ingested as `$480.00` USD.
- Prior art: existing tests in `tests/test_api.py`, `tests/test_tracking_sync.py`, and `tests/test_escalation.py`.

## Out of Scope

- Automatic trigger of Render cloud deployment (held until user explicitly commands).
- Reviewing, refactoring, or integrating Sam's proposed PR (`feature/escalation-export`).
- Direct SMTP/IMAP mailbox polling or email attachment extraction.
- Database migrations (the service continues using flat CSV storage).

## Further Notes

- The sample export `helpdesk_export_new_format.csv` contains 120 tickets, 34 escalated tickets, and $7,283.00 in escalated refund values.
- All 88 existing backend tests and 4 frontend tests must continue to pass cleanly.

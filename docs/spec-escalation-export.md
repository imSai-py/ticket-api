# Specification: Escalated Tickets CSV Export for Finance

## Daily Approach Plan

1. Analyze new helpdesk export schema and compare with Sam's proposed escalation export PR.
2. Formulate GitHub issues (#29–#33) and technical specification document.
3. Implement core CSV export engine (`app/export.py`) supporting `labels`, `customer_email`, and inclusive dates.
4. Add `GET /escalations/export` endpoint with streaming CSV download and date range validation.
5. Update frontend URL builder, integrate export trigger button, and write constructive code review for Sam.

## Problem Statement

Finance requires a weekly CSV export of escalated tickets within an adjustable date range to audit refunds, disputed charges, and service credits before Friday.

Upstream IT modified the helpdesk export workflow:
1. **Delivery Channel**: Automated daily email dispatch instead of live database connectivity.
2. **Column Renames**:
   - `tags` is renamed to `labels`.
   - `requester_email` is renamed to `customer_email`.

An initial implementation proposed by Sam (`feature/escalation-export`) contains critical defects:
- **Schema Breakage**: Sam's code relies on `x.get("tags")`, returning empty strings against the new export format and missing all escalated tickets.
- **Missing Subject Field**: Sam outputs `x.get("subject", "")` into CSV columns, but `helpdesk_export_new_format.csv` contains no `subject` column.
- **Date Boundary Cutoff**: Using strict inequality `s <= d < e` drops all tickets created on the end date `e`.
- **Corrupted Tabular Structure**: Writing footer summary rows (`w.writerow(["total tickets", n])`) into the data table breaks standard automated ingestion in pandas and spreadsheet tools.
- **Missing API Endpoint**: The frontend helper calls `/escalations/export`, but no such endpoint exists in the FastAPI application.
- **Code Smells**: Every variable is a cryptic single-letter abbreviation (`exp`, `t`, `s`, `e`, `o`, `w`, `n`, `tot`, `cats`), lacking types, error handling, and tests.

## Data Analysis (`helpdesk_export_new_format.csv`)

A thorough automated analysis of the client's new CSV format yields:
- **Total Records**: 120 tickets spanning `2026-10-05 13:05` to `2026-10-12 06:16`.
- **Fieldnames**: `ticket_id`, `created_at`, `status`, `priority`, `category`, `assigned_to`, `customer_email`, `labels`, `refund_amount`.
- **Categories**: Billing (33), Technical (26), Shipping (20), Refunds (17), Login (17), Account (7).
- **Priorities**: normal (60), high (31), low (15), urgent (14).
- **Statuses**: in_progress (42), open (37), resolved (32), closed (9).
- **Escalation Labels**:
  - Raw label values: `escalated` (6), `esc` (7), `ESCALATED` (8), `Escalated` (7), `Escalated;vip` (4), `escalated;team-account` (1), `esc;vip` (1).
  - Total escalated tickets: **34 tickets** matching `escalated` or `esc` case-insensitively.
- **Refund Amounts**:
  - Total rows with refund amount: 34.
  - Total empty refund values: 86.
  - Total refund sum across all 120 tickets: **$8,936.00**.
  - Escalated tickets with refund amount: **20 tickets**.
  - Total refund sum among escalated tickets: **$7,283.00**.

## Solution Architecture & Implementation Decisions

1. **Robust Core Export Module (`app/export.py`)**:
   - Provide `export_escalated_tickets_csv(tickets, start_date, end_date) -> str`.
   - Support both `labels` (new format) and `tags` (legacy format) seamlessly.
   - Match `escalated` and `esc` case-insensitively, splitting semicolon-separated labels.
   - Standardize date filtering: parse ISO/space dates (`%Y-%m-%d %H:%M`) and compare inclusively `start_date <= ticket_dt <= end_date_eod` (23:59:59.999999).
   - Format output strictly to RFC 4180 CSV standard with columns:
     `ticket_id,created_at,category,priority,status,customer_email,labels,refund_amount`.
   - Replace cryptic single-letter names with explicit domain types and descriptive identifiers.
2. **FastAPI Endpoint (`GET /escalations/export`)**:
   - Add endpoint in `app/main.py` accepting query parameters `start` and `end` (in `YYYY-MM-DD` format).
   - Resolve helpdesk export dataset dynamically via `HELPDESK_EXPORT_PATH` environment variable with fallback to `../day4-materials/helpdesk_export_new_format.csv` or `data/helpdesk_export.csv`.
   - Return HTTP response with `media_type="text/csv"` and `Content-Disposition: attachment; filename="escalated_tickets_<start>_<end>.csv"`.
3. **Frontend Helper & Dashboard Integration (`frontend/src/`)**:
   - Refactor `frontend/src/exportButton.ts` into a clean, typed helper `getExportUrl(startDate, endDate)`.
   - Prevent UTC timezone offset shifts when extracting `YYYY-MM-DD`.
   - Integrate date range pickers and an "Export Escalations CSV" button in `frontend/src/App.tsx`.
4. **Constructive Peer Review (`docs/review-sam-export.md`)**:
   - Follow `day4-materials/review_template.md` to review Sam's PR empathetically and thoroughly.
   - Decision: Request Changes.
   - Detail findings across schema mismatch, date boundary clipping, tabular data integrity, missing endpoint, and naming conventions.

## Testing Decisions

- Unit tests in `tests/test_export.py` verifying:
  - Exact 34 escalated tickets extracted from `helpdesk_export_new_format.csv`.
  - Date filtering inclusivity across start and end dates.
  - Multi-label parsing (`Escalated;vip`, `esc;vip`).
  - Graceful handling of empty records, missing refund amounts, and legacy `tags`/`requester_email` fields.
- Integration tests in `tests/test_export_endpoint.py` verifying:
  - `GET /escalations/export` HTTP 200, headers, and CSV content.
  - HTTP 422 on invalid date strings.
- Frontend tests in `frontend/src/exportButton.test.ts` verifying URL generation and local date parsing.

## Out of Scope

- Direct SMTP inbox polling / IMAP email scraping (client exports are delivered as CSV files).
- Multi-currency conversion (USD assumed for all refund amounts).

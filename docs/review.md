# Review of "Add CSV export of escalated tickets"

## Summary

Thanks for jumping on this so quickly, Sam. Finance really needs this for Friday, and getting the frontend helper and test file set up right away gives us a solid head start. That said, I'm requesting changes because the export currently misses tickets from the new helpdesk format, drops tickets created on the end date, and appends summary lines that will break Finance's automated imports.

Decision: **Request changes**

## What is good

- **Fast turnaround:** Really appreciate you picking this up quickly so Finance has what they need for Friday.
- **Clean separation:** Splitting the Python export logic from the frontend URL helper keeps both sides neat and focused.
- **Added tests:** Great call adding a test file right away rather than leaving it for later.

## Comments

| File and line | What I noticed | Why it matters | Suggestion | Must fix, should fix or nit |
| --- | --- | --- | --- | --- |
| `app/export.py:17` | The code checks `x.get("tags")`, but the incoming helpdesk CSV now names this column `labels`. | Tickets in the new format will not match, so the export comes out completely empty. | Look for `labels` first, then fall back to `tags`: `x.get("labels") or x.get("tags", "")`. Also split by commas as well as semicolons. | Must fix |
| `app/export.py:16` | The date filter uses `s <= d < e`. | If someone picks Friday as the end date, `e` defaults to `00:00`, leaving out every ticket created on Friday. | Make the end boundary inclusive through the end of the day (`23:59:59`), or check `s <= d <= e`. | Must fix |
| `app/export.py:20` | `float(x["refund_amount"])` runs directly on the raw string. | If an amount has a dollar sign like `"$250"` or a comma like `"1,000"`, Python throws a `ValueError` and crashes the export. | Strip out currency symbols and commas before converting, and fall back to `0.0` if empty. | Must fix |
| `app/export.py:29` | Text fields like `subject` are written straight to CSV without cleaning. | If a subject contains a line break or tab, it splits across multiple lines and breaks the CSV row layout. | Wrap text values with our `sanitize_cell()` helper before writing them. | Must fix |
| `app/export.py:31–35` | Summary totals and category counts are written at the bottom with 2 columns instead of 7. | Finance usually loads this file into automated tools or spreadsheets. Inconsistent column counts break their import scripts. | Keep the CSV rows uniform. If Finance needs totals, we can provide them through a separate summary file or endpoint. | Must fix |
| `app/export.py:6` | The function and its arguments use single letters: `def exp(t, s, e):`. | It is hard to tell at a glance what each argument expects, especially without type hints. | Rename to something clear like `export_escalated_tickets(tickets, start_date, end_date)` and add type annotations. | Should fix |
| `frontend/src/exportButton.ts:2–3` | Dates are sliced from `toISOString()`. | Converting to UTC can shift the date by a day for teammates working in other time zones. | Format the date using local date methods (`getFullYear`, `getMonth`, `getDate`). | Should fix |
| `tests/test_export.py:14–16` | There is only one test, and it just checks if `"TCK-1"` appears anywhere in the output text. | It misses edge cases like empty date ranges, missing refund amounts, or tickets with `esc` instead of `escalated`. | Add a few more tests for date boundaries, empty lists, and the new `labels` format. | Should fix |

## Questions for the author

1. How does Finance plan to ingest the CSV? If they use automated software, they will need a strict rectangular format. If they just open it manually in Excel, we have slightly more flexibility.
2. For the date filter, do you want Friday exports to include tickets created throughout the day on Friday (up to 23:59)?
3. Are you planning to add the FastAPI route (`/escalations/export`) in this PR, or in a follow-up?

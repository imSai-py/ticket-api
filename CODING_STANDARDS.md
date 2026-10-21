# Coding Standards & Pull Request Guidelines

## 1. Code Integrity & Hygiene
- **Docstrings and Types:** Preserve existing docstrings, type annotations, and comments unless explicitly instructed otherwise.
- **Code Style:**
  - Python: Enforce with `pytest`, `ruff`, and `black`.
  - TypeScript: Enforce with `vitest`, `tsc`, and `vite build`.

## 2. Flat-File & Delimited Storage Standards
- **Record Sanitization:** All text fields written to CSV or delimited storage must pass through `sanitize_cell()` to strip raw newlines (`\r`, `\n`) and tab characters (`\t`), guaranteeing single-line record integrity.
- **Currency Normalization:** Currency values with symbols or commas (e.g. `$1,250.00`) must be normalized to standard float representations before storage.
- **File Lock Contention:** File operations on tabular files must handle lock contention (e.g., `PermissionError` / `SpreadsheetLockedError`) gracefully with user-friendly remediation messages.
- **Enum Representation:** Always serialize enum attributes using `.value` (never `Enum.name`).

## 3. Pull Request (PR) Lifecycle & Timing
- **PR Timing Policy:**
  - Slices/tickets are implemented, verified, and committed sequentially on the integration/feature branch.
  - Open a Pull Request only when all tickets in the specification are fully implemented and verified, or when explicitly requested by the user.
- **PR Structure Template:**
  Every pull request body must strictly contain only the seven approved template sections below. Do not include third-party bot annotations or external summary blocks:

```markdown
## Summary

<Visual diagram, call tree, diff-sketch, or shallow file tree>

## Verified end to end

- <Concrete end-to-end verification workflows, execution scenarios, edge-case validations>

## Verification

- `<command>` — passed (<evidence / test counts>)

## Engineering practices applied

- <Key design principles, typed boundaries, isolated state, synthetic fixtures, standard library constraints>

## Review

- **Standards:** <StandardsReview findings and conventions adherence>
- **Spec:** <SpecReview findings and functional requirements coverage>

## Follow-ups

- <Upcoming tickets, follow-up items, or out-of-scope enhancements>

## Merge Danger

**Door:** <one-way or two-way with rollback rationale>
**Blast Radius:** <isolated / narrow / medium / broad with scope assessment>
```

## 4. Ticket Completion Protocol
Upon completing each individual ticket:
1. Verify with tests and commit to the branch.
2. Close or comment on the associated issue.
3. Show verification evidence.
4. Ask: *"Would you like to proceed with the next ticket?"*

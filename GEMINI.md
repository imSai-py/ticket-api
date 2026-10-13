# Agent Instructions & Workflow

## 1. Communication Protocol
- **Language Standard**: Use ASD-STE 100 language for all communication.
- **Style**: Concise, direct GitHub-flavored markdown.
- **Link Policy**:
  - **Internal Conversations**: Use clickable links for files and symbols with `file://` scheme.
  - **External Deliverables (Email drafts, PR notes, release reports)**: Use remote GitHub repository URLs (`https://github.com/imSai-py/bitcot-technical-assignment/blob/master/...`).

## 2. Git & Branching Strategy
- **Core Branches**:
  - `master` (aliased to `main`): Production release branch.
  - `staging`: Staging and pre-production validation branch.
  - `dev`: Active development integration branch.
- **Task Branching**:
  - Always branch from `dev`.
  - Branch naming format: `[ticket-type]/[ticket-number]/[ticket-short-name]` (e.g., `feat/T-101/user-auth`, `fix/T-204/session-timeout`).
- **Pre-Commit Synchronization**:
  - Pull latest upstream changes from `dev` (or `master` if explicitly required by ticket instructions) before staging and committing changes.
- **Stacked Pull Request Merges**:
  - When merging stacked or interdependent pull requests, merge all pull requests in dependency order without deleting branch heads.
  - Delete feature branches in a single cleanup operation only after all pull requests merge successfully.

## 3. Development & Verification Standards
- **Toolchain**:
  - Python: Use `pytest` for tests, and `ruff` / `black` for formatting and linting.
  - TypeScript: Use `vitest` for tests, and TypeScript compiler (`tsc`) for type-checking.
- **Unified Verification Gate**:
  - Run the unified verification script before committing:
    - Windows: `powershell -ExecutionPolicy Bypass -File scripts/verify-all.ps1`
    - Linux / macOS: `bash scripts/verify-all.sh`
  - Show verification evidence (command output) prior to claiming task completion.
- **Code Integrity**: Preserve existing docstrings, type annotations, and comments unless explicitly instructed otherwise.

## 4. Pull Request (PR) & Ticket Lifecycle
- **PR Structure Template**:
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
- **PR Completion Gate**: Upon opening or completing a PR:
  1. Provide the clickable link to the PR.
  2. Ask: *"Would you like to proceed with the next ticket?"*

## 5. Environment Variable Security
Whenever creating or updating an `.env.example` file, README, or other documentation containing environment variable examples, use mock/placeholder values only. Never copy or expose actual credentials, API keys, tokens, passwords, or secrets from the `.env` file. Ensure all example values are clearly fake and safe to share.
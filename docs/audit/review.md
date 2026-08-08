# Review Blueprint Audit Report

**Blueprint**: `review/`  
**LOC**: 1,789  
**Last Audited**: 2026-08-08
**Status**: ✅ **CLEAN**

## Security Audit
✅ **NO ISSUES FOUND**

## Code Quality Audit
✅ **GOOD** - Refactored to use `get_db_session()`, clean export logic

## PII Audit
✅ **MASKED**

**Protections**:
- ✅ Discrepancy export has no patient names
- ✅ Grader comments masked with `| mask_text_emails` filter
- ✅ Job payloads conditionally masked (exports masked, uploads preserved for troubleshooting)

**Exception**: Upload job errors preserve PII for troubleshooting (documented in policy)

**Related Beads**: 
- 5G (55n): Jobs & Review Audit ✅
- 5K (f6n): Export Pipeline Sanitization ✅

**Tests**: `tests/security/test_jobs_review_pii.py` (3/3 passing)

**Action Items**: NONE - Clean

## 2026-08-08 Review-history correction

Migration `c8a4e2f1d9b7` invokes the immutable versioned script
`scripts/review_grade_correction_20260808.py`. Before mutation, the script
reconciles retained `grades.log*` events against current grade IDs, task IDs,
reviewers, statuses, and timestamps. It fails the transaction if evidence is
missing or does not match the relational state.

Production correction result after backup `backup_20260808_053755_db.tar.gz`:

- 492 complete grade snapshots archived in `review_grade_correction_archive`.
- 389 structured AI-feedback events preserved for 359 AI grades; raw log lines,
  IP addresses, and free-text log comments were not copied into event evidence.
- 56 human review rows with a proven stored-grader/submission-actor mismatch
  removed from `grades`, making the tasks eligible for human re-review.
- Prior consensus restored for all 56 tasks: 50 `match` and 6 `adjudication`.
- 132 review snapshots with the historically reversed AI-influence tag archived;
  77 surviving rows corrected in place and 55 removed with ambiguous reviews.
- Per-disease image-listing materialized views refreshed; all 56 corrected tasks
  now report `has_review = false` while retaining their restored consensus.

The downgrade restores archived review rows and original tags only if no later
human review or consensus change exists. Archive rows are retained as the audit
trail. No correction-specific columns were added to `grades`.

## Transactional submission history and concurrency

Migration `d4f6a8b2c1e9` adds the append-only `review_submission_history` table.
Every successful human review, AI-feedback update, or combined submission stores
the complete before/after review, consensus, and affected AI-grade snapshots in
the same PostgreSQL transaction as the source changes. Failed or stale
submissions therefore create neither source changes nor audit rows.

Review forms carry version tokens for the review row, consensus, and AI feedback.
The POST path locks the task and mutable rows, rejects stale tokens, and asks the
reviewer to reload. Multiple reviewers remain allowed; after an explicit reload,
the most recently updated review wins. Disease listing MVs order review rows by
`updated_at DESC, id DESC` to implement that contract deterministically.

Review saves mark only the affected disease MV dirty. Redis coalesces bursts into
one trailing refresh. The worker retries refresh errors and invalidates all
discrepancy-review page caches only after the refreshed snapshot is available.

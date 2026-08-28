# Current state

## Completed and pushed

### Lean authorization (`ff0fd5a1`)

- Old catalogue/policy/ReBAC machinery removed.
- Named role-and-scope helpers and domain-owned upload/task/grade access added.
- Dedicated privilege-escalation mitigation implemented.
- Missing facts deny; workers reauthorize exact current facts.
- Redis authorization and protected row-set caches removed.
- Exact Remidio route lineage implemented.
- One authorization migration added and exercised through upgrade/downgrade.
- Independent authorization audit verdict: `READY`, no material findings.

### PostgreSQL test harness (`03e954ce`)

- Shared `fundus_test` lifecycle serialized with a PostgreSQL advisory lock.
- Concurrent pytest sessions no longer reset each other's schema.
- Destructive MadhuNetrAI migration test moved to a UUID-named disposable DB.
- `DATABASE_URL` is restored and cleanup uses nested finalizers.
- Independent harness audit verdict: `READY`, no material findings.

## Verification already obtained

- Two concurrent route-coverage sessions: `2 passed` each.
- Previously failing mixed authz/security/Remidio sequence: `50 passed`.
- Disposable migration plus Remidio routing: `13 passed`.
- Remidio routing alone: `12 passed`.
- Full suite completes beyond the prior deadlock/schema-loss point.

## Latest full-suite baseline

Command: `make test`

Result:

- 1,549 collected, plus one collection skip
- 1,314 passed
- 29 skipped
- 13 xfailed
- 1 xpassed
- 122 failed
- 71 errors
- 102 warnings
- duration: 264.71 seconds

The previous baseline was 1,272 passed, 148 failed, and 81 errors. The remaining
failures are no longer a shared-schema cascade; they are independent test or
application contracts.

## Working tree at handoff creation

Only the following unrelated user files were dirty before this handoff and must
remain excluded from commits:

- `.claude/settings.json`
- `CLAUDE.md`
- `.claude/launch.json`
- `.serena/`
- `:memory:.ses`

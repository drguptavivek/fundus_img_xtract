# Authorization v2 completion plan

The clean cutover remains disabled until every runtime consumer is classified, every list query is scoped equivalently, the single consolidated migration is validated, and the cutover gate passes.

1. Complete high-risk upload, media, export, administration, grant, and project-management HTTP families.
2. Complete remaining read/workspace HTTP families and replace legacy action literals.
3. Classify all Celery entry points with explicit automation principals, actions, and exact targets.
4. Migrate query candidates used by protected lists to Authz v2 query policies and prove row-level equivalence.
5. Run the full security matrix, consolidated migration upgrade/downgrade/upgrade, independent quality audit, then perform the atomic clean cutover with no compatibility fallback.

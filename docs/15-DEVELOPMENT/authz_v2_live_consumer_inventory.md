# Authz v2 live-consumer inventory

Status: foundation inventory for clean cutover; `authz_v2` is not registered in the live application.

## Reproducible inventory

Run inside the Compose network:

```bash
docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache -T web \
  uv run python -m scripts.authz_v2_inventory
```

The command enumerates the runtime Flask URL map and the full Celery task registry, unwraps each callable to its source file and line, records any literal canonical/legacy action name in the callable, and emits deterministic JSON. The reviewed baseline is enforced by `tests/unit/app_init/test_authz_v2_consumer_inventory.py`.

| Consumer | Count | Authz v2 contract | Direct action literal | Explicitly unmapped |
|---|---:|---:|---:|---:|
| Flask/API route rules | 680 | 17 | 50 | 613 |
| Celery tasks | 47 | 0 | 0 | 47 |
| Production list-materialization candidates (`all`, `paginate`, `yield_per`) | 977 | 0 | 0 | 977 |
| Total | 1,704 | 17 | 50 | 1,637 |

Reviewed identity fingerprint: `6851094b619dd3800bdc2421d681f0b9dc97cc2c5d83ce11a047f8125680aba3`.

An action literal is only a discovery hint. It can be a redirect, link, or helper argument and does not prove that the route authorizes the loaded object. Every row remains `legacy_*` or `automation_unmapped` until cutover adds an explicit endpoint/worker contract. The inventory deliberately exposes these as gaps instead of inferring authority from route names or role decorators.

The query candidates are intentionally over-inclusive: they include ordinary domain and lookup materialization as well as authorization-sensitive lists. This prevents helper/service queries from disappearing from the audit surface. The table below records the relationship/state-dependent live sets already proven to require Authz policy; each remaining candidate must be marked scope-only, action-specific, choice-only, exact-only, or non-authorization filtering as its vertical slice is migrated.

Largest unmapped HTTP families are `fundus_api` (195), `admin` (164), `grading` (27), `mobile_api` (27), `verify_encounter_set` (16), `analytics` (14), `verify_remedio` (14), and `direct_uploads` (12). The `media` family is now 17/17 explicitly classified. These counts define the route-migration workload; they are not authorization approvals.

### Vertical slice 1: clinical media delivery

All 17 media routes now declare exact `media.image.view` or `media.pdf.view` contracts. Signed image/thumbnail routes require the signed session channel and exact resource; authenticated routes require exact scoped resources. The polymorphic signed `/<uuid>` endpoint declares a closed two-action allowlist and uses a dynamic binding, so a resolver may select only image or PDF authorization after resolving the stored source. An undeclared action, missing binding, missing resource, or resolver error denies before handler execution.

## Authorization-sensitive list/query classification

| Live set consumer | Canonical decision | Classification | Authz v2 provider |
|---|---|---|---|
| Resident task queue | `grading.resident.submit` | action-specific SQL | exact disease/Lab Unit slot, pending state, no same/conflicting grade, exact enforced project allocation |
| Resident2 task queue | `grading.resident2.submit` | action-specific SQL | exact disease/Lab Unit slot, resident-done state, no same/conflicting grade, exact enforced project allocation |
| Arbitrator task queue | `grading.arbitrator.submit` | action-specific SQL | exact disease/Lab Unit slot, arbitration state, no same/conflicting grade, exact enforced project allocation |
| Grading history/grade access | `grading.grades.view` | action-specific SQL | qualified participant or scoped Admin break-glass |
| Recent jobs and result polling | `jobs.result.view` | action-specific SQL | owner or containing non-System scope; project rows excluded from classical scopes; NULL-scope rows are owner/Admin only |
| Workspace picker | `authorization.me.workspaces.view` | choice-only | registered workspace projection |
| Upload options/profile picker | `authorization.me.upload_options.view` | choice-only | registered upload projection; returns allowed profile identity, not internal profile validation |
| Upload submission | upload create actions | exact-only | exact active upload-profile assignment; kind, disease, camera, area, mydriatic state, and other profile contents remain domain validation |
| Password reset and public dataset share | signed actions | exact-only | principal/session-bound signed credential; no list policy |
| Automated inference | automation actions | exact-only | stored active rule bound to exact target and automation session; no general list policy |
| Dataset mutation/export/share | dataset actions | exact-only mutation/download | lifecycle and all participating project-site policy flags are evaluated on the exact dataset; broad list use remains unsupported |
| Polymorphic image/report/media families | their exact actions | exact-only or typed member list | a cross-table family cannot use one ambiguous SQL list; unregistered list use denies `unsupported_query` |

## Core gaps closed in this slice

- Grading-slot evidence had been emitted without checking `UserDiseaseUnitRole`. It now requires the exact active disease/Lab Unit slot for Resident, Resident2, or Arbitrator.
- Enforced project grading had matched only project, Lab Unit, user, and capacity. It now also requires the server-resolved semantic allocation scope, disease, and encounter-set type.
- `jobs.result.view` previously had no owner path, and NULL-lab jobs could not resolve safely. Exact and list decisions now agree: owner or containing scope, with System-scoped non-Admin grants unable to expose another user's NULL-lab job.
- The five live relationship-aware list decisions above have registered action/resource SQL policies. Other relationship/state-dependent actions remain fail-closed for `filter_query()` unless this inventory explicitly classifies and implements a list use.

## Remaining cutover work

The remaining 660 explicitly unmapped runtime consumers (613 HTTP rules and 47 Celery tasks) must be assigned an endpoint or worker contract during vertical-slice migration. This inventory is the baseline that makes additions/removals visible; it does not activate `authz_v2`, retain a legacy fallback, or claim route-level cutover.

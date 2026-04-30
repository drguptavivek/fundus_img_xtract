# KPI API Surface

This folder documents the JSON and file-export APIs used by the analytics pages.

## Pages

- [Encounter Files KPIs](encounter-files.md)
- [Direct Files KPIs](direct-files.md)

## Contract notes

- All KPI endpoints are `GET`.
- Auth is `login_required` plus `admin` or `data_manager` role checks.
- Filter parameters are parsed through `api.kpis.kpiutils.parse_filter_params()`.
- Standard JSON responses use `create_kpi_response()` or `create_error_response()`.

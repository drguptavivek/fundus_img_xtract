# KPI APIs

These endpoints expose dataframe exports and dashboard metrics.

## Encounter-file KPIs

- `GET /api/kpis/encounter-files/filtered-dataframe`
- `GET /api/kpis/encounter-files/filtered-dataframe-excel`
- `GET /api/kpis/encounter-files/year-month-wise-uploads`
- `GET /api/kpis/encounter-files/dr-reports-count`
- `GET /api/kpis/encounter-files/glaucoma-reports-count`
- `GET /api/kpis/encounter-files/images-count`
- `GET /api/kpis/encounter-files/dr-results-distribution`
- `GET /api/kpis/encounter-files/glaucoma-results-distribution`
- `GET /api/kpis/encounter-files/vcdr-distribution`

## Direct-file KPIs

- `GET /api/kpis/direct-files/filtered-dataframe`
- `GET /api/kpis/direct-files/filtered-dataframe-excel`
- `GET /api/kpis/direct-files/upload-metrics`

## Notes

- These are analytics exports, not transactional APIs.
- Existing longer-form docs live in `docs/11-KPI and DFs/`.

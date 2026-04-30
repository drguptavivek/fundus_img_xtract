# Upload Stats API

These endpoints provide upload counts for dashboards and JavaScript widgets.

## `GET /api/upload-stats/today`

Returns upload stats for the current day, scoped to the current user’s hospital/lab context.

## `GET /api/upload-stats/last-7-days`

Returns upload stats for the last seven days.

## Notes

- The payload is used by dashboard widgets, so it should remain stable and documented whenever new keys are added.

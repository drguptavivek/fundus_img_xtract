# Dataset APIs

These routes support dataset sharing, downloads, and state transitions.

## `GET /datasets/download/<token>/status`

Returns download status for a share token.

Common error states:
- invalid token
- locked
- invalid share
- not verified
- terms not accepted

## `POST /datasets/download/<token>/verify`
## `POST /datasets/download/<token>/generate`
## `POST /datasets/download/<token>/regenerate`
## `POST /datasets/download/<token>/accept`

Drive the dataset download workflow for verified shares.

## `GET /datasets/download/<token>/file/<job_token>/<path:filename>`

Streams a generated dataset file.

## Notes

- Dataset curation uses page routes too, but the download/status endpoints are the JS-visible contract.

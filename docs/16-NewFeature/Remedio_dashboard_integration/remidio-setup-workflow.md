# Remidio Setup Workflow

This workflow is for connecting a Remidio dashboard account to EyeImageManager projects.

## 1. Configure Remidio Sites

In Remidio:

1. Open `https://dashboard.remidio.com/sites`.
2. Open each geographic/screening site.
3. Go to **Configure Site Settings**.
4. Set a stable **Site Custom Identifier**.

Example identifiers:

```text
AIIMS-Delhi    -> rpc_comoph_1
AIIMS-Delhi 2  -> rpc_comoph_2
AIIMS-DELHI 4  -> rpc_comoph_4
```

Rules:

- Site Custom Identifier must be stable.
- Use lowercase/underscore identifiers.
- Do not reuse the same identifier for multiple Remidio sites.
- Keep a local mapping because `getSites` does not return this field.

## 2. Create EyeImageManager Remidio Connection

For each Remidio dashboard account, EyeImageManager should store:

```text
Remidio account name
base URL
clientName
clientIdentificationToken
email/password or generated clientAuthToken
active/inactive status
```

Secrets must be encrypted at rest. Tokens and passwords must not appear in logs.

## 3. Import Or Enter Remidio Sites

Use:

```http
GET /api/gateway/getSites
```

This returns:

```text
siteId
siteName
siteDomain
```

Then manually enter the dashboard-configured `siteCustomIdentifier` for each returned site.

EyeImageManager Remidio site rows should store:

```text
remidio_account_id
remidio_site_id
remidio_site_name
remidio_site_domain
site_custom_identifier
active
```

## 4. Configure Project Routing Rules

Create routing rules that map Remidio items into EyeImageManager.

Minimum rule:

```text
Remidio account
+ Remidio site
+ Remidio deviceType
-> EyeImageManager project
-> EyeImageManager lab_unit
-> EyeImageManager camera
-> base/default disease policy
```

Notes:

- Remidio `site` means geographic/screening site.
- EyeImageManager `lab_unit` is our operational location.
- EyeImageManager anatomical `Area/site` is not used for Remidio geographic routing.

## 5. Endpoint Usage Rules

Use numeric Remidio `siteId` for:

```http
GET /api/gateway/getPatientWithLastExam/{siteId}/{mrn}
```

Use Remidio `siteCustomIdentifier` for:

```http
GET /api/gateway/getExamsByDate/{startDate}/{endDate}/{siteCustomIdentifier}
```

Use queue sync for incremental ingestion:

```http
GET /api/gateway/getQueueItem
POST /api/gateway/itemSuccessfullyHandled
```

Only call `itemSuccessfullyHandled` after local persistence succeeds.

## 6. Validation Checklist

Before enabling sync for a Remidio account:

- Login succeeds.
- `getAuthToken` succeeds and stores a valid `clientAuthToken`.
- `getSites` returns expected Remidio sites.
- Every expected Remidio site has a manually entered `siteCustomIdentifier`.
- `getExamsByDate` returns HTTP `200` for each `siteCustomIdentifier`.
- At least one known MRN can be tested with `getPatientWithLastExam` using numeric `siteId`.
- Every active site/device combination has exactly one EyeImageManager routing rule.
- No queue item is acknowledged unless image/report metadata and files are safely stored.

## 7. PDF And Disease Workflow

Routing decides where the encounter belongs:

```text
project + lab_unit + camera + base/default disease
```

PDF/report parsing decides additional disease workflows:

```text
DR / glaucoma / AMD / other configured disease tasks
```

Do not overwrite Remidio source patient identity. If identity corrections are needed, store them as EyeImageManager correction records layered on top of immutable Remidio source data.

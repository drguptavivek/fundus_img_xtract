

**MadhuNetrAI Vision Centre Screening API**

*Integration Guide*

This document describes how AIIMS Delhi vision centre software submits fundus images to the MadhuNetrAI Screening API and receives the diabetic retinopathy (DR) and diabetic macular oedema (DME) grading in the same request.

| Application | MadhuNetrAI |
| :---- | :---- |
| **Document** | MadhuNetrAI Vision Centre Screening API — Integration Guide |
| **Version** | 1.0 |
| **Date** | August 12, 2026 |
| **Audience** | AIIMS Delhi integration team |
| **By** | Wadhwani AI |

**Table of Contents**

**[1\.  Overview	3](#heading=)**

[**2\.  Prerequisites	3**](#heading=)

[**3\.  Integration Flow	3**](#heading=)

[**Current Vision Centre Flow	3**](#heading=)

[**Integrated Flow	4**](#heading=)

[**Key Characteristics	4**](#heading=)

[**4\.  API Documentation	4**](#heading=)

[**Authentication	4**](#heading=)

[**The request\_id	5**](#heading=)

[**1\.  Presign Upload URLs API	5**](#heading=)

[**2\.  Upload Image API	8**](#heading=)

[**3\.  Submit Screening API	9**](#heading=)

[**Patient Matching	14**](#heading=)

[**Single-Eye Screenings	14**](#heading=)

[**Ungradable Eye	15**](#heading=)

[**Idempotency & Retries	15**](#heading=)

[**Implementation Notes	15**](#heading=)

[**5\.  Response Field Definitions	15**](#heading=)

[**6\.  Error Reference	16**](#heading=)

[**Retry Rules	17**](#heading=)

[**7\.  Support	18**](#heading=)

# **1\.  Overview**

AIIMS Delhi's vision centres photograph patients' retinas using their own software and camera. At present, each patient must be re-entered into MadhuNetrAI by hand in order to obtain an AI reading.

This API allows the vision centre software to submit the fundus images directly and receive the DR and DME grading in the same response. The screening is simultaneously recorded as a MadhuNetrAI report, so it appears in the ophthalmologist's worklist and in the patient's history with no further data entry. The duplicate data entry is removed.

The integration consists of three API calls per screening. Image bytes are uploaded directly to cloud storage using temporary URLs issued by the API, so image data does not pass through the API server and no storage credentials are shared with the vision centre.

# **2\.  Prerequisites**

Please confirm each of the following before development begins. A mismatch here is the most common cause of an integration failing on the first day of use.

| Item | Requirement |
| :---- | :---- |
| **Fundus camera output** | JPEG or PNG. Format is verified from the file contents, so TIFF and BMP are rejected even when renamed. If the camera exports TIFF, a conversion step is required before upload |
| **Patient identifier (UHID)** | 30 characters or fewer, and referring to the same person consistently across all vision centres. Please inform Wadhwani AI before go-live if your identifiers are longer |
| **HTTP client timeout** | 120 seconds on the Submit Screening API. A default 30 second timeout will terminate valid gradings |
| **Credentials** | Base URL and API token, issued by Wadhwani AI and stored server-side |

# **3\.  Integration Flow**

## **Current Vision Centre Flow**

The screening process currently requires the patient to be recorded twice, once in the vision centre software and once in MadhuNetrAI.

1. **Image capture:** the optometrist photographs the patient’s retinas using the vision centre camera and software.

2. **Manual re-entry:** the operator creates the same patient again in MadhuNetrAI by hand.

3. **Manual upload:** the fundus images are uploaded through the MadhuNetrAI interface.

4. **Grading:** the AI grading is produced and made available to the ophthalmologist.

## **Integrated Flow**

The integration replaces the manual re-entry and upload steps with three API calls made by the vision centre software. The grading is returned synchronously, so no polling and no webhook are required on your side.

* **Request upload URLs:** the software declares how many images it has and for which eye. The API returns one temporary upload URL per image.

* **Upload images:** each image is uploaded directly to cloud storage using its own URL.

* **Submit screening:** the software submits the patient details and the image references. The API verifies the images, runs the model, records the screening in MadhuNetrAI, and returns the DR and DME grading in the same response.

| Step | Call | Purpose |
| :---: | ----- | ----- |
| 1 | `POST /api/inference/presign/` | Returns one temporary upload URL per image |
| 2 | `PUT {upload_url}` | Uploads the image bytes directly to cloud storage |
| 3 | `POST /api/inference/` | Verifies, grades, records the screening, and returns the grading |

## **Key Characteristics**

| Property | Value |
| :---- | :---- |
| **Response mode** | Synchronous. The grading is returned in the Submit Screening response. No polling and no callbacks |
| **Response time** | 5 to 30 seconds typical, 95 seconds maximum |
| **Images per screening** | 1 to 10 per eye. One or both eyes |
| **Accepted formats** | JPEG and PNG only, verified from the file contents |
| **Authentication** | One non-expiring API token per vision centre, issued by Wadhwani AI |
| **Payload format** | JSON, except the image upload, which sends raw image bytes |

# **4\.  API Documentation**

***NOTE**: The base URL and the API token will be shared separately over email.*

Each API below is documented as a request, a successful response, and **one representative error response**. The error shown is an example of the shape to expect, not the only error the call can return. The complete list of error codes for every call is in section 6, Error Reference.

## **Authentication**

Every call to `/api/inference/*` must carry the API token in the `Authorization` header. The scheme is `Token`, not `Bearer`.

**Request Header:**

`Authorization: Token {API_TOKEN}`

* The token does not expire and requires no renewal. There is no login endpoint to implement.

* The token identifies your vision centre. Never send a facility or optometrist in the request body.

* Treat the token as a password: keep it server-side, out of source control, and out of any client application. If it is exposed, inform Wadhwani AI so that it can be revoked and replaced.

**Error (401) — authentication failure:**

`{`
  `"detail": "Invalid token."`
`}`

**Note.** Authentication failures are the only errors that carry no `error` key. A response body containing only `detail` should therefore be handled as an authentication failure.

## **The request\_id**

The caller generates one `request_id` per screening. The same value is used in the Presign and Submit calls and in every retry. It is the mechanism that makes retries safe: resubmitting with the same value returns the stored result instead of re-running the model or creating a duplicate record.

| Rule | Requirement |
| :---- | :---- |
| **Uniqueness** | Unique per screening, permanently. A UUIDv4 is recommended |
| **Length** | Maximum 100 characters |
| **Character set** | Letters, digits, hyphen and underscore only. Any other character returns `400 invalid_request` |
| **Consistency** | The same value in the Presign call, the Submit call, and every retry |
| **Reuse** | Never reused for a different patient or a different visit |
| **Persistence** | Written to your own database before the Presign call is made, so that an interrupted screening can be resumed rather than restarted |

## **1\.  Presign Upload URLs API**

Declares the images to be sent and returns one temporary upload URL per image.

**Request:**

```
curl -X POST https://{BASE_URL}/api/inference/presign/ \
  -H "Authorization: Token {API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
        "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "images": [
          { "original_filename": "OD_001.jpg", "eye": "right" },
          { "original_filename": "OD_002.jpg", "eye": "right" },
          { "original_filename": "OS_001.jpg", "eye": "left"  },
          { "original_filename": "OS_002.jpg", "eye": "left"  }
        ]
      }'
```

**Response (200):**

```
{
  "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "uploads": [
    {
      "eye": "right",
      "key": "inference/f47ac10b-.../right/right_1.jpg",
      "original_filename": "OD_001.jpg",
      "content_type": "image/jpeg",
      "upload_url": "https://{bucket}.s3.ap-south-1.amazonaws.com/..."
    },
    {
      "eye": "right",
      "key": "inference/f47ac10b-.../right/right_2.jpg",
      "original_filename": "OD_002.jpg",
      "content_type": "image/jpeg",
      "upload_url": "https://{bucket}.s3.ap-south-1.amazonaws.com/..."
    },
    {
      "eye": "left",
      "key": "inference/f47ac10b-.../left/left_1.jpg",
      "original_filename": "OS_001.jpg",
      "content_type": "image/jpeg",
      "upload_url": "https://{bucket}.s3.ap-south-1.amazonaws.com/..."
    },
    {
      "eye": "left",
      "key": "inference/f47ac10b-.../left/left_2.jpg",
      "original_filename": "OS_002.jpg",
      "content_type": "image/jpeg",
      "upload_url": "https://{bucket}.s3.ap-south-1.amazonaws.com/..."
    }
  ]
}
```

**One entry per declared image.** The four images declared above produce four upload entries, returned in the same order. Keys are numbered per eye — `right_1`, `right_2`, `left_1`, `left_2` — and each has its own `upload_url`.

**Error (400) — invalid\_request:**

```
{
  "error": "invalid_request",
  "detail": { "images": ["This list may not be empty."] }
}
```

**Request Body**

| Parameter | Type | Description |
| ----- | ----- | ----- |
| `request_id` | `string; required` | Screening identifier generated by the caller. See The request\_id above |
| `images` | `array; required` | At least 1 entry, maximum 10 per eye |
| `images[].original_filename` | `string; required` | Up to 255 characters. Retained for your reference and echoed back in the grading response; it is not interpreted |
| `images[].eye` | `string; required` | Enum: left / right. Lowercase exactly |

**Response Body**

| Parameter | Type | Description |
| ----- | ----- | ----- |
| `request_id` | `string` | Echo of the submitted screening identifier |
| `uploads` | `array` | One entry per requested image, in the order submitted |
| `uploads[].eye` | `string` | The eye declared for this image |
| `uploads[].key` | `string` | Storage key for this image. Required unchanged in the Submit Screening call |
| `uploads[].original_filename` | `string` | Echo of the submitted filename |
| `uploads[].content_type` | `string` | The exact value to send as the Content-Type header when uploading |
| `uploads[].upload_url` | `string` | Pre-signed URL for the upload. Valid for 15 minutes |

**Expiry.** Upload URLs are valid for 15 minutes. If a URL expires before it is used, call this API again with the same `request_id` to obtain fresh URLs for the same keys.

## **2\.  Upload Image API**

Uploads the raw bytes of a single image to cloud storage using the pre-signed URL returned by the Presign API. This call goes to cloud storage, not to the Wadhwani AI API, and does not carry the API token.

**Request:**

```
# one call per image, using that image's own upload_url

curl -X PUT "{upload_url_for_right_1}" \
  -H "Content-Type: image/jpeg" \
  --upload-file OD_001.jpg

curl -X PUT "{upload_url_for_right_2}" \
  -H "Content-Type: image/jpeg" \
  --upload-file OD_002.jpg
```

The worked example requires four such calls, one per declared image. Each call uses the `upload_url` and `content_type` returned for that specific key.

**Response (200):**

An empty body. Uploads for different images may run in parallel, and a single failed image may be retried on its own.

**Error (403) — SignatureDoesNotMatch:**

```
<Error>
  <Code>SignatureDoesNotMatch</Code>
  <Message>The request signature we calculated does not match ...</Message>
</Error>
```

**Upload Rules**

| Rule | If not followed |
| :---- | :---- |
| The `Content-Type` header must exactly match the `content_type` returned by the Presign API | `403 SignatureDoesNotMatch`. This is the most frequent integration error |
| Send raw bytes only. No multipart form and no base64 encoding | The Submit Screening call rejects the image with `400 invalid_image` |
| Use the `PUT` method and add no headers beyond `Content-Type` | `403` |
| Upload within 15 minutes of receiving the URL | `403`, URL expired. Call the Presign API again |
| Send JPEG or PNG only | The Submit Screening call rejects the image with `400 invalid_image` |

## **3\.  Submit Screening API**

Submits the patient details and the uploaded image keys. The API verifies the images, runs the model, records the screening in MadhuNetrAI, and returns the grading in the same response.

**Request:**

```
curl --max-time 120 -X POST https://{BASE_URL}/api/inference/ \
  -H "Authorization: Token {API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
        "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "patient": {
          "patient_id": "UHID9988776655",
          "age": 57,
          "sex": "male"
        },
        "images": [
          { "key": "inference/f47ac10b-.../right/right_1.jpg",
            "eye": "right" },
          { "key": "inference/f47ac10b-.../right/right_2.jpg",
            "eye": "right" },
          { "key": "inference/f47ac10b-.../left/left_1.jpg",
            "eye": "left" },
          { "key": "inference/f47ac10b-.../left/left_2.jpg",
            "eye": "left" }
        ]
      }'
```

**Response (200):**

```
{
  "report_id": "ededf725-f90e-4313-8cbe-bfa3b403daf5",
  "request_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "patient_id": "UHID9988776655",
  "status": "completed",
  "results": {
    "images": {
      "left": [
        {
          "key": "inference/f47ac10b-.../left/left_1.jpg",
          "filename": "OS_001.jpg",
          "is_primary": false,
          "model_outputs": {
            "fundus": {
              "fundus_label": "fundus",
              "probability_fundus": 1.0,
              "probability_non_fundus": 6.37e-24,
              "logit_fundus": 26.9101,
              "logit_non_fundus": -26.5001
            },
            "eyes": {
              "eyes_label": "left_eye",
              "probability_left_eye": 0.9997,
              "probability_right_eye": 0.0002,
              "logit_left_eye": 9.3095,
              "logit_right_eye": 0.8564
            },
            "drdme": {
              "DR_grade": "No DR",
              "DR_score": 0.0088,
              "DME_grade": "No DME",
              "DME_score": 0.0217
            },
            "similarity_score": 40.2843
          }
        },
        {
          "key": "inference/f47ac10b-.../left/left_2.jpg",
          "filename": "OS_002.jpg",
          "is_primary": true,
          "model_outputs": {
            "fundus": { "fundus_label": "fundus", "...": "..." },
            "eyes":   { "eyes_label": "left_eye", "...": "..." },
            "drdme": {
              "DR_grade": "No DR",
              "DR_score": 0.0158,
              "DME_grade": "No DME",
              "DME_score": -0.0166
            },
            "similarity_score": 28.7597
          }
        }
      ],
      "right": [ "... right_1 and right_2, same structure ..." ]
    }
  }
}
```

**Every submitted image is returned.** The four images submitted above produce four entries: two under `left` and two under `right`. Exactly one entry per eye has `is_primary` set to `true` — here `left_2` — and that entry's `drdme` block is the grading for that eye.

**Error (400) — unknown\_key:**

```
{
  "error": "unknown_key",
  "detail": {
    "missing_keys": ["inference/f47ac10b-.../left/left_1.jpg"]
  }
}
```

**Request Body**

| Parameter | Type | Description |
| ----- | ----- | ----- |
| `request_id` | `string; required` | The same value used in the Presign call |
| `patient.patient_id` | `string; required` | Patient identifier (UHID) maintained by the vision centre. Maximum 30 characters. Must refer to the same person consistently |
| `patient.age` | `integer; required` | Age in years, 0 to 120 |
| `patient.sex` | `string; optional` | Enum: male / female / other |
| `patient.is_monocular` | `boolean; optional` | Defaults to false. Set true only when the patient genuinely has one eye. See Single-Eye Screenings below |
| `images` | `array; required` | One entry per uploaded image |
| `images[].key` | `string; required` | The key returned by the Presign call, unchanged. Keys belonging to another screening are rejected |
| `images[].eye` | `string; required` | Enum: left / right. Must match the eye declared in the Presign call |
| `images[].original_filename` | `string; optional` | Up to 255 characters |

**Fields not listed above are ignored.** Sending an unrecognised field does not cause an error, and its value is not recorded.

**Response Body**

| Parameter | Type | Description |
| ----- | ----- | ----- |
| `report_id` | `string` | UUID of the MadhuNetrAI report created for this screening. Log it against your patient record |
| `request_id` | `string` | Echo of the submitted screening identifier |
| `patient_id` | `string` | Echo of the submitted patient identifier |
| `status` | `string` | Reads `completed` for a successful screening |
| `results.images.left` | `array` | One entry per left-eye image submitted. Empty when no left-eye image was sent |
| `results.images.right` | `array` | One entry per right-eye image submitted. Empty when no right-eye image was sent |
| `results.images[].key` | `string` | The storage key of this image |
| `results.images[].filename` | `string` | The filename you declared for this image |
| `results.images[].is_primary` | `boolean` | True for exactly one image per eye. This is the image whose grading represents the eye |
| `results.images[].model_outputs` | `object` | Model output for this image. See Response Field Definitions |

### **Patient Matching**

The patient is looked up by the pair (vision centre, `patient_id`) and created if not already present. A given `patient_id` must therefore always refer to the same person. Age and sex recorded on an existing patient are not overwritten by a later screening, so a correction to those values must be made in MadhuNetrAI.

### **Single-Eye Screenings**

A screening may contain one eye only. The eye that was not submitted is returned as an empty array:

```
"images": { "left": [ ... ], "right": [] }
```

The reason for the missing eye is recorded from `patient.is_monocular`. The two reasons display differently in MadhuNetrAI, so the flag carries clinical meaning and must reflect the patient.

| patient.is\_monocular | Reason recorded in MadhuNetrAI |
| :---- | :---- |
| `true` | Patient is monocular |
| `false, omitted, or any other value` | Unclear image due to the presence of other ophthalmic conditions |

**Set true only for a genuine single-eye patient.** If the second eye was simply not captured at this visit, omit the flag or send `false`.

### **Ungradable Eye**

When an eye cannot be graded, its entries carry an error object in place of the model output:

`"model_outputs": { "status": "error", "detail": "..." }`

* The other eye is still graded and the report is still created.

* Re-photograph the affected eye and submit it as a new screening with a new `request_id`.

* If no eye can be graded, the call returns `502 grading_failed` and no report is created.

### **Idempotency & Retries**

Every screening corresponds to one `request_id`, which serves as the deduplication key. It must remain unchanged across automatic retry scenarios such as network timeouts. Resubmitting the same `request_id` is always safe:

| Condition | Result |
| :---- | :---- |
| The screening is already recorded | The stored result is returned with the same `report_id`. The model is not run again and no record is duplicated |
| The screening is not yet recorded | The request is processed normally |
| The `request_id` was used for a different `patient_id` | `409 request_id_conflict` is returned. The first patient’s report is never disclosed |

**After a timeout.** If this call times out, the outcome is unknown to the caller. Retrying with the same `request_id` is always the correct action: it either completes the screening or returns the result already stored. Never generate a new `request_id` after a timeout, as this would create a second screening for the same patient.

### **Implementation Notes**

* Set the HTTP client timeout to **120 seconds**. Grading is synchronous and may take up to 95 seconds.

* Read each eye’s grading from the entry where `is_primary` is `true`, selected by the flag and never by position in the array.

* Ignore any field in `model_outputs` that you do not recognise. Fields may be added without notice, and a strict parser will fail on them.

* Branch on the `error` code rather than on the `detail` text, whose wording may change.

* Store the returned `report_id` against your patient record. It is the reference used to trace a screening in MadhuNetrAI and in any support request.

# **5\.  Response Field Definitions**

The fields below appear inside `model_outputs` for each image. They are passed through from the model largely unaltered.

| Field | Type | Description |
| ----- | ----- | ----- |
| `fundus.fundus_label` | `string` | Reads `fundus` when the image is a usable retinal photograph. An image that is not a fundus photograph is still graded and returned; it is never discarded |
| `fundus.probability_fundus` | `float` | Confidence behind the fundus label |
| `eyes.eyes_label` | `string` | Enum: left\_eye / right\_eye. The eye the model identifies in the image. Compare it with the eye you declared in order to detect laterality mislabels at the point of capture |
| `drdme.DR_grade` | `string` | Enum: No DR / Mild NPDR / Moderate NPDR / Severe NPDR / PDR. The DR grade for this image |
| `drdme.DR_score` | `float` | Raw model score behind the DR grade |
| `drdme.DME_grade` | `string` | The DME prediction for this image, for example `No DME` |
| `drdme.DME_score` | `float` | Raw model score behind the DME grade |
| `similarity_score` | `float` | Sits directly inside `model_outputs`, alongside `fundus`, `eyes` and `drdme`, and not inside `drdme`. It measures how far the image is from the data the model was trained on: the lower the value, the more typical the image and the more reliable its grading |

**Scores are not probabilities.** `DR_score` and `DME_score` are raw model outputs. They are not bounded to 0 and 1 and may be negative, as `DME_score` is for the primary image in the example response. Please do not validate them as probabilities or reject a response on the basis of a negative value.

**The \`logit\_\` and \`probability\_\` values are retained for audit.** They are not required in order to read a grading and may be ignored.

# **6\.  Error Reference**

Every error other than an authentication failure has the same shape:

```
{ "error": "{code}", "detail": "{string, or an object with specifics}" }
```

Branch on the `error` code. Authentication failures carry no `error` key, only `detail`, with status `401`.

| HTTP | error | Cause | Action |
| :---: | ----- | ----- | ----- |
| 400 | `invalid_request` | A missing or invalid field: absent or malformed `request_id`, absent `patient_id`, `patient_id` longer than 30 characters, `age` outside 0 to 120, invalid `sex`, `eye` not `left` or `right`, or an empty `images` list | Correct the payload. Resubmitting it unchanged fails identically |
| 400 | `too_many_images` | More than 10 images for one eye | Submit fewer images |
| 400 | `unknown_key` | A key does not exist, or belongs to a different `request_id` | Confirm the keys came from this screening’s Presign call, re-upload if required, and retry with the same `request_id` |
| 400 | `invalid_image` | The uploaded bytes are not JPEG or PNG: a non-image file, TIFF or BMP, a base64 or multipart wrapper, or a truncated upload | Re-upload valid images and retry with the same `request_id` |
| 401 | `(none)` | Absent or invalid `Authorization` header | Verify the `Token {value}` format. If it is correct, contact Wadhwani AI |
| 409 | `request_id_conflict` | This `request_id` was already used for a different patient | A deliberate safety stop. Use a new `request_id` |
| 502 | `model_unavailable` | The grading service was unreachable or timed out | Transient. Retry after a delay with the same `request_id` |
| 502 | `grading_failed` | No submitted image could be graded | The images are unusable. Re-photograph and submit as a new screening |
| 500 | `internal_error` | A fault on the Wadhwani AI side | Retry once with the same `request_id`. If it recurs, contact Wadhwani AI with the `request_id` |

## **Retry Rules**

| Situation | request\_id |
| :---- | :---- |
| Timeout, or no response received | Reuse. Required |
| `502 model_unavailable`, `500 internal_error` | Reuse |
| `400 unknown_key` or `400 invalid_image`, after re-uploading | Reuse |
| `400 invalid_request` or `400 too_many_images`, after correcting the payload | Reuse |
| `409 request_id_conflict`, `502 grading_failed` | Generate a new one |

**Back off between attempts.** Use an increasing delay of 2 seconds, then 10 seconds, then 30 seconds. Please do not retry immediately in a loop.

# **7\.  Support**

Please include the following when raising an issue. These are the values used to locate the call in the audit log.

| Item | Notes |
| :---- | :---- |
| `request_id` | Always required |
| `report_id` | If one was returned |
| `Timestamp` | With timezone |
| `HTTP status` | The status code received |
| `Response body` | The complete body, with the API token removed |

**Please do not send patient names or the API token.** The `request_id` and `patient_id` are sufficient to trace any screening.

Copyright © 2026 Wadhwani AI. All rights reserved.

All data and information contained in this document are copyrighted by WIAI and may not be duplicated, copied, modified or otherwise adapted without our written permission. Your use of this document does not grant you any ownership to our content.
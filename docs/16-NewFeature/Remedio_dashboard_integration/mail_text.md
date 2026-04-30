# Remidio Host Gateway API Integration Mail

Dear

I have attached the Postman collection along with this mail. Please forward this mail to your IT team so they can perform the integration by following the documentation below.

Please follow the documentation exactly as mentioned below to understand how to integrate via our API links.

## API Details

## Initial One-Time Setup

### 1. Login

This is the standard login API. It takes a user's email address and password and returns an access token. This access token is used to make subsequent API calls.

The token is short-lived and expires within 15 minutes of inactivity.

### 2. Get Client Auth Token

This API takes the user's access token from the login step and returns a separate access token for your client software.

This token is called the `clientAuthToken`. It uniquely authorizes your client to make API calls on behalf of that user.

The `clientAuthToken` is long-lived with a near-permanent lifespan. It is invalidated only when you call the API again to obtain a new `clientAuthToken`.

Treat this token extremely securely, as you would treat any API key.

The above two steps complete the one-time setup. The next set of API calls use this `clientAuthToken` to obtain a provider's patient data stored on Remidio servers.

## Regular API Calls

### 1. Get Element From Queue

This API returns a specific object currently in the download queue. The object may be an image from Remidio devices, a video, or a PDF report.

As providers use the Remidio system to capture images, videos, or generate reports, those objects are immediately added to a download queue for your client software to fetch.

This API returns the first object from the queue.

The returned object includes information about:

1. Patient details such as name, MRN, date of birth, gender, and ID.
2. Patient examination details such as exam date and exam ID.
3. Object type, such as image, report, or video.
4. Device from which the object was generated.
5. Object metadata, such as laterality and image dimensions.
6. Download link for the file itself.

Once you receive this information, you can store it in your own database or file storage layer.

If you receive a `404` from this method, it means the queue is empty.

### 2. Element Handled Successfully

After the Get Element From Queue API call is completed and you have stored the data in your own system, you must call the Element Handled Successfully API.

This tells Remidio servers that the item was successfully handled and removes it from the download queue.

If this API call is not made, you will keep receiving the same object repeatedly.

Once an item is removed from the queue, it is never added to the queue again. Make sure you have saved the information in your database or file storage before calling this method.

### 3. Get Latest Patient Exam

This is an alternative approach to the queue system.

This API takes a Site Custom ID and a patient MRN, and returns the most recent exam for that patient, including all captured images and videos.

This lets you bypass the item-by-item queue and fetch only a specific patient's latest information.

This API requires the Site Custom ID of the site where the exam is being conducted. A site refers to a specific location or screening site.

The Site Custom ID can be configured under the "Configure Site Settings" menu of the Remidio Connect Dashboard. The parameter name is `siteCustomIdentifier`.

You can check the Custom ID of your site using the Get Sites API described below.

### 4. Create a Patient Exam

This API lets you register patient information in the Remidio system and schedule an exam for that patient.

If the patient MRN already exists, a new patient is not created. Instead, a new exam is scheduled for that patient.

### 5. Get Sites

This API returns all sites within a customer organization, including their Custom IDs.

This is needed if you use the Get Latest Patient Exam API or the Create Patient Exam API.

A site refers to a specific location or screening site.

### 6. Single / Batch Audit Logs

These APIs let you log anything you want with Remidio servers.

They are normally used to log errors encountered while interacting with the Remidio API, which helps with troubleshooting.

These APIs are optional.

### 7. Get Patient Visits By Date

This API takes a Start Date, End Date, and Site Custom ID, and returns all exams associated with patient visits recorded between the provided dates.

Dates must be in `DD-MM-YYYY` format. Both dates are inclusive.

Each exam object returned includes metadata such as:

- Images captured for each exam
- Reports generated for each exam
- Patient information
- Exam information

## Headers

Pay attention to all headers, including authorization headers.

The following headers must be set correctly:

- `clientName`
- `clientIdentificationToken`
- `clientAuthToken`
- `Authorization`, with the bearer token

## Notes

1. You will need the latest version of Postman to use the attached collection.
2. For the `createPatientExam` API, remove comments from the request body before calling the API. Comments were added only for explanation, but Postman does not automatically remove them.

## Testing

All of this can be tested only after a dashboard account is created for you by a Remidio service engineer.

Web application link: `dashboard.remidio.com`

Please let us know if you need any additional information or support.

Thanks & Regards,



Product Consultant - Remidio

# Managing the WAI DR-DME AI Model

This guide is for administrators who configure and operate the encounter-scoped MadhuNetrAI Vision Centre Screening integration. The integration sends one eligible EncounterSet to Wadhwani AI and records both DR and DME image-level results under the linked AI model.

## AI model ownership

The provider connection belongs to the combined DR/DME AI model, not to a global application setting. The installed model is normally:

- **Name:** `madhunetra_17aug2026`
- **Version:** `17aug2026`
- **Diseases:** DR and DME
- **Provider:** `wai_dr_dme`

Only one AI model can own the MadhuNetrAI DR-DME provider integration. In the current installation this model is available at `/admin/ai-models/3/edit`. Use the AI Models list rather than assuming ID 3 on another installation.

Do not attach these credentials to the Glaucoma model. Glaucoma continues to use its separate `wadhwani_glaucoma` Client ID and Bearer Token configuration.

## Configure the endpoint and token

1. Sign in with the **admin** role.
2. Open **Admin → AI Models**.
3. Find the model linked to **MadhuNetrAI DR + DME API** and select **Edit**.
4. Confirm that both **DR** and **DME** remain selected under Diseases.
5. In the **MadhuNetrAI DR + DME API** card, select **Link to and enable MadhuNetrAI DR + DME API**. This enables the configuration fields.
6. Enter:
   - **API base URL:** the credential-free HTTPS server root supplied by Wadhwani AI, such as `https://screening.example.org`. Do not append `/api/inference/` or `/api/inference/presign/`.
   - **Environment:** Staging during acceptance testing or Production after approval.
   - **Access token:** the raw token supplied by Wadhwani AI. Do not type the `Token ` prefix; the application adds it to the Authorization header.
7. Select **Save DR + DME API configuration**.

The token is encrypted before database storage and is never displayed again. A blank token field with the message **Configured; leave blank to retain** means a token is already stored.

## Rotate or disable credentials

To rotate the token, enter the replacement token on the same model edit page and save. To change only the URL or environment, leave the token field blank.

To stop new provider calls, clear **Link to and enable MadhuNetrAI DR + DME API** and save. Disabling the connection retains its endpoint, encrypted token, historical runs, reports, and grades.

## Enable the workflow for a project

Provider configuration and project authorization are separate controls:

1. Open **Admin → Projects** and select the project.
2. Under **Manual Remote AI Workflows**, enable **MadhuNetrAI DR + DME — EncounterSet screening** to allow authorized operators to queue verified EncounterSets.
3. Under **Automated Remote AI Inference**, enable the **DR + DME** row only when eligible prospective ingestion should trigger screening automatically.
4. Select the automatic eligibility rule in that row: **Always** or **OCR-confirmed DR report**.
5. Save each section independently. Saving either section preserves the setting in the other section.
6. Resolve any displayed blockers. The project needs an active Upload Profile capable of producing image-level DR EncounterSet tasks. DME is a linked output of the same model execution; it is not a separate Upload Profile capability requirement. Automatic execution is independent of Remidio provenance and runs only from a supported EncounterSet completion trigger.

## Run a manual screening

1. Open `/uploads/encountersets/wadhwani_inference?workflow=dr_dme`.
   The browser initially shows only eligible EncounterSets. Use the Eligibility filter to inspect all candidates, unverified EncounterSets, or non-monocular encounters that have macula images for only one eye.
2. Select the project and load candidates.
3. Review the OD and OS macula-image counts and eligibility messages.
4. Select one or more eligible, verified EncounterSets and queue them.
5. Keep the batch status page open until it shows Complete, Partial, or Failed.

Each EncounterSet is one provider request. All selected eligible macula images are uploaded before the combined Submit request. The status page shows the request ID and provider report ID without exposing the access token or signed upload URLs.

## Common problems

| Message or symptom | Action |
| --- | --- |
| Integration disabled or incomplete | Save an HTTPS base URL and token on the linked DR/DME model, then enable it. |
| Authentication failed or HTTP 401 | Confirm the raw token is current. Do not include `Token ` in the saved field. |
| No projects are listed | Enable the project's manual DR-DME workflow and confirm the user has upload scope for an EncounterSet in that project. |
| Project capability blocker | Confirm the project has an active EncounterSet Upload Profile with an image-level DR grading target. |
| Patient metadata blocker | Ensure the selected EncounterSet Type includes `hospital_UHID`, `patient_age_yrs`, and `sex`. For a genuine single-eye patient, also supply boolean `is_monocular=true`. |
| EncounterSet cannot be selected | Complete verification and correct missing/ambiguous laterality, focus, file type, patient identifier, or per-eye image-count issues. |
| Provider request fails after URL change | Confirm the saved URL is only the HTTPS server root and does not already include the inference path. |

## Security notes

- Never place the token in the URL, model name, description, screenshots, logs, or support messages.
- Use the Production environment only after Wadhwani AI confirms the production endpoint and token.
- Provider configuration requires the admin role. Project workflow management requires the applicable project/lab management scope.
- Existing results remain attributable to the linked AI model even when the provider is later disabled.

For the underlying API contracts, see [MadhuNetrAI DR-DME Encounter APIs](../API/madhunetra-dr-dme/README.md).

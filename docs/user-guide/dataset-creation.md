# Dataset Creation

This guide explains how to create and finalize curated datasets.

## Steps

1. Go to Analytics and create a new curated dataset.
2. Configure filters (disease, grades, lab units) and run auto-selection if needed.
3. Screen the dataset and confirm the final list of images.
4. Finalize the dataset to lock selections and enable export/share.
5. Use **Export** on the finalized dataset page. Download the image ZIP files,
   grade spreadsheet, and `annotations.json` from the completed export job.

Inside each ZIP, EncounterSet images are grouped under
`EncounterSets/<encounter_uuid>/`. Each image has a neighboring
`<image_uuid>.annotations.json` sidecar. The sidecar holds all exported linked
disease tasks for that image, with each task's grade, class, and annotations
kept separate. The top-level `annotations.json` is a searchable index of the
same task data across the export.

`annotations.json` is a native companion file. Its `tasks` array maps each
exported task UUID to its image UUID, ZIP image filename, disease, and saved
grades. Each grade includes its role, selected class features, raw workbench
geometry, and normalized annotation instances. Segmentation mask tiles include
base64 encoded PNG bytes, tile coordinates, dimensions, and checksums. A task
with no saved annotations has an empty `grades` array or grades with no
geometry. If an image cannot be added to a ZIP, the export includes a warning
and still retains that task's saved annotation data.

## Notes

- Finalization is required before sharing or exporting.
- Only finalized datasets can be shared.
- The creator can unfinalize within 30 minutes; admins can override.

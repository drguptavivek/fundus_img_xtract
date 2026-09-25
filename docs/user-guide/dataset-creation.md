# Dataset Creation

This guide explains how to create and finalize curated datasets.

## Steps

1. Go to Analytics and create a new curated dataset.
2. Configure filters (disease, grades, lab units) and run auto-selection if needed.
3. Screen the dataset and confirm the final list of images.
4. Finalize the dataset to lock selections and enable export/share.
5. Use **Export** on the finalized dataset page. Download the image ZIP files,
   grade spreadsheet, `annotations.jsonl`, `annotator_submissions.jsonl`,
   `coco.jsonl`, and `coco.json` from the completed export job.

Inside each ZIP, EncounterSet images are grouped under
`EncounterSets/<encounter_uuid>/`. Each image has a neighboring
`<image_uuid>.annotations.json` sidecar. The sidecar holds all exported linked
disease tasks for that image, with each task's grade, class, and annotations
kept separate. The top-level `annotations.json` is a searchable index of the
same task data across the export.

Each ZIP image also has a neighboring `<image_uuid>.coco.jsonl` sidecar.
It also has `<image_uuid>.annotators.jsonl`, with one line per saved grade
submission. Each line identifies the image task, disease, role, grade, class,
and complete geometry or segmentation. The top-level
`annotator_submissions.jsonl` contains the same submissions across the export,
including tasks whose image could not be added to a ZIP.
Each line of the top-level `annotations.jsonl` follows the IITK
`aiims-eom-v1` image-label convention (`labels.boxes` with pixel `x`, `y`,
`w`, `h`, and snake-case `cls`). `coco.jsonl` contains one COCO image record
per line with its annotations and categories; `coco.json` is a standard COCO
dataset. Segmentation polygons and mask tiles are converted to COCO polygon
or uncompressed RLE segmentation. The COCO training outputs use the highest
available human role for each included task: regrade adjudicator, arbitrator,
review, second resident, then resident. A higher role with no annotation falls
back to the highest earlier human role with annotations. All saved roles remain in the native
annotation index and sidecars. Only images successfully included in a ZIP
appear in the COCO outputs.

The COCO JSONL `task_grades` field identifies the later grade and role
separately from `annotation_source_role_slot`. COCO annotations also carry
`task_final_grade` and `annotation_source_grade`, so an earlier box stays
attributed to its original annotator role.

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

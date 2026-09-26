import base64
import json
from contextlib import contextmanager
from types import SimpleNamespace
from zipfile import ZipFile

from PIL import Image

from datasets import annotation_export
from grading.workbench.models import AnnotationSet
from models import Grade
from review import discrepancy_export
from review.discrepancy_export import ExportTaskRow, _write_zips


def _row(task_id, task_uuid, image_uuid, disease):
    return {
        "task_id": task_id,
        "task_uuid": task_uuid,
        "image_uuid": image_uuid,
        "image_filename": f"{image_uuid}.jpg",
        "disease": disease,
    }


def test_annotation_companion_preserves_per_task_grade_and_mask_tiles(monkeypatch, tmp_path):
    tile = SimpleNamespace(tile_x=0, tile_y=1, width=2, height=2,
                           checksum="checksum", png_bytes=b"png")
    instance = SimpleNamespace(
        id=30, uuid="instance-1", image_uuid="image-1",
        class_source="project_class", grading_feature_id=None, project_class_id=7,
        class_key_snapshot="lesion", class_label_snapshot="Lesion", policy_revision=2,
        geometry_type="brush_mask", geometry_json={"tile_size": 256},
        bbox_x=1, bbox_y=2, bbox_w=3, bbox_h=4, instance_order=0,
        locked=False, mask_tiles=[tile],
    )
    annotation_set = SimpleNamespace(
        grade_id=10, uuid="set-1", schema_version=1, policy_source="project",
        policy_revision=2, source_image_width=100, source_image_height=80,
        instances=[instance],
    )
    grades = [
        SimpleNamespace(id=10, task_id=1, role_slot="resident", grade_name="Positive",
                        selected_features_json='[{"id":7}]',
                        feature_geometry_json={"selected_class_id": "project:7"}),
        SimpleNamespace(id=20, task_id=2, role_slot="resident", grade_name="Negative",
                        selected_features_json=None, feature_geometry_json=None),
    ]

    class Result:
        def __init__(self, values):
            self.values = values

        def scalars(self):
            return self

        def all(self):
            return self.values

    class DB:
        def execute(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is Grade:
                assert set(next(iter(query.compile().params.values()))) == {1, 2}
                return Result(grades)
            assert entity is AnnotationSet
            return Result([annotation_set])

    @contextmanager
    def db_session():
        yield DB()

    monkeypatch.setattr(annotation_export, "get_db_session", db_session)
    destination = tmp_path / "annotations.json"
    annotation_export.write_annotation_export(
        [_row(1, "task-1", "image-1", "Disease A"),
         _row(2, "task-2", "image-2", "Disease B")], destination
    )
    tasks = json.loads(destination.read_text())["tasks"]
    assert tasks[0]["grades"][0]["feature_geometry"] == {"selected_class_id": "project:7"}
    assert tasks[0]["grades"][0]["annotation_set"]["instances"][0]["mask_tiles"][0]["png_base64"] == base64.b64encode(b"png").decode()
    assert tasks[1]["grades"][0]["annotation_set"] is None
    assert tasks[1]["image_uuid"] == "image-2"


def test_encounter_set_zip_pairs_one_image_with_linked_disease_sidecar(tmp_path):
    image_path = tmp_path / "source.jpg"
    image_path.write_bytes(b"image")
    image_rows = [
        {**_row(1, "task-a", "image-1", "Disease A"),
         "encounter_uuid": "encounter-1", "image_path": image_path},
        {**_row(2, "task-b", "image-1", "Disease B"),
         "encounter_uuid": "encounter-1", "image_path": image_path},
    ]
    manifest = {"schema_version": 1, "tasks": [
        {"task_uuid": "task-a", "image_uuid": "image-1", "disease": "Disease A", "grades": []},
        {"task_uuid": "task-b", "image_uuid": "image-1", "disease": "Disease B", "grades": []},
    ]}
    zip_paths, warnings = _write_zips(image_rows, tmp_path, annotation_manifest=manifest)
    assert warnings == []
    with ZipFile(zip_paths[0]) as archive:
        assert archive.namelist() == [
            "EncounterSets/encounter-1/image-1.jpg",
            "EncounterSets/encounter-1/image-1.annotations.json",
        ]
        sidecar = json.loads(archive.read(archive.namelist()[1]))
        assert [task["disease"] for task in sidecar["tasks"]] == ["Disease A", "Disease B"]


def test_encounter_set_payload_resolves_image_and_encounter_folder(monkeypatch, tmp_path):
    image = SimpleNamespace(
        uuid="image-1", folder_rel="encounter-folder", original_filename="original.jpg",
        edited_filename="edited.jpg", s3_config_id=None, s3_object_key=None,
        s3_object_key_edited=None,
    )

    class Query:
        def join(self, *_args, **_kwargs):
            return self

        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return [(image, "encounter-1")]

    class DB:
        def query(self, *_args):
            return Query()

    @contextmanager
    def db_session():
        yield DB()

    monkeypatch.setattr(discrepancy_export, "get_db_session", db_session)
    monkeypatch.setattr(discrepancy_export, "BASE_DIR", tmp_path)
    monkeypatch.setattr(discrepancy_export, "_load_ai_model_meta", lambda *_args: {})
    monkeypatch.setattr(discrepancy_export, "_load_grade_dates", lambda *_args: {})
    row = ExportTaskRow(
        task_id=1, task_uuid="task-1", disease="Disease A", lab_unit="Lab",
        hospital="Hospital", state="completed", consensus_status=None,
        consensus_method=None, final_impression="Positive", final_plus_review=None,
        grading_details_json="[]", ai_review_comments=[], ai_review_statuses=[],
        image_uuid="image-1", encounter_file_id=None, encounter_file_uuid=None,
        encounter_filename=None, encounter_upload_date=None, direct_image_upload_id=None,
        direct_image_uuid=None, direct_filename=None, direct_edited_filename=None,
        direct_folder_rel=None,
    )
    payload = discrepancy_export._build_task_payload([row])[0]
    assert payload["image_path"] == tmp_path / "encounter-folder" / "edited.jpg"
    assert payload["encounter_uuid"] == "encounter-1"
    assert payload["image_filename"] == "image-1.jpg"


def test_iitk_jsonl_and_coco_sidecar_use_pixel_boxes_and_final_role(tmp_path):
    image_path = tmp_path / "source.png"
    Image.new("RGB", (20, 15)).save(image_path)
    row = {**_row(1, "task-1", "image-1", "OSN"),
           "image_filename": "image-1.png", "encounter_uuid": "encounter-1",
           "image_path": image_path}
    exported_images = {}
    image_zip, warnings = _write_zips([row], tmp_path, exported_images=exported_images)
    assert warnings == []
    instance = {
        "uuid": "instance-1", "image_uuid": "image-1", "class_source": "project_class",
        "class_key": "lesion", "class_label": "Lesion", "geometry_type": "box",
        "bbox": [2, 3, 5, 4], "geometry": {}, "mask_tiles": [],
    }
    manifest = {"tasks": [{
        "task_uuid": "task-1", "image_uuid": "image-1", "disease": "OSN",
        "final_grade": "Positive",
        "grades": [
            {"grade_id": 1, "role_slot": "resident", "grade_name": "Positive", "annotation_set": {"instances": [instance]}},
            {"grade_id": 2, "role_slot": "arbitrator", "grade_name": "Positive", "annotation_set": {"instances": [instance]}},
        ],
    }]}
    assert annotation_export.write_coco_exports(manifest, exported_images, tmp_path) == []
    label = json.loads((tmp_path / "annotations.jsonl").read_text())
    assert label["schema"] == "aiims-eom-v1"
    assert label["labels"]["boxes"] == [{"x": 2.0, "y": 3.0, "w": 5.0, "h": 4.0, "cls": "lesion"}]
    coco = json.loads((tmp_path / "coco.json").read_text())
    coco_line = json.loads((tmp_path / "coco.jsonl").read_text())
    assert coco_line["image"] == coco["images"][0]
    assert coco_line["annotations"] == coco["annotations"]
    assert coco["images"][0]["width"] == 20
    assert len(coco["annotations"]) == 1
    assert coco["annotations"][0]["bbox"] == [2.0, 3.0, 5.0, 4.0]
    assert coco["annotations"][0]["source_role_slot"] == "arbitrator"
    assert coco["annotations"][0]["task_final_grade"] == "Positive"
    assert coco_line["task_grades"][0]["annotation_source_role_slot"] == "arbitrator"
    assert coco["categories"] == [{"id": 1, "name": "lesion"}]
    annotation_export.write_annotator_exports(manifest, exported_images, tmp_path)
    annotator_records = [json.loads(line) for line in (tmp_path / "annotator_submissions.jsonl").read_text().splitlines()]
    assert [record["role_slot"] for record in annotator_records] == ["resident", "arbitrator"]
    with ZipFile(image_zip[0]) as archive:
        assert "EncounterSets/encounter-1/image-1.coco.jsonl" in archive.namelist()
        assert "EncounterSets/encounter-1/image-1.annotators.jsonl" in archive.namelist()
        sidecar = json.loads(archive.read("EncounterSets/encounter-1/image-1.coco.jsonl"))
        assert sidecar["image"]["file_name"] == "EncounterSets/encounter-1/image-1.png"


def test_coco_falls_back_to_annotated_lower_role():
    annotated = {"grade_id": 1, "role_slot": "resident", "annotation_set": {
        "instances": [{"geometry_type": "box"}],
    }}
    unannotated_g2 = {"grade_id": 2, "role_slot": "resident2", "annotation_set": {
        "instances": [],
    }}
    unannotated_adjudicator = {"grade_id": 3, "role_slot": "arbitrator", "annotation_set": None}
    assert annotation_export._selected_human_grade(
        [annotated, unannotated_g2, unannotated_adjudicator]
    ) is annotated


def test_coco_records_keep_later_grade_separate_from_earlier_class(tmp_path):
    zip_path = tmp_path / "1.zip"
    with ZipFile(zip_path, "w"):
        pass
    image = {"file_name": "EncounterSets/encounter-1/image-1.jpg", "width": 20,
             "height": 20, "zip_path": zip_path, "encounter_uuid": "encounter-1"}
    instance = {"image_uuid": "image-1", "class_source": "project_class",
                "class_key": "lesion", "class_label": "Lesion", "geometry_type": "box",
                "bbox": [1, 2, 3, 4], "geometry": {}, "mask_tiles": []}
    manifest = {"tasks": [{"task_uuid": "task-1", "image_uuid": "image-1",
                          "disease": "OSN", "final_grade": "Negative", "grades": [
        {"grade_id": 1, "role_slot": "resident", "grade_name": "Positive",
         "annotation_set": {"instances": [instance]}},
        {"grade_id": 2, "role_slot": "arbitrator", "grade_name": "Negative",
         "annotation_set": {"instances": []}},
    ]}]}
    annotation_export.write_coco_exports(manifest, {"image-1": image}, tmp_path)
    record = json.loads((tmp_path / "coco.jsonl").read_text())
    assert record["task_grades"][0]["highest_human_grade"] == "Negative"
    assert record["task_grades"][0]["annotation_source_role_slot"] == "resident"
    assert record["annotations"][0]["task_final_grade"] == "Negative"
    assert record["annotations"][0]["annotation_source_grade"] == "Positive"


def test_coco_mask_tiles_become_column_major_rle():
    from io import BytesIO

    tile = Image.new("L", (2, 2), 0)
    tile.putpixel((1, 0), 255)
    output = BytesIO()
    tile.save(output, format="PNG")
    instance = {
        "bbox": [1, 0, 1, 1], "geometry": {}, "geometry_type": "brush_mask",
        "mask_tiles": [{"tile_x": 0, "tile_y": 0, "width": 2, "height": 2,
                        "png_base64": base64.b64encode(output.getvalue()).decode()}],
    }
    annotation = annotation_export.coco_annotation(instance, 2, 2)
    assert annotation["segmentation"] == {"size": [2, 2], "counts": [2, 1, 1]}
    assert annotation["area"] == 1


def test_coco_polygon_uses_pixel_points_and_area():
    instance = {
        "bbox": [1, 1, 4, 3], "geometry_type": "polygon", "mask_tiles": [],
        "geometry": {"polygon": {"pixel": [[1, 1], [5, 1], [5, 4], [1, 4]]}},
    }
    annotation = annotation_export.coco_annotation(instance, 10, 10)
    assert annotation["segmentation"] == [[1, 1, 5, 1, 5, 4, 1, 4]]
    assert annotation["area"] == 12

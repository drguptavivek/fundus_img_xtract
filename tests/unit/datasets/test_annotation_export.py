import base64
import json
from contextlib import contextmanager
from types import SimpleNamespace
from zipfile import ZipFile

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

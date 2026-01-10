import json
from datetime import timezone

from models import Session, AdHocTaskCreation, GradingTask, Disease, LabUnit


def test_ad_hoc_batch_persist_and_link():
    with Session() as session:
        # Pre-reqs: a disease and lab unit may already exist in fixtures; if not, skip linking
        batch = AdHocTaskCreation(
            created_by_id=1,
            diseases_json=json.dumps([1]),
            max_images=5,
            filters_json=json.dumps({'source': 'direct'}),
            selected_image_refs_json=json.dumps([]),
        )
        session.add(batch)
        session.flush()

        # Can assign ad_hoc_id on a GradingTask if present (no image linkage created here)
        # Just verify column exists and can be set NULL/INT without commit errors
        gt = GradingTask(
            disease_id=1,
            lab_unit_id=1,
            state='pending',
            ad_hoc_id=batch.id,
            direct_image_upload_id=1,
        )
        session.add(gt)
        session.commit()

        assert batch.id is not None
        assert gt.ad_hoc_id == batch.id


from pathlib import Path

from scripts.review_grade_correction_20260808 import parse_log_files


def test_parser_imports_structured_evidence_without_ip_or_free_text(tmp_path: Path):
    log_path = tmp_path / "grades.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-05-06 04:15:44,553 [INFO] grades Grade submission "
                "[IP: 10.2.3.4] [user_id: 13] [Task ID: 4319] [Slot Type: review] "
                "[Disease ID: 1] [Grade: 1] [Type: revision] [Grade ID: 11719] "
                "[Comments - identifiable free text] [Previous Grade: 1]",
                "2026-05-06 04:15:44,553 [INFO] grades Consensus override via review "
                "[user_id: 13] [task_id: 4319] [new_grade_id: 1] "
                "[prev_method: match] [prev_grade_id: 1]",
                "2026-05-06 04:15:44,553 [INFO] grades AI review feedback "
                "[user_id: 13] [task_id: 4319] AI grade 9382 status=ok "
                "model=wai_glaucoma_ver1",
            ]
        ),
        encoding="utf-8",
    )

    evidence = parse_log_files([log_path])

    review_event = evidence.review_events_by_task[4319][0]
    assert review_event["actor_user_id"] == 13
    assert review_event["submitted_disease_grading_id"] == 1
    assert review_event["logged_grade_id"] == 11719
    assert "ip" not in review_event
    assert "comment" not in review_event
    assert "identifiable free text" not in str(review_event)
    assert evidence.consensus_events_by_task[4319][0]["previous_method"] == "match"
    assert evidence.ai_events_by_grade[9382][0]["status"] == "ok"
    assert evidence.source_manifest[0]["sha256"]


def test_parser_preserves_repeated_ai_feedback_as_ordered_history(tmp_path: Path):
    old_log = tmp_path / "grades.log.1"
    current_log = tmp_path / "grades.log"
    old_log.write_text(
        "2025-12-03 09:47:10,500 [INFO] grades AI review feedback "
        "[user_id: 7] [task_id: 99] AI grade 500 status=minor_miss model=model_v1\n",
        encoding="utf-8",
    )
    current_log.write_text(
        "2026-05-06 10:00:00,000 [INFO] grades AI review feedback "
        "[user_id: 8] [task_id: 99] AI grade 500 status=ok model=model_v1\n",
        encoding="utf-8",
    )

    evidence = parse_log_files([current_log, old_log])

    history = evidence.ai_events_by_grade[500]
    assert [event["actor_user_id"] for event in history] == [7, 8]
    assert [event["status"] for event in history] == ["minor_miss", "ok"]

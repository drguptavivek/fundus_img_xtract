from encounter_sets import post_processing


def test_run_pii_flag_reaches_the_data_task_inline(monkeypatch):
    calls = []

    class Task:
        def __init__(self, name):
            self.name = name

        def run(self, *args, **kwargs):
            calls.append((self.name, args, kwargs))
            return {"set_image_id": 1, "status": "ok"}

    import celery_tasks.tasks.encounter_set_tasks as tasks
    import utils.celery_helpers as helpers

    monkeypatch.setattr(helpers, "celery_enabled", lambda: False)
    monkeypatch.setattr(tasks, "process_encounter_set_image_thumbnail_task", Task("thumb"))
    monkeypatch.setattr(tasks, "process_encounter_set_image_data_combined_task", Task("data"))

    assert post_processing.queue_image_post_processing([1], run_pii=False) == 1
    assert calls[-1][0] == "data" and calls[-1][2] == {"run_pii": False}
    post_processing.queue_image_post_processing([1])
    assert calls[-1][2] == {"run_pii": True}

"""Patient identifiers belong to the pre-grading steps only.

Capturing, uploading and verifying an encounter all require identifying the
patient. From grading onwards the work is on the image, so identifiers are
masked: grading, discrepancy review, regrade adjudication, intra-rater work,
analytics and datasets never need them.

The distinction is a property of the action, not of the actor's roles.
Deciding it from roles alone unmasks a grader who also happens to upload -
on the grading screen itself - and seven of this deployment's active users
hold exactly that combination.
"""

import pytest

from authz.policies import POLICIES, PRE_GRADING_ACTIONS, action_shows_pii

POST_GRADING = [
    "grading.resident.submit",
    "grading.resident2.submit",
    "grading.arbitrator.submit",
    "grading.grades.view",
    "review.discrepancy.view",
    "review.discrepancy.export",
    "review.task.view",
    "review.task.submit",
    "review.regrade.adjudicate",
    "intra_rater.task.view",
    "intra_rater.task.submit",
    "intra_rater.batch.view",
    "analytics.encounters.view",
    "analytics.kpi.encounter_files.rows",
    "analytics.kpi.direct_files.rows",
    "dataset.curation.view",
    "dataset.export.create",
    "dataset.export.download",
    "tasks.view",
    "tasks.viewer.view",
]


@pytest.mark.parametrize("action", sorted(PRE_GRADING_ACTIONS))
def test_pre_grading_actions_may_show_identifiers(action):
    assert action in POLICIES, f"{action} is listed as pre-grading but is not registered"
    assert action_shows_pii(action)


@pytest.mark.parametrize("action", POST_GRADING)
def test_grading_and_onwards_never_shows_identifiers(action):
    assert not action_shows_pii(action)


def test_an_unclassified_action_masks():
    """A surface nobody has classified conceals rather than reveals."""
    assert not action_shows_pii("no.such.action")


def test_every_pii_action_is_pre_grading():
    """Nothing outside the declared list may show identifiers."""
    showing = {a for a, p in POLICIES.items() if p.shows_pii}
    assert showing == set(PRE_GRADING_ACTIONS) & set(POLICIES)


def test_no_grading_or_review_action_is_marked_pre_grading():
    offenders = sorted(
        a for a in PRE_GRADING_ACTIONS
        if a.startswith(("grading.", "review.", "intra_rater.", "dataset.", "analytics."))
    )
    assert not offenders, f"these belong after grading: {offenders}"

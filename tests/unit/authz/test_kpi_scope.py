"""Aggregate KPIs report a lab's throughput; row-level KPIs disclose data.

The two are deliberately scoped differently. A count of what a lab captured
is a fact about that lab's own work, so lab scope reaches it whether or not
the image belongs to a project. A per-image listing or export is a
disclosure, so project rows there need an explicit project grant.
"""

import pytest

from authz import ResourceRef, authorize
from authz.policies import POLICIES
from authz.types import AuthzActor, GrantSource, RelationshipGrant

HOSPITAL_ID, LAB_ID, PROJECT_ID = 1, 10, 5

AGGREGATE = [
    "analytics.kpi.encounter_files.view",
    "analytics.kpi.direct_files.view",
    "analytics.upload_stats.view",
    "analytics.hospital_dashboard.view",
]
ROW_LEVEL = [
    "analytics.kpi.encounter_files.rows",
    "analytics.kpi.direct_files.rows",
]


def _analyst():
    return AuthzActor(id=1, roles=frozenset({"analytics_viewer"}), hospital_id=HOSPITAL_ID)


def _lab_grant():
    return RelationshipGrant(source=GrantSource.LAB_UNIT_ASSIGNMENT, lab_unit_id=LAB_ID)


def _image(project_id):
    return ResourceRef(type="image", id=1, attributes={
        "project_id": project_id, "hospital_id": HOSPITAL_ID, "lab_unit_id": LAB_ID})


@pytest.mark.parametrize("action", AGGREGATE)
def test_aggregate_counts_a_non_project_image_in_my_lab(action):
    assert authorize(_analyst(), action, _image(None), grants=[_lab_grant()]).allowed


@pytest.mark.parametrize("action", AGGREGATE)
def test_aggregate_also_counts_a_project_image_in_my_lab(action):
    """Throughput of your own lab, whoever owns the image."""
    assert authorize(_analyst(), action, _image(PROJECT_ID), grants=[_lab_grant()]).allowed


@pytest.mark.parametrize("action", AGGREGATE)
def test_aggregate_does_not_reach_another_lab(action):
    """Not project-gated does not mean unscoped."""
    other = ResourceRef(type="image", id=2, attributes={
        "project_id": None, "hospital_id": HOSPITAL_ID, "lab_unit_id": 99})
    assert not authorize(_analyst(), action, other, grants=[_lab_grant()]).allowed


@pytest.mark.parametrize("action", ROW_LEVEL)
def test_row_level_returns_a_non_project_image_in_my_lab(action):
    assert authorize(_analyst(), action, _image(None), grants=[_lab_grant()]).allowed


@pytest.mark.parametrize("action", ROW_LEVEL)
def test_row_level_withholds_a_project_image_without_a_grant(action):
    """The disclosure surface stays project-gated."""
    assert not authorize(_analyst(), action, _image(PROJECT_ID), grants=[_lab_grant()]).allowed


@pytest.mark.parametrize("action", ROW_LEVEL)
def test_row_level_returns_a_project_image_with_a_grant(action):
    grant = RelationshipGrant(
        source=GrantSource.PROJECT_ROLE,
        attributes={"project_id": PROJECT_ID, "hospital_id": None, "lab_unit_id": None,
                    "role_names": frozenset({"analytics_viewer"})},
    )
    assert authorize(_analyst(), action, _image(PROJECT_ID), grants=[_lab_grant(), grant]).allowed


def test_only_aggregate_kpis_are_ungated():
    """project_gated=False is a deliberate, narrow exception."""
    ungated = sorted(a for a, p in POLICIES.items() if not p.project_gated and not p.public)
    assert ungated == sorted(AGGREGATE), f"unexpected ungated actions: {ungated}"


@pytest.mark.parametrize("action", AGGREGATE)
def test_ungated_actions_never_accept_a_project_relationship(action):
    """An ungated action reports throughput; it must not also be a project surface."""
    policy = POLICIES[action]
    project_sources = {GrantSource.PROJECT_ROLE, GrantSource.LEGACY_PROJECT_CAPABILITY,
                       GrantSource.PROJECT_COLLABORATOR}
    assert not (policy.grant_sources & project_sources)

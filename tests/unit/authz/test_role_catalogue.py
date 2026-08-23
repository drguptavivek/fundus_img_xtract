"""Every role in the catalogue must actually do something.

A role nobody can use is worse than absent: it looks assignable in the admin
UI and confers nothing, which reads as a permissions bug to whoever grants
it. Designations - who someone *is* on a project - are recorded on
project_investigators and are deliberately not roles.
"""

from auth.roles import DEFAULT_ROLES
from authz.policies import POLICIES

DESIGNATIONS = {"principal_investigator", "co_investigator", "coordinator"}


def _roles_used_by_policies() -> set[str]:
    used: set[str] = set()
    for policy in POLICIES.values():
        used |= policy.roles | policy.roles_for_project() | policy.owner_roles
    return used


def test_every_catalogued_role_authorizes_something():
    unusable = sorted(set(DEFAULT_ROLES) - _roles_used_by_policies())
    assert not unusable, f"roles that confer nothing: {unusable}"


def test_designations_are_not_roles():
    """A designation describes a person on a project; it grants nothing."""
    assert not (DESIGNATIONS & set(DEFAULT_ROLES))


def test_no_policy_grants_authority_to_a_designation():
    offenders = sorted(DESIGNATIONS & _roles_used_by_policies())
    assert not offenders, f"designations used as authorization roles: {offenders}"


# --- project oversight -------------------------------------------------------

OVERSIGHT = {"project_pi", "site_pi", "project_admin", "collaborator"}


def _project_actions(role: str) -> set[str]:
    return {a for a, p in POLICIES.items() if role in p.roles_for_project()}


def test_collaborator_never_reaches_patient_identifiers():
    """The non-PII browser role for international collaborators."""
    showing = sorted(a for a in _project_actions("collaborator") if POLICIES[a].shows_pii)
    assert not showing, f"collaborator must not reach identifiers: {showing}"


def test_collaborator_does_not_ingest_data():
    """Browsing is not uploading."""
    uploads = sorted(a for a in _project_actions("collaborator") if a.startswith("project.upload."))
    assert not uploads


def test_collaborator_cannot_read_identifiers_off_an_image():
    """OCR'd text is still an identifier."""
    assert "media.ocr_pii.read" not in _project_actions("collaborator")
    assert "media.ocr_pii.process" not in _project_actions("collaborator")


def test_oversight_roles_can_follow_the_project():
    """Designations exist to see how the project is going."""
    for role in sorted(OVERSIGHT):
        actions = _project_actions(role)
        assert "project.view" in actions, role                       # setup, people, scheme
        assert "project.encountersets.browse" in actions, role       # the uploads themselves
        assert "analytics.encounters.view" in actions, role          # progress
        assert "tasks.view" in actions, role                         # grading statistics


def test_oversight_is_read_only():
    """Oversight observes; it does not grade, verify or adjudicate."""
    for role in sorted(OVERSIGHT):
        actions = _project_actions(role)
        assert not {a for a in actions if a.startswith("grading.")}, role
        assert not {a for a in actions if a.startswith("verification.")}, role
        assert "review.regrade.adjudicate" not in actions, role

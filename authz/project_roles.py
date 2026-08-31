"""Project role names and the small delegation matrix.

These are relationship facts, not route actions.  A caller still chooses the
named scope helper appropriate to the record it is reading or changing.
"""

PROJECT_PI = "project_pi"
SITE_PI = "site_pi"
PROJECT_ADMIN = "project_admin"
DATA_MANAGER = "data_manager"
PII_EXPORTER = "pii_exporter"

PROJECT_GOVERNANCE_ROLES = frozenset({PROJECT_PI, SITE_PI, PROJECT_ADMIN})
PROJECT_OPERATIONAL_ROLES = frozenset(
    {
        "collaborator",
        "verifier",
        "ophthalmologist",
        "optometrist",
        "analytics_viewer",
        "dataset_creator",
        DATA_MANAGER,
        "data_exporter",
        PII_EXPORTER,
        "discrepancy_reviewer",
        "regrade_adjudicator",
    }
)
PROJECT_ASSIGNABLE_ROLES = PROJECT_GOVERNANCE_ROLES | PROJECT_OPERATIONAL_ROLES

# PII release is deliberately exceptional: a project-wide Project Admin may
# delegate it, but a site-scoped Project Admin may not.  Keeping it out of the
# ordinary set makes that ceiling visible and independently testable.
PROJECT_ADMIN_STANDARD_DELEGABLE_ROLES = PROJECT_OPERATIONAL_ROLES - {PII_EXPORTER}

# System Admin alone appoints either PI role.  PIs appoint Project Admins inside
# their own scope.  Project Admins appoint operational roles inside theirs.
PI_DELEGATORS = frozenset({PROJECT_PI, SITE_PI})
PROJECT_ADMIN_DELEGATORS = frozenset({PROJECT_ADMIN})


def role_allows_scope(*, role_name: str, scope_type: str) -> bool:
    """Return whether a project role has a valid structural scope shape."""
    if role_name == PROJECT_PI:
        return scope_type == "project"
    if role_name == SITE_PI:
        return scope_type == "lab_unit"
    return role_name in PROJECT_ASSIGNABLE_ROLES and scope_type in {
        "project",
        "lab_unit",
    }

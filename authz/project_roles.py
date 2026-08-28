"""Project role names and the small delegation matrix.

These are relationship facts, not route actions.  A caller still chooses the
named scope helper appropriate to the record it is reading or changing.
"""

PROJECT_PI = "project_pi"
SITE_PI = "site_pi"
PROJECT_ADMIN = "project_admin"

PROJECT_GOVERNANCE_ROLES = frozenset({PROJECT_PI, SITE_PI, PROJECT_ADMIN})
PROJECT_OPERATIONAL_ROLES = frozenset(
    {
        "collaborator",
        "verifier",
        "ophthalmologist",
        "optometrist",
        "analytics_viewer",
        "dataset_creator",
        "data_exporter",
        "discrepancy_reviewer",
        "regrade_adjudicator",
    }
)
PROJECT_ASSIGNABLE_ROLES = PROJECT_GOVERNANCE_ROLES | PROJECT_OPERATIONAL_ROLES

# System Admin alone appoints either PI role.  PIs appoint Project Admins inside
# their own scope.  Project Admins appoint operational roles inside theirs.
PI_DELEGATORS = frozenset({PROJECT_PI, SITE_PI})
PROJECT_ADMIN_DELEGATORS = frozenset({PROJECT_ADMIN})

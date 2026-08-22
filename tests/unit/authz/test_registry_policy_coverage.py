"""Every registered action must have an executable policy, and vice versa.

Before this invariant existed, 62 of 78 registered actions had no policy, so
``authz.authorize`` returned ``deny("unknown_action")`` for them. A silent deny
is indistinguishable from a real denial at the call site, so the gap could not
be seen from behaviour alone.
"""

from authz.policies import POLICIES
from authz.registry import load_action_registry
from authz.types import GrantSource


def test_every_registered_action_has_a_policy() -> None:
    missing = sorted(set(load_action_registry()) - set(POLICIES))
    assert not missing, f"registered actions without a policy: {missing}"


def test_every_policy_has_a_registered_action() -> None:
    orphaned = sorted(set(POLICIES) - set(load_action_registry()))
    assert not orphaned, f"policies with no registered action: {orphaned}"


def test_non_public_policies_declare_a_grant_source() -> None:
    """A non-public policy with no grant source can never allow anything."""
    unreachable = sorted(
        action
        for action, policy in POLICIES.items()
        if not policy.public and not policy.grant_sources
    )
    assert not unreachable, f"policies that can never allow: {unreachable}"


def test_project_actions_never_rely_on_classical_scope_alone() -> None:
    """Project rows must require an explicit project relationship.

    Hospital or lab-unit membership alone must never authorize a project
    resource; that is the leak this migration exists to close.
    """
    classical_only = {
        GrantSource.ADMIN_GLOBAL,
        GrantSource.HOSPITAL_SCOPE,
        GrantSource.LAB_UNIT_ASSIGNMENT,
    }
    offenders = sorted(
        action
        for action, policy in POLICIES.items()
        if action.startswith("project.") and not (policy.grant_sources - classical_only)
    )
    assert not offenders, f"project actions authorized by classical scope alone: {offenders}"

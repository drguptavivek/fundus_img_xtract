from pathlib import Path

from authz.policies import POLICIES


POLICY_DOC = Path("docs/policy/authorizations.md")


def test_executable_policies_have_human_readable_rules() -> None:
    text = POLICY_DOC.read_text(encoding="utf-8")

    for action in POLICIES:
        assert f"### `{action}`" in text
        assert f"- Rule:" in text


def test_policy_doc_states_the_migration_gate() -> None:
    text = POLICY_DOC.read_text(encoding="utf-8")

    assert "Do not wire a route to an authorization action until this document has a rule for that action." in text
    assert "When code and this document disagree, stop and update the policy before changing enforcement." in text

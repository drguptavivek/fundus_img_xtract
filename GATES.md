# Authz v2 foundation: domain isolation

- [x] G1 Core policy code imports no application-domain modules.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py::test_authz_core_has_no_application_domain_imports -q'
  EXPECT: exit 0
  EVIDENCE: Passed in Docker as part of the 3-test domain-boundary suite.

- [x] G2 Authz sources contain no enumerated clinical, imaging, workflow, or upload-content fields.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py::test_authz_does_not_encode_application_workflow_or_content_rules -q'
  EXPECT: exit 0
  EVIDENCE: Passed in Docker as part of the 3-test domain-boundary suite.

- [x] G3 Generic authorization-state facts remain limited to approved resource adapters.
  CHECK: make test PYTEST_ARGS='tests/unit/authz_v2/test_domain_boundary.py::test_domain_valid_is_limited_to_authorization_state_inputs -q'
  EXPECT: exit 0
  EVIDENCE: Docker run passed all 3 domain-boundary tests in 6.55s.

from __future__ import annotations

from sqlalchemy import select

from authz_v2.core.catalogue import CATALOGUE
from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.resources.adapters import TypedResourceRef
from authz_v2.resources.composition import register_core_adapters
from authz_v2.resources.references import AutomationTargetRef
from authz_v2.resources.registry import ResourceRegistry
from authz_v2.resources.scoping import scope_model_query
from authz_v2.resources.upload_targets import UploadTargetRef
from models import DirectImageUpload


def test_composition_registers_every_catalogue_resource_exactly_once():
    resources = ResourceRegistry()
    register_core_adapters(resources)
    required = {
        definition.resource_type
        for definition in CATALOGUE.values()
        if definition.requires_resource
    }
    assert resources.types() == required
    register_core_adapters(resources)
    assert resources.types() == required


def test_polymorphic_resource_families_reject_ambiguous_integer_references():
    resources = ResourceRegistry()
    register_core_adapters(resources)

    class NoDatabaseCalls:
        def get(self, *_args):
            raise AssertionError(
                "ambiguous reference must be rejected before DB access"
            )

    for resource_type in ("image", "encounter_file", "report", "inference_result"):
        assert resources.require(resource_type).resolver(NoDatabaseCalls(), 1) is None
    assert isinstance(TypedResourceRef("direct", 1), TypedResourceRef)

    assert (
        resources.require("project_upload_target").resolver(NoDatabaseCalls(), 1)
        is None
    )
    assert resources.require("upload_target").resolver(NoDatabaseCalls(), 1) is None


def test_every_resource_adapter_rejects_missing_or_non_positive_references():
    resources = ResourceRegistry()
    register_core_adapters(resources)

    class NoDatabaseCalls:
        def get(self, *_args):
            raise AssertionError("invalid reference reached the database")

        def execute(self, *_args):
            raise AssertionError("invalid reference reached the database")

    db = NoDatabaseCalls()
    for resource_type in resources.types():
        resolver = resources.require(resource_type).resolver
        for invalid in (None, True, False, 0, -1, "", "   "):
            assert resolver(db, invalid) is None, (resource_type, invalid)

    for resource_type in ("image", "encounter_file", "report", "inference_result"):
        assert (
            resources.require(resource_type).resolver(
                db, TypedResourceRef("direct", True)
            )
            is None
        )
    for resource_type in ("upload_target", "project_upload_target"):
        assert (
            resources.require(resource_type).resolver(db, UploadTargetRef(True, 1))
            is None
        )
    for resource_type in ("job", "project"):
        assert (
            resources.require(resource_type).resolver(db, AutomationTargetRef(1, True))
            is None
        )


def test_sql_scoper_never_uses_non_admin_system_grant_as_global_bypass():
    principal = PrincipalDTO(1, True, True)
    system_non_admin = GrantRecord(
        1, 1, Role.DATA_MANAGER, ScopeDTO(ScopeType.SYSTEM), True
    )
    query = scope_model_query(
        DirectImageUpload, (system_non_admin,), select(DirectImageUpload)
    )
    assert "WHERE false" in str(query)

    system_admin = GrantRecord(2, 1, Role.ADMIN, ScopeDTO(ScopeType.SYSTEM), True)
    unfiltered = scope_model_query(
        DirectImageUpload, (system_admin,), select(DirectImageUpload)
    )
    assert "WHERE" not in str(unfiltered)
    assert principal.authenticated


def test_classical_scope_filter_excludes_project_owned_rows():
    hospital = ScopeDTO(ScopeType.HOSPITAL, 10, hospital_id=10)
    grant = GrantRecord(1, 1, Role.DATA_MANAGER, hospital, True)
    query = scope_model_query(DirectImageUpload, (grant,), select(DirectImageUpload))
    sql = str(query)
    assert "direct_image_uploads.project_id IS NULL" in sql
    assert "direct_image_uploads.hospital_id IN" in sql

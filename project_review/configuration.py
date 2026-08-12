"""Effective, non-PII configuration read model for a project."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from data_authorization.models import ProjectRoleGrant
from grading_allocation.models import ProjectGraderAllocation, ProjectGradingAllocationPolicy
from grading_schemes.service import sanitize_guidelines_html
from iitk_api_integration.models import IITKApiProjectConfig
from models import Disease, DiseaseGrading, LinkedDiseaseGrading, ProjectReferralDisease
from project_annotations.models import ProjectAnnotationPolicy
from remote_inference.models import ProjectAutomatedRemoteInferenceRule, ProjectManualRemoteInferenceWorkflow
from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding
from upload_profiles.models import ProjectUploadProfile

from .dto import (
    AnnotationConfigurationDTO, ConfiguredUserDTO, DiseaseDefinitionDTO, GradeChoiceDTO,
    GradingTargetDTO, MetadataFieldDTO, ProjectAnalysisDTO, ProjectSourceDTO,
    ReferralDiseaseDTO,
)


def effective_configuration(db: Session, *, project_id: int, allowed_lab_ids: frozenset[int] | None) -> dict:
    """Build currently enabled configuration. ``None`` means project-wide visibility."""
    mappings = db.execute(
        select(ProjectUploadProfile)
        .options(
            selectinload(ProjectUploadProfile.profile),
            selectinload(ProjectUploadProfile.assignments),
        )
        .where(ProjectUploadProfile.project_id == project_id, ProjectUploadProfile.active.is_(True))
    ).scalars().all()
    mappings = [m for m in mappings if m.profile.active]
    return {
        "sources": _sources(db, project_id, mappings, allowed_lab_ids),
        "automated_analyses": _analyses(db, project_id),
        "grading_targets": _targets(db, mappings),
        "annotation": _annotation(db, project_id),
        "metadata_fields": _metadata(mappings),
        "configured_users": _users(db, project_id, mappings, allowed_lab_ids),
        "allocation_enforced": bool(db.execute(select(ProjectGradingAllocationPolicy.enforcement_enabled).where(
            ProjectGradingAllocationPolicy.project_id == project_id
        )).scalar_one_or_none()),
        "referral_diseases": _referrals(db, project_id, mappings),
    }


def _sources(db, project_id, mappings, allowed_lab_ids):
    rows = []
    for mapping in mappings:
        p = mapping.profile
        assignments = [a for a in mapping.assignments if a.active and _lab_visible(a.lab_unit_id, allowed_lab_ids)]
        details = [
            ("Upload modes", _labels(x.upload_kind for x in p.upload_kinds)),
            ("Diseases", _labels(f"{x.disease.name}{' (default)' if x.is_default else ''}" for x in p.diseases)),
            ("Cameras", _labels(x.camera.name for x in p.cameras)),
            ("Areas / sites", _labels(x.area.name for x in p.areas)),
            ("Dilation", _dilation(p)),
            ("EncounterSet types", _labels(x.encounter_set_type.name for x in p.encounter_set_types if x.active)),
            ("ZIP intake", _labels(x for x, enabled in (("Remidio ZIP", p.allow_remidio_zip_encounter_set), ("IITK ZIP", p.allow_iitk_zip_encounter_set)) if enabled)),
            ("Authorised uploaders", _labels(f"{a.user.full_name or a.user.username} - {a.lab_unit.hospital.name} / {a.lab_unit.name}" for a in assignments)),
        ]
        rows.append(ProjectSourceDTO(
            id=f"profile-{mapping.id}", kind="Upload profile", name=p.name,
            summary=_labels(x.upload_kind for x in p.upload_kinds),
            badges=tuple(sorted(x.upload_kind.replace("_", " ").title() for x in p.upload_kinds)),
            details=tuple((k, v) for k, v in details if v and v != "None"),
        ))

    today = date.today()
    remidio = db.execute(select(ProjectUploadProfileRemidioApiBinding).options(
        selectinload(ProjectUploadProfileRemidioApiBinding.routing_profile),
        selectinload(ProjectUploadProfileRemidioApiBinding.source_rule),
        selectinload(ProjectUploadProfileRemidioApiBinding.project_profile).selectinload(ProjectUploadProfile.profile),
        selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit),
        selectinload(ProjectUploadProfileRemidioApiBinding.camera),
    ).join(ProjectUploadProfile).where(
        ProjectUploadProfile.project_id == project_id,
        ProjectUploadProfile.active.is_(True),
        ProjectUploadProfileRemidioApiBinding.active.is_(True),
        ProjectUploadProfileRemidioApiBinding.active_from_date <= today,
    )).scalars().all()
    remidio = [r for r in remidio if (r.active_to_date is None or r.active_to_date >= today)
               and r.source_rule.active and r.project_profile.profile.active
               and r.routing_profile is not None and r.routing_profile.active
               and _lab_visible(r.lab_unit_id, allowed_lab_ids)]
    if remidio:
        details = []
        for r in remidio:
            site = r.source_rule.site
            site_name = f" ({site.site_name})" if site and site.site_name else ""
            details.append((r.source_rule.site_custom_identifier + site_name,
                f"{r.source_rule.remidio_device_type}; {r.lab_unit.hospital.name} / {r.lab_unit.name}; "
                f"{r.camera.name}; {r.project_profile.profile.name}; {r.active_from_date} to {r.active_to_date or 'Open-ended'}"))
        rows.append(ProjectSourceDTO(
            id="remidio-api", kind="API intake", name="Remidio API",
            summary=f"{len(remidio)} active route{'s' if len(remidio) != 1 else ''}",
            badges=tuple(sorted({r.source_rule.site_custom_identifier for r in remidio})), details=tuple(details)))

    iitk = db.execute(select(IITKApiProjectConfig).options(
        selectinload(IITKApiProjectConfig.lab_unit), selectinload(IITKApiProjectConfig.project_profile).selectinload(ProjectUploadProfile.profile),
        selectinload(IITKApiProjectConfig.encounter_set_type), selectinload(IITKApiProjectConfig.camera),
    ).where(IITKApiProjectConfig.project_id == project_id, IITKApiProjectConfig.active.is_(True))).scalar_one_or_none()
    if iitk and iitk.project_profile.active and iitk.project_profile.profile.active and _lab_visible(iitk.lab_unit_id, allowed_lab_ids):
        rows.append(ProjectSourceDTO(id="iitk-api", kind="API intake", name="IITK API",
            summary=iitk.site_filter or "All configured sites", badges=(iitk.encounter_set_type.name,),
            details=(("Site filter", iitk.site_filter or "All configured sites"),
                     ("Destination", f"{iitk.lab_unit.hospital.name} / {iitk.lab_unit.name}"),
                     ("Upload profile", iitk.project_profile.profile.name),
                     ("EncounterSet type", iitk.encounter_set_type.name),
                     ("Camera", iitk.camera.name if iitk.camera else "Not fixed"),
                     ("Sync from", str(iitk.sync_from_date or "Not restricted")))))
    return tuple(rows)


def _analyses(db, project_id):
    result = []
    automated = db.execute(select(ProjectAutomatedRemoteInferenceRule).options(
        selectinload(ProjectAutomatedRemoteInferenceRule.disease), selectinload(ProjectAutomatedRemoteInferenceRule.ai_model)
    ).where(ProjectAutomatedRemoteInferenceRule.project_id == project_id, ProjectAutomatedRemoteInferenceRule.active.is_(True))
      .order_by(ProjectAutomatedRemoteInferenceRule.display_order)).scalars()
    manual = db.execute(select(ProjectManualRemoteInferenceWorkflow).options(
        selectinload(ProjectManualRemoteInferenceWorkflow.disease), selectinload(ProjectManualRemoteInferenceWorkflow.ai_model)
    ).where(ProjectManualRemoteInferenceWorkflow.project_id == project_id, ProjectManualRemoteInferenceWorkflow.active.is_(True))).scalars()
    for row, mode in [(r, "Automatic") for r in automated] + [(r, "Manual") for r in manual]:
        integration = row.ai_model.integration
        if integration is not None and not integration.is_enabled:
            continue
        result.append(ProjectAnalysisDTO(row.id, mode, f"{row.ai_model.name} {row.ai_model.version}",
            integration.provider if integration else "Local", row.disease.name, row.upload_kind,
            getattr(row, "trigger_timing", "User initiated"), getattr(row, "encounter_eligibility", "User selected"),
            getattr(row, "image_selection", "User selected")))
    return tuple(result)


def _targets(db, mappings):
    targets, seen = [], set()
    for mapping in mappings:
        p = mapping.profile
        kinds = {k.upload_kind for k in p.upload_kinds}
        if kinds & {"direct_image", "pregraded", "remidio"}:
            for link in p.diseases:
                if link.disease.grading_scope != "image":
                    continue
                key = ("single", link.disease_id, p.id)
                if key not in seen:
                    seen.add(key)
                    targets.append(GradingTargetDTO(f"single-{p.id}-{link.disease_id}", "Single-image disease-wise",
                        link.disease.name, p.name, "", "", "disease specific", "Uploader-selected",
                        "Uploader-selected", (), _definitions(db, link.disease, target_level="Image-level")))
        for est in p.encounter_set_types:
            if not est.active or not est.encounter_set_type.active:
                continue
            for package in est.grading_packages:
                if not package.active or package.applicability == "disabled":
                    continue
                encounter_schemes = [x for x in package.encounter_grading_schemes if x.active]
                primary = encounter_schemes[0].disease if encounter_schemes else package.default_image_grading_scheme
                root_id = _package_root_disease_id(package)
                root_scheme = next((x for x in package.image_grading_schemes if x.active and x.disease_id == root_id), None)
                active_image_schemes = [x for x in package.image_grading_schemes if x.active and x.auto_create_policy != "never"]
                task_creation = _human(package.applicability)
                rules = []
                if root_scheme and root_scheme.auto_create_policy == "positive_plus_negative_controls":
                    linked_names = [x.disease.name for x in active_image_schemes if x.disease_id != root_id]
                    image_scope = root_scheme.disease.name
                    if linked_names:
                        image_scope += " and linked " + ", ".join(linked_names)
                    task_creation = (
                        f"Referral-positive {root_scheme.disease.name} EncounterSets; plus "
                        f"{root_scheme.negative_controls_per_positive} {root_scheme.disease.name}-negative "
                        f"control EncounterSets per positive"
                    )
                    rules.append(f"Image grading scope: {image_scope} tasks on the same selected images")
                for scheme in package.image_grading_schemes:
                    if not scheme.active or scheme.auto_create_policy == "never":
                        continue
                    if root_scheme and root_scheme.auto_create_policy == "positive_plus_negative_controls":
                        if scheme.metadata_field_key:
                            rules.append(f"{scheme.disease.name}: only when {scheme.metadata_field_key} = {scheme.metadata_match_value}")
                        continue
                    rule = f"{scheme.disease.name}: {_human(scheme.auto_create_policy)}"
                    if scheme.negative_controls_per_positive:
                        rule += f" ({scheme.negative_controls_per_positive} negative control per positive)"
                    if scheme.metadata_field_key:
                        rule += f"; when {scheme.metadata_field_key} = {scheme.metadata_match_value}"
                    rules.append(rule)
                disease = primary.name if primary else "Unified EncounterSet"
                definitions = _package_definitions(
                    db,
                    package=package,
                    encounter_schemes=encounter_schemes,
                    root_id=root_id,
                )
                targets.append(GradingTargetDTO(f"package-{package.id}",
                    "EncounterSet unified tasks" if package.grading_mode == "unified" else "EncounterSet disease-scoped tasks",
                    disease, p.name, est.encounter_set_type.name, _clean_text(package.name), _human(package.grading_mode),
                    task_creation, _human(package.applicability), tuple(rules), definitions))
    return tuple(targets)


def _definitions(db, disease, *, target_level):
    if disease is None:
        return ()
    diseases = [(disease, "Primary")]
    linked = db.execute(select(LinkedDiseaseGrading).options(selectinload(LinkedDiseaseGrading.linked_disease)).where(
        LinkedDiseaseGrading.primary_disease_id == disease.id, LinkedDiseaseGrading.is_active.is_(True)
    ).order_by(LinkedDiseaseGrading.display_order)).scalars()
    diseases.extend((x.linked_disease, "Linked") for x in linked)
    result = []
    for item, relationship in diseases:
        grades = db.execute(select(DiseaseGrading).options(selectinload(DiseaseGrading.features)).where(
            DiseaseGrading.disease_id == item.id, DiseaseGrading.is_active.is_(True)
        ).order_by(DiseaseGrading.display_order)).scalars()
        result.append(DiseaseDefinitionDTO(item.name, target_level, relationship, tuple(
            GradeChoiceDTO(g.impression, sanitize_guidelines_html(g.guidelines) or "", tuple(f.label for f in sorted(g.features, key=lambda x: x.sr_no))) for g in grades)))
    return tuple(result)


def _definition(db, disease, *, target_level, relationship):
    grades = db.execute(select(DiseaseGrading).options(selectinload(DiseaseGrading.features)).where(
        DiseaseGrading.disease_id == disease.id, DiseaseGrading.is_active.is_(True)
    ).order_by(DiseaseGrading.display_order)).scalars()
    return DiseaseDefinitionDTO(disease.name, target_level, relationship, tuple(
        GradeChoiceDTO(g.impression, sanitize_guidelines_html(g.guidelines) or "", tuple(
            f.label for f in sorted(g.features, key=lambda x: x.sr_no)
        )) for g in grades))


def _package_definitions(db, *, package, encounter_schemes, root_id):
    image_schemes = [scheme for scheme in package.image_grading_schemes if scheme.active]
    if package.grading_mode != "unified":
        return tuple(
            [
                _definition(db, scheme.disease, target_level="Encounter-level", relationship="Encounter grade")
                for scheme in encounter_schemes
            ]
            + [
                _definition(
                    db, scheme.disease, target_level="Image-level",
                    relationship="Root disease" if scheme.disease_id == root_id else "Linked disease",
                )
                for scheme in image_schemes
            ]
        )

    definitions = [
        _definition(
            db,
            scheme.disease,
            target_level="EncounterSet-level",
            relationship="EncounterSet grading scheme",
        )
        for scheme in encounter_schemes
    ]
    definitions.extend(
        _definition(
            db,
            scheme.disease,
            target_level="Per-image",
            relationship="Per-image grading scheme",
        )
        for scheme in image_schemes
    )
    configured_ids = {scheme.disease_id for scheme in image_schemes}
    for scheme in image_schemes:
        linked = db.execute(
            select(LinkedDiseaseGrading)
            .options(selectinload(LinkedDiseaseGrading.linked_disease))
            .where(
                LinkedDiseaseGrading.primary_disease_id == scheme.disease_id,
                LinkedDiseaseGrading.is_active.is_(True),
            )
            .order_by(LinkedDiseaseGrading.display_order)
        ).scalars()
        definitions.extend(
            _definition(
                db,
                link.linked_disease,
                target_level="Linked disease",
                relationship=f"Linked to {scheme.disease.name}",
            )
            for link in linked
            if link.linked_disease_id not in configured_ids
        )
    return tuple(definitions)


def _package_root_disease_id(package):
    scope_config = package.scope_config_json or {}
    configured = scope_config.get("root_image_grading_scheme_id")
    if not configured:
        configured = next((
            scope.get("scope_disease_id")
            for scope in scope_config.get("scopes", [])
            if isinstance(scope, dict) and scope.get("link_role") == "root"
        ), None)
    try:
        return int(configured) if configured else None
    except (TypeError, ValueError):
        return None


def _annotation(db, project_id):
    policy = db.execute(select(ProjectAnnotationPolicy).options(
        selectinload(ProjectAnnotationPolicy.tools), selectinload(ProjectAnnotationPolicy.project_classes)
    ).where(ProjectAnnotationPolicy.project_id == project_id, ProjectAnnotationPolicy.enabled.is_(True))).scalar_one_or_none()
    if not policy:
        return None
    return AnnotationConfigurationDTO(policy.revision, _human(policy.default_localization), _human(policy.preferred_tool_key),
        tuple(_human(t.tool_key) for t in policy.tools if t.enabled),
        tuple((c.key, _human(c.localization), "Multiple" if c.multiple_instances else "Single")
              for c in sorted(policy.project_classes, key=lambda x: x.display_order) if c.active))


def _metadata(mappings):
    fields = {}
    for mapping in mappings:
        for est in mapping.profile.encounter_set_types:
            if not est.active or not est.encounter_set_type.active:
                continue
            source = f"{mapping.profile.name} / {est.encounter_set_type.name}"
            for field in (est.encounter_set_type.metadata_schema_json or {}).get("fields", []):
                key = str(field.get("key") or "").strip()
                if not key:
                    continue
                current = fields.setdefault(key, {**field, "sources": set()})
                current["sources"].add(source)
    result = []
    for key, f in sorted(fields.items(), key=lambda x: (str(x[1].get("scope", "")), str(x[1].get("label", x[0])))):
        options = tuple(str(x.get("label") or x.get("value")) if isinstance(x, dict) else str(x) for x in (f.get("options") or []))
        result.append(MetadataFieldDTO(key, str(f.get("label") or key), str(f.get("scope") or "encounter"),
            str(f.get("type") or f.get("field_type") or "text"), "Required" if f.get("required_at_upload") else "Optional",
            bool(f.get("editable_during_verification")), bool(f.get("is_pii")), options, tuple(sorted(f["sources"]))))
    return tuple(result)


def _users(db, project_id, mappings, allowed_lab_ids):
    grants = db.execute(select(ProjectRoleGrant).options(selectinload(ProjectRoleGrant.user), selectinload(ProjectRoleGrant.role),
        selectinload(ProjectRoleGrant.hospital), selectinload(ProjectRoleGrant.lab_unit)).where(
        ProjectRoleGrant.project_id == project_id, ProjectRoleGrant.active.is_(True))).scalars().all()
    grants = [g for g in grants if _grant_visible(g, allowed_lab_ids)]
    allocations = db.execute(select(ProjectGraderAllocation).options(selectinload(ProjectGraderAllocation.user),
        selectinload(ProjectGraderAllocation.lab_unit), selectinload(ProjectGraderAllocation.disease),
        selectinload(ProjectGraderAllocation.encounter_set_type)).where(
        ProjectGraderAllocation.project_id == project_id, ProjectGraderAllocation.active.is_(True))).scalars().all()
    allocations = [a for a in allocations if _lab_visible(a.lab_unit_id, allowed_lab_ids)]
    by_user = defaultdict(lambda: {"user": None, "scopes": set(), "roles": set(), "uploads": set(), "allocations": set()})
    for g in grants:
        x = by_user[g.user_id]; x["user"] = g.user; x["roles"].add(g.role.name)
        x["scopes"].add("Project-wide" if g.scope_type == "project" else
            f"Hospital: {g.hospital.name}" if g.scope_type == "hospital" else
            f"Lab unit: {g.lab_unit.hospital.name} / {g.lab_unit.name}")
    for mapping in mappings:
        for a in mapping.assignments:
            if a.active and _lab_visible(a.lab_unit_id, allowed_lab_ids):
                x = by_user[a.user_id]; x["user"] = a.user
                x["uploads"].add(f"{mapping.profile.name} - {a.lab_unit.hospital.name} / {a.lab_unit.name}")
    for a in allocations:
        x = by_user[a.user_id]; x["user"] = a.user
        target = a.disease.name if a.disease else a.encounter_set_type.name
        x["allocations"].add(f"{_human(a.capacity)} - {_human(a.scope)} - {target} - {a.lab_unit.name}")
    return tuple(ConfiguredUserDTO(uid, x["user"].full_name or x["user"].username, tuple(sorted(x["scopes"])),
        tuple(sorted(x["roles"])), tuple(sorted(x["uploads"])), tuple(sorted(x["allocations"])))
        for uid, x in sorted(by_user.items(), key=lambda item: (item[1]["user"].full_name or item[1]["user"].username).lower()))


def _referrals(db, project_id, mappings):
    grading = {d.disease.name for m in mappings for d in m.profile.diseases}
    sampled_roots = set()
    linked_targets = set()
    for mapping in mappings:
        for est in mapping.profile.encounter_set_types:
            if not est.active:
                continue
            for package in est.grading_packages:
                if not package.active or package.applicability == "disabled":
                    continue
                root_id = _package_root_disease_id(package)
                for scheme in package.image_grading_schemes:
                    if not scheme.active:
                        continue
                    grading.add(scheme.disease.name)
                    if scheme.disease_id == root_id and scheme.auto_create_policy == "positive_plus_negative_controls":
                        sampled_roots.add(scheme.disease.name)
                    elif package.grading_mode == "disease_specific" and root_id is not None and scheme.disease_id != root_id:
                        linked_targets.add(scheme.disease.name)
    explicit = {x.disease.name for x in db.execute(select(ProjectReferralDisease).options(selectinload(ProjectReferralDisease.disease)).where(
        ProjectReferralDisease.project_id == project_id, ProjectReferralDisease.active.is_(True))).scalars()}
    all_diseases = grading | explicit
    result = []
    for name in sorted(all_diseases):
        if name in sampled_roots:
            source = "Sampling trigger and grading target"
        elif name in linked_targets:
            source = "Linked grading target"
        elif name in grading:
            source = "Grading target"
        else:
            source = "Referral only"
        result.append(ReferralDiseaseDTO(name, source))
    return tuple(result)


def _lab_visible(lab_id, allowed): return allowed is None or lab_id in allowed
def _grant_visible(grant, allowed):
    if allowed is None or grant.scope_type == "project": return True
    if grant.scope_type == "lab_unit": return grant.lab_unit_id in allowed
    return any(lab.hospital_id == grant.hospital_id for lab in grant.hospital.lab_units if lab.id in allowed)
def _human(value): return str(value or "").replace("_", " ").strip().title()
def _clean_text(value): return " ".join(str(value or "").split())
def _labels(values):
    items = [str(x) for x in values if x]
    return ", ".join(items) if items else "None"
def _dilation(profile):
    options = []
    if profile.allow_mydriatic: options.append("Mydriatic")
    if profile.allow_non_mydriatic: options.append("Non-mydriatic")
    default = "Mydriatic" if profile.default_is_mydriatic else "Non-mydriatic"
    return f"{', '.join(options)}; default: {default}"

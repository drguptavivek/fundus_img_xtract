from __future__ import annotations

import re

from sqlalchemy.orm import selectinload

from models import Project, User
from project_annotations.contracts import (
    AnnotationContextDTO,
    FeaturePolicyDTO,
    NON_PROJECT_POLICY_REVISION,
    PolicyUpdateDTO,
    ProjectClassInputDTO,
    ResolvedProjectClassDTO,
    SUPPORTED_LOCALIZATIONS,
    SUPPORTED_TOOL_KEYS,
)
from project_annotations.errors import (
    AnnotationPolicyAccessDenied,
    AnnotationPolicyConflictError,
    AnnotationPolicyNotFound,
    AnnotationPolicyValidationError,
)
from project_annotations.models import (
    ProjectAnnotationClass,
    ProjectAnnotationPolicy,
    ProjectAnnotationPolicyRevision,
    ProjectAnnotationTool,
)
from upload_profiles.models import ProjectUploadProfile, ProjectUploadProfileAssignment


CLASS_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
SEGMENTATION_TOOLS = frozenset({"rect", "polygon", "brush_mask", "ellipse", "pyramid"})


def _resolved_project_id(task) -> int | None:
    source_task = getattr(task, "source_task", None)
    if source_task is not None:
        return _resolved_project_id(source_task)
    image = (
        getattr(task, "direct_image", None)
        or getattr(task, "direct_image_upload", None)
        or getattr(task, "encounter_file", None)
        or getattr(task, "encounter_set_image", None)
        or getattr(task, "patient_encounter", None)
    )
    if image is None:
        return None
    project_id = getattr(image, "project_id", None)
    if project_id is not None:
        return int(project_id)
    encounter = getattr(image, "patient_encounter", None)
    encounter_project_id = getattr(encounter, "project_id", None)
    return int(encounter_project_id) if encounter_project_id is not None else None


def _non_project_context() -> AnnotationContextDTO:
    return AnnotationContextDTO(
        policy_source="non_project_default",
        project_id=None,
        enabled=True,
        revision=NON_PROJECT_POLICY_REVISION,
        enabled_tools=SUPPORTED_TOOL_KEYS,
        default_feature_policy=FeaturePolicyDTO(
            localization="box_or_segmentation",
            preferred_tool="box",
            allowed_tools=SUPPORTED_TOOL_KEYS,
        ),
    )


def _require_bool(value, path: str) -> bool:
    if not isinstance(value, bool):
        raise AnnotationPolicyValidationError(f"{path} must be a boolean.")
    return value


def _require_string(value, path: str, *, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnnotationPolicyValidationError(f"{path} is required.")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise AnnotationPolicyValidationError(f"{path} is too long.")
    return normalized


def _tool_list(value, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AnnotationPolicyValidationError(f"{path} must be a list.")
    tools: list[str] = []
    for item in value:
        if item not in SUPPORTED_TOOL_KEYS:
            raise AnnotationPolicyValidationError(f"{path} contains an unsupported tool.")
        if item not in tools:
            tools.append(item)
    return tuple(tool for tool in SUPPORTED_TOOL_KEYS if tool in tools)


def _localization(value, path: str) -> str:
    normalized = _require_string(value, path, maximum=32)
    if normalized not in SUPPORTED_LOCALIZATIONS:
        raise AnnotationPolicyValidationError(f"{path} is unsupported.")
    return normalized


def _preferred_tool(value, path: str) -> str:
    normalized = _require_string(value, path, maximum=32)
    if normalized not in SUPPORTED_TOOL_KEYS:
        raise AnnotationPolicyValidationError(f"{path} is unsupported.")
    return normalized


def _nonnegative_int(value, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnnotationPolicyValidationError(f"{path} must be a non-negative integer.")
    return value


def compatible_tools(localization: str, enabled_tools: tuple[str, ...]) -> tuple[str, ...]:
    """Return enabled tools that can satisfy one localization contract."""
    if localization == "none":
        return ()
    if localization == "box":
        return tuple(tool for tool in enabled_tools if tool == "box")
    if localization == "segmentation":
        return tuple(tool for tool in enabled_tools if tool in SEGMENTATION_TOOLS)
    return enabled_tools


def parse_policy_update(payload: object) -> PolicyUpdateDTO:
    if not isinstance(payload, dict):
        raise AnnotationPolicyValidationError("Request body must be an object.")
    revision = _nonnegative_int(payload.get("revision"), "revision")
    enabled = _require_bool(payload.get("enabled"), "enabled")
    enabled_tools = _tool_list(payload.get("enabled_tools"), "enabled_tools")
    default_raw = payload.get("default_feature_policy")
    if not isinstance(default_raw, dict):
        raise AnnotationPolicyValidationError("default_feature_policy must be an object.")
    default_localization = _localization(default_raw.get("localization"), "default_feature_policy.localization")
    preferred_tool = _preferred_tool(
        default_raw.get("preferred_tool"),
        "default_feature_policy.preferred_tool",
    )
    default_allowed = _tool_list(default_raw.get("allowed_tools"), "default_feature_policy.allowed_tools")
    if default_allowed != enabled_tools:
        raise AnnotationPolicyValidationError("Default allowed tools must match the project-enabled tools.")
    if enabled and not enabled_tools:
        raise AnnotationPolicyValidationError("An enabled policy requires at least one tool.")
    if enabled_tools and preferred_tool not in enabled_tools:
        raise AnnotationPolicyValidationError("The default preferred tool must be enabled.")
    compatible_default_tools = compatible_tools(default_localization, enabled_tools)
    if default_localization != "none" and not compatible_default_tools:
        raise AnnotationPolicyValidationError(
            "The default localization requires at least one compatible enabled tool."
        )
    if default_localization != "none" and preferred_tool not in compatible_default_tools:
        raise AnnotationPolicyValidationError(
            "The default preferred tool is incompatible with the default localization."
        )

    class_rows = payload.get("project_classes", [])
    if not isinstance(class_rows, list):
        raise AnnotationPolicyValidationError("project_classes must be a list.")
    classes: list[ProjectClassInputDTO] = []
    seen_keys: set[str] = set()
    seen_ids: set[int] = set()
    allowed_class_fields = {
        "id", "key", "localization", "display_order", "multiple_instances", "active"
    }
    for index, row in enumerate(class_rows):
        path = f"project_classes[{index}]"
        if not isinstance(row, dict):
            raise AnnotationPolicyValidationError(f"{path} must be an object.")
        unsupported_fields = set(row) - allowed_class_fields
        if unsupported_fields:
            raise AnnotationPolicyValidationError(
                f"{path} contains unsupported fields: {', '.join(sorted(unsupported_fields))}."
            )
        key = _require_string(row.get("key"), f"{path}.key", maximum=64)
        if not CLASS_KEY_RE.fullmatch(key):
            raise AnnotationPolicyValidationError(f"{path}.key must be snake-case.")
        if key in seen_keys:
            raise AnnotationPolicyValidationError("Project class keys must be unique.")
        seen_keys.add(key)
        class_id = row.get("id")
        if (
            class_id is not None
            and (
                isinstance(class_id, bool)
                or not isinstance(class_id, int)
                or class_id <= 0
            )
        ):
            raise AnnotationPolicyValidationError(f"{path}.id must be a positive integer.")
        if class_id is not None and class_id in seen_ids:
            raise AnnotationPolicyValidationError("Project class IDs must be unique.")
        if class_id is not None:
            seen_ids.add(class_id)
        localization = _localization(row.get("localization"), f"{path}.localization")
        active = _require_bool(row.get("active", True), f"{path}.active")
        if active and localization != "none" and not compatible_tools(localization, enabled_tools):
            raise AnnotationPolicyValidationError(
                f"{path}.localization has no compatible enabled tool."
            )
        classes.append(ProjectClassInputDTO(
            id=class_id,
            key=key,
            localization=localization,
            display_order=_nonnegative_int(
                row.get("display_order", index * 10),
                f"{path}.display_order",
            ),
            multiple_instances=_require_bool(row.get("multiple_instances"), f"{path}.multiple_instances"),
            active=active,
        ))

    return PolicyUpdateDTO(
        revision=revision,
        enabled=enabled,
        default_localization=default_localization,
        preferred_tool=preferred_tool,
        enabled_tools=enabled_tools,
        project_classes=tuple(classes),
    )


def _policy_query(db, project_id: int, *, for_update: bool = False):
    query = (
        db.query(ProjectAnnotationPolicy)
        .options(
            selectinload(ProjectAnnotationPolicy.tools),
            selectinload(ProjectAnnotationPolicy.project_classes),
        )
        .filter(ProjectAnnotationPolicy.project_id == project_id)
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def _require_policy_manager_scope(db, *, user_id: int, project_id: int) -> None:
    user = (
        db.query(User)
        .options(selectinload(User.lab_units), selectinload(User.roles))
        .filter(User.id == user_id)
        .first()
    )
    manager_lab_ids = {lab.id for lab in user.lab_units} if user is not None else set()
    if not manager_lab_ids:
        raise AnnotationPolicyAccessDenied("No project-management lab scope.")

    project_lab_ids = {
        row[0]
        for row in (
            db.query(ProjectUploadProfileAssignment.lab_unit_id)
            .join(
                ProjectUploadProfile,
                ProjectUploadProfileAssignment.project_upload_profile_id
                == ProjectUploadProfile.id,
            )
            .filter(
                ProjectUploadProfile.project_id == project_id,
                ProjectUploadProfile.active.is_(True),
                ProjectUploadProfileAssignment.active.is_(True),
            )
            .all()
        )
    }
    if not project_lab_ids and not any(
        role.name == "admin" for role in (user.roles if user is not None else [])
    ):
        raise AnnotationPolicyAccessDenied(
            "The project has no lab assignment and requires a global administrator."
        )
    if project_lab_ids and project_lab_ids.isdisjoint(manager_lab_ids):
        raise AnnotationPolicyAccessDenied(
            "The project is outside your project-management lab scope."
        )


def _project_context(policy: ProjectAnnotationPolicy, *, expose_disabled: bool = False) -> AnnotationContextDTO:
    enabled_tools = tuple(
        tool for tool in SUPPORTED_TOOL_KEYS
        if any(item.tool_key == tool and item.enabled for item in policy.tools)
    )
    visible = policy.enabled or expose_disabled
    project_classes = tuple(
        ResolvedProjectClassDTO(
            id=item.id,
            key=item.key,
            localization=item.localization,
            display_order=item.display_order,
            multiple_instances=item.multiple_instances,
            active=item.active,
        )
        for item in sorted(
            policy.project_classes,
            key=lambda row: (row.display_order, row.key, row.id),
        )
        # Inactive rows remain in the resolved contract so clients can identify
        # and preserve historical annotations, but only active rows are offered
        # for new annotations.
    ) if visible else ()
    return AnnotationContextDTO(
        policy_source="project",
        project_id=policy.project_id,
        enabled=policy.enabled,
        revision=policy.revision,
        enabled_tools=enabled_tools if visible else (),
        default_feature_policy=FeaturePolicyDTO(
            localization=policy.default_localization,
            preferred_tool=policy.preferred_tool_key,
            allowed_tools=enabled_tools if visible else (),
        ),
        project_classes=project_classes,
    )


def get_project_policy_configuration(
    db,
    project_id: int,
    *,
    actor_user_id: int,
) -> AnnotationContextDTO:
    if db.get(Project, project_id) is None:
        raise AnnotationPolicyNotFound("Project not found.")
    _require_policy_manager_scope(
        db,
        user_id=actor_user_id,
        project_id=project_id,
    )
    policy = _policy_query(db, project_id)
    if policy is None:
        return AnnotationContextDTO(
            policy_source="project",
            project_id=project_id,
            enabled=False,
            revision=0,
            enabled_tools=(),
            default_feature_policy=FeaturePolicyDTO("box_or_segmentation", "box", ()),
        )
    return _project_context(policy, expose_disabled=True)


def save_project_policy(db, *, project_id: int, actor_user_id: int, update: PolicyUpdateDTO) -> AnnotationContextDTO:
    if db.get(Project, project_id) is None:
        raise AnnotationPolicyNotFound("Project not found.")
    _require_policy_manager_scope(
        db,
        user_id=actor_user_id,
        project_id=project_id,
    )
    policy = _policy_query(db, project_id, for_update=True)
    if policy is None:
        if update.revision != 0:
            raise AnnotationPolicyConflictError(
                "The annotation policy changed. Reload and try again."
            )
        policy = ProjectAnnotationPolicy(project_id=project_id, revision=1, created_by_id=actor_user_id)
        db.add(policy)
        db.flush()
    else:
        if update.revision != policy.revision:
            raise AnnotationPolicyConflictError(
                "The annotation policy changed. Reload and try again."
            )
        policy.revision += 1
    policy.enabled = update.enabled
    policy.default_localization = update.default_localization
    policy.preferred_tool_key = update.preferred_tool
    policy.updated_by_id = actor_user_id

    tools_by_key = {item.tool_key: item for item in policy.tools}
    for tool_key in SUPPORTED_TOOL_KEYS:
        tool = tools_by_key.get(tool_key)
        if tool is None:
            tool = ProjectAnnotationTool(policy=policy, tool_key=tool_key)
            db.add(tool)
        tool.enabled = tool_key in update.enabled_tools

    classes_by_id = {item.id: item for item in policy.project_classes}
    classes_by_key = {item.key: item for item in policy.project_classes}
    planned_rows: list[tuple[ProjectClassInputDTO, ProjectAnnotationClass | None]] = []
    retained_ids: set[int] = set()
    for row in update.project_classes:
        item = classes_by_id.get(row.id) if row.id is not None else classes_by_key.get(row.key)
        if row.id is not None and item is None:
            raise AnnotationPolicyValidationError("A project class does not belong to this policy.")
        if item is not None and row.id is not None and item.key != row.key:
            raise AnnotationPolicyValidationError("A project class stable key cannot be changed.")
        if item is not None and item.id in retained_ids:
            raise AnnotationPolicyValidationError("A project class was submitted more than once.")
        if item is not None:
            retained_ids.add(item.id)
        planned_rows.append((row, item))

    removed_any = False
    for item in list(policy.project_classes):
        if item.id not in retained_ids:
            item.active = False
            removed_any = True
    if removed_any:
        # Persist deactivations before applying retained rows. Historical class
        # identities are retained and are never physically deleted.
        db.flush()

    for row, item in planned_rows:
        if item is None:
            item = ProjectAnnotationClass(
                policy=policy,
                key=row.key,
                localization=row.localization,
                display_order=row.display_order,
                multiple_instances=row.multiple_instances,
                active=row.active,
            )
            db.add(item)
        item.key = row.key
        item.localization = row.localization
        item.display_order = row.display_order
        item.multiple_instances = row.multiple_instances
        item.active = row.active

    db.flush()
    policy = _policy_query(db, project_id)
    context = _project_context(policy, expose_disabled=True)
    db.add(
        ProjectAnnotationPolicyRevision(
            policy_id=policy.id,
            revision=policy.revision,
            configuration_json=context.to_dict(),
            created_by_id=actor_user_id,
        )
    )
    db.flush()
    return context


def resolve_task_annotation_context(db, task) -> AnnotationContextDTO:
    """Resolve annotation policy from the authoritative task target."""
    project_id = _resolved_project_id(task)
    if project_id is None:
        return _non_project_context()

    policy = _policy_query(db, project_id)
    if policy is None:
        return AnnotationContextDTO(
            policy_source="project",
            project_id=project_id,
            enabled=False,
            revision=0,
            enabled_tools=(),
            default_feature_policy=FeaturePolicyDTO("box_or_segmentation", "box", ()),
        )
    return _project_context(policy)


def validate_geometry_policy(
    payload: dict | None,
    context: AnnotationContextDTO,
) -> tuple[bool, str]:
    """Validate annotation class, tool, multiplicity, and policy revision."""
    if payload is None:
        return True, ""
    items = payload.get("items")
    if not isinstance(items, list):
        return False, "Invalid feature geometry payload."
    if not items:
        return True, ""
    if not context.enabled:
        return False, "Annotations are disabled for this project."
    submitted_revision = payload.get("policy_revision")
    if submitted_revision != context.revision:
        return False, "The project annotation policy changed. Reload before submitting."

    active_classes = {item.id: item for item in context.project_classes if item.active}
    class_counts: dict[int, int] = {}
    for item in items:
        if not isinstance(item, dict):
            return False, "Invalid feature geometry payload."
        geometry_type = str(item.get("geometry_type") or "box").strip().lower()
        if geometry_type == "none":
            tool_key = None
        else:
            tool_key = {
                "box": "box",
                "rect": "rect",
                "ellipse": "ellipse",
                "polygon": "polygon",
                "pyramid": "pyramid",
                "region": "brush_mask",
            }.get(geometry_type)
        if geometry_type != "none" and (tool_key is None or tool_key not in context.enabled_tools):
            return False, "An annotation uses a tool that is not enabled for this project."

        source = item.get("class_source", "grading_feature")
        if source == "grading_feature":
            localization = context.default_feature_policy.localization
        elif source == "project_class":
            class_id = item.get("project_class_id")
            if isinstance(class_id, bool) or not isinstance(class_id, int):
                return False, "Invalid project annotation class."
            project_class = active_classes.get(class_id)
            if project_class is None:
                return False, "A project annotation class is inactive or unavailable."
            if item.get("project_class_key") != project_class.key:
                return False, "A project annotation class identity is stale."
            localization = project_class.localization
            class_counts[class_id] = class_counts.get(class_id, 0) + 1
            if not project_class.multiple_instances and class_counts[class_id] > 1:
                return False, f"Project class {project_class.key} allows only one annotation."
        else:
            return False, "Invalid annotation class source."

        if localization == "none" and geometry_type != "none":
            return False, "An image-level class cannot contain geometry."
        if localization != "none" and geometry_type == "none":
            return False, "This annotation class requires localization geometry."
        if geometry_type != "none" and tool_key not in compatible_tools(localization, context.enabled_tools):
            return False, "An annotation tool is incompatible with its class localization."

    return True, ""

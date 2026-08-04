export type GradingSlot = "resident" | "resident2" | "arbitrator";
export type ImageSource = "encounter_file" | "direct_image" | "encounter_set_image";
export type ToolKey = "box" | "rect" | "polygon" | "brush_mask" | "ellipse" | "pyramid";
export type Localization = "none" | "box" | "segmentation" | "box_or_segmentation";

export interface NamedEntity {
  id: number;
  name: string;
}

export interface WorkbenchImage {
  uuid: string;
  source: ImageSource;
  url: string;
  filename: string | null;
  position: number | null;
}

export interface GradingFeature {
  id: number;
  sr_no: number;
  label: string;
}

export interface GradingOption {
  id: number;
  impression: string;
  display_order: number;
  is_active: boolean;
  is_ungradable: boolean;
  guidelines: string | null;
  features: GradingFeature[];
}

export interface ExistingGrade {
  id: number;
  grading_id: number;
  selected_feature_ids: number[];
  comment: string;
  annotations: Record<string, unknown>[];
}

export interface GradingPanel {
  id: string;
  task_uuid: string;
  disease: NamedEntity;
  grading_scope: "image" | "encounter";
  target_level: "image" | "encounter";
  state: string;
  read_only: boolean;
  read_only_reason: string | null;
  grades: GradingOption[];
  existing_grade: ExistingGrade | null;
}

export interface ProjectAnnotationClass {
  id: number;
  key: string;
  localization: Localization;
  display_order: number;
  multiple_instances: boolean;
  active: boolean;
}

export interface AnnotationContext {
  policy_source: "project" | "non_project_default";
  project_id: number | null;
  enabled: boolean;
  revision: number;
  enabled_tools: ToolKey[];
  default_feature_policy: {
    localization: Localization;
    preferred_tool: ToolKey;
    allowed_tools: ToolKey[];
  };
  project_classes: ProjectAnnotationClass[];
}

export interface GradingWorkspace {
  schema_version: 2;
  context_revision: string;
  target: {
    type: "task";
    ref: string;
    slot: GradingSlot;
  };
  task: {
    uuid: string;
    state: string;
    disease: NamedEntity;
    lab_unit: NamedEntity;
  };
  image: WorkbenchImage;
  images: WorkbenchImage[];
  active_image_uuid: string;
  panels: GradingPanel[];
  annotation_context: AnnotationContext;
  capabilities: {
    view: boolean;
    annotate: boolean;
    submit: boolean;
  };
  read_only_reasons: string[];
}

const GRADING_SLOTS = new Set<GradingSlot>(["resident", "resident2", "arbitrator"]);
const IMAGE_SOURCES = new Set<ImageSource>(["encounter_file", "direct_image", "encounter_set_image"]);
const TOOL_KEYS = new Set<ToolKey>(["box", "rect", "polygon", "brush_mask", "ellipse", "pyramid"]);
const LOCALIZATIONS = new Set<Localization>(["none", "box", "segmentation", "box_or_segmentation"]);
const SCOPES = new Set(["image", "encounter"] as const);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`${path} must be an object.`);
  return value;
}

function requireArray(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${path} must be a list.`);
  return value;
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${path} must be a non-empty string.`);
  return value;
}

function optionalString(value: unknown, path: string): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new Error(`${path} must be a string or null.`);
  return value;
}

function requireInteger(value: unknown, path: string): number {
  if (!Number.isInteger(value)) throw new Error(`${path} must be an integer.`);
  return value as number;
}

function nullableInteger(value: unknown, path: string): number | null {
  if (value === null || value === undefined) return null;
  return requireInteger(value, path);
}

function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new Error(`${path} must be a boolean.`);
  return value;
}

function parseNamedEntity(value: unknown, path: string): NamedEntity {
  const record = requireRecord(value, path);
  return { id: requireInteger(record.id, `${path}.id`), name: requireString(record.name, `${path}.name`) };
}

function parseImage(value: unknown, path: string): WorkbenchImage {
  const record = requireRecord(value, path);
  const source = requireString(record.source, `${path}.source`) as ImageSource;
  if (!IMAGE_SOURCES.has(source)) throw new Error(`${path}.source is unsupported.`);
  return {
    uuid: requireString(record.uuid, `${path}.uuid`),
    source,
    url: requireString(record.url, `${path}.url`),
    filename: optionalString(record.filename, `${path}.filename`),
    position: nullableInteger(record.position, `${path}.position`)
  };
}

function parseFeature(value: unknown, path: string): GradingFeature {
  const record = requireRecord(value, path);
  return {
    id: requireInteger(record.id, `${path}.id`),
    sr_no: requireInteger(record.sr_no, `${path}.sr_no`),
    label: requireString(record.label, `${path}.label`)
  };
}

function parseGrade(value: unknown, path: string): GradingOption {
  const record = requireRecord(value, path);
  return {
    id: requireInteger(record.id, `${path}.id`),
    impression: requireString(record.impression, `${path}.impression`),
    display_order: requireInteger(record.display_order, `${path}.display_order`),
    is_active: requireBoolean(record.is_active, `${path}.is_active`),
    is_ungradable: requireBoolean(record.is_ungradable, `${path}.is_ungradable`),
    guidelines: optionalString(record.guidelines, `${path}.guidelines`),
    features: requireArray(record.features, `${path}.features`).map((item, index) => parseFeature(item, `${path}.features[${index}]`))
  };
}

function parseExistingGrade(value: unknown, path: string): ExistingGrade | null {
  if (value === null || value === undefined) return null;
  const record = requireRecord(value, path);
  return {
    id: requireInteger(record.id, `${path}.id`),
    grading_id: requireInteger(record.grading_id, `${path}.grading_id`),
    selected_feature_ids: requireArray(record.selected_feature_ids, `${path}.selected_feature_ids`).map((item, index) => requireInteger(item, `${path}.selected_feature_ids[${index}]`)),
    comment: typeof record.comment === "string" ? record.comment : "",
    annotations: requireArray(record.annotations, `${path}.annotations`).map((item, index) => requireRecord(item, `${path}.annotations[${index}]`))
  };
}

function parsePanel(value: unknown, path: string): GradingPanel {
  const record = requireRecord(value, path);
  const gradingScope = requireString(record.grading_scope, `${path}.grading_scope`) as "image" | "encounter";
  const targetLevel = requireString(record.target_level, `${path}.target_level`) as "image" | "encounter";
  if (!SCOPES.has(gradingScope) || !SCOPES.has(targetLevel)) throw new Error(`${path} has an unsupported grading scope.`);
  return {
    id: requireString(record.id, `${path}.id`),
    task_uuid: requireString(record.task_uuid, `${path}.task_uuid`),
    disease: parseNamedEntity(record.disease, `${path}.disease`),
    grading_scope: gradingScope,
    target_level: targetLevel,
    state: requireString(record.state, `${path}.state`),
    read_only: requireBoolean(record.read_only, `${path}.read_only`),
    read_only_reason: optionalString(record.read_only_reason, `${path}.read_only_reason`),
    grades: requireArray(record.grades, `${path}.grades`).map((item, index) => parseGrade(item, `${path}.grades[${index}]`)),
    existing_grade: parseExistingGrade(record.existing_grade, `${path}.existing_grade`)
  };
}

function parseToolList(value: unknown, path: string): ToolKey[] {
  return requireArray(value, path).map((item, index) => {
    const tool = requireString(item, `${path}[${index}]`) as ToolKey;
    if (!TOOL_KEYS.has(tool)) throw new Error(`${path}[${index}] is unsupported.`);
    return tool;
  });
}

function parseLocalization(value: unknown, path: string): Localization {
  const localization = requireString(value, path) as Localization;
  if (!LOCALIZATIONS.has(localization)) throw new Error(`${path} is unsupported.`);
  return localization;
}

function parseAnnotationContext(value: unknown): AnnotationContext {
  const record = requireRecord(value, "workspace.annotation_context");
  const source = requireString(record.policy_source, "workspace.annotation_context.policy_source");
  if (source !== "project" && source !== "non_project_default") throw new Error("workspace.annotation_context.policy_source is unsupported.");
  const defaultPolicy = requireRecord(record.default_feature_policy, "workspace.annotation_context.default_feature_policy");
  return {
    policy_source: source,
    project_id: nullableInteger(record.project_id, "workspace.annotation_context.project_id"),
    enabled: requireBoolean(record.enabled, "workspace.annotation_context.enabled"),
    revision: requireInteger(record.revision, "workspace.annotation_context.revision"),
    enabled_tools: parseToolList(record.enabled_tools, "workspace.annotation_context.enabled_tools"),
    default_feature_policy: {
      localization: parseLocalization(defaultPolicy.localization, "workspace.annotation_context.default_feature_policy.localization"),
      preferred_tool: parseToolList([defaultPolicy.preferred_tool], "workspace.annotation_context.default_feature_policy.preferred_tool")[0],
      allowed_tools: parseToolList(defaultPolicy.allowed_tools, "workspace.annotation_context.default_feature_policy.allowed_tools")
    },
    project_classes: requireArray(record.project_classes, "workspace.annotation_context.project_classes").map((item, index) => {
      const projectClass = requireRecord(item, `workspace.annotation_context.project_classes[${index}]`);
      return {
        id: requireInteger(projectClass.id, `workspace.annotation_context.project_classes[${index}].id`),
        key: requireString(projectClass.key, `workspace.annotation_context.project_classes[${index}].key`),
        localization: parseLocalization(projectClass.localization, `workspace.annotation_context.project_classes[${index}].localization`),
        display_order: requireInteger(projectClass.display_order, `workspace.annotation_context.project_classes[${index}].display_order`),
        multiple_instances: requireBoolean(projectClass.multiple_instances, `workspace.annotation_context.project_classes[${index}].multiple_instances`),
        active: requireBoolean(projectClass.active, `workspace.annotation_context.project_classes[${index}].active`)
      };
    })
  };
}

export function parseWorkspace(value: unknown): GradingWorkspace {
  const root = requireRecord(value, "workspace");
  if (root.schema_version !== 2) throw new Error("Unsupported grading workspace schema version.");
  const target = requireRecord(root.target, "workspace.target");
  if (target.type !== "task") throw new Error("workspace.target.type must be task.");
  const slot = requireString(target.slot, "workspace.target.slot") as GradingSlot;
  if (!GRADING_SLOTS.has(slot)) throw new Error("workspace.target.slot is unsupported.");
  const task = requireRecord(root.task, "workspace.task");
  const capabilities = requireRecord(root.capabilities, "workspace.capabilities");
  const images = requireArray(root.images, "workspace.images").map((item, index) => parseImage(item, `workspace.images[${index}]`));
  if (images.length === 0) throw new Error("workspace.images must contain a viewable image.");
  const activeImageUuid = requireString(root.active_image_uuid, "workspace.active_image_uuid");
  if (!images.some((image) => image.uuid === activeImageUuid)) throw new Error("workspace.active_image_uuid is not in workspace.images.");
  const readOnlyReasons = requireArray(root.read_only_reasons, "workspace.read_only_reasons");
  if (!readOnlyReasons.every((item) => typeof item === "string")) throw new Error("workspace.read_only_reasons must contain strings.");

  return {
    schema_version: 2,
    context_revision: requireString(root.context_revision, "workspace.context_revision"),
    target: { type: "task", ref: requireString(target.ref, "workspace.target.ref"), slot },
    task: {
      uuid: requireString(task.uuid, "workspace.task.uuid"),
      state: requireString(task.state, "workspace.task.state"),
      disease: parseNamedEntity(task.disease, "workspace.task.disease"),
      lab_unit: parseNamedEntity(task.lab_unit, "workspace.task.lab_unit")
    },
    image: parseImage(root.image, "workspace.image"),
    images,
    active_image_uuid: activeImageUuid,
    panels: requireArray(root.panels, "workspace.panels").map((item, index) => parsePanel(item, `workspace.panels[${index}]`)),
    annotation_context: parseAnnotationContext(root.annotation_context),
    capabilities: {
      view: requireBoolean(capabilities.view, "workspace.capabilities.view"),
      annotate: requireBoolean(capabilities.annotate, "workspace.capabilities.annotate"),
      submit: requireBoolean(capabilities.submit, "workspace.capabilities.submit")
    },
    read_only_reasons: readOnlyReasons as string[]
  };
}

export async function fetchWorkspace(url: string, signal?: AbortSignal): Promise<GradingWorkspace> {
  const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" }, signal });
  if (!response.ok) throw new Error(`Unable to load grading workspace (${response.status}).`);
  return parseWorkspace(await response.json());
}

export type GradingSlot = "resident" | "resident2" | "arbitrator";
export type ImageSource = "encounter_file" | "direct_image" | "encounter_set_image";

export interface NamedEntity {
  id: number;
  name: string;
}

export interface GradingWorkspace {
  schema_version: 1;
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
  image: {
    uuid: string;
    source: ImageSource;
    url: string;
    filename: string | null;
  };
  capabilities: {
    view: boolean;
    annotate: boolean;
    submit: boolean;
  };
  read_only_reasons: string[];
}

const GRADING_SLOTS = new Set<GradingSlot>(["resident", "resident2", "arbitrator"]);
const IMAGE_SOURCES = new Set<ImageSource>([
  "encounter_file",
  "direct_image",
  "encounter_set_image"
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`${path} must be an object.`);
  }
  return value;
}

function requireString(value: unknown, path: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${path} must be a non-empty string.`);
  }
  return value;
}

function requireBoolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`${path} must be a boolean.`);
  }
  return value;
}

function parseNamedEntity(value: unknown, path: string): NamedEntity {
  const record = requireRecord(value, path);
  if (!Number.isInteger(record.id)) {
    throw new Error(`${path}.id must be an integer.`);
  }
  return {
    id: record.id as number,
    name: requireString(record.name, `${path}.name`)
  };
}

export function parseWorkspace(value: unknown): GradingWorkspace {
  const root = requireRecord(value, "workspace");
  if (root.schema_version !== 1) {
    throw new Error("Unsupported grading workspace schema version.");
  }

  const target = requireRecord(root.target, "workspace.target");
  if (target.type !== "task") {
    throw new Error("workspace.target.type must be task.");
  }
  const slot = requireString(target.slot, "workspace.target.slot") as GradingSlot;
  if (!GRADING_SLOTS.has(slot)) {
    throw new Error("workspace.target.slot is unsupported.");
  }

  const task = requireRecord(root.task, "workspace.task");
  const image = requireRecord(root.image, "workspace.image");
  const source = requireString(image.source, "workspace.image.source") as ImageSource;
  if (!IMAGE_SOURCES.has(source)) {
    throw new Error("workspace.image.source is unsupported.");
  }

  const capabilities = requireRecord(root.capabilities, "workspace.capabilities");
  if (!Array.isArray(root.read_only_reasons) || !root.read_only_reasons.every((item) => typeof item === "string")) {
    throw new Error("workspace.read_only_reasons must be a list of strings.");
  }

  const filename = image.filename;
  if (filename !== null && typeof filename !== "string") {
    throw new Error("workspace.image.filename must be a string or null.");
  }

  return {
    schema_version: 1,
    context_revision: requireString(root.context_revision, "workspace.context_revision"),
    target: {
      type: "task",
      ref: requireString(target.ref, "workspace.target.ref"),
      slot
    },
    task: {
      uuid: requireString(task.uuid, "workspace.task.uuid"),
      state: requireString(task.state, "workspace.task.state"),
      disease: parseNamedEntity(task.disease, "workspace.task.disease"),
      lab_unit: parseNamedEntity(task.lab_unit, "workspace.task.lab_unit")
    },
    image: {
      uuid: requireString(image.uuid, "workspace.image.uuid"),
      source,
      url: requireString(image.url, "workspace.image.url"),
      filename
    },
    capabilities: {
      view: requireBoolean(capabilities.view, "workspace.capabilities.view"),
      annotate: requireBoolean(capabilities.annotate, "workspace.capabilities.annotate"),
      submit: requireBoolean(capabilities.submit, "workspace.capabilities.submit")
    },
    read_only_reasons: [...root.read_only_reasons]
  };
}

export async function fetchWorkspace(url: string, signal?: AbortSignal): Promise<GradingWorkspace> {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal
  });
  if (!response.ok) {
    throw new Error(`Unable to load grading workspace (${response.status}).`);
  }
  return parseWorkspace(await response.json());
}

import { DEFAULT_FILTERS, type ViewerFilterMode, type ViewerFilters } from "./workbenchState";

const FILTER_MODES = new Set<ViewerFilterMode>(["none", "enhance", "redfree", "redfreeenhanced"]);

export interface ViewerPreset {
  id?: number;
  name?: string | null;
  brightness?: number;
  contrast?: number;
  saturation?: number;
  red_luminance?: number;
  red_saturation?: number;
  green_luminance?: number;
  green_saturation?: number;
  blue_luminance?: number;
  blue_saturation?: number;
  gamma?: number;
  black_point?: number;
  white_point?: number;
  shadow_lift?: number;
  flattening?: number;
  invert?: boolean;
  filter?: string;
}

export type ViewerPresetMap = Partial<Record<1 | 2 | 3 | 4 | 5, ViewerPreset>>;

function clamp(value: unknown, fallback: number, minimum: number, maximum: number): number {
  const numeric = typeof value === "number" && Number.isFinite(value) ? value : fallback;
  return Math.min(maximum, Math.max(minimum, numeric));
}

export function filtersFromPreset(preset: ViewerPreset): ViewerFilters {
  const mode = FILTER_MODES.has(preset.filter as ViewerFilterMode) ? preset.filter as ViewerFilterMode : "none";
  return {
    ...DEFAULT_FILTERS,
    mode,
    brightness: Number((clamp(preset.brightness, 1, 0.5, 5) - 1).toFixed(3)),
    contrast: Number((clamp(preset.contrast, 1, 0.5, 5) - 1).toFixed(3)),
    saturation: Number((clamp(preset.saturation, 1, 0, 3) - 1).toFixed(3)),
    redLuminance: Number((clamp(preset.red_luminance, 1, 0, 3) - 1).toFixed(3)),
    redSaturation: Number((clamp(preset.red_saturation, 1, 0, 3) - 1).toFixed(3)),
    greenLuminance: Number((clamp(preset.green_luminance, 1, 0, 3) - 1).toFixed(3)),
    greenSaturation: Number((clamp(preset.green_saturation, 1, 0, 3) - 1).toFixed(3)),
    blueLuminance: Number((clamp(preset.blue_luminance, 1, 0, 3) - 1).toFixed(3)),
    blueSaturation: Number((clamp(preset.blue_saturation, 1, 0, 3) - 1).toFixed(3)),
    gamma: clamp(preset.gamma, 1, 0.35, 2.5),
    blackPoint: clamp(preset.black_point, 0, -0.2, 0.25),
    whitePoint: clamp(preset.white_point, 1, 0.5, 1.2),
    shadowLift: clamp(preset.shadow_lift, 0, 0, 1),
    flattening: clamp(preset.flattening, 0, 0, 1),
    invert: preset.invert === true
  };
}

export function normalizePresetTuning(preset: ViewerPreset): ViewerPreset {
  const filters = filtersFromPreset(preset);
  return {
    ...preset,
    brightness: 1 + filters.brightness,
    contrast: 1 + filters.contrast,
    saturation: 1 + filters.saturation,
    red_luminance: 1 + filters.redLuminance,
    red_saturation: 1 + filters.redSaturation,
    green_luminance: 1 + filters.greenLuminance,
    green_saturation: 1 + filters.greenSaturation,
    blue_luminance: 1 + filters.blueLuminance,
    blue_saturation: 1 + filters.blueSaturation,
    gamma: filters.gamma,
    black_point: filters.blackPoint,
    white_point: filters.whitePoint,
    shadow_lift: filters.shadowLift,
    flattening: filters.flattening,
    invert: filters.invert
  };
}

export function presetFromViewer(filters: ViewerFilters, slot: number): ViewerPreset {
  return {
    name: `Preset ${slot}`,
    brightness: 1 + filters.brightness,
    contrast: 1 + filters.contrast,
    saturation: 1 + filters.saturation,
    red_luminance: 1 + filters.redLuminance,
    red_saturation: 1 + filters.redSaturation,
    green_luminance: 1 + filters.greenLuminance,
    green_saturation: 1 + filters.greenSaturation,
    blue_luminance: 1 + filters.blueLuminance,
    blue_saturation: 1 + filters.blueSaturation,
    gamma: filters.gamma,
    black_point: filters.blackPoint,
    white_point: filters.whitePoint,
    shadow_lift: filters.shadowLift,
    flattening: filters.flattening,
    invert: filters.invert,
    filter: filters.mode
  };
}

function csrfToken(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ?? "";
}

export async function fetchViewerPresets(signal?: AbortSignal): Promise<ViewerPresetMap> {
  const response = await fetch("/api/viewer/presets", { credentials: "same-origin", signal });
  if (!response.ok) throw new Error("Unable to load viewer presets");
  return await response.json() as ViewerPresetMap;
}

export async function saveViewerPreset(slot: 1 | 2 | 3 | 4 | 5, preset: ViewerPreset): Promise<void> {
  const response = await fetch(`/api/viewer/presets/${slot}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
    body: JSON.stringify(preset)
  });
  if (!response.ok) throw new Error("Unable to save viewer preset");
}

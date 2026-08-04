import type {
  AnnotationContext,
  GradingPanel,
  GradingWorkspace,
  Localization,
  ToolKey
} from "./workspace";

export interface AnnotationClassRef {
  id: string;
  source: "project_class" | "grading_feature";
  label: string;
  localization: Localization;
  multipleInstances: boolean;
  panelId: string | null;
  projectClassId?: number;
  featureId?: number;
}

export type Point = [number, number];
export type AnnotationGeometry =
  | { type: "box"; x: number; y: number; width: number; height: number }
  | { type: "rect"; x: number; y: number; width: number; height: number; rotation?: number }
  | { type: "ellipse"; x: number; y: number; width: number; height: number; rotation?: number }
  | { type: "polygon"; points: Point[] }
  | { type: "pyramid"; points: Point[] }
  | { type: "brush_mask"; strokes: Point[][]; size: number };

export interface WorkbenchAnnotation {
  id: string;
  imageUuid: string;
  panelId: string;
  classRef: AnnotationClassRef;
  tool: ToolKey;
  geometry: AnnotationGeometry;
  visible: boolean;
  locked: boolean;
}

export interface PanelDraft {
  gradeId: number | null;
  selectedFeatureIds: Set<number>;
  comment: string;
}

export interface ViewerFilters {
  mode: ViewerFilterMode;
  brightness: number;
  contrast: number;
  saturation: number;
  redLuminance: number;
  redSaturation: number;
  greenLuminance: number;
  greenSaturation: number;
  blueLuminance: number;
  blueSaturation: number;
  gamma: number;
  blackPoint: number;
  whitePoint: number;
  shadowLift: number;
  flattening: number;
  invert: boolean;
}

export type ViewerFilterMode = "none" | "enhance" | "redfree" | "redfreeenhanced";

export const CLINICAL_FILTER_MODES: { key: ViewerFilterMode; short: string; label: string }[] = [
  { key: "none", short: "N", label: "Normal · capture levels" },
  { key: "enhance", short: "E", label: "Protected shadow lift" },
  { key: "redfree", short: "RF", label: "Red-free simulation" },
  { key: "redfreeenhanced", short: "RF+", label: "Enhanced red-free" }
];

export const DEFAULT_FILTERS: ViewerFilters = {
  mode: "none",
  brightness: 0,
  contrast: 0,
  saturation: 0,
  redLuminance: 0,
  redSaturation: 0,
  greenLuminance: 0,
  greenSaturation: 0,
  blueLuminance: 0,
  blueSaturation: 0,
  gamma: 1,
  blackPoint: 0,
  whitePoint: 1,
  shadowLift: 0,
  flattening: 0,
  invert: false
};

export function filtersForClinicalMode(mode: ViewerFilterMode, saved?: ViewerFilters): ViewerFilters {
  if (mode === "none") return { ...DEFAULT_FILTERS };
  if (saved?.mode === mode) return { ...saved };
  return {
    ...DEFAULT_FILTERS,
    mode,
    shadowLift: mode === "enhance" ? 0.5 : 0
  };
}

export interface AnnotationBounds { x: number; y: number; width: number; height: number; }

function rotatePoint(point: Point, center: Point, radians: number): Point {
  const dx = point[0] - center[0];
  const dy = point[1] - center[1];
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  return [center[0] + dx * cosine - dy * sine, center[1] + dx * sine + dy * cosine];
}

export function geometryControlPoints(geometry: AnnotationGeometry): Point[] {
  if (geometry.type === "box" || geometry.type === "rect" || geometry.type === "ellipse") {
    const center: Point = [geometry.x + geometry.width / 2, geometry.y + geometry.height / 2];
    const corners: Point[] = [
      [geometry.x, geometry.y],
      [geometry.x + geometry.width, geometry.y],
      [geometry.x + geometry.width, geometry.y + geometry.height],
      [geometry.x, geometry.y + geometry.height]
    ];
    const rotation = geometry.type === "box" ? 0 : geometry.rotation ?? 0;
    return rotation ? corners.map((point) => rotatePoint(point, center, rotation)) : corners;
  }
  const bounds = annotationBounds(geometry);
  return [
    [bounds.x, bounds.y],
    [bounds.x + bounds.width, bounds.y],
    [bounds.x + bounds.width, bounds.y + bounds.height],
    [bounds.x, bounds.y + bounds.height]
  ];
}

export function annotationBounds(geometry: AnnotationGeometry): AnnotationBounds {
  if (geometry.type === "box" || geometry.type === "rect" || geometry.type === "ellipse") {
    if (geometry.type !== "box" && geometry.rotation) {
      const points = geometryControlPoints(geometry);
      const xs = points.map((point) => point[0]);
      const ys = points.map((point) => point[1]);
      return { x: Math.min(...xs), y: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
    }
    return { x: geometry.x, y: geometry.y, width: geometry.width, height: geometry.height };
  }
  const points = geometry.type === "brush_mask" ? geometry.strokes.flat() : geometry.points;
  if (!points.length) return { x: 0, y: 0, width: 0, height: 0 };
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const padding = geometry.type === "brush_mask" ? geometry.size / 2 : 0;
  const minX = Math.min(...xs) - padding;
  const minY = Math.min(...ys) - padding;
  return {
    x: minX,
    y: minY,
    width: Math.max(...xs) + padding - minX,
    height: Math.max(...ys) + padding - minY
  };
}

function pointToSegmentDistance(point: Point, start: Point, end: Point): number {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  if (dx === 0 && dy === 0) return Math.hypot(point[0] - start[0], point[1] - start[1]);
  const t = Math.max(0, Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy));
}

function pointInPolygon(point: Point, points: Point[]): boolean {
  let inside = false;
  for (let index = 0, previous = points.length - 1; index < points.length; previous = index++) {
    const [x, y] = points[index];
    const [px, py] = points[previous];
    if ((y > point[1]) !== (py > point[1]) && point[0] < ((px - x) * (point[1] - y)) / (py - y) + x) inside = !inside;
  }
  return inside;
}

export function annotationContainsPoint(annotation: WorkbenchAnnotation, point: Point, tolerance = 5): boolean {
  if (!annotation.visible) return false;
  const geometry = annotation.geometry;
  if (geometry.type === "box" || geometry.type === "rect") {
    const center: Point = [geometry.x + geometry.width / 2, geometry.y + geometry.height / 2];
    const localPoint = geometry.type === "rect" && geometry.rotation ? rotatePoint(point, center, -geometry.rotation) : point;
    return localPoint[0] >= geometry.x - tolerance && localPoint[0] <= geometry.x + geometry.width + tolerance
      && localPoint[1] >= geometry.y - tolerance && localPoint[1] <= geometry.y + geometry.height + tolerance;
  }
  if (geometry.type === "ellipse") {
    const rx = Math.max(geometry.width / 2 + tolerance, 1);
    const ry = Math.max(geometry.height / 2 + tolerance, 1);
    const cx = geometry.x + geometry.width / 2;
    const cy = geometry.y + geometry.height / 2;
    const localPoint = geometry.rotation ? rotatePoint(point, [cx, cy], -geometry.rotation) : point;
    return ((localPoint[0] - cx) / rx) ** 2 + ((localPoint[1] - cy) / ry) ** 2 <= 1;
  }
  if (geometry.type === "polygon" || geometry.type === "pyramid") return pointInPolygon(point, geometry.points);
  return geometry.strokes.some((stroke) => stroke.slice(1).some((end, index) => pointToSegmentDistance(point, stroke[index], end) <= geometry.size / 2 + tolerance));
}

export function duplicateAnnotation(annotation: WorkbenchAnnotation, id: string, offset = 12): WorkbenchAnnotation {
  const shift = ([x, y]: Point): Point => [x + offset, y + offset];
  const geometry = annotation.geometry;
  const shifted: AnnotationGeometry = geometry.type === "box" || geometry.type === "rect" || geometry.type === "ellipse"
    ? { ...geometry, x: geometry.x + offset, y: geometry.y + offset }
    : geometry.type === "brush_mask"
      ? { ...geometry, strokes: geometry.strokes.map((stroke) => stroke.map(shift)) }
      : { ...geometry, points: geometry.points.map(shift) };
  return { ...annotation, id, geometry: shifted, visible: true, locked: false };
}

export function moveGeometry(geometry: AnnotationGeometry, dx: number, dy: number): AnnotationGeometry {
  const shift = ([x, y]: Point): Point => [x + dx, y + dy];
  if (geometry.type === "box" || geometry.type === "rect" || geometry.type === "ellipse") {
    return { ...geometry, x: geometry.x + dx, y: geometry.y + dy };
  }
  if (geometry.type === "brush_mask") {
    return { ...geometry, strokes: geometry.strokes.map((stroke) => stroke.map(shift)) };
  }
  return { ...geometry, points: geometry.points.map(shift) };
}

export function scaleGeometry(
  geometry: AnnotationGeometry,
  origin: Point,
  scaleX: number,
  scaleY: number
): AnnotationGeometry {
  const scale = ([x, y]: Point): Point => [origin[0] + (x - origin[0]) * scaleX, origin[1] + (y - origin[1]) * scaleY];
  if (geometry.type === "box" || geometry.type === "rect" || geometry.type === "ellipse") {
    const [x, y] = scale([geometry.x, geometry.y]);
    return { ...geometry, x, y, width: geometry.width * scaleX, height: geometry.height * scaleY };
  }
  if (geometry.type === "brush_mask") {
    return {
      ...geometry,
      strokes: geometry.strokes.map((stroke) => stroke.map(scale)),
      size: geometry.size * Math.max(Math.abs(scaleX), Math.abs(scaleY))
    };
  }
  return { ...geometry, points: geometry.points.map(scale) };
}

export function rotateGeometry(geometry: AnnotationGeometry, center: Point, radians: number): AnnotationGeometry {
  if (geometry.type === "box") return geometry;
  if (geometry.type === "rect" || geometry.type === "ellipse") {
    return { ...geometry, rotation: (geometry.rotation ?? 0) + radians };
  }
  const rotate = ([x, y]: Point): Point => {
    const dx = x - center[0];
    const dy = y - center[1];
    const cosine = Math.cos(radians);
    const sine = Math.sin(radians);
    const nextX = Number((center[0] + dx * cosine - dy * sine).toFixed(8));
    const nextY = Number((center[1] + dx * sine + dy * cosine).toFixed(8));
    return [Object.is(nextX, -0) ? 0 : nextX, Object.is(nextY, -0) ? 0 : nextY];
  };
  if (geometry.type === "brush_mask") {
    return { ...geometry, strokes: geometry.strokes.map((stroke) => stroke.map(rotate)) };
  }
  return { ...geometry, points: geometry.points.map(rotate) };
}

export function eraseBrushMask(
  geometry: Extract<AnnotationGeometry, { type: "brush_mask" }>,
  eraserPath: Point[],
  radius: number
): Extract<AnnotationGeometry, { type: "brush_mask" }> | null {
  if (!eraserPath.length) return geometry;
  const erased = (point: Point): boolean => {
    if (eraserPath.length === 1) return Math.hypot(point[0] - eraserPath[0][0], point[1] - eraserPath[0][1]) <= radius;
    return eraserPath.slice(1).some((end, index) => pointToSegmentDistance(point, eraserPath[index], end) <= radius);
  };
  const strokes: Point[][] = [];
  for (const stroke of geometry.strokes) {
    let segment: Point[] = [];
    const flush = () => {
      if (segment.length >= 2) strokes.push(segment);
      segment = [];
    };
    for (const point of stroke) {
      if (erased(point)) flush();
      else segment.push(point);
    }
    flush();
  }
  return strokes.length ? { ...geometry, strokes } : null;
}

function titleCaseKey(key: string): string {
  return key.split("_").map((part) => part ? part[0].toUpperCase() + part.slice(1) : part).join(" ");
}

export function availableAnnotationClasses(
  workspace: GradingWorkspace,
  panel: GradingPanel,
  gradeId: number | null,
  selectedFeatureIds: Set<number>
): AnnotationClassRef[] {
  if (!workspace.annotation_context.enabled) return [];
  const projectClasses = workspace.annotation_context.project_classes
    .filter((item) => item.active)
    .sort((a, b) => a.display_order - b.display_order || a.key.localeCompare(b.key) || a.id - b.id)
    .map((item): AnnotationClassRef => ({
      id: `project:${item.id}`,
      source: "project_class",
      label: titleCaseKey(item.key),
      localization: item.localization,
      multipleInstances: item.multiple_instances,
      panelId: null,
      projectClassId: item.id
    }));

  const grade = panel.grades.find((item) => item.id === gradeId);
  const featureClasses = (grade?.features ?? [])
    .filter((feature) => selectedFeatureIds.has(feature.id))
    .sort((a, b) => a.sr_no - b.sr_no || a.id - b.id)
    .map((feature): AnnotationClassRef => ({
      id: `feature:${panel.id}:${feature.id}`,
      source: "grading_feature",
      label: feature.label,
      localization: workspace.annotation_context.default_feature_policy.localization,
      multipleInstances: true,
      panelId: panel.id,
      featureId: feature.id
    }));
  return [...projectClasses, ...featureClasses];
}

export function toolsForClass(context: AnnotationContext, annotationClass: AnnotationClassRef): ToolKey[] {
  const enabled = annotationClass.source === "grading_feature"
    ? context.default_feature_policy.allowed_tools.filter((tool) => context.enabled_tools.includes(tool))
    : context.enabled_tools;
  if (annotationClass.localization === "none") return [];
  if (annotationClass.localization === "box") return enabled.filter((tool) => tool === "box");
  if (annotationClass.localization === "segmentation") return enabled.filter((tool) => tool !== "box");
  return enabled;
}

export function canCreateAnnotation(
  annotationClass: AnnotationClassRef,
  annotations: WorkbenchAnnotation[]
): boolean {
  if (annotationClass.multipleInstances) return true;
  return !annotations.some((annotation) => annotation.classRef.id === annotationClass.id);
}

export function createInitialPanelDraft(panel: GradingPanel): PanelDraft {
  return {
    gradeId: panel.existing_grade?.grading_id ?? null,
    selectedFeatureIds: new Set(panel.existing_grade?.selected_feature_ids ?? []),
    comment: panel.existing_grade?.comment ?? ""
  };
}

export function annotationColor(annotationClass: AnnotationClassRef): number {
  let hash = 2166136261;
  for (const character of annotationClass.id) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const palette = [0x2dd4bf, 0x60a5fa, 0xf59e0b, 0xf472b6, 0xa78bfa, 0x34d399, 0xfb7185];
  return palette[Math.abs(hash) % palette.length];
}

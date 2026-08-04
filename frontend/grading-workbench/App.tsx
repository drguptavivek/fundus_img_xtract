import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import { clearDraft, loadDraft, saveDraft, type StoredWorkbenchDraft } from "./draftStore";
import { analyzeImageUrl, clinicalDisplayRecipe, type ChannelDistribution, type ImageAnalysis } from "./imageAnalysis";
import { PixiViewport, type ViewerControls } from "./PixiViewport";
import {
  DEFAULT_FILTERS,
  CLINICAL_FILTER_MODES,
  annotationColor,
  availableAnnotationClasses,
  canCreateAnnotation,
  createInitialPanelDraft,
  duplicateAnnotation,
  filtersForClinicalMode,
  toolsForClass,
  type AnnotationClassRef,
  type AnnotationGeometry,
  type PanelDraft,
  type ViewerFilters,
  type ViewerFilterMode,
  type WorkbenchAnnotation
} from "./workbenchState";
import {
  fetchWorkspace,
  type GradingPanel,
  type GradingWorkspace,
  type ToolKey
} from "./workspace";
import {
  fetchViewerPresets,
  filtersFromPreset,
  normalizePresetTuning,
  presetFromViewer,
  saveViewerPreset,
  type ViewerPreset,
  type ViewerPresetMap
} from "./viewerPresets";

interface AppProps {
  workspaceUrl: string;
}

type PresetSlot = 1 | 2 | 3 | 4 | 5;
type PresetTuningField = "brightness" | "contrast" | "saturation" | "red_luminance" | "red_saturation" | "green_luminance" | "green_saturation" | "blue_luminance" | "blue_saturation" | "gamma" | "black_point" | "white_point" | "shadow_lift" | "flattening";

interface FineTuneSnapshot {
  filters: ViewerFilters;
  activePresetSlot: PresetSlot | null;
}

const OVERALL_TUNING: { field: PresetTuningField; label: string }[] = [
  { field: "brightness", label: "Brightness" },
  { field: "contrast", label: "Contrast" },
  { field: "saturation", label: "Saturation" }
];

const CHANNEL_TUNING: { key: "red" | "green" | "blue"; label: string; luminance: PresetTuningField; saturation: PresetTuningField }[] = [
  { key: "red", label: "R", luminance: "red_luminance", saturation: "red_saturation" },
  { key: "green", label: "G", luminance: "green_luminance", saturation: "green_saturation" },
  { key: "blue", label: "B", luminance: "blue_luminance", saturation: "blue_saturation" }
];

const CLINICAL_TUNING: { field: PresetTuningField; label: string; min: number; max: number; neutral: number }[] = [
  { field: "gamma", label: "Gamma / midtones", min: 0.35, max: 2.5, neutral: 1 },
  { field: "black_point", label: "Black point shift", min: -0.2, max: 0.25, neutral: 0 },
  { field: "white_point", label: "White point shift", min: 0.5, max: 1.2, neutral: 1 },
  { field: "shadow_lift", label: "Protected shadow lift", min: 0, max: 1, neutral: 0 },
  { field: "flattening", label: "Illumination flattening", min: 0, max: 1, neutral: 0 }
];

function tuningValue(preset: ViewerPreset, field: PresetTuningField): number {
  const value = preset[field];
  return typeof value === "number" && Number.isFinite(value) ? value : 1;
}

function tuningPercent(value: number): string {
  const percent = Math.round((value - 1) * 100);
  return `${percent > 0 ? "+" : ""}${percent}%`;
}

function clinicalTuningValue(preset: ViewerPreset, field: PresetTuningField, neutral: number): number {
  const value = preset[field];
  return typeof value === "number" && Number.isFinite(value) ? value : neutral;
}

interface FineTunePanelProps {
  slot: PresetSlot;
  draft: ViewerPreset;
  imageAnalysis: ImageAnalysis | null;
  saving: boolean;
  onChangeFilter: (mode: ViewerFilterMode) => void;
  onUpdate: (field: PresetTuningField, value: number) => void;
  onToggleInvert: (value: boolean) => void;
  onReset: () => void;
  onCancel: () => void;
  onSave: () => void;
}

function histogramPath(values: number[], height = 76): string {
  const maximum = Math.max(1, ...values.map((value) => Math.log1p(value)));
  return values.map((value, index) => {
    const x = index;
    const y = height - Math.log1p(value) / maximum * (height - 4);
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function activeHistogram(analysis: ImageAnalysis, mode: ViewerFilterMode): { label: string; distribution: ChannelDistribution } {
  if (mode === "redfree" || mode === "redfreeenhanced") return { label: "Green", distribution: analysis.green };
  return { label: "Luminance", distribution: analysis.luminance };
}

function FineTuneHistogram({ draft, analysis }: { draft: ViewerPreset; analysis: ImageAnalysis | null }) {
  if (!analysis) return <div className="workbench-histogram-empty">Analyzing decoded image pixels…</div>;
  const mode = (draft.filter ?? "none") as ViewerFilterMode;
  const recipe = clinicalDisplayRecipe(mode, analysis);
  const black = Math.max(0, Math.min(1, recipe.blackPoint + (draft.black_point ?? 0)));
  const white = Math.max(0, Math.min(1, recipe.whitePoint + (draft.white_point ?? 1) - 1));
  const active = activeHistogram(analysis, mode);
  return <div className="workbench-histogram">
    <svg viewBox="0 0 256 76" preserveAspectRatio="none" role="img" aria-label="RGB intensity histogram with black and white window markers">
      <path className="is-luminance" d={histogramPath(analysis.histograms.luminance)} />
      <path className="is-red" d={histogramPath(analysis.histograms.red)} />
      <path className="is-green" d={histogramPath(analysis.histograms.green)} />
      <path className="is-blue" d={histogramPath(analysis.histograms.blue)} />
      <line className="is-black-point" x1={black * 255} x2={black * 255} y1="0" y2="76" />
      <line className="is-white-point" x1={white * 255} x2={white * 255} y1="0" y2="76" />
    </svg>
    <div className="workbench-histogram-legend"><span className="is-red">R</span><span className="is-green">G</span><span className="is-blue">B</span><span>{active.label}: P1 {active.distribution.p01} · median {active.distribution.median} · P99 {active.distribution.p99}</span></div>
    <div className="workbench-histogram-window"><span>Black {Math.round(black * 255)}</span><span>Auto-window + preset adjustment</span><span>White {Math.round(white * 255)}</span></div>
  </div>;
}

function FineTunePanel({ slot, draft, imageAnalysis, saving, onChangeFilter, onUpdate, onToggleInvert, onReset, onCancel, onSave }: FineTunePanelProps) {
  return (
    <section className="workbench-fine-tune is-inspector" role="region" aria-labelledby="fine-tune-title">
      <header>
        <div><span>Viewer preset {slot}</span><h2 id="fine-tune-title">Fine tune color</h2><p>Adjust while watching the image · source pixels remain unchanged</p></div>
        <button type="button" aria-label="Close fine tune panel" onClick={onCancel}><i className="fa-solid fa-xmark" /></button>
      </header>
      <div className="workbench-fine-tune-body">
        <section>
          <div className="workbench-fine-tune-heading"><h3>Filter</h3><span>Choose and preview</span></div>
          <div className="workbench-fine-tune-filters" role="radiogroup" aria-label="Preset clinical filter">
            {CLINICAL_FILTER_MODES.map((filter) => (
              <button
                type="button"
                role="radio"
                aria-checked={(draft.filter ?? "none") === filter.key}
                className={(draft.filter ?? "none") === filter.key ? "is-active" : ""}
                key={filter.key}
                title={filter.label}
                onClick={() => onChangeFilter(filter.key)}
              ><strong>{filter.short}</strong><span>{filter.label}</span></button>
            ))}
          </div>
        </section>
        <section>
          <div className="workbench-fine-tune-heading"><h3>Overall</h3><span>{CLINICAL_FILTER_MODES.find((item) => item.key === draft.filter)?.label ?? "No filter"}</span></div>
          <div className="workbench-tuning-stack">
            {OVERALL_TUNING.map(({ field, label }) => {
              const value = tuningValue(draft, field);
              return <label key={field}><span>{label}</span><input type="range" min={field === "saturation" ? 0 : 0.5} max={field === "brightness" ? 3 : 2} step="0.01" value={value} onChange={(event) => onUpdate(field, Number(event.target.value))} /><output>{tuningPercent(value)}</output></label>;
            })}
          </div>
        </section>
        <section>
          <div className="workbench-fine-tune-heading"><h3>Clinical enhancement</h3><span>Presentation only</span></div>
          <FineTuneHistogram draft={draft} analysis={imageAnalysis} />
          <div className="workbench-tuning-stack">
            {CLINICAL_TUNING.map(({ field, label, min, max, neutral }) => {
              const value = clinicalTuningValue(draft, field, neutral);
              return <label key={field}><span>{label}</span><input type="range" min={min} max={max} step="0.01" value={value} onChange={(event) => onUpdate(field, Number(event.target.value))} /><output>{field === "gamma" ? value.toFixed(2) : tuningPercent(value + (neutral === 0 ? 1 : 0))}</output></label>;
            })}
            <label className="workbench-tuning-toggle"><span>Invert luminance</span><input type="checkbox" checked={draft.invert === true} onChange={(event) => onToggleInvert(event.target.checked)} /><output>{draft.invert ? "On" : "Off"}</output></label>
          </div>
          <p className="workbench-fine-tune-note">Auto-windowing is recalculated from each image. Zoom, pan and loupe are never stored in presets.</p>
        </section>
        <section>
          <div className="workbench-fine-tune-heading"><h3>Channels</h3><span>Luminance and saturation</span></div>
          <div className="workbench-channel-tuning">
            <div className="workbench-channel-tuning-head"><span>Channel</span><span>Luminance</span><span>Saturation</span></div>
            {CHANNEL_TUNING.map((channel) => {
              const luminance = tuningValue(draft, channel.luminance);
              const saturation = tuningValue(draft, channel.saturation);
              return <div className={`workbench-channel-row is-${channel.key}`} key={channel.key}>
                <strong>{channel.label}</strong>
                <label><input aria-label={`${channel.label} luminance`} type="range" min="0" max="2" step="0.01" value={luminance} onChange={(event) => onUpdate(channel.luminance, Number(event.target.value))} /><output>{tuningPercent(luminance)}</output></label>
                <label><input aria-label={`${channel.label} saturation`} type="range" min="0" max="2" step="0.01" value={saturation} onChange={(event) => onUpdate(channel.saturation, Number(event.target.value))} /><output>{tuningPercent(saturation)}</output></label>
              </div>;
            })}
          </div>
        </section>
      </div>
      <footer>
        <button type="button" onClick={onReset}>Reset tuning</button>
        <span />
        <button type="button" onClick={onCancel}>Cancel</button>
        <button type="button" className="is-primary" disabled={saving} onClick={onSave}>{saving ? "Saving…" : "Save changes"}</button>
      </footer>
    </section>
  );
}

const TOOL_LABELS: Record<ToolKey, string> = {
  box: "Box",
  rect: "Rect segment",
  polygon: "Polygon",
  brush_mask: "Brush",
  ellipse: "Ellipse",
  pyramid: "Pyramid"
};

const TOOL_SHORTCUTS: Record<ToolKey, string> = {
  box: "B",
  rect: "R",
  polygon: "P",
  brush_mask: "M",
  ellipse: "E",
  pyramid: "Y"
};

function cssColor(annotationClass: AnnotationClassRef): string {
  return `#${annotationColor(annotationClass).toString(16).padStart(6, "0")}`;
}

function geometrySummary(geometry: AnnotationGeometry): string {
  if (geometry.type === "box" || geometry.type === "rect" || geometry.type === "ellipse") {
    return `${geometry.type.replace("_", " ")} · ${Math.round(geometry.width)} × ${Math.round(geometry.height)} px`;
  }
  if (geometry.type === "brush_mask") {
    return `brush mask · ${geometry.strokes.reduce((count, stroke) => count + stroke.length, 0)} points`;
  }
  return `${geometry.type} · ${geometry.points.length} points`;
}

function guidelineText(value: string): string {
  if (typeof DOMParser !== "undefined") {
    return new DOMParser().parseFromString(value, "text/html").body.textContent?.trim() || value;
  }
  return value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function legacyGeometry(value: Record<string, unknown>): AnnotationGeometry | null {
  const geometryType = typeof value.geometry_type === "string" ? value.geometry_type : "box";
  const roi = value.roi && typeof value.roi === "object" ? value.roi as Record<string, unknown> : null;
  const roiPoints = Array.isArray(roi?.pixel) ? roi.pixel as number[][] : [];
  const polygon = value.polygon && typeof value.polygon === "object" ? value.polygon as Record<string, unknown> : null;
  const polygonPoints = Array.isArray(polygon?.pixel) ? polygon.pixel as number[][] : [];
  if ((geometryType === "polygon" || geometryType === "pyramid" || geometryType === "region") && polygonPoints.length >= 3) {
    return {
      type: geometryType === "pyramid" ? "pyramid" : "polygon",
      points: polygonPoints.map((point) => [Number(point[0]), Number(point[1])])
    };
  }
  if (roiPoints.length === 2) {
    const x = Math.min(roiPoints[0][0], roiPoints[1][0]);
    const y = Math.min(roiPoints[0][1], roiPoints[1][1]);
    const width = Math.abs(roiPoints[1][0] - roiPoints[0][0]);
    const height = Math.abs(roiPoints[1][1] - roiPoints[0][1]);
    return { type: geometryType === "ellipse" ? "ellipse" : "box", x, y, width, height };
  }
  return null;
}

function initialAnnotations(workspace: GradingWorkspace, panelDrafts: Record<string, PanelDraft>): WorkbenchAnnotation[] {
  const annotations: WorkbenchAnnotation[] = [];
  for (const panel of workspace.panels) {
    const draft = panelDrafts[panel.id];
    const classes = availableAnnotationClasses(workspace, panel, draft.gradeId, draft.selectedFeatureIds);
    for (const raw of panel.existing_grade?.annotations ?? []) {
      const featureId = typeof raw.feature_id === "number" ? raw.feature_id : null;
      const classRef = classes.find((item) => item.featureId === featureId);
      const geometry = legacyGeometry(raw);
      if (!classRef || !geometry) continue;
      const tool = geometry.type === "brush_mask" ? "brush_mask" : geometry.type;
      annotations.push({
        id: crypto.randomUUID(),
        imageUuid: workspace.active_image_uuid,
        panelId: panel.id,
        classRef,
        tool,
        geometry,
        visible: true,
        locked: false
      });
    }
  }
  return annotations;
}

function panelDraftMap(workspace: GradingWorkspace): Record<string, PanelDraft> {
  return Object.fromEntries(workspace.panels.map((panel) => [panel.id, createInitialPanelDraft(panel)]));
}

export function App({ workspaceUrl }: AppProps) {
  const [workspace, setWorkspace] = useState<GradingWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(100);
  const [activeImageUuid, setActiveImageUuid] = useState("");
  const [activePanelId, setActivePanelId] = useState("");
  const [panelDrafts, setPanelDrafts] = useState<Record<string, PanelDraft>>({});
  const [annotations, setAnnotations] = useState<WorkbenchAnnotation[]>([]);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [activeClassId, setActiveClassId] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<ToolKey | null>(null);
  const [transformEnabled, setTransformEnabled] = useState(false);
  const [eraserEnabled, setEraserEnabled] = useState(false);
  const [filters, setFilters] = useState<ViewerFilters>(DEFAULT_FILTERS);
  const [imageAnalysis, setImageAnalysis] = useState<ImageAnalysis | null>(null);
  const [viewerPresets, setViewerPresets] = useState<ViewerPresetMap>({});
  const [activePresetSlot, setActivePresetSlot] = useState<PresetSlot | null>(null);
  const [presetMenu, setPresetMenu] = useState<{ slot: PresetSlot; x: number; y: number } | null>(null);
  const [fineTuneSlot, setFineTuneSlot] = useState<PresetSlot | null>(null);
  const [fineTuneDraft, setFineTuneDraft] = useState<ViewerPreset | null>(null);
  const [fineTuneSaving, setFineTuneSaving] = useState(false);
  const [savingPreset, setSavingPreset] = useState(false);
  const [loupeEnabled, setLoupeEnabled] = useState(false);
  const [brushSize, setBrushSize] = useState(24);
  const [eraserSize, setEraserSize] = useState(36);
  const [rightTab, setRightTab] = useState<"grading" | "annotations">("grading");
  const [status, setStatus] = useState("Loading workspace");
  const [undoStack, setUndoStack] = useState<WorkbenchAnnotation[][]>([]);
  const [redoStack, setRedoStack] = useState<WorkbenchAnnotation[][]>([]);
  const [pendingRecovery, setPendingRecovery] = useState<StoredWorkbenchDraft | null>(null);
  const [draftReady, setDraftReady] = useState(false);
  const viewerRef = useRef<ViewerControls>(null);
  const fineTuneSnapshotRef = useRef<FineTuneSnapshot | null>(null);
  const filterProfilesRef = useRef<Partial<Record<ViewerFilterMode, ViewerFilters>>>({});
  const onZoomChange = useCallback((percent: number) => setZoom(percent), []);

  useEffect(() => {
    const controller = new AbortController();
    setWorkspace(null);
    setError(null);
    fetchWorkspace(workspaceUrl, controller.signal)
      .then((resolved) => {
        const drafts = panelDraftMap(resolved);
        setWorkspace(resolved);
        setPanelDrafts(drafts);
        setAnnotations(initialAnnotations(resolved, drafts));
        setActiveImageUuid(resolved.active_image_uuid);
        setActivePanelId(resolved.panels[0]?.id ?? "");
        setFilters(DEFAULT_FILTERS);
        setActivePresetSlot(null);
        setFineTuneDraft(null);
        setFineTuneSlot(null);
        fineTuneSnapshotRef.current = null;
        setSavingPreset(false);
        setStatus("Workspace ready · capture levels (N)");
        const key = `${resolved.target.type}:${resolved.target.ref}:${resolved.target.slot}`;
        return loadDraft(key).then((draft) => {
          if (draft && draft.contextRevision === resolved.context_revision) setPendingRecovery(draft);
          else setDraftReady(true);
        }).catch(() => setDraftReady(true));
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load grading workspace.");
      });
    return () => controller.abort();
  }, [workspaceUrl]);

  useEffect(() => {
    if (filters.mode !== "none") filterProfilesRef.current[filters.mode] = { ...filters };
  }, [filters]);

  useEffect(() => {
    if (!workspace) return;
    const controller = new AbortController();
    fetchViewerPresets(controller.signal).then(setViewerPresets).catch(() => setStatus("Workspace ready; presets unavailable"));
    return () => controller.abort();
  }, [workspace]);

  const activePanel = useMemo(
    () => workspace?.panels.find((panel) => panel.id === activePanelId) ?? workspace?.panels[0] ?? null,
    [activePanelId, workspace]
  );
  const activeDraft = activePanel ? panelDrafts[activePanel.id] : null;
  const classOptions = useMemo(() => {
    if (!workspace || !activePanel || !activeDraft) return [];
    return availableAnnotationClasses(workspace, activePanel, activeDraft.gradeId, activeDraft.selectedFeatureIds);
  }, [activeDraft, activePanel, workspace]);
  const activeClass = classOptions.find((item) => item.id === activeClassId) ?? null;
  const toolOptions = workspace && activeClass ? toolsForClass(workspace.annotation_context, activeClass) : [];
  const currentImage = workspace?.images.find((image) => image.uuid === activeImageUuid) ?? workspace?.image ?? null;
  const visibleAnnotations = annotations.filter(
    (annotation) => annotation.imageUuid === activeImageUuid && annotation.panelId === activePanel?.id
  );
  const selectedAnnotation = visibleAnnotations.find((annotation) => annotation.id === selectedAnnotationId) ?? null;
  const allAnnotationsHidden = visibleAnnotations.length > 0 && visibleAnnotations.every((annotation) => !annotation.visible);

  useEffect(() => {
    setImageAnalysis(null);
    if (!currentImage) return;
    const controller = new AbortController();
    analyzeImageUrl(currentImage.url, controller.signal)
      .then(setImageAnalysis)
      .catch(() => {
        if (!controller.signal.aborted) setStatus("Image ready · automatic channel windowing unavailable");
      });
    return () => controller.abort();
  }, [currentImage?.url]);

  useEffect(() => {
    if (classOptions.length === 0) {
      setActiveClassId(null);
      setActiveTool(null);
      return;
    }
    const nextClass = classOptions.find((item) => item.id === activeClassId) ?? classOptions[0];
    const classChanged = nextClass.id !== activeClassId;
    if (classChanged) setActiveClassId(nextClass.id);
    if (!workspace) return;
    const tools = toolsForClass(workspace.annotation_context, nextClass);
    if (classChanged || (activeTool && !tools.includes(activeTool))) {
      const preferred = workspace.annotation_context.default_feature_policy.preferred_tool;
      setActiveTool(tools.includes(preferred) ? preferred : tools[0] ?? null);
    }
  }, [activeClassId, activeTool, classOptions, workspace]);

  const draftKey = workspace ? `${workspace.target.type}:${workspace.target.ref}:${workspace.target.slot}` : "";
  const storedDraft = useCallback((): StoredWorkbenchDraft | null => {
    if (!workspace || !activePanelId || !activeImageUuid) return null;
    return {
      contextRevision: workspace.context_revision,
      activeImageUuid,
      activePanelId,
      panels: workspace.panels.map((panel) => ({
        panelId: panel.id,
        gradeId: panelDrafts[panel.id]?.gradeId ?? null,
        selectedFeatureIds: [...(panelDrafts[panel.id]?.selectedFeatureIds ?? [])],
        comment: panelDrafts[panel.id]?.comment ?? ""
      })),
      annotations,
      updatedAt: new Date().toISOString()
    };
  }, [activeImageUuid, activePanelId, annotations, panelDrafts, workspace]);

  useEffect(() => {
    if (!draftReady || !draftKey || pendingRecovery) return;
    const timer = window.setTimeout(() => {
      const draft = storedDraft();
      if (!draft) return;
      saveDraft(draftKey, draft).then(() => setStatus("Draft saved locally")).catch(() => setStatus("Local draft could not be saved"));
    }, 650);
    return () => window.clearTimeout(timer);
  }, [draftKey, draftReady, pendingRecovery, storedDraft]);

  const commitAnnotations = useCallback((next: WorkbenchAnnotation[]) => {
    setAnnotations((current) => {
      setUndoStack((stack) => [...stack.slice(-39), current]);
      setRedoStack([]);
      return next;
    });
  }, []);

  const undo = useCallback(() => {
    setUndoStack((stack) => {
      const previous = stack.at(-1);
      if (!previous) return stack;
      setAnnotations((current) => { setRedoStack((redo) => [...redo, current]); return previous; });
      setSelectedAnnotationId(null);
      return stack.slice(0, -1);
    });
  }, []);

  const redo = useCallback(() => {
    setRedoStack((stack) => {
      const next = stack.at(-1);
      if (!next) return stack;
      setAnnotations((current) => { setUndoStack((undoItems) => [...undoItems, current]); return next; });
      setSelectedAnnotationId(null);
      return stack.slice(0, -1);
    });
  }, []);

  const chooseClass = (annotationClass: AnnotationClassRef) => {
    const existing = visibleAnnotations.find((annotation) => annotation.classRef.id === annotationClass.id);
    if (!annotationClass.multipleInstances && existing) {
      setSelectedAnnotationId(existing.id);
      setActiveClassId(annotationClass.id);
      setActiveTool(null);
      setTransformEnabled(true);
      setEraserEnabled(false);
      setRightTab("annotations");
      setStatus(`${annotationClass.label} already has its single allowed instance`);
      return;
    }
    setActiveClassId(annotationClass.id);
    setSelectedAnnotationId(null);
    setTransformEnabled(false);
    setEraserEnabled(false);
    if (workspace) {
      const tools = toolsForClass(workspace.annotation_context, annotationClass);
      const preferred = workspace.annotation_context.default_feature_policy.preferred_tool;
      setActiveTool(tools.includes(preferred) ? preferred : tools[0] ?? null);
    }
    setStatus(`${annotationClass.label} selected`);
  };

  const createAnnotation = useCallback((geometry: AnnotationGeometry) => {
    if (!workspace || !activePanel || !activeClass || !activeTool) return;
    if (!canCreateAnnotation(activeClass, annotations)) {
      const existing = annotations.find((item) => item.classRef.id === activeClass.id);
      setSelectedAnnotationId(existing?.id ?? null);
      setStatus(`${activeClass.label} allows one instance; selected the existing annotation`);
      return;
    }
    const annotation: WorkbenchAnnotation = {
      id: crypto.randomUUID(),
      imageUuid: activeImageUuid,
      panelId: activePanel.id,
      classRef: activeClass,
      tool: activeTool,
      geometry,
      visible: true,
      locked: false
    };
    commitAnnotations([...annotations, annotation]);
    setSelectedAnnotationId(annotation.id);
    setActiveTool(null);
    setTransformEnabled(true);
    setEraserEnabled(false);
    setRightTab("annotations");
    setStatus(`${activeClass.label} annotation added`);
  }, [activeClass, activeImageUuid, activePanel, activeTool, annotations, commitAnnotations, workspace]);

  const deleteAnnotation = useCallback((annotationId: string) => {
    commitAnnotations(annotations.filter((annotation) => annotation.id !== annotationId));
    setSelectedAnnotationId((selected) => selected === annotationId ? null : selected);
    setTransformEnabled((enabled) => selectedAnnotationId === annotationId ? false : enabled);
    setEraserEnabled((enabled) => selectedAnnotationId === annotationId ? false : enabled);
    setStatus("Annotation deleted");
  }, [annotations, commitAnnotations, selectedAnnotationId]);

  const copyAnnotation = useCallback((annotationId: string) => {
    const source = annotations.find((annotation) => annotation.id === annotationId);
    if (!source) return;
    if (!source.classRef.multipleInstances) {
      setStatus(`${source.classRef.label} allows only one instance`);
      return;
    }
    const copy = duplicateAnnotation(source, crypto.randomUUID());
    commitAnnotations([...annotations, copy]);
    setSelectedAnnotationId(copy.id);
    setActiveTool(null);
    setTransformEnabled(true);
    setEraserEnabled(false);
    setRightTab("annotations");
    setStatus(`${source.classRef.label} annotation duplicated`);
  }, [annotations, commitAnnotations]);

  const enterPanMode = useCallback(() => {
    setSelectedAnnotationId(null);
    setActiveTool(null);
    setTransformEnabled(false);
    setEraserEnabled(false);
    setStatus("Pan mode");
  }, []);

  const selectAnnotationForEdit = useCallback((annotationId: string | null) => {
    setSelectedAnnotationId(annotationId);
    setActiveTool(null);
    setEraserEnabled(false);
    setTransformEnabled(true);
    if (annotationId) {
      setRightTab("annotations");
      setStatus("Annotation selected");
    }
  }, []);

  const updateAnnotationGeometry = useCallback((annotationId: string, geometry: AnnotationGeometry) => {
    commitAnnotations(annotations.map((annotation) => annotation.id === annotationId ? { ...annotation, geometry } : annotation));
    setStatus("Annotation updated");
  }, [annotations, commitAnnotations]);

  const toggleAnnotationLock = useCallback((annotationId: string) => {
    const annotation = annotations.find((item) => item.id === annotationId);
    if (!annotation) return;
    commitAnnotations(annotations.map((item) => item.id === annotationId ? { ...item, locked: !item.locked } : item));
    if (!annotation.locked) setEraserEnabled(false);
    setStatus(annotation.locked ? "Annotation unlocked" : "Annotation locked");
  }, [annotations, commitAnnotations]);

  const toggleAllAnnotationVisibility = useCallback(() => {
    const nextVisible = allAnnotationsHidden;
    commitAnnotations(annotations.map((annotation) => (
      annotation.imageUuid === activeImageUuid && annotation.panelId === activePanel?.id
        ? { ...annotation, visible: nextVisible }
        : annotation
    )));
    setStatus(nextVisible ? "All annotations shown" : "All annotations hidden");
  }, [activeImageUuid, activePanel?.id, allAnnotationsHidden, annotations, commitAnnotations]);

  const restoreCaptureLevels = useCallback((message = "Capture levels restored (N)") => {
    setFilters(DEFAULT_FILTERS);
    setActivePresetSlot(null);
    setFineTuneDraft(null);
    setFineTuneSlot(null);
    fineTuneSnapshotRef.current = null;
    setSavingPreset(false);
    setStatus(message);
  }, []);

  const openImageAtCaptureLevels = useCallback((imageUuid: string) => {
    setActiveImageUuid(imageUuid);
    setSelectedAnnotationId(null);
    restoreCaptureLevels("Image opened at capture levels (N)");
  }, [restoreCaptureLevels]);

  const usePreset = useCallback((slot: PresetSlot) => {
    if (savingPreset) {
      const preset = presetFromViewer(filters, slot);
      saveViewerPreset(slot, preset).then(() => {
        setViewerPresets((current) => ({ ...current, [slot]: preset }));
        setActivePresetSlot(slot);
        setSavingPreset(false);
        setStatus(`Viewer preset ${slot} saved`);
      }).catch(() => setStatus(`Viewer preset ${slot} could not be saved`));
      return;
    }
    const preset = viewerPresets[slot];
    if (!preset) { setStatus(`Preset ${slot} is empty; choose Save then ${slot}`); return; }
    setFilters(filtersFromPreset(preset));
    setActivePresetSlot(slot);
    setStatus(`Viewer preset ${slot} applied`);
  }, [filters, savingPreset, viewerPresets]);

  const openFineTune = useCallback((slot: PresetSlot) => {
    const preset = viewerPresets[slot];
    if (!preset) return;
    fineTuneSnapshotRef.current = { filters, activePresetSlot };
    setPresetMenu(null);
    setFineTuneSlot(slot);
    setFineTuneDraft(normalizePresetTuning(preset));
    setFilters(filtersFromPreset(preset));
    setActivePresetSlot(slot);
    setStatus(`Fine tuning viewer preset ${slot}`);
  }, [activePresetSlot, filters, viewerPresets]);

  const cancelFineTune = useCallback(() => {
    const snapshot = fineTuneSnapshotRef.current;
    if (snapshot) {
      setFilters(snapshot.filters);
      setActivePresetSlot(snapshot.activePresetSlot);
    }
    fineTuneSnapshotRef.current = null;
    setFineTuneDraft(null);
    setFineTuneSlot(null);
    setStatus("Preset tuning cancelled");
  }, []);

  const updateFineTune = useCallback((field: PresetTuningField, value: number) => {
    setFineTuneDraft((current) => {
      if (!current) return current;
      const updated = { ...current, [field]: value };
      if (field === "shadow_lift") {
        if (value > 0 && (updated.filter ?? "none") === "none") updated.filter = "enhance";
        if (value === 0 && updated.filter === "enhance") updated.filter = "none";
      }
      setFilters(filtersFromPreset(updated));
      return updated;
    });
  }, []);

  const resetFineTune = useCallback(() => {
    setFineTuneDraft((current) => {
      if (!current) return current;
      const updated = { ...current };
      for (const { field } of OVERALL_TUNING) updated[field] = 1;
      for (const channel of CHANNEL_TUNING) {
        updated[channel.luminance] = 1;
        updated[channel.saturation] = 1;
      }
      for (const { field, neutral } of CLINICAL_TUNING) updated[field] = neutral;
      updated.invert = false;
      setFilters(filtersFromPreset(updated));
      return updated;
    });
  }, []);

  const commitFineTune = useCallback(async () => {
    if (!fineTuneSlot || !fineTuneDraft) return;
    setFineTuneSaving(true);
    try {
      await saveViewerPreset(fineTuneSlot, fineTuneDraft);
      setViewerPresets((current) => ({ ...current, [fineTuneSlot]: fineTuneDraft }));
      setActivePresetSlot(fineTuneSlot);
      fineTuneSnapshotRef.current = null;
      setFineTuneDraft(null);
      setFineTuneSlot(null);
      setStatus(`Viewer preset ${fineTuneSlot} tuned and saved`);
    } catch {
      setStatus(`Viewer preset ${fineTuneSlot} could not be saved`);
    } finally {
      setFineTuneSaving(false);
    }
  }, [fineTuneDraft, fineTuneSlot]);

  useEffect(() => {
    if (!presetMenu) return;
    const closeMenu = () => setPresetMenu(null);
    window.addEventListener("pointerdown", closeMenu);
    return () => window.removeEventListener("pointerdown", closeMenu);
  }, [presetMenu]);

  const updateAnnotation = (annotationId: string, change: Partial<WorkbenchAnnotation>) => {
    commitAnnotations(annotations.map((annotation) => annotation.id === annotationId ? { ...annotation, ...change } : annotation));
  };

  const chooseGrade = (panel: GradingPanel, gradeId: number) => {
    const featureAnnotations = annotations.filter(
      (annotation) => annotation.panelId === panel.id && annotation.classRef.source === "grading_feature"
    );
    if (featureAnnotations.length) {
      commitAnnotations(annotations.filter((annotation) => !featureAnnotations.includes(annotation)));
      setStatus("Grade changed; feature annotations from the prior grade were cleared");
    }
    setPanelDrafts((drafts) => ({
      ...drafts,
      [panel.id]: { ...drafts[panel.id], gradeId, selectedFeatureIds: new Set() }
    }));
    setActiveClassId(null);
  };

  const toggleFeature = (panel: GradingPanel, featureId: number) => {
    const draft = panelDrafts[panel.id];
    const selected = new Set(draft.selectedFeatureIds);
    if (selected.has(featureId)) {
      const hasAnnotations = annotations.some(
        (annotation) => annotation.panelId === panel.id && annotation.classRef.featureId === featureId
      );
      if (hasAnnotations) {
        setStatus("Delete this feature's annotations before deselecting it");
        return;
      }
      selected.delete(featureId);
    } else {
      selected.add(featureId);
    }
    setPanelDrafts((drafts) => ({ ...drafts, [panel.id]: { ...draft, selectedFeatureIds: selected } }));
  };

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (fineTuneSlot && event.key === "Escape") {
        event.preventDefault();
        cancelFineTune();
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        event.shiftKey ? redo() : undo();
        return;
      }
      const tool = (Object.keys(TOOL_SHORTCUTS) as ToolKey[]).find((key) => TOOL_SHORTCUTS[key].toLowerCase() === event.key.toLowerCase());
      if (event.key === "Escape" || event.key.toLowerCase() === "v") {
        event.preventDefault();
        enterPanMode();
      } else if (event.key.toLowerCase() === "s") {
        setActiveTool(null);
        setTransformEnabled(true);
        setEraserEnabled(false);
        setStatus("Select and transform mode");
      } else if (event.key.toLowerCase() === "x") {
        const selected = annotations.find((annotation) => annotation.id === selectedAnnotationId);
        if (selected?.geometry.type === "brush_mask" && !selected.locked) {
          setActiveTool(null);
          setTransformEnabled(false);
          setEraserEnabled(true);
          setStatus("Brush eraser active");
        }
      } else if (tool && toolOptions.includes(tool)) {
        setSelectedAnnotationId(null);
        setTransformEnabled(false);
        setEraserEnabled(false);
        setActiveTool(tool);
      }
      else if (event.key.toLowerCase() === "l") setLoupeEnabled((enabled) => !enabled);
      else if (event.key.toLowerCase() === "f") viewerRef.current?.fit();
      else if (/^[1-9]$/.test(event.key)) classOptions[Number(event.key) - 1] && chooseClass(classOptions[Number(event.key) - 1]);
      else if ((event.key === "Delete" || event.key === "Backspace") && selectedAnnotationId) deleteAnnotation(selectedAnnotationId);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });

  const restoreRecovery = () => {
    if (!pendingRecovery) return;
    setActiveImageUuid(pendingRecovery.activeImageUuid);
    setActivePanelId(pendingRecovery.activePanelId);
    setPanelDrafts(Object.fromEntries(pendingRecovery.panels.map((item) => [item.panelId, {
      gradeId: item.gradeId,
      selectedFeatureIds: new Set(item.selectedFeatureIds),
      comment: item.comment
    }])));
    setAnnotations(pendingRecovery.annotations);
    setPendingRecovery(null);
    setDraftReady(true);
    setStatus("Recovered local draft");
  };

  const discardRecovery = () => {
    clearDraft(draftKey).catch(() => undefined);
    setPendingRecovery(null);
    setDraftReady(true);
    setStatus("Previous draft discarded");
  };

  if (error) {
    return <section className="workbench-fatal" role="alert"><p className="workbench-kicker">Unable to open viewer</p><h1>Grading workbench unavailable</h1><p>{error}</p><a href="/grading/">Return to grading</a></section>;
  }
  if (!workspace || !activePanel || !activeDraft || !currentImage) {
    return <div className="workbench-loading" role="status"><span className="workbench-loader" /><strong>Preparing grading workspace</strong><small>Resolving images, schemes, and annotation policy</small></div>;
  }

  const selectedGrade = activePanel.grades.find((grade) => grade.id === activeDraft.gradeId) ?? null;
  const completedPanels = workspace.panels.filter((panel) => panelDrafts[panel.id]?.gradeId).length;
  const filtersChanged = JSON.stringify(filters) !== JSON.stringify(DEFAULT_FILTERS);

  return (
    <div className="workbench-shell">
      <header className="workbench-topbar">
        <div className="workbench-brand">
          <span className="workbench-brand-mark">FX</span>
          <div><strong>Grading Workbench</strong><span>{workspace.task.lab_unit.name}</span></div>
        </div>
        <div className="workbench-case-context">
          <span className="workbench-kicker">{workspace.target.slot} · {workspace.task.state}</span>
          <strong>{activePanel.disease.name}</strong>
        </div>
        <div className="workbench-progress" aria-label={`${completedPanels} of ${workspace.panels.length} grading panels complete`}>
          <span>{completedPanels}/{workspace.panels.length} panels</span>
          <i><b style={{ width: `${workspace.panels.length ? completedPanels / workspace.panels.length * 100 : 0}%` }} /></i>
        </div>
        <div className="workbench-top-actions">
          <a href="/grading/">Close</a>
        </div>
      </header>

      <div className="workbench-viewer-toolbar" aria-label="Image viewing controls">
        <div className="workbench-toolbar-group workbench-history-controls">
          <button type="button" onClick={undo} disabled={!undoStack.length} title="Undo (⌘Z)" aria-label="Undo"><i className="fa-solid fa-rotate-left" /></button>
          <button type="button" onClick={redo} disabled={!redoStack.length} title="Redo (⇧⌘Z)" aria-label="Redo"><i className="fa-solid fa-rotate-right" /></button>
        </div>
        <div className="workbench-toolbar-group workbench-filter-modes" aria-label="Predefined image filters">
          <span>Filters</span>
          {CLINICAL_FILTER_MODES.map((filter) => {
            const active = filter.key === "none" ? !filtersChanged : filters.mode === filter.key;
            return <button type="button" key={filter.key} className={active ? "is-active" : ""} title={filter.label} aria-label={filter.label} onClick={() => {
              if (filter.key === "none") restoreCaptureLevels();
              else {
                setActivePresetSlot(null);
                setFilters(filtersForClinicalMode(filter.key, filterProfilesRef.current[filter.key]));
              }
            }}>{filter.short}</button>;
          })}
        </div>
        <label className="workbench-toolbar-slider"><span>Exposure</span><input aria-label="Exposure" type="range" min="-0.5" max="2" step="0.01" value={filters.brightness} onChange={(event) => { setActivePresetSlot(null); setFilters((current) => ({ ...current, brightness: Number(event.target.value) })); }} /><output>{Math.round(filters.brightness * 100)}</output></label>
        <label className="workbench-toolbar-slider"><span>Contrast</span><input aria-label="Contrast" type="range" min="-0.5" max="1" step="0.01" value={filters.contrast} onChange={(event) => { setActivePresetSlot(null); setFilters((current) => ({ ...current, contrast: Number(event.target.value) })); }} /><output>{Math.round(filters.contrast * 100)}</output></label>
        <label className="workbench-toolbar-slider"><span>Shadow lift</span><input aria-label="Protected shadow lift" type="range" min="0" max="1" step="0.01" value={filters.shadowLift} onChange={(event) => { const value = Number(event.target.value); setActivePresetSlot(null); setFilters((current) => ({ ...current, shadowLift: value, mode: value > 0 && current.mode === "none" ? "enhance" : value === 0 && current.mode === "enhance" ? "none" : current.mode })); }} /><output>{Math.round(filters.shadowLift * 100)}</output></label>
        <div className="workbench-toolbar-group workbench-view-controls">
          <button type="button" className={loupeEnabled ? "is-active" : ""} onClick={() => setLoupeEnabled((value) => !value)} title="Loupe (L)"><i className="fa-solid fa-magnifying-glass" /> Loupe</button>
        </div>
        <div className="workbench-toolbar-group workbench-preset-controls" aria-label="Viewer presets">
          <span>Presets</span>
          {([1, 2, 3, 4, 5] as const).map((slot) => <button type="button" key={slot} aria-pressed={activePresetSlot === slot} className={`${viewerPresets[slot] ? "has-preset" : ""} ${activePresetSlot === slot ? "is-active" : ""} ${savingPreset ? "is-save-target" : ""}`} title={savingPreset ? `Save current settings to preset ${slot}` : viewerPresets[slot] ? `Apply preset ${slot}; right-click to fine tune` : `Preset ${slot} is empty`} onClick={() => usePreset(slot)} onContextMenu={(event) => { if (!viewerPresets[slot]) return; event.preventDefault(); setPresetMenu({ slot, x: event.clientX, y: event.clientY }); }} onKeyDown={(event) => { if (viewerPresets[slot] && event.shiftKey && event.key === "F10") { event.preventDefault(); const bounds = event.currentTarget.getBoundingClientRect(); setPresetMenu({ slot, x: bounds.left, y: bounds.bottom + 4 }); } }}>{slot}</button>)}
          <button type="button" className={savingPreset ? "is-active" : ""} onClick={() => setSavingPreset((current) => !current)}>{savingPreset ? "Cancel" : "Save"}</button>
        </div>
        <button type="button" className="workbench-toolbar-reset" disabled={!filtersChanged && !loupeEnabled} onClick={() => { restoreCaptureLevels("Viewer reset to capture levels (N)"); setLoupeEnabled(false); }}>Reset</button>
        <div className="workbench-toolbar-spacer" />
        <div className="workbench-toolbar-group workbench-view-controls">
          <button type="button" onClick={() => viewerRef.current?.fit()} title="Fit image (F)"><i className="fa-solid fa-expand" /> Fit</button>
          <span className="workbench-zoom">{zoom}%</span>
        </div>
      </div>

      {pendingRecovery && (
        <div className="workbench-recovery" role="alert">
          <div><strong>Unsaved work found</strong><span>Local draft from {new Date(pendingRecovery.updatedAt).toLocaleString()}</span></div>
          <button type="button" onClick={discardRecovery}>Discard</button>
          <button type="button" className="is-primary" onClick={restoreRecovery}>Restore draft</button>
        </div>
      )}

      {presetMenu && (
        <div className="workbench-preset-menu" role="menu" style={{ left: presetMenu.x, top: presetMenu.y }} onPointerDown={(event) => event.stopPropagation()}>
          <button type="button" role="menuitem" onClick={() => openFineTune(presetMenu.slot)}><i className="fa-solid fa-sliders" /> Fine tune preset {presetMenu.slot}</button>
        </div>
      )}

      <main className="workbench-main">
        <nav className="workbench-toolrail" aria-label="Annotation tools">
          <button type="button" className={!activeTool && !transformEnabled && !eraserEnabled ? "is-active" : ""} onClick={enterPanMode}><span>Pan</span><kbd>V</kbd></button>
          <button type="button" className={transformEnabled ? "is-active" : ""} onClick={() => { setActiveTool(null); setTransformEnabled(true); setEraserEnabled(false); setStatus("Select and transform mode"); }}><span>Select</span><kbd>S</kbd></button>
          <div className="workbench-tool-divider" />
          {workspace.annotation_context.enabled_tools.includes("box") && (
            <button type="button" className={activeTool === "box" ? "is-active" : ""} disabled={!activeClass || !toolOptions.includes("box")} onClick={() => { setSelectedAnnotationId(null); setTransformEnabled(false); setEraserEnabled(false); setActiveTool("box"); }} title="Bounding box (B)"><span>Box</span><kbd>B</kbd></button>
          )}
          <div className="workbench-tool-divider" />
          <span className="workbench-tool-group-label">Segmen&shy;tation</span>
          {workspace.annotation_context.enabled_tools.filter((tool) => tool !== "box").map((tool) => (
            <Fragment key={tool}>
              <button
                type="button"
                className={activeTool === tool ? "is-active" : ""}
                disabled={!activeClass || !toolOptions.includes(tool)}
                onClick={() => { setSelectedAnnotationId(null); setTransformEnabled(false); setEraserEnabled(false); setActiveTool(tool); }}
                title={`${TOOL_LABELS[tool]} (${TOOL_SHORTCUTS[tool]})`}
              ><span>{TOOL_LABELS[tool]}</span><kbd>{TOOL_SHORTCUTS[tool]}</kbd></button>
              {tool === "brush_mask" && (
                <button type="button" className={eraserEnabled ? "is-active" : ""} disabled={selectedAnnotation?.geometry.type !== "brush_mask" || selectedAnnotation.locked} onClick={() => { setActiveTool(null); setTransformEnabled(false); setEraserEnabled(true); setStatus("Brush eraser active"); }} title="Erase selected brush mask (X)"><span>Eraser</span><kbd>X</kbd></button>
              )}
            </Fragment>
          ))}
          {activeTool === "brush_mask" && (
            <label className="workbench-brush-size">Size<input type="range" min="4" max="96" value={brushSize} onChange={(event) => setBrushSize(Number(event.target.value))} /><output>{brushSize}</output></label>
          )}
          {eraserEnabled && (
            <label className="workbench-brush-size">Eraser<input type="range" min="8" max="128" value={eraserSize} onChange={(event) => setEraserSize(Number(event.target.value))} /><output>{eraserSize}</output></label>
          )}
        </nav>

        <section className="workbench-stage">
          <PixiViewport
            ref={viewerRef}
            imageUrl={currentImage.url}
            imageLabel={currentImage.filename || `Fundus image ${currentImage.uuid}`}
            activeTool={activeTool}
            transformEnabled={transformEnabled}
            eraserEnabled={eraserEnabled}
            activeClass={activeClass}
            annotations={visibleAnnotations}
            selectedAnnotationId={selectedAnnotationId}
            viewerFilters={filters}
            imageAnalysis={imageAnalysis}
            loupeEnabled={loupeEnabled}
            brushSize={brushSize}
            eraserSize={eraserSize}
            onCreateAnnotation={createAnnotation}
            onSelectAnnotation={selectAnnotationForEdit}
            onDuplicateAnnotation={copyAnnotation}
            onDeleteAnnotation={deleteAnnotation}
            onUpdateAnnotationGeometry={updateAnnotationGeometry}
            onToggleAnnotationLock={toggleAnnotationLock}
            onExitToPan={enterPanMode}
            onZoomChange={onZoomChange}
          />

          <div className="workbench-class-palette" aria-label="Quick annotation class selection">
            <span className="workbench-palette-title">Class</span>
            {classOptions.length ? classOptions.map((item, index) => {
              const occupied = !item.multipleInstances && visibleAnnotations.some((annotation) => annotation.classRef.id === item.id);
              return (
                <button type="button" key={item.id} className={activeClass?.id === item.id ? "is-active" : ""} onClick={() => chooseClass(item)}>
                  <i style={{ background: cssColor(item) }} />
                  <span>{item.label}</span>
                  {index < 9 && <kbd>{index + 1}</kbd>}
                  {occupied && <em>1/1</em>}
                </button>
              );
            }) : <span className="workbench-empty-inline">Select a grade and feature, or configure project classes</span>}
          </div>

          {workspace.images.length > 1 && (
            <div className="workbench-image-strip" aria-label="Encounter images">
              {workspace.images.map((image, index) => (
                <button type="button" key={image.uuid} className={image.uuid === activeImageUuid ? "is-active" : ""} onClick={() => openImageAtCaptureLevels(image.uuid)}>
                  <img src={image.url} alt="" />
                  <span>{image.position ? `Position ${image.position}` : `Image ${index + 1}`}</span>
                </button>
              ))}
            </div>
          )}

          <div className="workbench-stage-status" aria-live="polite"><span className={activeTool ? "is-drawing" : ""} />{status}</div>
        </section>

        <aside className="workbench-inspector">
          {fineTuneSlot && fineTuneDraft ? (
            <FineTunePanel
              slot={fineTuneSlot}
              draft={fineTuneDraft}
              imageAnalysis={imageAnalysis}
              saving={fineTuneSaving}
              onChangeFilter={(mode) => {
                setFineTuneDraft((current) => {
                  if (!current) return current;
                  const updated = {
                    ...current,
                    filter: mode,
                    shadow_lift: mode === "enhance" ? ((current.shadow_lift ?? 0) > 0 ? current.shadow_lift : 0.5) : 0
                  };
                  setFilters(filtersFromPreset(updated));
                  return updated;
                });
              }}
              onUpdate={updateFineTune}
              onToggleInvert={(value) => {
                setFineTuneDraft((current) => {
                  if (!current) return current;
                  const updated = { ...current, invert: value };
                  setFilters(filtersFromPreset(updated));
                  return updated;
                });
              }}
              onReset={resetFineTune}
              onCancel={cancelFineTune}
              onSave={commitFineTune}
            />
          ) : <>
          <div className="workbench-panel-tabs" role="tablist" aria-label="Grading panels">
            {workspace.panels.map((panel) => (
              <button type="button" role="tab" aria-selected={panel.id === activePanel.id} key={panel.id} className={panel.id === activePanel.id ? "is-active" : ""} onClick={() => { setActivePanelId(panel.id); setSelectedAnnotationId(null); }}>
                <span>{panel.disease.name}</span><small>{panel.target_level}</small>{panelDrafts[panel.id]?.gradeId && <i />}
              </button>
            ))}
          </div>
          <div className="workbench-inspector-head">
            <div><span className="workbench-kicker">{activePanel.target_level === "encounter" ? "Grade Encounter" : "Grade Image"}</span><h1>{activePanel.disease.name}</h1></div>
            <span className={`workbench-state-badge ${activePanel.read_only ? "is-readonly" : ""}`}>{activePanel.read_only ? "Read only" : activePanel.state}</span>
          </div>
          {activePanel.read_only_reason && <div className="workbench-panel-note">{activePanel.read_only_reason}</div>}
          <div className="workbench-inspector-tabs" role="tablist">
            <button type="button" role="tab" aria-selected={rightTab === "grading"} className={rightTab === "grading" ? "is-active" : ""} onClick={() => setRightTab("grading")}>Grading</button>
            <button type="button" role="tab" aria-selected={rightTab === "annotations"} className={rightTab === "annotations" ? "is-active" : ""} onClick={() => setRightTab("annotations")}>Annotations <span>{visibleAnnotations.length}</span></button>
          </div>

          <div className="workbench-inspector-body">
            {rightTab === "grading" ? (
              <>
                <section className="workbench-section">
                  <div className="workbench-section-title"><h2>Grades</h2><span>{activeDraft.gradeId ? "Selected" : "Required"}</span></div>
                  <div className="workbench-grade-grid">
                    {activePanel.grades.map((grade) => (
                      <button type="button" key={grade.id} disabled={activePanel.read_only} className={activeDraft.gradeId === grade.id ? "is-selected" : ""} onClick={() => chooseGrade(activePanel, grade.id)}>
                        <span>{grade.impression}</span>{grade.is_ungradable && <small>Ungradable</small>}
                      </button>
                    ))}
                  </div>
                  {selectedGrade?.guidelines && <p className="workbench-guideline">{guidelineText(selectedGrade.guidelines)}</p>}
                </section>

                <section className="workbench-section">
                  <div className="workbench-section-title"><h2>Features</h2><span>{activeDraft.selectedFeatureIds.size} selected</span></div>
                  {selectedGrade ? selectedGrade.features.length ? (
                    <div className="workbench-feature-list">
                      {selectedGrade.features.map((feature) => {
                        const selected = activeDraft.selectedFeatureIds.has(feature.id);
                        return <label key={feature.id} className={selected ? "is-selected" : ""}><input type="checkbox" disabled={activePanel.read_only} checked={selected} onChange={() => toggleFeature(activePanel, feature.id)} /><span>{feature.label}</span>{selected && <small>Available as class</small>}</label>;
                      })}
                    </div>
                  ) : <p className="workbench-empty">No findings are configured for this grade.</p> : <p className="workbench-empty">Select a classification to reveal its findings.</p>}
                </section>

                <section className="workbench-section">
                  <div className="workbench-section-title"><h2>Comment</h2><span>Optional</span></div>
                  <textarea disabled={activePanel.read_only} value={activeDraft.comment} placeholder="Add concise clinical context…" onChange={(event) => setPanelDrafts((drafts) => ({ ...drafts, [activePanel.id]: { ...activeDraft, comment: event.target.value } }))} />
                </section>
              </>
            ) : (
              <section className="workbench-section workbench-annotations-section">
                <div className="workbench-section-title"><h2>Current annotations</h2><div className="workbench-annotation-list-actions"><span>{visibleAnnotations.length} on image</span>{visibleAnnotations.length > 0 && <button type="button" onClick={toggleAllAnnotationVisibility}><i className={`fa-solid ${allAnnotationsHidden ? "fa-eye" : "fa-eye-slash"}`} /> {allAnnotationsHidden ? "Show all" : "Hide all"}</button>}</div></div>
                {visibleAnnotations.length ? <div className="workbench-annotation-list">
                  {visibleAnnotations.map((annotation, index) => (
                    <article key={annotation.id} className={selectedAnnotationId === annotation.id ? "is-selected" : ""} onClick={() => selectAnnotationForEdit(annotation.id)}>
                      <div className="workbench-annotation-row">
                        <button type="button" className="workbench-icon-button" title={annotation.visible ? "Hide annotation" : "Show annotation"} aria-label={annotation.visible ? "Hide annotation" : "Show annotation"} onClick={(event) => { event.stopPropagation(); updateAnnotation(annotation.id, { visible: !annotation.visible }); }}><i className={`fa-solid ${annotation.visible ? "fa-eye" : "fa-eye-slash"}`} /></button>
                        <span className="workbench-annotation-number">{index + 1}</span>
                        <i className="workbench-annotation-swatch" style={{ background: cssColor(annotation.classRef) }} />
                        <select aria-label={`Class for annotation ${index + 1}`} value={annotation.classRef.id} disabled={annotation.locked} onClick={(event) => event.stopPropagation()} onChange={(event) => {
                        const replacement = classOptions.find((item) => item.id === event.target.value);
                        if (!replacement) return;
                        if (!canCreateAnnotation(replacement, annotations.filter((item) => item.id !== annotation.id))) { setStatus(`${replacement.label} already has its single allowed instance`); return; }
                        updateAnnotation(annotation.id, { classRef: replacement });
                        }}>{classOptions.filter((item) => toolsForClass(workspace.annotation_context, item).includes(annotation.tool)).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
                        <button type="button" className="workbench-icon-button is-danger" title="Delete annotation" aria-label="Delete annotation" onClick={(event) => { event.stopPropagation(); deleteAnnotation(annotation.id); }}><i className="fa-solid fa-trash-can" /></button>
                      </div>
                      {selectedAnnotationId === annotation.id && (
                        <div className="workbench-annotation-detail">
                          <span>{geometrySummary(annotation.geometry)}</span>
                          <button type="button" title={annotation.locked ? "Unlock annotation" : "Lock annotation"} onClick={(event) => { event.stopPropagation(); toggleAnnotationLock(annotation.id); }}><i className={`fa-solid ${annotation.locked ? "fa-lock" : "fa-lock-open"}`} /> {annotation.locked ? "Unlock" : "Lock"}</button>
                          <button type="button" disabled={!annotation.classRef.multipleInstances} onClick={(event) => { event.stopPropagation(); copyAnnotation(annotation.id); }}><i className="fa-solid fa-copy" /> Duplicate</button>
                        </div>
                      )}
                    </article>
                  ))}
                </div> : <div className="workbench-empty-state"><strong>No annotations on this image</strong><p>Choose a class, select a tool, then draw directly on the image.</p></div>}
              </section>
            )}
          </div>

          <footer className="workbench-submit-bar">
            <div><span>{status}</span><small>{workspace.capabilities.submit ? "Ready to submit" : "Saved locally until server persistence is enabled"}</small></div>
            <button type="button" onClick={() => { const draft = storedDraft(); if (draft) saveDraft(draftKey, draft).then(() => setStatus("Draft saved locally")); }}>Save draft</button>
            <button type="button" className="is-primary" disabled={!workspace.capabilities.submit || !activeDraft.gradeId}>Submit</button>
          </footer>
          </>}
        </aside>
      </main>
      <div className="workbench-phone-guard"><strong>Editing needs a larger screen</strong><p>Open this workbench on a desktop or tablet to grade and annotate safely.</p><a href="/grading/">Return to grading</a></div>
    </div>
  );
}

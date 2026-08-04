import { describe, expect, it } from "vitest";

import type { GradingPanel, GradingWorkspace } from "./workspace";
import {
  CLINICAL_FILTER_MODES,
  DEFAULT_FILTERS,
  annotationContainsPoint,
  availableAnnotationClasses,
  canCreateAnnotation,
  duplicateAnnotation,
  filtersForClinicalMode,
  moveGeometry,
  scaleGeometry,
  rotateGeometry,
  eraseBrushMask,
  toolsForClass,
  type WorkbenchAnnotation
} from "./workbenchState";

const panel = {
  id: "task:primary",
  task_uuid: "primary",
  disease: { id: 4, name: "DR" },
  grading_scope: "image",
  target_level: "image",
  state: "pending",
  read_only: false,
  read_only_reason: null,
  grades: [{
    id: 41,
    impression: "Moderate",
    display_order: 2,
    is_active: true,
    is_ungradable: false,
    guidelines: null,
    features: [
      { id: 401, sr_no: 2, label: "Hard exudates" },
      { id: 400, sr_no: 1, label: "Microaneurysms" }
    ]
  }],
  existing_grade: null
} satisfies GradingPanel;

const workspace = {
  annotation_context: {
    policy_source: "project",
    project_id: 7,
    enabled: true,
    revision: 3,
    enabled_tools: ["box", "rect", "polygon", "ellipse"],
    default_feature_policy: {
      localization: "box_or_segmentation",
      preferred_tool: "box",
      allowed_tools: ["box", "rect", "polygon", "ellipse"]
    },
    project_classes: [
      { id: 72, key: "lesion", localization: "box_or_segmentation", display_order: 20, multiple_instances: true, active: true },
      { id: 71, key: "iris", localization: "segmentation", display_order: 10, multiple_instances: false, active: true }
    ]
  }
} as GradingWorkspace;

describe("clinical image filter controls", () => {
  it("offers only the agreed routine viewing modes", () => {
    expect(CLINICAL_FILTER_MODES).toEqual([
      { key: "none", short: "N", label: "Normal · capture levels" },
      { key: "enhance", short: "E", label: "Protected shadow lift" },
      { key: "redfree", short: "RF", label: "Red-free simulation" },
      { key: "redfreeenhanced", short: "RF+", label: "Enhanced red-free" }
    ]);
  });

  it("restores tuning independently for each clinical mode", () => {
    const tunedRf = { ...filtersForClinicalMode("redfree"), greenLuminance: 0.35, contrast: 0.2 };
    expect(filtersForClinicalMode("enhance")).toMatchObject({ mode: "enhance", shadowLift: 0.5 });
    expect(filtersForClinicalMode("redfree", tunedRf)).toEqual(tunedRf);
    expect(filtersForClinicalMode("none")).toEqual(DEFAULT_FILTERS);
  });
});

describe("workbench annotation class resolution", () => {
  it("keeps project classes ordered and activates only selected grading features", () => {
    const classes = availableAnnotationClasses(workspace, panel, 41, new Set([401]));

    expect(classes.map((item) => item.label)).toEqual(["Iris", "Lesion", "Hard exudates"]);
    expect(classes[2]).toMatchObject({ source: "grading_feature", featureId: 401, panelId: panel.id });
  });

  it("resolves tools from class localization and project-enabled tools", () => {
    const [iris, lesion] = availableAnnotationClasses(workspace, panel, 41, new Set());

    expect(toolsForClass(workspace.annotation_context, iris)).toEqual(["rect", "polygon", "ellipse"]);
    expect(toolsForClass(workspace.annotation_context, lesion)).toEqual(["box", "rect", "polygon", "ellipse"]);
  });

  it("prevents a second active instance of a single-instance project class", () => {
    const [iris] = availableAnnotationClasses(workspace, panel, 41, new Set());
    const annotation = {
      id: "annotation-1",
      imageUuid: "image-1",
      panelId: panel.id,
      classRef: iris,
      tool: "polygon",
      geometry: { type: "polygon", points: [[1, 1], [10, 1], [5, 10]] },
      visible: true,
      locked: false
    } satisfies WorkbenchAnnotation;

    expect(canCreateAnnotation(iris, [annotation])).toBe(false);
  });

  it("hit-tests rectangular and polygon annotations in image coordinates", () => {
    const [annotationClass] = availableAnnotationClasses(workspace, panel, 41, new Set());
    const box = {
      id: "box-1", imageUuid: "image-1", panelId: panel.id, classRef: annotationClass,
      tool: "box", geometry: { type: "box", x: 20, y: 30, width: 80, height: 50 }, visible: true, locked: false
    } satisfies WorkbenchAnnotation;
    const polygon = {
      ...box, id: "polygon-1", tool: "polygon", geometry: { type: "polygon", points: [[150, 20], [220, 30], [180, 90]] }
    } satisfies WorkbenchAnnotation;

    expect(annotationContainsPoint(box, [50, 45])).toBe(true);
    expect(annotationContainsPoint(box, [110, 45])).toBe(false);
    expect(annotationContainsPoint(polygon, [180, 45])).toBe(true);
    expect(annotationContainsPoint(polygon, [230, 45])).toBe(false);
  });

  it("duplicates an annotation with a new id and offset geometry", () => {
    const [annotationClass] = availableAnnotationClasses(workspace, panel, 41, new Set());
    const annotation = {
      id: "annotation-1", imageUuid: "image-1", panelId: panel.id, classRef: annotationClass,
      tool: "polygon", geometry: { type: "polygon", points: [[1, 1], [10, 1], [5, 10]] }, visible: false, locked: true
    } satisfies WorkbenchAnnotation;

    expect(duplicateAnnotation(annotation, "annotation-2", 12)).toMatchObject({
      id: "annotation-2",
      geometry: { type: "polygon", points: [[13, 13], [22, 13], [17, 22]] },
      visible: true,
      locked: false
    });
  });

  it("moves segmentation geometry without changing its shape", () => {
    expect(moveGeometry({ type: "polygon", points: [[1, 2], [8, 2], [4, 9]] }, 10, -2)).toEqual({
      type: "polygon",
      points: [[11, 0], [18, 0], [14, 7]]
    });
  });

  it("resizes bounding boxes from a fixed anchor", () => {
    expect(scaleGeometry({ type: "box", x: 10, y: 20, width: 40, height: 30 }, [10, 20], 1.5, 2)).toEqual({
      type: "box", x: 10, y: 20, width: 60, height: 60
    });
  });

  it("rotates polygon segmentation around its center", () => {
    const rotated = rotateGeometry({ type: "polygon", points: [[0, 0], [10, 0], [10, 10]] }, [5, 5], Math.PI / 2);
    expect(rotated).toEqual({ type: "polygon", points: [[10, 0], [10, 10], [0, 10]] });
  });

  it("erases brush-mask points and preserves remaining stroke segments", () => {
    expect(eraseBrushMask(
      { type: "brush_mask", strokes: [[[0, 0], [5, 0], [10, 0], [15, 0], [20, 0]]], size: 6 },
      [[10, 0]],
      2
    )).toEqual({ type: "brush_mask", strokes: [[[0, 0], [5, 0]], [[15, 0], [20, 0]]], size: 6 });
  });
});

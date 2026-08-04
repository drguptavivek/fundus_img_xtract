import { describe, expect, it } from "vitest";

import { parseWorkspace } from "./workspace";


describe("parseWorkspace", () => {
  it("accepts the versioned task workspace returned by Flask", () => {
    const workspace = parseWorkspace({
      schema_version: 2,
      context_revision: "a".repeat(64),
      target: { type: "task", ref: "task-uuid", slot: "resident" },
      task: {
        uuid: "task-uuid",
        state: "pending",
        disease: { id: 3, name: "Glaucoma" },
        lab_unit: { id: 8, name: "Glaucoma Lab" }
      },
      image: {
        uuid: "image-uuid",
        source: "encounter_file",
        url: "/media/img/image-uuid",
        filename: "fundus.jpg",
        position: null
      },
      images: [{
        uuid: "image-uuid",
        source: "encounter_file",
        url: "/media/img/image-uuid",
        filename: "fundus.jpg",
        position: null
      }],
      active_image_uuid: "image-uuid",
      panels: [{
        id: "task:task-uuid",
        task_uuid: "task-uuid",
        disease: { id: 3, name: "Glaucoma" },
        grading_scope: "image",
        target_level: "image",
        state: "pending",
        read_only: false,
        read_only_reason: null,
        grades: [{
          id: 31,
          impression: "Referable",
          display_order: 1,
          is_active: true,
          is_ungradable: false,
          guidelines: "Refer when suspicious.",
          features: [{ id: 301, sr_no: 1, label: "Disc haemorrhage" }]
        }],
        existing_grade: null
      }],
      annotation_context: {
        policy_source: "non_project_default",
        project_id: null,
        enabled: true,
        revision: 1,
        enabled_tools: ["box", "rect", "polygon", "brush_mask", "ellipse", "pyramid"],
        default_feature_policy: {
          localization: "box_or_segmentation",
          preferred_tool: "box",
          allowed_tools: ["box", "rect", "polygon", "brush_mask", "ellipse", "pyramid"]
        },
        project_classes: []
      },
      capabilities: { view: true, annotate: false, submit: false },
      read_only_reasons: ["Foundation viewer is read-only."]
    });

    expect(workspace.target.slot).toBe("resident");
    expect(workspace.image.url).toBe("/media/img/image-uuid");
    expect(workspace.panels[0].grades[0].features[0].label).toBe("Disc haemorrhage");
    expect(workspace.capabilities.submit).toBe(false);
  });

  it("rejects an unknown workspace schema before rendering clinical data", () => {
    expect(() => parseWorkspace({ schema_version: 1 })).toThrow(
      "Unsupported grading workspace schema version."
    );
  });
});

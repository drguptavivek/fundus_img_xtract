import { describe, expect, it } from "vitest";

import { parseWorkspace } from "./workspace";


describe("parseWorkspace", () => {
  it("accepts the versioned task workspace returned by Flask", () => {
    const workspace = parseWorkspace({
      schema_version: 1,
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
        filename: "fundus.jpg"
      },
      capabilities: { view: true, annotate: false, submit: false },
      read_only_reasons: ["Foundation viewer is read-only."]
    });

    expect(workspace.target.slot).toBe("resident");
    expect(workspace.image.url).toBe("/media/img/image-uuid");
    expect(workspace.capabilities.submit).toBe(false);
  });

  it("rejects an unknown workspace schema before rendering clinical data", () => {
    expect(() => parseWorkspace({ schema_version: 2 })).toThrow(
      "Unsupported grading workspace schema version."
    );
  });
});

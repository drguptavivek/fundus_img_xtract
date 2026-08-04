import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS } from "./workbenchState";
import { filtersFromPreset, normalizePresetTuning, presetFromViewer } from "./viewerPresets";

describe("grading workbench viewer presets", () => {
  it("round-trips workbench filters through the legacy preset contract", () => {
    const filters = {
      ...DEFAULT_FILTERS,
      mode: "redfree" as const,
      brightness: 0.2,
      contrast: -0.15,
      saturation: 0.3,
      redLuminance: 0.1,
      redSaturation: -0.2,
      greenLuminance: 0.25,
      greenSaturation: 0.15,
      blueLuminance: -0.1,
      blueSaturation: 0.05,
      shadowLift: 0.45,
    };
    const preset = presetFromViewer(filters, 3);

    expect(preset).toMatchObject({
      name: "Preset 3",
      brightness: 1.2,
      contrast: 0.85,
      saturation: 1.3,
      red_luminance: 1.1,
      red_saturation: 0.8,
      green_luminance: 1.25,
      green_saturation: 1.15,
      blue_luminance: 0.9,
      blue_saturation: 1.05,
      shadow_lift: 0.45,
      filter: "redfree"
    });
    expect(preset).not.toHaveProperty("zoom");
    expect(preset).not.toHaveProperty("pan_x");
    expect(preset).not.toHaveProperty("pan_y");
    expect(preset).not.toHaveProperty("loupe_zoom");
    expect(preset).not.toHaveProperty("highlight_protection");
    expect(preset).not.toHaveProperty("local_contrast");
    expect(preset).not.toHaveProperty("denoise");
    expect(preset).not.toHaveProperty("sharpen");
    expect(filtersFromPreset(preset)).toEqual(filters);
  });

  it("round-trips the dedicated protected-shadow filter", () => {
    const preset = presetFromViewer({
      ...DEFAULT_FILTERS,
      mode: "enhance",
      shadowLift: 0.5
    }, 2);

    expect(preset).toMatchObject({ filter: "enhance", shadow_lift: 0.5 });
    expect(filtersFromPreset(preset)).toMatchObject({ mode: "enhance", shadowLift: 0.5 });
  });

  it("falls back safely for malformed legacy preset values", () => {
    expect(filtersFromPreset({ brightness: 99, contrast: -4, filter: "unknown" })).toMatchObject({
      mode: "none", brightness: 4, contrast: -0.5
    });
  });

  it("normalizes legacy out-of-range values before fine tuning", () => {
    expect(normalizePresetTuning({ brightness: 4, contrast: 0.1 })).toMatchObject({
      brightness: 4,
      contrast: 0.5,
      saturation: 1,
      red_luminance: 1,
      green_luminance: 1,
      blue_luminance: 1
    });
  });
});

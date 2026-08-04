import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS } from "./workbenchState";
import { IDENTITY_COLOR_MATRIX, channelTuningMatrix, multiplyColorMatrices } from "./viewerFilterMath";

describe("viewer filter matrix math", () => {
  it("keeps neutral channel tuning as the identity matrix", () => {
    expect(channelTuningMatrix(DEFAULT_FILTERS)).toEqual(IDENTITY_COLOR_MATRIX);
  });

  it("changes only the red output gain for red luminance tuning", () => {
    expect(channelTuningMatrix({ ...DEFAULT_FILTERS, redLuminance: 0.2 })).toEqual([
      1.2, 0, 0, 0, 0,
      0, 1, 0, 0, 0,
      0, 0, 1, 0, 0,
      0, 0, 0, 1, 0
    ]);
  });

  it("desaturates the red output toward perceptual luminance", () => {
    const matrix = channelTuningMatrix({ ...DEFAULT_FILTERS, redSaturation: -1 });
    expect(matrix.slice(0, 3)).toEqual([0.2126, 0.7152, 0.0722]);
    expect(matrix.slice(5, 8)).toEqual([0, 1, 0]);
    expect(matrix.slice(10, 13)).toEqual([0, 0, 1]);
  });

  it("composes matrices in display order", () => {
    const redGain = channelTuningMatrix({ ...DEFAULT_FILTERS, redLuminance: 0.5 });
    expect(multiplyColorMatrices(redGain, IDENTITY_COLOR_MATRIX)).toEqual(redGain);
  });
});

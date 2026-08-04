import { describe, expect, it } from "vitest";

import { analyzeImagePixels, clinicalDisplayRecipe } from "./imageAnalysis";

describe("browser-side fundus image analysis", () => {
  it("ignores transparent and black surround pixels when measuring channels", () => {
    const pixels = new Uint8ClampedArray([
      0, 0, 0, 255,
      255, 255, 255, 0,
      80, 20, 10, 255,
      160, 40, 20, 255,
      240, 60, 30, 255
    ]);
    const analysis = analyzeImagePixels(pixels, 5, 1);

    expect(analysis.sampleCount).toBe(3);
    expect(analysis.red.median).toBe(160);
    expect(analysis.green.median).toBe(40);
    expect(analysis.blue.median).toBe(20);
  });

  it("creates a readable red-free recipe for a dark green channel", () => {
    const pixels = new Uint8ClampedArray([
      50, 12, 8, 255,
      90, 20, 10, 255,
      130, 30, 14, 255,
      180, 45, 18, 255,
      240, 170, 90, 255
    ]);
    const recipe = clinicalDisplayRecipe("redfree", analyzeImagePixels(pixels, 5, 1));

    expect(recipe.blackPoint).toBeLessThan(0.1);
    expect(recipe.whitePoint).toBeGreaterThan(0.5);
    expect(recipe.gamma).toBeLessThan(1);
    expect(recipe.highlightProtection).toBeGreaterThan(0);
  });

  it("keeps the normal capture view as an exact identity recipe", () => {
    const analysis = analyzeImagePixels(new Uint8ClampedArray([90, 80, 70, 255]), 1, 1);
    expect(clinicalDisplayRecipe("none", analysis)).toEqual({
      blackPoint: 0,
      whitePoint: 1,
      gamma: 1,
      highlightProtection: 0,
      localContrast: 0
    });
  });

  it("leaves tonal shaping to the protected-shadow shader in E mode", () => {
    const analysis = analyzeImagePixels(new Uint8ClampedArray([90, 80, 70, 255]), 1, 1);
    expect(clinicalDisplayRecipe("enhance", analysis)).toEqual(clinicalDisplayRecipe("none", analysis));
  });
});

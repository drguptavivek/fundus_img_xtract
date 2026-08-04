import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";


describe("grading workbench entrypoint", () => {
  it("loads Pixi's strict-CSP fallback before the application", () => {
    const source = readFileSync(
      resolve(process.cwd(), "frontend/grading-workbench/main.tsx"),
      "utf8"
    );
    const cspFallbackImport = source.indexOf('import "pixi.js/unsafe-eval";');
    const applicationImport = source.indexOf('import { App } from "./App";');

    expect(cspFallbackImport).toBeGreaterThanOrEqual(0);
    expect(applicationImport).toBeGreaterThan(cspFallbackImport);
  });
});

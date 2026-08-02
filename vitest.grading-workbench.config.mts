import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["frontend/grading-workbench/**/*.test.ts"]
  }
});

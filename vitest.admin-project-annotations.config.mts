import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["frontend/admin-project-annotations/**/*.test.ts"]
  }
});

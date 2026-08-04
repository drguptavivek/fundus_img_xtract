import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/static/grading-workbench/",
  plugins: [react()],
  build: {
    outDir: "static/grading-workbench",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: resolve(import.meta.dirname, "frontend/grading-workbench/main.tsx"),
      output: {
        entryFileNames: "assets/workbench-[hash].js",
        chunkFileNames: "assets/chunk-[hash].js",
        assetFileNames: "assets/workbench-[hash][extname]"
      }
    }
  }
});

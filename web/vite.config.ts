import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
    // Playwright specs live in e2e/ and are run by its own runner.
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

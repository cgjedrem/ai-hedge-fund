import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const frontendRoot = dirname(fileURLToPath(import.meta.url));
const buildOutputDirectory =
  process.env.HEDGE_FUND_TEST_MODE === "1" && process.env.AIHF_WEB_STATIC_DIR
  ? resolve(process.env.AIHF_WEB_STATIC_DIR)
  : resolve(frontendRoot, "../hedge_fund/web/static");
let apiTarget: URL;
const envDirectory = process.env.AIHF_VITE_ENV_DIR
  ? resolve(process.env.AIHF_VITE_ENV_DIR)
  : undefined;

if (process.env.HEDGE_FUND_TEST_MODE === "1") {
  const testRoot = resolve(process.env.HEDGE_FUND_TEST_ROOT ?? "");
  if (
    !process.env.AIHF_WEB_STATIC_DIR ||
    dirname(buildOutputDirectory) !== testRoot ||
    basename(buildOutputDirectory) !== "web-static"
  ) {
    throw new Error("Isolated browser builds must use owned fixture assets.");
  }
}

if (
  envDirectory &&
  (!process.env.HEDGE_FUND_TEST_MODE ||
    resolve(dirname(envDirectory)) !== resolve(process.env.HEDGE_FUND_TEST_ROOT ?? "") ||
    envDirectory.split(/[\\/]/).pop() !== "vite-env")
) {
  throw new Error("AIHF_VITE_ENV_DIR must be the owned test fixture directory.");
}

try {
  apiTarget = new URL(process.env.AIHF_WEB_API_TARGET ?? "http://127.0.0.1:8876");
} catch {
  throw new Error("AIHF_WEB_API_TARGET must be a loopback HTTP origin.");
}

if (
  process.env.HEDGE_FUND_TEST_MODE === "1" &&
  apiTarget.origin !== "http://127.0.0.1:8876"
) {
  throw new Error("Isolated browser builds must target the owned test port.");
}

if (
  apiTarget.protocol !== "http:" ||
  !["127.0.0.1", "localhost"].includes(apiTarget.hostname) ||
  apiTarget.username ||
  apiTarget.password ||
  apiTarget.pathname !== "/" ||
  apiTarget.search ||
  apiTarget.hash
) {
  throw new Error("AIHF_WEB_API_TARGET must be a loopback HTTP origin.");
}

export default defineConfig({
  envDir: envDirectory,
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(frontendRoot, "src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiTarget.origin,
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: buildOutputDirectory,
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});

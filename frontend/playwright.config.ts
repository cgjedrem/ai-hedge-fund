import { defineConfig, devices } from "@playwright/test";

const port = process.env.AIHF_WEB_PORT ?? "8765";
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  reporter: "list",
  outputDir: "./test-results",
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `python -m poetry -C .. run aihf-web --demo --port ${port}`,
    url: `${baseURL}/api/capabilities`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});

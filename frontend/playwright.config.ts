import { defineConfig, devices } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { basename, dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(frontendRoot, "..");
const port = process.env.AIHF_WEB_PORT;
if (port !== "8876") {
  throw new Error("Run browser acceptance through the owned 8876 harness.");
}
const baseURL = `http://127.0.0.1:${port}`;
const testRoot = requiredPath("AIHF_WEB_TEST_ROOT");
const demoRoot = requiredPath("AIHF_WEB_DEMO_ROOT");
const outputDir = requiredPath("AIHF_PLAYWRIGHT_OUTPUT_DIR");
const screenshotDir = requiredPath("AIHF_PLAYWRIGHT_SCREENSHOT_DIR");
const python = requiredPath("AIHF_E2E_PYTHON");
const serverCommand = process.env.AIHF_WEB_SERVER_COMMAND;
const browserChannel = process.platform === "win32" ? "msedge" : undefined;
const browserArgs = [
  "--disable-background-networking",
  "--disable-component-update",
  "--disable-sync",
  "--no-default-browser-check",
  "--no-first-run",
];
const expectedOutputDir = resolve(testRoot, "playwright-results");
const expectedScreenshotDir = resolve(
  repositoryRoot,
  "specs",
  "005-web-engine-migration",
  "screenshots",
);
const expectedDemoRelative = relative(testRoot, demoRoot);
const marker = resolve(testRoot, ".test-owned");
const expectedServerCommand = [
  shellQuote(python),
  "-m hedge_fund.web --demo",
  `--port ${port}`,
  `--root ${shellQuote(demoRoot)}`,
].join(" ");

if (dirname(testRoot) !== resolve(repositoryRoot, "outputs")) {
  throw new Error("Browser fixture root is outside checkout outputs.");
}
if (!basename(testRoot).startsWith("spec005-test-e2e-")) {
  throw new Error("Browser fixture root is not test-owned.");
}
if (!existsSync(marker) || readFileSync(marker, "utf8") !== "test-owned\n") {
  throw new Error("Browser fixture ownership marker is missing.");
}
if (
  !expectedDemoRelative ||
  expectedDemoRelative === ".." ||
  expectedDemoRelative.startsWith(`..${sep}`) ||
  isAbsolute(expectedDemoRelative)
) {
  throw new Error("Demo data root is outside its owned fixture.");
}
if (outputDir !== expectedOutputDir) {
  throw new Error("Playwright output must remain inside its owned fixture.");
}
if (screenshotDir !== expectedScreenshotDir) {
  throw new Error("Screenshot output must use the migration evidence directory.");
}
if (!serverCommand || serverCommand !== expectedServerCommand) {
  throw new Error("Browser server command does not match the owned fixture.");
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  reporter: "list",
  outputDir,
  use: {
    baseURL,
    launchOptions: { args: browserArgs },
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(browserChannel ? { channel: browserChannel } : {}),
      },
    },
  ],
  webServer: {
    command: serverCommand,
    url: `${baseURL}/api/capabilities`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});

function requiredPath(name: string): string {
  const value = process.env[name];
  if (!value || !isAbsolute(value)) {
    throw new Error(`${name} must be an absolute path from the owned harness.`);
  }
  return resolve(value);
}

function shellQuote(value: string): string {
  if (process.platform === "win32") {
    if (/["%&|<>^!]/.test(value)) {
      throw new Error("Owned browser path contains an unsupported shell character.");
    }
    return `"${value}"`;
  }
  return `'${value.replaceAll("'", "'\\''")}'`;
}

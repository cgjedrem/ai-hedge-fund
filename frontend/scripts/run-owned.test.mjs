import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  isolatedEnvironment,
  fingerprintDirectory,
  preflightEnvironment,
  runOwnedProcess,
} from "../e2e/run-owned.mjs";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = resolve(frontendRoot, "..", "outputs");

test("abort terminates the exact owned child", async () => {
  const controller = new AbortController();
  const env = {};
  for (const name of ["PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"]) {
    if (process.env[name]) env[name] = process.env[name];
  }
  const childPromise = runOwnedProcess(
    process.execPath,
    ["-e", "setInterval(() => {}, 1000)"],
    { cwd: process.cwd(), env, stdio: "ignore" },
    controller.signal,
  );
  await delay(100);
  controller.abort();
  const result = await childPromise;

  assert.ok(result.pid);
  assert.notEqual(result.pid, process.pid);
  assert.equal(result.signal, "SIGTERM");
});

test("browser config fixes port and output ownership without server reuse", () => {
  const config = readFileSync(
    resolve(frontendRoot, "playwright.config.ts"),
    "utf8",
  );
  const runner = readFileSync(resolve(frontendRoot, "e2e", "run-owned.mjs"), "utf8");

  assert.match(config, /port !== "8876"/);
  assert.match(config, /reuseExistingServer:\s*false/);
  assert.match(config, /process\.platform === "win32"/);
  assert.match(config, /channel:\s*browserChannel/);
  assert.match(config, /--disable-background-networking/);
  assert.match(config, /--disable-component-update/);
  assert.match(config, /--disable-sync/);
  assert.match(config, /AIHF_PLAYWRIGHT_OUTPUT_DIR/);
  assert.match(runner, /randomUUID\(\)\.slice\(0,\s*8\)/);
  assert.ok(runner.includes('.write_bytes(b"test-owned\\\\n")'));
  assert.doesNotMatch(config, /8765|AIHF_WEB_REUSE_EXISTING_SERVER/);
});

test("dev proxy and browser screenshots avoid the protected preview and old spec", () => {
  const vite = readFileSync(resolve(frontendRoot, "vite.config.ts"), "utf8");
  const browser = readFileSync(resolve(frontendRoot, "e2e", "desk.spec.ts"), "utf8");
  const runner = readFileSync(resolve(frontendRoot, "e2e", "run-owned.mjs"), "utf8");
  const vitestGuard = readFileSync(
    resolve(frontendRoot, "src", "test", "setup.ts"),
    "utf8",
  );

  assert.match(vite, /127\.0\.0\.1:8876/);
  assert.doesNotMatch(vite, /8765/);
  assert.match(browser, /005-web-engine-migration\/screenshots/);
  assert.doesNotMatch(browser, /004-react-web-ui\/screenshots|8765/);
  assert.match(vitestGuard, /globalThis\.fetch = async/);
  assert.match(vitestGuard, /XMLHttpRequest\.prototype, "open"/);
  assert.match(runner, /AIHF_WEB_STATIC_DIR/);
  assert.match(vite, /AIHF_WEB_STATIC_DIR/);
  assert.match(vite, /process\.env\.AIHF_VITE_ENV_DIR/);
  assert.doesNotMatch(runner, /"--envDir"/);
  assert.match(vite, /outDir:\s*buildOutputDirectory/);
});

test("preflight strips inherited interpreter and Node module overrides", () => {
  const env = preflightEnvironment({
    PATH: "system-path",
    PYTHONHOME: "C:\\decoy",
    PYTHONPATH: "C:\\decoy",
    PYTHONSTARTUP: "C:\\decoy\\startup.py",
    NODE_OPTIONS: "--require C:\\decoy\\module.js",
    NODE_PATH: "C:\\decoy\\node_modules",
    NPM_CONFIG_REGISTRY: "https://example.invalid/",
    npm_config_userconfig: "C:\\decoy\\npmrc",
    PLAYWRIGHT_BROWSERS_PATH: "C:\\decoy\\browser-cache",
    AIHF_WEB_PORT: "8765",
  });

  assert.equal(env.PATH, "system-path");
  for (const name of [
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "NODE_OPTIONS",
    "NODE_PATH",
    "NPM_CONFIG_REGISTRY",
    "npm_config_userconfig",
    "PLAYWRIGHT_BROWSERS_PATH",
    "AIHF_WEB_PORT",
  ]) {
    assert.equal(env[name], undefined, `${name} must not reach Poetry preflight`);
  }
});

test("owned child strips interpreter and Node module overrides", () => {
  const env = isolatedEnvironment(
    {
      PATH: "system-path",
      PYTHONHOME: "C:\\decoy",
      PYTHONSTARTUP: "C:\\decoy\\startup.py",
      NODE_PATH: "C:\\decoy\\node_modules",
      NPM_CONFIG_REGISTRY: "https://example.invalid/",
      PLAYWRIGHT_BROWSERS_PATH: "C:\\decoy\\browser-cache",
      AIHF_WEB_PORT: "8765",
      HEDGE_FUND_TEST_ROOT: "C:\\decoy",
    },
    "C:\\Python\\python.exe",
  );

  assert.equal(env.PATH, "system-path");
  assert.equal(env.AIHF_WEB_PORT, "8876");
  assert.equal(env.PYTHONHOME, undefined);
  assert.equal(env.PYTHONSTARTUP, undefined);
  assert.equal(env.NODE_PATH, undefined);
  assert.equal(env.NPM_CONFIG_REGISTRY, undefined);
  assert.notEqual(env.PLAYWRIGHT_BROWSERS_PATH, "C:\\decoy\\browser-cache");
  assert.notEqual(env.HEDGE_FUND_TEST_ROOT, "C:\\decoy");
  const testRoot = resolve(env.HEDGE_FUND_TEST_ROOT);
  assert.equal(dirname(testRoot), resolve(frontendRoot, "..", "outputs"));
  assert.match(basename(testRoot), /^spec005-test-e2e-/);
  assert.ok(basename(testRoot).length <= 32);
  assert.equal(dirname(resolve(env.PLAYWRIGHT_BROWSERS_PATH)), testRoot);
  assert.equal(basename(env.PLAYWRIGHT_BROWSERS_PATH), "playwright-browsers");
});

test("artifact fingerprint binds sorted relative paths and bytes", () => {
  mkdirSync(outputRoot, { recursive: true });
  const root = mkdtempSync(join(outputRoot, "spec005-test-artifact-"));
  const html = "<main>desk</main>";
  const script = "export {};";
  try {
    mkdirSync(join(root, "assets"));
    writeFileSync(join(root, "index.html"), html);
    writeFileSync(join(root, "assets", "app.js"), script);

    const expected = createHash("sha256")
      .update("assets/app.js\0")
      .update(script)
      .update("\0")
      .update("index.html\0")
      .update(html)
      .update("\0")
      .digest("hex");
    const first = fingerprintDirectory(root);

    assert.deepEqual(first, {
      sha256: expected,
      files: 2,
      bytes: Buffer.byteLength(html) + Buffer.byteLength(script),
    });
    writeFileSync(join(root, "index.html"), "<main>changed</main>");
    assert.notEqual(fingerprintDirectory(root).sha256, first.sha256);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

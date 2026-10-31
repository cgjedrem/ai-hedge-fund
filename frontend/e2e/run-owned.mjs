import { createHash, randomUUID } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { createServer } from "node:net";
import {
  delimiter,
  dirname,
  isAbsolute,
  join,
  relative,
  resolve,
  sep,
} from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(frontendRoot, "..");
const outputRoot = resolve(repositoryRoot, "outputs");
const port = 8876;
const rootName = `spec005-test-e2e-${process.pid}-${randomUUID().slice(0, 8)}`;
const testRoot = resolve(outputRoot, rootName);
const marker = join(testRoot, ".test-owned");
const demoRoot = join(testRoot, "demo-data");
const screenshotDir = resolve(
  repositoryRoot,
  "specs",
  "005-web-engine-migration",
  "screenshots",
);

const credentialVariables = [
  "ANTHROPIC_API_KEY",
  "OPENAI_API_KEY",
  "XAI_API_KEY",
  "DEEPSEEK_API_KEY",
  "GOOGLE_API_KEY",
  "KIMI_API_KEY",
  "TYPESAFE_API_KEY",
  "MOONSHOT_API_KEY",
  "FINANCIAL_DATASETS_API_KEY",
  "SAXO_API_KEY",
  "SAXO_CLIENT_ID",
  "SAXO_CLIENT_SECRET",
  "SAXO_APP_KEY_REF",
  "SAXO_APP_SECRET_REF",
  "SAXO_REFRESH_TOKEN_REF",
  "HEDGE_FUND_LLM_MODEL",
  "HEDGE_FUND_DATA_PROVIDER",
  "HEDGE_FUND_ROOT",
  "HEDGE_FUND_HOME",
  "AIHF_ROOT",
  "OLLAMA_BASE_URL",
  "OLLAMA_NUM_CTX",
  "OLLAMA_TIMEOUT",
  "MOONSHOT_BASE_URL",
  "OPENAI_API_BASE",
  "SAXO_REFRESH_LOCK_DIR",
  "OPENROUTER_API_KEY",
  "MISTRAL_API_KEY",
  "COHERE_API_KEY",
  "GROQ_API_KEY",
  "HF_TOKEN",
  "HUGGINGFACEHUB_API_TOKEN",
  "AZURE_OPENAI_API_KEY",
  "AWS_ACCESS_KEY_ID",
  "AWS_SECRET_ACCESS_KEY",
  "AWS_SESSION_TOKEN",
  "AWS_SECURITY_TOKEN",
  "AWS_PROFILE",
  "AWS_SHARED_CREDENTIALS_FILE",
  "AWS_CONFIG_FILE",
  "GOOGLE_APPLICATION_CREDENTIALS",
  "AZURE_OPENAI_AD_TOKEN",
  "AZURE_CLIENT_SECRET",
  "AZURE_FEDERATED_TOKEN_FILE",
  "NPM_TOKEN",
  "NODE_AUTH_TOKEN",
  "GITHUB_TOKEN",
  "GH_TOKEN",
  "NODE_EXTRA_CA_CERTS",
  "NODE_TLS_REJECT_UNAUTHORIZED",
];
const proxyVariables = [
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "ALL_PROXY",
  "NO_PROXY",
  "http_proxy",
  "https_proxy",
  "all_proxy",
  "no_proxy",
];
const unsafeOverrides = [
  "AIHF_WEB_PORT",
  "AIHF_WEB_TEST_ROOT",
  "AIHF_WEB_DEMO_ROOT",
  "AIHF_WEB_STATIC_DIR",
  "AIHF_PLAYWRIGHT_OUTPUT_DIR",
  "AIHF_PLAYWRIGHT_SCREENSHOT_DIR",
  "AIHF_WEB_SERVER_COMMAND",
  "AIHF_WEB_API_TARGET",
  "AIHF_VITE_ENV_DIR",
  "HEDGE_FUND_TEST_MODE",
  "HEDGE_FUND_TEST_ROOT",
  "PLAYWRIGHT_BROWSERS_PATH",
];

let activeChild;
let activeChildUsesGroup = false;
let interrupted = false;

export function isolatedEnvironment(source, python) {
  const env = { ...source };
  for (const name of Object.keys(env)) {
    if (
      name.startsWith("VITE_") ||
      name.startsWith("AIHF_TEST_") ||
      name.toLowerCase().startsWith("npm_config_")
    ) {
      delete env[name];
    }
  }
  for (const name of [
    "NODE_OPTIONS",
    "NODE_PATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
  ]) {
    delete env[name];
  }
  for (const name of [
    ...credentialVariables,
    ...proxyVariables,
    ...unsafeOverrides,
  ]) {
    delete env[name];
  }
  delete env.PYTHONPATH;

  const home = join(testRoot, "home");
  const temporary = join(testRoot, "tmp");
  const drive = process.platform === "win32" ? home.slice(0, 2) : "";
  env.HOME = home;
  env.USERPROFILE = home;
  env.HOMEDRIVE = drive;
  env.HOMEPATH = home.slice(drive.length);
  env.TEMP = temporary;
  env.TMP = temporary;
  env.APPDATA = join(home, "AppData", "Roaming");
  env.LOCALAPPDATA = join(home, "AppData", "Local");
  env.XDG_CACHE_HOME = join(home, ".cache");
  env.XDG_CONFIG_HOME = join(home, ".config");
  env.XDG_DATA_HOME = join(home, ".local", "share");
  env.PYTHON_DOTENV_DISABLED = "1";
  env.PYTHONDONTWRITEBYTECODE = "1";
  env.PYTHONNOUSERSITE = "1";
  env.HEDGE_FUND_TEST_MODE = "1";
  env.HEDGE_FUND_TEST_ROOT = testRoot;
  env.PYTHONPATH = [
    resolve(repositoryRoot, "hedge_fund", "test_support"),
    repositoryRoot,
  ].join(delimiter);
  env.AIHF_WEB_PORT = String(port);
  env.AIHF_WEB_TEST_ROOT = testRoot;
  env.AIHF_WEB_DEMO_ROOT = demoRoot;
  env.AIHF_WEB_STATIC_DIR = join(testRoot, "web-static");
  env.AIHF_WEB_API_TARGET = `http://127.0.0.1:${port}`;
  env.AIHF_PLAYWRIGHT_OUTPUT_DIR = join(testRoot, "playwright-results");
  env.AIHF_PLAYWRIGHT_SCREENSHOT_DIR = screenshotDir;
  env.AIHF_E2E_PYTHON = python;
  env.AIHF_WEB_SERVER_COMMAND = [
    shellQuote(python),
    "-m hedge_fund.web --demo",
    `--port ${port}`,
    `--root ${shellQuote(demoRoot)}`,
  ].join(" ");
  env.AIHF_VITE_ENV_DIR = join(testRoot, "vite-env");
  env.PLAYWRIGHT_BROWSERS_PATH = join(testRoot, "playwright-browsers");
  env.NPM_CONFIG_CACHE = join(testRoot, "npm-cache");
  env.NPM_CONFIG_USERCONFIG = join(testRoot, "test.npmrc");
  env.NPM_CONFIG_OFFLINE = "true";
  env.NPM_CONFIG_AUDIT = "false";
  env.NPM_CONFIG_FUND = "false";
  env.NPM_CONFIG_UPDATE_NOTIFIER = "false";
  return env;
}

function resolveProjectPython(source) {
  const explicit = source.AIHF_E2E_PYTHON;
  if (explicit) {
    if (!isAbsolute(explicit) || !existsSync(explicit)) {
      throw new Error("AIHF_E2E_PYTHON must be an existing absolute path.");
    }
    return resolve(explicit);
  }

  const command = process.platform === "win32" ? "python" : "python3";
  const result = spawnSync(
    command,
    ["-m", "poetry", "-C", repositoryRoot, "env", "info", "--executable"],
    {
      cwd: repositoryRoot,
      env: preflightEnvironment(source),
      encoding: "utf8",
      timeout: 15_000,
      windowsHide: true,
    },
  );
  const executable = result.stdout?.trim();
  if (result.error || result.status !== 0 || !executable) {
    throw new Error(
      "Poetry could not resolve the project interpreter. Set AIHF_E2E_PYTHON to an existing absolute path.",
    );
  }
  if (!isAbsolute(executable) || !existsSync(executable)) {
    throw new Error("Poetry returned an invalid project interpreter path.");
  }
  return resolve(executable);
}

export function preflightEnvironment(source) {
  const env = { ...source };
  for (const name of Object.keys(env)) {
    if (
      name.startsWith("VITE_") ||
      name.startsWith("AIHF_TEST_") ||
      name.toLowerCase().startsWith("npm_config_")
    ) {
      delete env[name];
    }
  }
  for (const name of [
    ...credentialVariables,
    ...proxyVariables,
    ...unsafeOverrides,
  ]) {
    delete env[name];
  }
  for (const name of [
    "NODE_OPTIONS",
    "NODE_PATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
  ]) {
    delete env[name];
  }
  delete env.PYTHONPATH;
  env.PYTHON_DOTENV_DISABLED = "1";
  env.PYTHONDONTWRITEBYTECODE = "1";
  env.PYTHONNOUSERSITE = "1";
  return env;
}

export function fingerprintDirectory(directory) {
  const root = resolve(directory);
  const files = [];
  const visit = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const path = join(current, entry.name);
      if (entry.isSymbolicLink()) {
        throw new Error("Build output cannot contain symbolic links.");
      }
      if (entry.isDirectory()) {
        visit(path);
      } else if (entry.isFile()) {
        files.push(path);
      } else {
        throw new Error("Build output contains an unsupported file type.");
      }
    }
  };
  visit(root);

  files.sort((left, right) => {
    const leftName = relative(root, left).split(sep).join("/");
    const rightName = relative(root, right).split(sep).join("/");
    return leftName < rightName ? -1 : leftName > rightName ? 1 : 0;
  });
  const hash = createHash("sha256");
  let bytes = 0;
  for (const path of files) {
    const name = relative(root, path).split(sep).join("/");
    const content = readFileSync(path);
    hash.update(name);
    hash.update("\0");
    hash.update(content);
    hash.update("\0");
    bytes += content.length;
  }
  return { sha256: hash.digest("hex"), files: files.length, bytes };
}

function runPythonHelper(python, script, args, env) {
  const result = spawnSync(python, ["-c", script, ...args], {
    cwd: repositoryRoot,
    env,
    encoding: "utf8",
    timeout: 30_000,
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    throw new Error(
      result.stderr?.trim() || result.error?.message || "Python fixture helper failed.",
    );
  }
  return result.stdout.trim();
}

function prepareTestRoot(python, env) {
  const script = [
    "import sys",
    "from pathlib import Path",
    "from hedge_fund.test_support.network_guard import configure_test_environment, prepare_test_output_root",
    "outputs = prepare_test_output_root(Path(sys.argv[1]))",
    "root = outputs / sys.argv[2]",
    "root.mkdir(exist_ok=False)",
    '(root / ".test-owned").write_bytes(b"test-owned\\n")',
    "configure_test_environment(root)",
    "print(root)",
  ].join("\n");
  const prepared = runPythonHelper(python, script, [outputRoot, rootName], env);
  if (resolve(prepared) !== testRoot) {
    throw new Error("Python fixture helper returned an unexpected root.");
  }
}

function cleanupTestRoot(python, env) {
  if (!existsSync(testRoot)) return true;
  const script = [
    "import sys",
    "from pathlib import Path",
    "from hedge_fund.test_support.network_guard import cleanup_test_root",
    "cleaned = cleanup_test_root(Path(sys.argv[1]), Path(sys.argv[2]))",
    'print("cleaned" if cleaned else "refused")',
    "sys.exit(0 if cleaned else 1)",
  ].join("\n");
  try {
    runPythonHelper(python, script, [testRoot, marker], env);
    return true;
  } catch (error) {
    console.error(`Test-root cleanup refused: ${error.message}`);
    return false;
  }
}

function assertShellPath(value) {
  if (process.platform === "win32" && /["%&|<>^!]/.test(value)) {
    throw new Error("Test path contains an unsupported shell character.");
  }
}

function shellQuote(value) {
  assertShellPath(value);
  if (process.platform === "win32") return `"${value}"`;
  return `'${value.replaceAll("'", "'\\''")}'`;
}

function assertPortBindable() {
  return new Promise((resolveResult) => {
    const server = createServer();
    server.once("error", () => resolveResult(false));
    server.listen({ host: "127.0.0.1", port, exclusive: true }, () => {
      server.close((error) => resolveResult(!error));
    });
  });
}

async function waitForPortRelease() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (await assertPortBindable()) return true;
    await new Promise((resolveResult) => setTimeout(resolveResult, 100));
  }
  return false;
}

export function runOwnedProcess(command, args, options, signal) {
  return new Promise((resolveResult, reject) => {
    const child = spawn(command, args, {
      ...options,
      windowsHide: true,
    });
    activeChild = child;
    activeChildUsesGroup = options.detached === true;
    const removeAbort = () => signal?.removeEventListener("abort", abort);
    const abort = () =>
      terminateChild(child, "SIGTERM", options.detached === true);
    if (signal?.aborted) abort();
    else signal?.addEventListener("abort", abort, { once: true });
    child.once("error", (error) => {
      if (activeChild === child) {
        activeChild = undefined;
        activeChildUsesGroup = false;
      }
      removeAbort();
      reject(error);
    });
    child.once("exit", (code, signal) => {
      if (activeChild === child) {
        activeChild = undefined;
        activeChildUsesGroup = false;
      }
      removeAbort();
      resolveResult({
        code: code ?? (signal === "SIGINT" ? 130 : 1),
        pid: child.pid,
        signal,
      });
    });
  });
}

function terminateChild(child, signal, processGroup = false) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (process.platform !== "win32" && processGroup && child.pid) {
    try {
      process.kill(-child.pid, signal);
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  } else {
    child.kill(signal);
  }
  const timer = setTimeout(() => {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill("SIGKILL");
    }
  }, 5_000);
  timer.unref();
}

async function runFrontendBuild(env) {
  const steps = [
    [
      resolve(frontendRoot, "node_modules", "typescript", "bin", "tsc"),
      ["--noEmit"],
    ],
    [
      resolve(frontendRoot, "node_modules", "vite", "bin", "vite.js"),
      ["build"],
    ],
  ];
  for (const [script, args] of steps) {
    if (!existsSync(script)) {
      throw new Error("Frontend build dependencies are missing; install offline first.");
    }
    const result = await runOwnedProcess(process.execPath, [script, ...args], {
      cwd: frontendRoot,
      env,
      stdio: "inherit",
    });
    if (result.code !== 0) return result.code;
    if (interrupted) return 130;
    if (args[0] === "build") {
      const artifact = fingerprintDirectory(env.AIHF_WEB_STATIC_DIR);
      console.log(
        `Frontend artifact SHA-256: ${artifact.sha256} (${artifact.files} files, ${artifact.bytes} bytes).`,
      );
    }
  }
  return 0;
}

function runPlaywright(env, args) {
  const cli = resolve(frontendRoot, "node_modules", "@playwright", "test", "cli.js");
  if (!existsSync(cli)) {
    throw new Error("Playwright is missing; install frontend dependencies offline first.");
  }
  if (
    args.some((arg) =>
      ["--config", "-c", "--output", "--reporter", "--ui"].some(
        (option) => arg === option || arg.startsWith(`${option}=`),
      ),
    )
  ) {
    throw new Error("Playwright config override is disabled in this harness.");
  }
  const config = resolve(frontendRoot, "playwright.config.ts");
  if (!existsSync(config)) throw new Error("Playwright config is missing.");
  return runOwnedProcess(process.execPath, [cli, "test", ...args], {
    cwd: frontendRoot,
    detached: process.platform !== "win32",
    env,
    stdio: "inherit",
  });
}

function installSignalHandlers() {
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => {
      interrupted = true;
      const child = activeChild;
      if (!child) return;
      const processGroup = activeChildUsesGroup;
      const timer = setTimeout(
        () => terminateChild(child, signal, processGroup),
        5_000,
      );
      timer.unref();
    });
  }
}

async function main() {
  installSignalHandlers();
  let python;
  let env;
  let cleanupEnvironment;
  let runnerResult;
  let failure = false;
  let serverStarted = false;

  try {
    const preflight = preflightEnvironment(process.env);
    cleanupEnvironment = preflight;
    python = resolveProjectPython(preflight);
    env = isolatedEnvironment(process.env, python);
    prepareTestRoot(python, preflight);
    mkdirSync(env.AIHF_VITE_ENV_DIR, { recursive: false });
    writeFileSync(env.NPM_CONFIG_USERCONFIG, "offline=true\naudit=false\nfund=false\n", {
      flag: "wx",
    });

    if (!(await assertPortBindable())) {
      throw new Error(`Test port ${port} is already occupied; no server adopted.`);
    }
    const buildCode = await runFrontendBuild(env);
    if (buildCode !== 0) {
      failure = true;
    } else if (interrupted) {
      failure = true;
    } else {
      serverStarted = true;
      runnerResult = await runPlaywright(env, process.argv.slice(2));
      if (runnerResult.code !== 0) failure = true;
      if (interrupted) failure = true;
      if (!(await waitForPortRelease())) {
        throw new Error(`Owned server did not release test port ${port}; root retained.`);
      }
      serverStarted = false;
    }
  } catch (error) {
    failure = true;
    console.error(error instanceof Error ? error.message : String(error));
  } finally {
    if (python && cleanupEnvironment) {
      if (serverStarted && !(await waitForPortRelease())) {
        console.error(`Port ${port} remains occupied; test root retained.`);
        failure = true;
      } else if (!cleanupTestRoot(python, cleanupEnvironment)) {
        failure = true;
      }
    }
  }

  process.exitCode = failure ? 1 : (runnerResult?.code ?? 0);
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  await main();
}

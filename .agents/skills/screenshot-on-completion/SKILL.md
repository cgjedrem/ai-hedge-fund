---
name: screenshot-on-completion
description: 'After a UI coding task, write and run a task-specific Playwright script that screenshots the new behaviour for visual verification. Use when a UI task completes or the user asks to see how it looks.'
---

# Workflow: screenshot-on-completion

## Trigger
- Coding task completes that adds/modifies UI components
- Agent finishes a feature branch with visual changes
- User says "screenshot this" or "show me how it looks"
- Coordinator presents completion summary for a UI task

## Purpose
On completion of a UI coding task, the agent writes a task-specific Playwright script that captures the exact features it just built, runs it, and uploads screenshots to the relevant chat thread for visual verification.

---

## Prerequisites
- Playwright available (npx-cached or locally installed)
- Dev server can be started or is already running
- Chat thread/channel ID is known for screenshot delivery
- Messaging tool available for file uploads

## Parameters

- `{requesting_user}` — user requesting the screenshot (default: inferred from session)
- `{chat_thread_id}` — target chat thread for screenshot delivery (default: current thread)
- `{dev_port}` — dev server port (default: auto-detect 3000-3003)

## Steps

### task1-detect-server
- **Purpose:** Find running dev server or start one
- **How:**
  ```bash
  lsof -i :3000 -i :3001 -i :3002 -i :3003 2>/dev/null | grep LISTEN
  ```
- **If running:** Note the port number, proceed to task2
- **If not running:** Start dev server, wait for "Ready" line, then proceed
- **Output:** `DEV_PORT` environment variable (e.g. `3002`)
- **Success:** Dev server confirmed running on a known port

### task2-identify-features
- **Purpose:** Determine which UI states, interactions, and visual variants need screenshots based on what was just built
- **How:** Review the task you just completed. Identify:
  - New pages or routes
  - New components and their visual states (open/closed, empty/populated, error/success)
  - Theme or variant differences that must be shown
  - Interactions needed to reach the visual state (click button, switch tab, open modal)
- **Output:** A list of screenshot scenarios, e.g.:
  - "theme A with timer idle"
  - "theme B with timer running"
  - "settings modal open"
  - "mobile viewport"
- **Success:** All new/modified visual states identified

### task3-write-script
- **Purpose:** Write a custom Playwright script tailored to the features you just built. Do NOT reuse a generic script.
- **How:**
  - Create `/tmp/screenshot-task.cjs` (CommonJS, uses `require`)
  - Use the locally available Playwright installation path
  - For each screenshot scenario from task2:
    - Navigate to the correct route
    - Perform any interactions needed (click buttons, switch themes, open modals)
    - Wait for animations/settle (`waitForTimeout(2000)`)
    - Capture with descriptive filename: `/tmp/screenshot-DESCRIPTION.png`
  - Close browser at the end
- **Example structure:**
  ```js
  const { chromium } = require('<local-playwright-path>');
  (async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    
    // Screenshot 1: Theme A idle
    await page.goto('http://localhost:PORT/', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: '/tmp/screenshot-theme-a-idle.png' });
    
    // Screenshot 2: Settings modal open
    await page.locator('[aria-label="Settings"]').click();
    await page.waitForTimeout(800);
    await page.screenshot({ path: '/tmp/screenshot-settings-modal.png' });
    
    await browser.close();
  })();
  ```
- **Rules:**
  - Use `.cjs` extension (CommonJS — npx-cached Playwright uses `require`)
  - Use the locally available Playwright path — never bare `import`, never `@playwright/test`
  - Use `waitUntil: 'networkidle'` + 2-3s settle delay for animations/images
  - Use `fullPage: false` for viewport screenshots
  - Use descriptive filenames: `screenshot-{feature}-{state}.png`
  - If theme switching requires specific clicks, code those interactions
  - If mobile viewport is relevant, add a second page context with `{ viewport: { width: 390, height: 844 } }`
- **Output:** `/tmp/screenshot-task.cjs` + PNG files in `/tmp/screenshot-*.png`
- **Success:** Script runs without errors, all screenshots captured

### task4-run-playwright
- **Purpose:** Execute the task-specific Playwright script
- **How:**
  ```bash
  node /tmp/screenshot-task.cjs
  ```
- **Validation:** Check that each screenshot file exists and is > 50KB (smaller files are likely blank/failed):
  ```bash
  ls -la /tmp/screenshot-*.png
  ```
  If any file is < 50KB, the screenshot likely failed. Debug and re-run.
- **If fails:** Check error, fix selector or timing, retry once
- **Output:** PNG files in `/tmp/screenshot-*.png`, each > 50KB
- **Success:** All screenshots captured, script exits 0, all files > 50KB

### task5-upload-screenshots
- **Purpose:** Attach screenshots to the relevant chat thread
- **How:** Use the messaging tool to upload each screenshot:
  - One message per screenshot with descriptive label
  - Or batch in a single message if <5 screenshots
- **CRITICAL:** This step is MANDATORY. Do NOT skip it. Do NOT just say "screenshots captured" — actually upload each file via the messaging tool.
- **Success:** All screenshots visible in chat thread

### task6-cleanup-files
- **Purpose:** Remove temporary files
- **How:**
  ```bash
  rm -f /tmp/screenshot-*.png /tmp/screenshot-task.cjs
  ```
- Also remove any screenshot scripts left in the project directory:
  ```bash
  rm -f screenshot-capture*.mjs screenshot-capture*.cjs
  ```
- **Success:** No temp files left in /tmp, no screenshot scripts in project dir

---

## Skills/Tools Used
- Shell execution tool (harness-specific) — run dev server detection, Playwright script, cleanup
- Messaging tool (harness-specific) — upload screenshots to chat thread (MANDATORY)
- Background process management tool (harness-specific) — monitor dev server startup if needed

## Outputs

- Screenshots uploaded to chat thread via messaging tool
- No persistent files (temp files cleaned up)

## Rollback

- If Playwright fails: check selector/timing, fix script, retry once
- If screenshots are < 50KB: likely blank captures, debug selectors and re-run
- If messaging upload fails: retry once, then notify coordinator with file paths
- If dev server won't start: report to {requesting_user}, don't block on screenshots

## Checklist (agent must verify before marking task complete)

- [ ] Dev server was running (or started)
- [ ] Task-specific Playwright script written for the features just built
- [ ] All screenshot files exist and are > 50KB (blank captures indicate failure)
- [ ] Screenshots uploaded to chat thread via messaging tool (not just "captured")
- [ ] Temp files cleaned up (both /tmp and project directory)

---

*Version 1.2 — Generalized: removed hardcoded paths, Ticker project references, and harness-specific tool names*

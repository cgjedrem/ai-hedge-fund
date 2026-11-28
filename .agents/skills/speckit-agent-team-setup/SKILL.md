---
name: speckit-agent-team-setup
description: Install the agent-team personas into .github/agents/, seed charter fragments,
  scaffold the red-team lens catalog, and register the QA review gate overlay (idempotent;
  safe to re-run)
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: preset:agent-team
---

# Speckit Agent Team Setup Skill

# Agent Team Setup

This command installs the cgjedrem agent-team personas and supporting material that
shipped with the `agent-team` preset into the current project.

The preset pack is on disk at `.specify/presets/agent-team/` relative to the
current project root. All source files referenced below live inside that
directory (unless noted otherwise).

## What to install

1. **Personas** — copy every file in `.specify/presets/agent-team/agents/` into
   `.github/agents/`:
   - coordinator.agent.md
   - backend-dev.agent.md
   - frontend-dev.agent.md
   - qa-reviewer.agent.md
   - code-explorer.agent.md
   - editor.agent.md
   - tasker.agent.md

2. **Charter fragment seeds** — copy `.specify/presets/agent-team/charter/` into
   `.charter/` at the project root (creating `.charter/` if absent). This seeds a
   charter registry with a starter `manifest.yml` and six fragments:
   `platform/windows-powershell` (mandatory) plus `backend/node-backend`,
   `client/react-client`, `quality/playwright-e2e`, `toolchain/npm-strict`,
   `toolchain/pnpm-strict` (recommended — per-project choices).

   **Per-project toolchain choice (v1.1.0)**: the toolchain fragment is chosen
   per project, not forced. When the project later runs
   `/speckit.charter.config`, select exactly ONE of:

   - `toolchain/npm-strict` — npm end-to-end repos (`npm ci`, `npm run <script>`,
     one-off tools via `npx --yes <tool>@<exact-version>`)
   - `toolchain/pnpm-strict` — pnpm repos (`pnpm install --frozen-lockfile`,
     `pnpm <script>` / `pnpm dlx`)

   Pick the manager the repo already uses (npm: Frivollig, Ungfritid,
   path-of-practice; pnpm: ticker, Pocket-Smith client). Composing both is a
   conflict; composing neither leaves package-manager rules unspecified.

   If `.charter/` already holds a v1.0.x seed (its manifest lists
   `toolchain/pnpm-strict` under `mandatory_fragments`), offer to update
   `.charter/manifest.yml` to the per-project-choice manifest and to add the
   new fragment files (`toolchain/npm-strict`, `quality/playwright-e2e`) —
   this is the expected v1.1.0 upgrade path. Keep any locally adapted fragment
   content the user wants to preserve (e.g. Frivillig's local npm adaptation
   is superseded by the official `toolchain/npm-strict` fragment).

3. **Red-team lens catalog scaffold (v1.1.0)** — the `red-team` extension
   requires `.specify/extensions/red-team/red-team-lenses.yml` as its config,
   but nothing scaffolds it at install time; without it the mandatory
   `before_plan` gate fails fast with "no lens catalog". If
   `.specify/extensions/red-team/red-team-lenses.yml` does NOT exist and the
   red-team extension is installed (its `config-template.yml` is present),
   copy `.specify/extensions/red-team/config-template.yml` to
   `.specify/extensions/red-team/red-team-lenses.yml`. Then verify the lens
   catalog covers ALL SIX trigger categories: the union of every lens's
   `trigger_match` must include `money_path`, `regulatory_path`, `ai_llm`,
   `immutability_audit`, `multi_party`, and `contracts` (the shipped 4-lens
   template covers all six). If `red-team-lenses.yml` already exists, leave it
   untouched — it may be locally calibrated. If the red-team extension is not
   installed, skip this step and say so.

4. **QA review gate overlay (auto-registered in v1.1.0)** — check whether the
   overlay is already registered:

   ```powershell
   specify workflow overlay list speckit
   ```

   If `qa-review-gate` is NOT listed, register the shipped overlay:

   ```powershell
   specify workflow overlay add .specify/presets/agent-team/overlays/qa-review-gate.yml
   ```

   then re-run `specify workflow overlay list speckit` and confirm
   `qa-review-gate` appears with `priority=10`, enabled.

   If already registered, inspect the effective overlay and compare its content
   with the shipped copy; an ID match alone is not proof of an upgrade. Preserve
   local customizations and ask before changing it. After approval, merge the
   changes into the project-local overlay, or re-add the shipped copy with the
   command above if wholesale replacement was approved (CLI 1.0.4 supports
   updating the same overlay ID). Never silently enable a deliberately disabled
   overlay.

   Preserve `qa-review` after `tasks`, and add `final-evidence-review` after
   `implement`, both `type: gate`. The final gate reviews criterion-level
   evidence; it does not execute runtime checks or grant commit/release consent.
   Behavior-affecting review fixes reopen affected rows and approval pending
   rerun, including changes after a workflow run completes.

5. **Evidence-aware bug overrides (v1.2.0)** — the preset installer, not file
   copying into `.specify/extensions/bug`, registers the three owned command
   templates. Verify resolution:

   ```powershell
   specify preset resolve speckit.bug.assess
   specify preset resolve speckit.bug.fix
   specify preset resolve speckit.bug.test
   specify workflow resolve speckit
   ```

   Each bug command should resolve to the agent-team preset unless an intentional
   higher-precedence project override exists. Inspect generated command/skill
   content and provenance, not just registered names. Report a higher-priority
   override or stale generated content as a conflict; do not overwrite it.
   Preserve command placeholders in source templates; use the CLI installer to
   generate skills. The CLI-bundled bug extension remains upstream-owned.

## Rules

- **Never overwrite an existing file without asking.** If a persona, fragment,
  or config file already exists at the destination, report it as a conflict,
  show the diff on request, and only replace it after explicit user
  confirmation. The red-team scaffold never touches an existing
  `red-team-lenses.yml`; an existing overlay is updated only after approval.
- Create destination directories as needed (`.github/agents/`, `.charter/`).
- Copy files byte-for-byte; do not reformat, re-wrap, or "improve" persona or
  fragment content for a new compatible destination. For an existing customized
  destination, apply only an explicitly approved governed-section merge.
- After copying, list exactly which files were created, skipped (already
  present), and — only with approval — overwritten.
- Existing personas/fragments need a content comparison on upgrade, not just
  presence checks. Offer a reviewed merge to preserve local adaptations.
- Inspect the effective agent loading path and prompt content where accessible.
  Disk parity or a registered persona name does not prove a running session
  loaded the new prompt. Report inaccessible/stale runtime prompts as
  `BLOCKED`/`INCONCLUSIVE`; do not reload sessions or user-level personas.

## Verify

When done, verify and report:
- `.github/agents/` contains all 7 `*.agent.md` files.
- `.charter/manifest.yml` exists, lists `platform/windows-powershell` as the
  only mandatory fragment, and lists `backend/node-backend`,
  `client/react-client`, `quality/playwright-e2e`, `toolchain/npm-strict`, and
  `toolchain/pnpm-strict` as recommended (per-project choice).
- `.specify/extensions/red-team/red-team-lenses.yml` exists (when the red-team
  extension is installed) and its lenses' combined `trigger_match` covers all
  six trigger categories.
- `specify workflow overlay list speckit` shows `qa-review-gate` with
  `priority=10`, enabled.
- `specify workflow resolve speckit` shows both `qa-review` after `tasks` and
  `final-evidence-review` after `implement`; both reject with abort.
- Source/installed preset/generated bug commands carry revision plus local
  changes or build ID/digest, environment, scenario, timestamp, provenance,
  separate static/build/runtime/user report evidence, measured thresholds and
  durations, stale-row invalidation, and `BLOCKED`/`INCONCLUSIVE` outcomes.
- QA stays read-only; execution-capable owners supply runtime evidence. Model
  routing is capability/risk based, with a complete evidence handoff before a
  switch and no unrequested model/effort changes. New evidence is required before
  a second patch; two failed attempts trigger root-cause reassessment.

### Installation and loading acceptance

- Compare canonical/preset, repository, installed/discovery and effective loaded
  identities separately, with revision/diff, path/digest, harness, timestamp and
  provenance. A skipped existing persona is not an update; a copy is not activation.
- Preserve repo-owned frontmatter/blocks and local customization. Check hooks for
  target paths, shells, event schemas and permissions; do not copy repo-relative
  hooks into a target lacking its approved script.
- Verify referenced skills, governance documents, helper scripts and hook
  dependencies at the intended revision. A missing dependency is BLOCKED.
- Establish effective loaded persona/instruction sources and precedence using
  target-harness evidence in a separately authorized test context; a self-reported
  instruction or registry name alone is insufficient. Missing access is BLOCKED;
  ambiguous/stale identity is INCONCLUSIVE.
- For applicable hooks, require a separately approved isolated smoke check of
  allowed and denied behavior at the installed revision. Offline parser checks
  alone do not prove activation. Mark N/A only with a rationale.
- Report source readiness, installation and loading acceptance separately. Do not
  overwrite global definitions, execute live hooks or force active-session reloads
  to satisfy the gate. BLOCKED/INCONCLUSIVE is not delivered acceptance.

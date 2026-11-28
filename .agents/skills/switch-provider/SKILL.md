---
name: switch-provider
description: Inspect or switch agent model priority arrays between GitHub Copilot primary and Ollama Cloud primary across workspaces, APM packages, or ~/.agents/agents, or route child sessions to a specific provider at spawn time. Use when the user asks to "switch to ollama", "switch to copilot", "check active model provider", or "spawn on ollama".
---

# Switch Model Provider (Copilot <-> Ollama Cloud)

ENSO `.agent.md` files use a priority-ordered `model:` array supported natively by Copilot SDK, Copilot App, Copilot CLI, and VS Code Copilot:

- **Copilot primary (default):** `model: ["<copilot_id>", "<ollama_uuid>/<ollama_id>", "<ollama_id>"]`
- **Ollama Cloud primary:** `model: ["<ollama_uuid>/<ollama_id>", "<ollama_id>", "<copilot_id>"]`

Because every agent carries both providers in its `model:` array:
1. If one provider is unavailable or rate-limited, the runtime falls back automatically instead of inheriting an expensive parent session model (such as `claude-opus-5.5` at 15x credits).
2. Flipping the primary provider for an entire repo or global `~/.agents/agents` takes one deterministic script call before opening a new session.

## Role Mapping Matrix

| Agent | Copilot Primary | Ollama Cloud Primary | `reasoningEffort` |
|---|---|---|---|
| `architect` | `claude-sonnet-5.5` (escalate to `claude-opus-5.5` / `claude-fable-5.2` on-demand for L/XL Stage-1) | `glm-5.3-flash:cloud` | `high` |
| `coordinator` | `gpt-6.1-terra` | `glm-5.3-flash:cloud` | `medium` |
| `backend-dev` | `gpt-6-luna` | `glm-5.3:cloud` | `medium` |
| `frontend-dev` | `gpt-6-luna` | `glm-5.3:cloud` | `medium` |
| `python-dev` | `gpt-6-luna` | `glm-5.3:cloud` | `medium` |
| `qa-reviewer` | `claude-sonnet-5.5` | `kimi-k3.1-pro:cloud` | `high` |
| `code-explorer` | `claude-haiku-4.5` | `glm-5.3-flash:cloud` | `low` |
| `tasker` | `gpt-5.6-luna` | `glm-5.3-flash:cloud` | `low` |
| `editor` | `gpt-5.6-luna` | `glm-5.3-flash:cloud` | `low` |
| `device-runner` | `gpt-5.6-luna` | `glm-5.3-flash:cloud` | `low` |

> **Effort compatibility note:** `kimi-k3*` models only accept `low`, `high`, or `max` (never `medium`). `qa-reviewer` uses `high`, which is valid on both `claude-sonnet-5.5` and `kimi-k3.1-pro:cloud`.

## Workflow 1: Switch a Workspace or Global Profile (Persistent)

Run the bundled `scripts/switch-model-profile.ps1` inside this skill folder (`.agents\skills\switch-provider\scripts\switch-model-profile.ps1` in standalone APM consumer repos, or `<enso-root>\scripts\vscode\switch-model-profile.ps1` in ENSO):

```powershell
$switcher = ".agents\skills\switch-provider\scripts\switch-model-profile.ps1"
# (Fallback in ENSO checkout: "scripts\vscode\switch-model-profile.ps1")

# 1. Inspect current primary provider + fallback models in a repo
powershell -NoProfile -File $switcher -Provider status -TargetPath <repo-root>

# 2. Switch a repository's .github/agents/*.agent.md to Ollama Cloud primary
powershell -NoProfile -File $switcher -Provider ollama -TargetPath <repo-root>

# 3. Switch back to GitHub Copilot primary
powershell -NoProfile -File $switcher -Provider copilot -TargetPath <repo-root>

# 4. Switch global ~/.agents/agents and sync to VS Code user prompts
powershell -NoProfile -File $switcher -Provider ollama -SyncDiscovery
```

After switching files on disk, start a **new session** (or reload VS Code window) so the session picks up the updated `.agent.md` frontmatter. Remember: do not commit temporary local provider flips in shared repos unless the repo intentionally defaults to Ollama.

## Workflow 2: Per-Session Override Without Editing Files

When `architect` spawns child `coordinator` sessions via `create_session` (see `speckit-parallel-spawn`):
- **For an Ollama child session:** Pass `kickoff.model: "<ollama_uuid>/glm-5.3-flash:cloud"` (default UUID `73192633-e8b9-4870-90db-123a98a64cc1`, auto-checked by running `switch-model-profile.ps1 -Provider status`).
- **For a Copilot child session:** Pass `kickoff.model: "gpt-6.1-terra"` or omit `kickoff.model` when the workspace is already Copilot-primary.
- **For Claude Code repos (`Frivillig-vite`, `Ungfritid-vite`):** Re-render `.claude/` via `scripts/claude/render-claude-kit.ps1 -RepoRoot <repo-root>` (`sonnet` default for `architect`, `coordinator`, devs, and `qa-reviewer`; `haiku` for `code-explorer`; `claude --model opus --agent architect` on-demand for `L/XL` architecture specs).

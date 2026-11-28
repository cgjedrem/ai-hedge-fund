<#
.SYNOPSIS
    Switch .agent.md model priority arrays between GitHub Copilot primary and Ollama Cloud primary.

.DESCRIPTION
    Every ENSO .agent.md file declares a priority-ordered `model:` array supported by Copilot SDK,
    Copilot App, Copilot CLI, and VS Code Copilot:

    - Copilot primary (default):
        model: ["<copilot_model>", "<ollama_uuid>/<ollama_model>", "<ollama_model>"]
    - Ollama primary (cost-free / local-cloud mode):
        model: ["<ollama_uuid>/<ollama_model>", "<ollama_model>", "<copilot_model>"]

    This script inspects (`-Provider status`) or flips (`-Provider copilot|ollama`) the `model:`
    and `reasoningEffort:` frontmatter keys across a target directory or repository without
    touching agent bodies, tools, or repo-owned rules.

    All output files are written as UTF-8 without BOM and LF line endings.
    Keep this script pure 7-bit ASCII: Windows PowerShell 5.1 parses BOM-less .ps1 files as ANSI.

.PARAMETER Provider
    Target mode: "status" (read-only table, default), "copilot" (Copilot primary + Ollama fallback),
    or "ollama" (Ollama Cloud primary + Copilot fallback).

.PARAMETER TargetPath
    Directory or repo root containing .agent.md files. Resolves `<TargetPath>\.github\agents`,
    `<TargetPath>\.apm\agents`, or `<TargetPath>` directly. Defaults to `~/.agents/agents` when
    present, else `<enso-root>\packages\_base\.apm\agents`.

.PARAMETER OllamaProviderId
    Explicit Copilot App custom-provider UUID prefix for Ollama Cloud models. When omitted,
    auto-detects from `~/.copilot/data.db` (via python sqlite3) or existing .agent.md files,
    falling back to `73192633-e8b9-4870-90db-123a98a64cc1`.

.PARAMETER SyncDiscovery
    When set and `sync-agents.ps1` exists alongside this script, runs `sync-agents.ps1` after
    updating `~/.agents/agents` so `%APPDATA%\Code\User\prompts` picks up the change immediately.

.PARAMETER DryRun
    Show planned changes without modifying any files.

.EXAMPLE
    .\switch-model-profile.ps1 -Provider status -TargetPath C:\repos\vitalis
    Inspect active primary provider and model fallbacks in vitalis.

.EXAMPLE
    .\switch-model-profile.ps1 -Provider ollama -TargetPath C:\repos\Pocket-Smith-Reports
    Flip Pocket-Smith-Reports .github/agents/*.agent.md to Ollama Cloud primary.

.EXAMPLE
    .\switch-model-profile.ps1 -Provider copilot -SyncDiscovery
    Restore Copilot primary in ~/.agents/agents and sync to VS Code user prompts.
#>
param(
    [ValidateSet("status", "copilot", "ollama")]
    [string]$Provider = "status",
    [string]$TargetPath = "",
    [string]$OllamaProviderId = "",
    [switch]$SyncDiscovery,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$defaultUuid = "73192633-e8b9-4870-90db-123a98a64cc1"

# Canonical dual-provider role mapping.
# Note: kimi-k3* supports reasoningEffort low|high|max only (never medium).
$roleProfiles = @{
    "architect"       = @{ Copilot = @("claude-sonnet-5.5");                Ollama = "glm-5.3-flash:cloud"; Effort = "high" }
    "coordinator"     = @{ Copilot = @("gpt-6.1-terra");                    Ollama = "glm-5.3-flash:cloud"; Effort = "medium" }
    "backend-dev"     = @{ Copilot = @("gpt-6-luna");                       Ollama = "glm-5.3:cloud";       Effort = "medium" }
    "frontend-dev"    = @{ Copilot = @("gpt-6-luna");                       Ollama = "glm-5.3:cloud";       Effort = "medium" }
    "python-dev"      = @{ Copilot = @("gpt-6-luna");                       Ollama = "glm-5.3:cloud";       Effort = "medium" }
    "qa-reviewer"     = @{ Copilot = @("claude-sonnet-5.5");                Ollama = "kimi-k3.1-pro:cloud"; Effort = "high" }
    "code-explorer"   = @{ Copilot = @("gpt-6-luna", "claude-haiku-5.5");   Ollama = "glm-5.3-flash:cloud"; Effort = "low" }
    "tasker"          = @{ Copilot = @("gpt-6.1-terra");                    Ollama = "glm-5.3-flash:cloud"; Effort = "low" }
    "editor"          = @{ Copilot = @("gpt-6.1-terra");                    Ollama = "glm-5.3-flash:cloud"; Effort = "low" }
    "device-runner"   = @{ Copilot = @("gpt-6-luna");                       Ollama = "glm-5.3:cloud";       Effort = "low" }
    "fos-am-learning" = @{ Copilot = @("gpt-5.6-luna");                     Ollama = "glm-5.3-flash:cloud"; Effort = "low" }
}

function Resolve-AgentDir([string]$RawPath) {
    if (-not $RawPath) {
        $userAgents = Join-Path $HOME ".agents\agents"
        if (Test-Path -LiteralPath $userAgents) { return (Resolve-Path -LiteralPath $userAgents).Path }
        $twoUp = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        if ($twoUp) {
            $ensoAgents = Join-Path $twoUp "packages\_base\.apm\agents"
            if (Test-Path -LiteralPath $ensoAgents) { return (Resolve-Path -LiteralPath $ensoAgents).Path }
            $fourUp = Split-Path -Parent (Split-Path -Parent $twoUp)
            if ($fourUp) {
                $repoAgents = Join-Path $fourUp ".github\agents"
                if (Test-Path -LiteralPath $repoAgents) { return (Resolve-Path -LiteralPath $repoAgents).Path }
            }
        }
        throw "Could not resolve default agent directory. Pass -TargetPath explicitly."
    }
    if (-not (Test-Path -LiteralPath $RawPath)) {
        throw "TargetPath does not exist: $RawPath"
    }
    $resolved = (Resolve-Path -LiteralPath $RawPath).Path
    if ((Get-Item -LiteralPath $resolved) -is [System.IO.FileInfo]) {
        return $resolved
    }
    foreach ($sub in @(".github\agents", ".apm\agents", "packages\_base\.apm\agents")) {
        $candidate = Join-Path $resolved $sub
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $resolved
}

function Resolve-SyncScriptPath {
    $candidates = @(
        (Join-Path $PSScriptRoot "sync-agents.ps1"),
        (Join-Path $HOME ".agents\scripts\sync-agents.ps1")
    )
    $twoUp = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if ($twoUp) {
        $candidates += (Join-Path $twoUp "scripts\vscode\sync-agents.ps1")
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) {
            return (Resolve-Path -LiteralPath $c).Path
        }
    }
    return $null
}

function Resolve-OllamaUuid([string]$ExplicitUuid, [System.IO.FileInfo[]]$Files) {
    if ($ExplicitUuid) { return $ExplicitUuid.Trim().TrimEnd("/") }

    # 1. Query ~/.copilot/data.db via python sqlite3 first so the machine's local
    #    Ollama provider UUID wins over the seeded repository fallback UUID.
    $dbPath = Join-Path $HOME ".copilot\data.db"
    if ((Test-Path -LiteralPath $dbPath) -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $py = @'
import re, sqlite3, sys
p = sys.argv[1]
pat = re.compile(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/[A-Za-z0-9._-]+:cloud")
try:
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    cur = con.cursor()
    for (tbl,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        try:
            for row in cur.execute(f'SELECT * FROM "{tbl}" LIMIT 200'):
                m = pat.search(" ".join(str(x) for x in row if x is not None))
                if m:
                    print(m.group(1).lower())
                    sys.exit(0)
        except Exception:
            pass
except Exception:
    pass
'@
        $detected = ($py | python - $dbPath 2>$null | Select-Object -First 1)
        if ($detected -and $detected.Trim() -match '^[0-9a-f]{8}-') {
            return $detected.Trim()
        }
    }

    # 2. Fallback: inspect existing .agent.md files for an already-pinned UUID prefix.
    foreach ($f in $Files) {
        $txt = [IO.File]::ReadAllText($f.FullName)
        if ($txt -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/[A-Za-z0-9._-]+:cloud') {
            return $Matches[1].ToLowerInvariant()
        }
    }

    return $defaultUuid
}

function Test-IsOllamaModel([string]$ModelId) {
    return ($ModelId -match ':cloud$' -or $ModelId -match '^[0-9a-fA-F-]{36}/')
}

function Parse-ModelList([string]$Frontmatter) {
    if ($Frontmatter -match '(?m)^model:\s*\[([^\]]*)\]') {
        $items = @()
        foreach ($m in [regex]::Matches($Matches[1], '"([^"]+)"|''([^'']+)''|([^,\s]+)')) {
            $val = if ($m.Groups[1].Success) { $m.Groups[1].Value }
                   elseif ($m.Groups[2].Success) { $m.Groups[2].Value }
                   else { $m.Groups[3].Value }
            if ($val) { $items += $val }
        }
        return $items
    }
    if ($Frontmatter -match '(?m)^model:\s*(.+)$') {
        $raw = $Matches[1].Trim().Trim('"').Trim("'")
        if ($raw) { return @($raw) }
    }
    return @()
}

$targetResolved = Resolve-AgentDir $TargetPath
$targetItem = Get-Item -LiteralPath $targetResolved
$agentFiles = if ($targetItem -is [System.IO.FileInfo]) {
    @($targetItem)
} else {
    @(Get-ChildItem -LiteralPath $targetResolved -Filter "*.agent.md" -File | Sort-Object Name)
}

if ($agentFiles.Count -eq 0) {
    Write-Host "No .agent.md files found at: $targetResolved" -ForegroundColor Yellow
    exit 0
}

$uuid = Resolve-OllamaUuid $OllamaProviderId $agentFiles

if ($Provider -eq "status") {
    Write-Host "=== Agent Model Profile Status ===" -ForegroundColor Cyan
    Write-Host "Target:      $targetResolved"
    Write-Host "Ollama UUID: $uuid"
    Write-Host ""
    $rows = foreach ($file in $agentFiles) {
        $raw = [IO.File]::ReadAllText($file.FullName) -replace "`r`n", "`n"
        if ($raw -notmatch '(?s)^---\n(.*?)\n---\n') { continue }
        $front = $Matches[1]
        $models = @(Parse-ModelList $front)
        $primary = if ($models.Count -gt 0) { $models[0] } else { "(none)" }
        $fallback = if ($models.Count -gt 1) { $models[1] } else { "(none)" }
        $activeProvider = if ($models.Count -eq 0) { "UNPINNED" }
                          elseif (Test-IsOllamaModel $primary) { "OLLAMA" }
                          else { "COPILOT" }
        $effort = if ($front -match '(?m)^reasoningEffort:\s*(\S+)') { $Matches[1] }
                  elseif ($front -match '(?m)^reasoning_effort:\s*(\S+)') { "$($Matches[1]) (snake_case!)" }
                  else { "(default)" }
        [PSCustomObject]@{
            Agent    = ($file.BaseName -replace '\.agent$', '')
            Active   = $activeProvider
            Primary  = $primary
            Fallback = $fallback
            Effort   = $effort
        }
    }
    $rows | Format-Table -AutoSize | Out-String | ForEach-Object { Write-Host $_.TrimEnd() }
    exit 0
}

$syncScript = $null
if ($SyncDiscovery -and $Provider -ne "status") {
    if ($targetItem -is [System.IO.FileInfo]) {
        Write-Error "-SyncDiscovery requires an agent directory target, not a single file: $targetResolved"
        exit 1
    }
    $syncScript = Resolve-SyncScriptPath
    if (-not $syncScript) {
        Write-Error "-SyncDiscovery requested, but sync-agents.ps1 was not found next to switch-model-profile.ps1 or under ~/.agents/scripts."
        exit 1
    }
}

Write-Host "=== Switch Agent Model Profile ===" -ForegroundColor Cyan
Write-Host "Target:      $targetResolved"
Write-Host "Provider:    $($Provider.ToUpperInvariant())"
Write-Host "Ollama UUID: $uuid"
Write-Host "Mode:        $(if ($DryRun) { 'DRY RUN' } else { 'LIVE' })"
Write-Host ""

$updated = 0
$unchanged = 0

foreach ($file in $agentFiles) {
    $origRaw = [IO.File]::ReadAllText($file.FullName)
    $eol = if ($origRaw.Contains("`r`n")) { "`r`n" } else { "`n" }
    $raw = $origRaw -replace "`r`n", "`n"
    if ($raw -notmatch '(?s)^---\n(.*?)\n---\n(.*)$') {
        Write-Warning "Skipping $($file.Name): missing YAML frontmatter"
        continue
    }
    $front = $Matches[1]
    $body = $Matches[2]
    $agentName = if ($front -match '(?m)^name:\s*(\S+)') { $Matches[1].Trim() } else { ($file.BaseName -replace '\.agent$', '') }

    $existing = @(Parse-ModelList $front)
    $ollamaExisting = @($existing | Where-Object { Test-IsOllamaModel $_ })
    $copilotExisting = @($existing | Where-Object { -not (Test-IsOllamaModel $_) })

    # Normalize existing Ollama models so both <uuid>/<slug>:cloud and bare <slug>:cloud are present.
    $ollamaList = @()
    if ($ollamaExisting.Count -gt 0) {
        $seen = @{}
        foreach ($om in $ollamaExisting) {
            $bare = $om -replace '^[0-9a-fA-F-]{36}/', ''
            foreach ($cand in @("$uuid/$bare", $bare)) {
                if (-not $seen.ContainsKey($cand)) {
                    $seen[$cand] = $true
                    $ollamaList += $cand
                }
            }
        }
    } elseif ($roleProfiles.ContainsKey($agentName)) {
        $bare = $roleProfiles[$agentName].Ollama
        $ollamaList = @("$uuid/$bare", $bare)
    }

    $copilotList = if ($copilotExisting.Count -gt 0) {
        @($copilotExisting)
    } elseif ($roleProfiles.ContainsKey($agentName)) {
        @($roleProfiles[$agentName].Copilot)
    } else {
        @()
    }

    if ($ollamaList.Count -eq 0 -and $copilotList.Count -eq 0) {
        Write-Warning "Skipping $($file.Name): unknown agent '$agentName' with no existing model list"
        continue
    }

    $targetModels = if ($Provider -eq "copilot") { @($copilotList) + @($ollamaList) } else { @($ollamaList) + @($copilotList) }

    $targetEffort = if ($front -match '(?m)^reasoningEffort:\s*(low|medium|high)\s*$') {
        $Matches[1]
    } elseif ($roleProfiles.ContainsKey($agentName)) {
        $roleProfiles[$agentName].Effort
    } else {
        ""
    }
    if (($targetModels -join ",") -match 'kimi-k3' -and $targetEffort -eq "medium") {
        $targetEffort = "high"
    }

    $quotedModels = ($targetModels | ForEach-Object { '"' + $_ + '"' }) -join ", "
    $modelLine = "model: [$quotedModels]"

    # Rebuild frontmatter lines: strip existing model / reasoningEffort / reasoning_effort lines,
    # then insert canonical model + reasoningEffort right after `name:`.
    $inBracketModel = $false
    $keptLines = New-Object System.Collections.Generic.List[string]
    foreach ($line in ($front -split "`n")) {
        if ($inBracketModel) {
            if ($line -match '\]') { $inBracketModel = $false }
            continue
        }
        if ($line -match '^model:\s*\[[^\]]*$') {
            $inBracketModel = $true
            continue
        }
        if ($line -match '^model:\s*') { continue }
        if ($line -match '^reasoningEffort:\s*' -or $line -match '^reasoning_effort:\s*') { continue }
        $keptLines.Add($line)
    }

    $outLines = New-Object System.Collections.Generic.List[string]
    $inserted = $false
    foreach ($line in $keptLines) {
        $outLines.Add($line)
        if (-not $inserted -and $line -match '^name:\s*') {
            $outLines.Add($modelLine)
            if ($targetEffort) { $outLines.Add("reasoningEffort: $targetEffort") }
            $inserted = $true
        }
    }
    if (-not $inserted) {
        $outLines.Insert(0, $modelLine)
        if ($targetEffort) { $outLines.Insert(1, "reasoningEffort: $targetEffort") }
    }

    $newText = "---`n" + ($outLines -join "`n") + "`n---`n" + $body
    $outText = if ($eol -eq "`r`n") { $newText -replace "`n", "`r`n" } else { $newText }
    if ($outText -eq $origRaw) {
        Write-Host "  SKIP (already $Provider): $($file.Name)" -ForegroundColor DarkGray
        $unchanged++
    } elseif ($DryRun) {
        Write-Host "  WOULD UPDATE ($Provider): $($file.Name) -> $modelLine" -ForegroundColor Yellow
        $updated++
    } else {
        [IO.File]::WriteAllText($file.FullName, $outText, $utf8NoBom)
        Write-Host "  UPDATED ($Provider): $($file.Name) -> $modelLine" -ForegroundColor Green
        $updated++
    }
}

Write-Host ""
Write-Host "Summary: $updated updated, $unchanged unchanged." -ForegroundColor Cyan

if ($SyncDiscovery -and -not $DryRun) {
    Write-Host ""
    & $syncScript -SourceDir $targetResolved
}

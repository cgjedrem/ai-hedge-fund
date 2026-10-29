#!/usr/bin/env pwsh
# Create a new feature
[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$AllowExistingBranch,
    [switch]$DryRun,
    [string]$ShortName,
    [Parameter()]
    [string]$Number = '',
    [switch]$Timestamp,
    [switch]$NoRemote,
    [switch]$Help,
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$FeatureDescription
)
$ErrorActionPreference = 'Stop'
$maxBranchLength = 244

# Offline opt-out: -NoRemote or SPECKIT_NO_REMOTE=1 disables every remote query
# (branch/head scans and the default-branch fetch used for numbering).
if (-not $NoRemote -and $env:SPECKIT_NO_REMOTE -match '^(1|true|yes)$') {
    $NoRemote = [switch]::Present
}

# Show help if requested
if ($Help) {
    Write-Host "Usage: ./create-new-feature.ps1 [-Json] [-DryRun] [-AllowExistingBranch] [-ShortName <name>] [-Number N] [-Timestamp] <feature description>"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Json               Output in JSON format"
    Write-Host "  -DryRun             Compute feature name and paths without creating directories or files"
    Write-Host "  -AllowExistingBranch  Reuse an existing feature directory if it already exists"
    Write-Host "  -ShortName <name>   Provide a custom short name (2-4 words) for the feature"
    Write-Host "  -Number N           Prefer a feature number (auto-corrected if its specs prefix exists)"
    Write-Host "  -Timestamp          Use timestamp prefix (YYYYMMDD-HHMMSS) instead of sequential numbering"
    Write-Host "  -NoRemote           Skip all remote queries (offline mode; numbering uses local data only)"
    Write-Host "  -Help               Show this help message"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  ./create-new-feature.ps1 'Add user authentication system' -ShortName 'user-auth'"
    Write-Host "  ./create-new-feature.ps1 'Implement OAuth2 integration for API'"
    Write-Host "  ./create-new-feature.ps1 -Timestamp -ShortName 'user-auth' 'Add user authentication'"
    exit 0
}

# Check if feature description provided
if (-not $FeatureDescription -or $FeatureDescription.Count -eq 0) {
    Write-Error "Usage: ./create-new-feature.ps1 [-Json] [-DryRun] [-AllowExistingBranch] [-ShortName <name>] [-Number N] [-Timestamp] <feature description>"
    exit 1
}

$featureDesc = ($FeatureDescription -join ' ').Trim()

# Validate description is not empty after trimming (e.g., user passed only whitespace)
if ([string]::IsNullOrWhiteSpace($featureDesc)) {
    Write-Error "Error: Feature description cannot be empty or contain only whitespace"
    exit 1
}

function Get-HighestNumberFromSpecs {
    param([string]$SpecsDir)

    [long]$highest = 0
    if (Test-Path $SpecsDir) {
        Get-ChildItem -Path $SpecsDir -Directory | ForEach-Object {
            # Match sequential prefixes (>=3 digits), but skip timestamp dirs.
            if ($_.Name -match '^(\d{3,})-' -and $_.Name -notmatch '^\d{8}-\d{6}-') {
                [long]$num = 0
                if ([long]::TryParse($matches[1], [ref]$num) -and $num -gt $highest) {
                    $highest = $num
                }
            }
        }
    }
    return $highest
}

function Get-HighestNumberFromNames {
    param(
        [string[]]$Names,
        [string]$ScopePrefix = ''
    )

    [long]$highest = 0
    foreach ($name in $Names) {
        if ($ScopePrefix -and -not $name.StartsWith($ScopePrefix, [System.StringComparison]::Ordinal)) {
            continue
        }
        if ($ScopePrefix) {
            $name = $name.Substring($ScopePrefix.Length)
        }
        $name = ($name -split '/')[-1]
        $hasTimestampPrefix = $name -match '^\d{8}-\d{6}-'
        $hasMalformedTimestamp = ($name -match '^\d{7}-\d{6}-') -or ($name -match '^(?:\d{7}|\d{8})-\d{6}$')
        if ($name -match '^(\d{3,})-' -and -not $hasTimestampPrefix -and -not $hasMalformedTimestamp) {
            [long]$num = 0
            if ([long]::TryParse($matches[1], [ref]$num) -and $num -gt $highest) {
                $highest = $num
            }
        }
    }
    return $highest
}

function Get-HighestNumberFromBranches {
    try {
        $branches = git branch -a 2>$null
        if ($LASTEXITCODE -eq 0 -and $branches) {
            $cleanNames = $branches | ForEach-Object {
                $_.Trim() -replace '^[+*]?\s+', '' -replace '^remotes/[^/]+/', ''
            }
            return Get-HighestNumberFromNames -Names $cleanNames
        }
    } catch {
        Write-Verbose "Could not check Git branches: $_"
    }
    return 0
}

function Get-HighestNumberFromRemoteRefs {
    [long]$highest = 0
    try {
        $remotes = git remote 2>$null
        if ($remotes) {
            foreach ($remote in $remotes) {
                $env:GIT_TERMINAL_PROMPT = '0'
                $refs = git ls-remote --heads $remote 2>$null
                $env:GIT_TERMINAL_PROMPT = $null
                if ($LASTEXITCODE -eq 0 -and $refs) {
                    $refNames = $refs | ForEach-Object {
                        if ($_ -match 'refs/heads/(.+)$') { $matches[1] }
                    } | Where-Object { $_ }
                    $remoteHighest = Get-HighestNumberFromNames -Names $refNames
                    if ($remoteHighest -gt $highest) { $highest = $remoteHighest }
                }
            }
        }
    } catch {
        Write-Verbose "Could not query remote refs: $_"
    }
    return $highest
}

function Get-HighestNumberFromMergedSpecs {
    # Highest sequential spec number already merged into the remote default
    # branch. Feature branches are usually deleted after merge, so a
    # branch-only scan misses these and reissues their numbers.
    try {
        $remotes = @(git remote 2>$null)
        if ($remotes.Count -eq 0) { return 0 }
        $remote = ($remotes | Where-Object { $_ -eq 'origin' } | Select-Object -First 1)
        if (-not $remote) { $remote = $remotes[0] }

        # Resolve the remote default branch: local symref first, live query second.
        $defaultBranch = ''
        $symref = git symbolic-ref "refs/remotes/$remote/HEAD" 2>$null
        if ($LASTEXITCODE -eq 0 -and $symref) {
            $defaultBranch = (($symref | Select-Object -First 1) -replace "^refs/remotes/$remote/", '').Trim()
        }
        if (-not $defaultBranch) {
            $env:GIT_TERMINAL_PROMPT = '0'
            $headLines = git ls-remote --symref $remote HEAD 2>$null
            $headOk = ($LASTEXITCODE -eq 0)
            $env:GIT_TERMINAL_PROMPT = $null
            if ($headOk -and $headLines) {
                foreach ($line in $headLines) {
                    if ($line -match '^ref: refs/heads/(\S+)\s+HEAD$') {
                        $defaultBranch = $matches[1]
                        break
                    }
                }
            }
        }
        if (-not $defaultBranch) { return 0 }

        # Refresh just the default branch (also freshens the remote-tracking
        # ref), then scan its specs/ tree. Offline/auth failures degrade to
        # the tracking ref we already have, or to 0 when there is none.
        $env:GIT_TERMINAL_PROMPT = '0'
        git fetch --quiet $remote $defaultBranch 2>$null | Out-Null
        $env:GIT_TERMINAL_PROMPT = $null
        $ref = "$remote/$defaultBranch"
        git rev-parse --verify --quiet $ref 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $ref = 'FETCH_HEAD'
            git rev-parse --verify --quiet $ref 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) { return 0 }
        }
        $entries = git ls-tree --name-only $ref -- specs/ 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $entries) { return 0 }
        $dirNames = @($entries | ForEach-Object { ($_ -split '/')[-1] })
        return Get-HighestNumberFromNames -Names $dirNames
    } catch {
        Write-Verbose "Could not scan merged specs on the remote default branch: $_"
        return 0
    }
}

function Get-HighestSpecNumber {
    # Remote-aware highest spec number: local specs/ directories, local and
    # remote branches, live remote heads, and spec directories merged into the
    # remote default branch. A local-only specs/ scan misses numbers claimed
    # by parallel sessions or merged PRs and causes duplicate numbers.
    # NOTE: this diverges from upstream spec-kit's local-only scan; keep in
    # sync with .specify/extensions/git/scripts/*/create-new-feature-branch.*.
    param(
        [string]$SpecsDir,
        [switch]$NoRemote
    )

    [long]$highest = Get-HighestNumberFromSpecs -SpecsDir $SpecsDir
    if ($NoRemote) { return $highest }

    $hasGit = $false
    try {
        git rev-parse --is-inside-work-tree 2>$null | Out-Null
        $hasGit = ($LASTEXITCODE -eq 0)
    } catch { }
    if (-not $hasGit) { return $highest }

    foreach ($candidate in @(
        (Get-HighestNumberFromBranches),
        (Get-HighestNumberFromRemoteRefs),
        (Get-HighestNumberFromMergedSpecs)
    )) {
        if ($candidate -gt $highest) { $highest = $candidate }
    }
    return $highest
}

function Test-SpecPrefixInUse {    param(
        [string]$SpecsDir,
        [string]$FeatureNum
    )

    if (-not (Test-Path -LiteralPath $SpecsDir -PathType Container)) {
        return $false
    }

    return $null -ne (Get-ChildItem -LiteralPath $SpecsDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "$FeatureNum-*" } |
        Select-Object -First 1)
}

function ConvertTo-CleanBranchName {
    param([string]$Name)

    return $Name.ToLower() -replace '[^a-z0-9]', '-' -replace '-{2,}', '-' -replace '^-', '' -replace '-$', ''
}

function Get-FittedBranchName {
    param(
        [string]$FeatureNum,
        [string]$BranchSuffix
    )

    $fittedName = "$FeatureNum-$BranchSuffix"
    if ($fittedName.Length -gt $maxBranchLength) {
        $prefixLength = $FeatureNum.Length + 1
        $maxSuffixLength = $maxBranchLength - $prefixLength
        $truncatedSuffix = $BranchSuffix.Substring(0, [Math]::Min($BranchSuffix.Length, $maxSuffixLength))
        $truncatedSuffix = $truncatedSuffix -replace '-$', ''
        $fittedName = "$FeatureNum-$truncatedSuffix"
    }

    return $fittedName
}
# Load common functions (includes Get-RepoRoot and Resolve-Template)
. "$PSScriptRoot/common.ps1"

# Use common.ps1 functions which prioritize .specify
$repoRoot = Get-RepoRoot

Set-Location $repoRoot

$specsDir = Join-Path $repoRoot 'specs'
if (-not $DryRun) {
    New-Item -ItemType Directory -Path $specsDir -Force | Out-Null
}

# Function to generate branch name with stop word filtering and length filtering
function Get-BranchName {
    param([string]$Description)

    # Common stop words to filter out
    $stopWords = @(
        'i', 'a', 'an', 'the', 'to', 'for', 'of', 'in', 'on', 'at', 'by', 'with', 'from',
        'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must', 'shall',
        'this', 'that', 'these', 'those', 'my', 'your', 'our', 'their',
        'want', 'need', 'add', 'get', 'set'
    )

    # Convert to lowercase and extract words (alphanumeric only)
    $cleanName = $Description.ToLower() -replace '[^a-z0-9\s]', ' '
    $words = $cleanName -split '\s+' | Where-Object { $_ }

    # Filter words: remove stop words and words shorter than 3 chars (unless they're uppercase acronyms in original)
    $meaningfulWords = @()
    foreach ($word in $words) {
        # Skip stop words
        if ($stopWords -contains $word) { continue }

        # Keep words that are length >= 3 OR appear as uppercase in original (likely acronyms)
        if ($word.Length -ge 3) {
            $meaningfulWords += $word
        } elseif ($Description -cmatch "\b$($word.ToUpper())\b") {
            # Keep short words only if they appear as uppercase in original (likely
            # acronyms). Use -cmatch so the comparison is case-sensitive, matching the
            # bash script's case-sensitive grep; -match would be case-insensitive and
            # would keep every short word.
            $meaningfulWords += $word
        }
    }

    # If we have meaningful words, use first 3-4 of them
    if ($meaningfulWords.Count -gt 0) {
        $maxWords = if ($meaningfulWords.Count -eq 4) { 4 } else { 3 }
        $result = ($meaningfulWords | Select-Object -First $maxWords) -join '-'
        return $result
    } else {
        # Fallback to original logic if no meaningful words found
        $result = ConvertTo-CleanBranchName -Name $Description
        $fallbackWords = ($result -split '-') | Where-Object { $_ } | Select-Object -First 3
        return [string]::Join('-', $fallbackWords)
    }
}

# Generate branch name
if ($ShortName) {
    # Use provided short name, just clean it up
    $branchSuffix = ConvertTo-CleanBranchName -Name $ShortName
} else {
    # Generate from description with smart filtering
    $branchSuffix = Get-BranchName -Description $featureDesc
}

# Treat an explicit empty string as omitted, matching the bash and Python twins.
$hasNumber = $PSBoundParameters.ContainsKey('Number') -and $Number -ne ''

# Warn if -Number and -Timestamp are both specified.
if ($Timestamp -and $hasNumber) {
    [Console]::Error.WriteLine("[specify] Warning: -Number is ignored when -Timestamp is used")
    $Number = ''
}

# Determine branch prefix
if ($Timestamp) {
    $featureNum = Get-Date -Format 'yyyyMMdd-HHmmss'
    $branchName = "$featureNum-$branchSuffix"
} else {
    # Determine branch number from existing feature directories. Auto-detect only
    # when -Number was not supplied; an explicit value (including 0) is honored,
    # matching the bash twin's `[ -z "$BRANCH_NUMBER" ]` check.
    [long]$resolvedNumber = 0
    if (-not $hasNumber) {
        $highestNumber = Get-HighestSpecNumber -SpecsDir $specsDir -NoRemote:$NoRemote
        if ($highestNumber -eq [long]::MaxValue) {
            Write-Error "Error: feature number must be between 0 and $([long]::MaxValue), got '9223372036854775808'"
            exit 1
        }
        $resolvedNumber = $highestNumber + 1
    } elseif ($Number -notmatch '^[0-9]+$') {
        Write-Error "Error: -Number must be an unsigned integer, got '$Number'"
        exit 1
    } elseif (-not [long]::TryParse($Number, [ref]$resolvedNumber)) {
        Write-Error "Error: -Number must be between 0 and $([long]::MaxValue), got '$Number'"
        exit 1
    }

    $featureNum = ('{0:000}' -f $resolvedNumber)

    # Treat an explicit number as a preference when its prefix is already used
    # by a feature directory. Auto-detected numbers are already conflict-free.
    $specConflict = $false
    if ($hasNumber -and (Test-Path -LiteralPath $specsDir -PathType Container)) {
        $requestedBranchName = Get-FittedBranchName -FeatureNum $featureNum -BranchSuffix $branchSuffix
        $requestedDir = Join-Path $specsDir $requestedBranchName
        if (-not $AllowExistingBranch -or -not (Test-Path -LiteralPath $requestedDir -PathType Container)) {
            $specConflict = Test-SpecPrefixInUse -SpecsDir $specsDir -FeatureNum $featureNum
        }
    }

    if ($specConflict) {
        $requestedNum = $featureNum
        $highestNumber = Get-HighestSpecNumber -SpecsDir $specsDir -NoRemote:$NoRemote
        $resolvedNumber = $highestNumber
        do {
            if ($resolvedNumber -eq [long]::MaxValue) {
                Write-Error "Error: feature number must be between 0 and $([long]::MaxValue), got '9223372036854775808'"
                exit 1
            }
            $resolvedNumber++
            $featureNum = ('{0:000}' -f $resolvedNumber)
        } while (Test-SpecPrefixInUse -SpecsDir $specsDir -FeatureNum $featureNum)
        [Console]::Error.WriteLine("[specify] Warning: -Number $requestedNum conflicts with an existing spec directory; using $featureNum instead")
    }

}

# GitHub enforces a 244-byte limit on branch names
# Validate and truncate if necessary
$originalBranchName = "$featureNum-$branchSuffix"
$branchName = Get-FittedBranchName -FeatureNum $featureNum -BranchSuffix $branchSuffix
if ($branchName -ne $originalBranchName) {
    [Console]::Error.WriteLine("[specify] Warning: Branch name exceeded GitHub's 244-byte limit")
    [Console]::Error.WriteLine("[specify] Original: $originalBranchName ($($originalBranchName.Length) bytes)")
    [Console]::Error.WriteLine("[specify] Truncated to: $branchName ($($branchName.Length) bytes)")
}

$featureDir = Join-Path $specsDir $branchName
$specFile = Join-Path $featureDir 'spec.md'

if (-not $DryRun) {
    if ((Test-Path -LiteralPath $featureDir -PathType Container) -and -not $AllowExistingBranch) {
        if ($Timestamp) {
            Write-Error "Error: Feature directory '$featureDir' already exists. Rerun to get a new timestamp or use a different -ShortName."
        } else {
            Write-Error "Error: Feature directory '$featureDir' already exists. Please use a different feature name or specify a different number with -Number."
        }
        exit 1
    }

    $needsSpec = -not (Test-Path -PathType Leaf $specFile)
    $content = $null
    if ($needsSpec) {
        $content = Resolve-TemplateContent -TemplateName 'spec-template' -RepoRoot $repoRoot
    }

    New-Item -ItemType Directory -Path $featureDir -Force | Out-Null

    if ($needsSpec) {
        if ($null -ne $content) {
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($specFile, $content, $utf8NoBom)
        } else {
            # Match the bash twin (create-new-feature.sh): warn on stderr that no
            # spec template was found before creating an empty spec file, so the
            # missing-template signal is not silently swallowed on Windows.
            [Console]::Error.WriteLine("Warning: Spec template not found; created empty spec file")
            New-Item -ItemType File -Path $specFile -Force | Out-Null
        }
    }

    # Persist to .specify/feature.json so downstream commands can find the feature
    Save-FeatureJson -RepoRoot $repoRoot -FeatureDirectory $featureDir

    # Set environment variables for the current session
    $env:SPECIFY_FEATURE = $branchName
    $env:SPECIFY_FEATURE_DIRECTORY = $featureDir

    $quotedBranchName = "'" + $branchName.Replace("'", "''") + "'"
    $quotedFeatureDir = "'" + $featureDir.Replace("'", "''") + "'"
    $featureAssignment = '$env:SPECIFY_FEATURE = ' + $quotedBranchName
    $directoryAssignment = '$env:SPECIFY_FEATURE_DIRECTORY = ' + $quotedFeatureDir
    [Console]::Error.WriteLine("# To persist: $featureAssignment")
    [Console]::Error.WriteLine("#              $directoryAssignment")
}

if ($Json) {
    $obj = [PSCustomObject]@{
        BRANCH_NAME = $branchName
        SPEC_FILE = $specFile
        FEATURE_NUM = $featureNum
    }
    if ($DryRun) {
        $obj | Add-Member -NotePropertyName 'DRY_RUN' -NotePropertyValue $true
    }
    $obj | ConvertTo-Json -Compress
} else {
    Write-Output "BRANCH_NAME: $branchName"
    Write-Output "SPEC_FILE: $specFile"
    Write-Output "FEATURE_NUM: $featureNum"
    if (-not $DryRun) {
        Write-Output "# To persist in your shell: $featureAssignment"
        Write-Output "#                           $directoryAssignment"
    }
}

# install-atomgit.ps1 - wiseflow one-click install script (Windows, prebuilt tarball route, atomgit mirror)
#
# Difference from install.ps1: this script uses the atomgit mirror (tarball via atomgit.com ->
# GitCode CDN, tag resolution via api.atomgit.com/api/v5), bypassing GitHub; suitable for networks
# inside mainland China. GitHub-accessible users should use install.ps1 (GitHub direct) instead.
#   To be friendly to `irm | iex` (so a one-liner works for beginners), the [CmdletBinding]param()
#   header is removed; all optional params go through environment variables:
#     $env:XIAOBEI_HOME        Program directory override (default ~\xiaobei)
#     $env:XIAOBEI_TAG         Specify a release tag (default pulls latest)
#     $env:XIAOBEI_TARBALL     Path to a locally downloaded tarball, skips download
#     $env:XIAOBEI_FORCE       =1 force overwrite existing runtime data (~\.openclaw)
#     $env:XIAOBEI_SKIP_BIND   =1 skip the WeChat scan-to-bind step at the end
#     $env:XIAOBEI_SKIP_BROWSER=1 skip camoufox-cli browser binary (smoke/CI)
#     $env:XIAOBEI_NO_PROMPT   =1 skip all interactive prompts (CI/automation)
#
# Usage (PowerShell, requires Git Bash or WSL):
#   irm https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.ps1 | iex
#   # or locally:
#   powershell -ExecutionPolicy Bypass -File install-atomgit.ps1
#
# WARNING: this file MUST be kept UTF-8 **without BOM**: under `irm | iex`, irm does not strip
#   the BOM, and iex treats the 3 BOM bytes as the first chars of a command name, so the first
#   line `﻿#` is parsed as an unknown command and errors (though it does not block the install).
#   The local `powershell -File` scenario also works fine without BOM (PowerShell 5.1+ defaults
#   to UTF-8 for parsing). All comments in this file are in English (ASCII) to avoid GBK/UTF-8
#   mojibake parsing errors under Windows PowerShell 5.1 with a non-BOM file.
#
# Structurally identical to install.sh (Plan B slim tarball):
#   1. Pull xiaobei-{tag}-win-x64.tar.gz (atomgit CDN; Windows bsdtar natively supports gzip, no
#      need to install zstd)
#   2. Extract to $XIAOBEI_HOME (default $env:USERPROFILE\xiaobei, the program directory)
#   3. portable node + pnpm install --prod --frozen-lockfile (under openclaw\)
#   4. pip install --user (python deps for skills; only runs if python is present)
#   5. Place config-templates\openclaw.json -> $OPENCLAW_HOME\openclaw.json + prefill WeChat binding
#   6. setup-crew.sh (requires bash: Git Bash or WSL; if absent, warn and skip; user can run it
#      manually later)
#   7. camoufox-cli: .cmd shim + camoufox-cli install downloads Firefox
#   8. openclaw-weixin plugin: openclaw plugins install ... --pin (npmmirror)
#      idempotency by VERSION: skip only when installed == pin; --force upgrade otherwise
#   9. Interactive prompt for AWK_API_KEY -> write daemon.env + setx user env var -> attempt
#      openclaw daemon install
#
# Directory responsibilities: $XIAOBEI_HOME (~\xiaobei) = program; $OPENCLAW_HOME (~\.openclaw)
#   = runtime data.
# Windows native wrapper: $XIAOBEI_HOME\bin\openclaw.cmd (WSL/Git Bash users can also use bin\openclaw).

$ErrorActionPreference = "Stop"

# --- Constants / directories ---
# atomgit mirror constants (host/version differ from GitHub, do not depend on runtime switches):
#   tarball direct host = atomgit.com (redirects to a signed file-cdn.gitcode.com CDN; anonymous
#                          GET works, ~140MB)
#   latest tag resolution goes through api.atomgit.com/api/v5 (NOT Gitea v1; both host and version
#                          differ)
$Repo = "wiseflow/xiaobei"
$AtomgitMirror = "https://atomgit.com/wiseflow/xiaobei"
$AtomgitApi = "https://api.atomgit.com/api/v5/repos/wiseflow/xiaobei"

$Root = if ($env:XIAOBEI_HOME) { $env:XIAOBEI_HOME } else { Join-Path $env:USERPROFILE "xiaobei" }
$OpenclawHome = if ($env:OPENCLAW_HOME) { $env:OPENCLAW_HOME } else { Join-Path $env:USERPROFILE ".openclaw" }

# Behavior switches (env vars, =1 to enable).
# IMPORTANT: use $script: scope so these are visible inside functions (Place-Config,
# Main, etc.). A bare $Force at the top level creates a *script-scope* variable that
# functions CANNOT see - they'd read a local $null instead, so XIAOBEI_FORCE=1 etc.
# would silently never take effect (a real bug observed in testing).
$script:Force       = ($env:XIAOBEI_FORCE         -eq "1" -or $env:XIAOBEI_FORCE         -eq "true")
$script:SkipBind    = ($env:XIAOBEI_SKIP_BIND    -eq "1" -or $env:XIAOBEI_SKIP_BIND    -eq "true")
$script:SkipBrowser = ($env:XIAOBEI_SKIP_BROWSER -eq "1" -or $env:XIAOBEI_SKIP_BROWSER -eq "true")
$script:NoPrompt    = ($env:XIAOBEI_NO_PROMPT   -eq "1" -or $env:XIAOBEI_NO_PROMPT   -eq "true")

$NodeExe   = Join-Path $Root "tools\node\node.exe"
$NpmCmd    = Join-Path $Root "tools\node\npm.cmd"
$PnpmMjs   = Join-Path $Root "tools\pnpm\bin\pnpm.mjs"
$ClawCmd   = Join-Path $Root "bin\openclaw.cmd"
$ClawSh    = Join-Path $Root "bin\openclaw"

function Write-Stage([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok([string]$msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg)  { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg)   { Write-Host "  [X]  $msg" -ForegroundColor Red }

# Run a native command and echo stdout+stderr line by line. pip/npm/camoufox-cli/openclaw normally
# write progress and warnings to stderr, and the $ErrorActionPreference="Stop" at the top of this
# script would treat stderr lines merged via 2>&1 as terminating errors, throwing
# NativeCommandError/RemoteException (a user's Windows run actually got stuck at pip install this
# way). Here we temporarily switch to Continue to run the native command; $LASTEXITCODE is still
# used by the caller to judge success/failure.
function Invoke-Streamed([scriptblock]$sb) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $sb 2>&1 | ForEach-Object { Write-Host "    $_" } }
    finally { $ErrorActionPreference = $prev }
}

# Same as Invoke-Streamed, but merges stdout+stderr into a single string and returns it (for callers
# that need to -match against the output). `2>$null` under Windows PowerShell 5.1 + Stop does not
# suppress a .cmd's stderr and still throws NativeCommandError; using Continue + 2>&1 is stable.
function Capture-Streamed([scriptblock]$sb) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { return (& $sb 2>&1 | Out-String) }
    finally { $ErrorActionPreference = $prev }
}

# --- 1. Resolve latest release tag (atomgit v5 API) ---
function Resolve-Tag {
    if ($env:XIAOBEI_TAG) { return $env:XIAOBEI_TAG }
    try {
        $rel = Invoke-RestMethod "$AtomgitApi/releases/latest" -Headers @{ "User-Agent" = "xiaobei-install" }
        if ($rel.tag_name) { return $rel.tag_name }
    } catch { Write-Warn "atomgit v5 API fetch failed, please set `$env:XIAOBEI_TAG=` manually and re-run" }
    throw "unable to resolve the latest release tag (atomgit v5 API)"
}

# --- 2. Download tarball (atomgit CDN) ---
# Version-level cache: same tag + plat re-uses ~/.xiaobei/cache/<asset>,
# skipping the 120MB re-download on rerun (incl. failed retry).
# Atomic write: download to <cached>.part first, then Move-Item -Force to <cached>,
# so a broken network never leaves a half-written file that the next run would
# mistake for a complete cache hit.
function Download-Tarball([string]$tag) {
    $asset = "xiaobei-$tag-win-x64.tar.gz"
    if ($env:XIAOBEI_TARBALL -and (Test-Path $env:XIAOBEI_TARBALL)) {
        Write-Ok "using local tarball: $env:XIAOBEI_TARBALL"
        return $env:XIAOBEI_TARBALL
    }

    $cacheDir = if ($env:XIAOBEI_CACHE_DIR) { $env:XIAOBEI_CACHE_DIR } else { Join-Path $env:USERPROFILE ".xiaobei\cache" }
    $cached = Join-Path $cacheDir $asset

    if (Test-Path $cached -PathType Leaf) {
        Write-Ok "using cached tarball: $cached"
        return $cached
    }

    $url = "$AtomgitMirror/releases/download/$tag/$asset"
    Write-Host "  downloading $url"
    New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
    $part = "$cached.part"
    if (Test-Path $part) { Remove-Item $part -Force }
    try {
        Invoke-WebRequest -Uri $url -OutFile $part -Headers @{ "User-Agent" = "xiaobei-install" }
        Move-Item -Path $part -Destination $cached -Force
    } catch {
        if (Test-Path $part) { Remove-Item $part -Force }
        throw "download failed: $url`n$($_.Exception.Message)"
    }
    return $cached
}

# --- 3. Extract ---
function Extract-Tarball([string]$tarball) {
    if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
        throw "tar not found (Windows 10 1803+ ships bsdtar; please upgrade Windows or install Git Bash)"
    }
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    Write-Host "  extracting to $Root"
    & tar -xzf $tarball -C $Root
    if ($LASTEXITCODE -ne 0) { throw "tar extraction failed (exit $LASTEXITCODE)" }
}

# --- 4. pnpm install --prod ---
function Install-Deps {
    Write-Stage "Installing dependencies (pnpm install --prod)"
    $openclawDir = Join-Path $Root "openclaw"
    if (-not (Test-Path $NodeExe)) { throw "portable node not found: $NodeExe" }
    Push-Location $openclawDir
    try {
        # postinstall subprocesses (esbuild/protobufjs etc.) look up node via PATH; the target
        # machine most likely has no global Node installed ('node' is not recognized, observed in
        # practice), so we prepend the portable node directory to PATH.
        $env:PATH = "$(Split-Path $NodeExe);$env:PATH"
        # pnpm 11 does not honor the npm_config_registry env var (in practice it still hits
        # registry.npmjs.org), so we pass an explicit --registry.
        $env:npm_config_registry = "https://registry.npmmirror.com"
        & $NodeExe $PnpmMjs install --prod --frozen-lockfile --registry https://registry.npmmirror.com
        if ($LASTEXITCODE -ne 0) { throw "pnpm install failed (exit $LASTEXITCODE)" }
        Write-Ok "deps installed"
    } finally { Pop-Location }
}

# --- 5. python skill deps ---
function Install-PythonDeps {
    Write-Stage "Installing python skill deps"
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { Write-Warn "python not found, skipping skill python deps"; return }
    $reqs = @()
    $reqs += Get-ChildItem -Path (Join-Path $Root "skills") -Filter "requirements.txt" -Recurse -ErrorAction SilentlyContinue
    $reqs += Get-ChildItem -Path (Join-Path $Root "crews") -Filter "requirements.txt" -Recurse -ErrorAction SilentlyContinue
    $reqs += Get-ChildItem -Path $Root -Filter "requirements.txt" -ErrorAction SilentlyContinue
    $reqs = $reqs | Select-Object -ExpandProperty FullName -Unique
    if (-not $reqs) { Write-Ok "no requirements.txt"; return }
    # Each line is passed as a pip command-line argument (not via -r file), so inline comments must
    # be stripped (pip only recognizes comments inside a requirements file; `Pillow # desc` passed
    # as an arg directly errors with Invalid requirement). The file is UTF-8; we explicitly specify
    # the encoding to prevent Chinese comments from being misread as ANSI and producing garbled args.
    $merged = ($reqs | ForEach-Object { Get-Content $_ -Encoding UTF8 -ErrorAction SilentlyContinue } |
        ForEach-Object { ($_ -replace '#.*$', '').Trim() } |
        Where-Object { $_ } | Sort-Object -Unique)
    if (-not $merged) { Write-Ok "no python deps"; return }
    Invoke-Streamed { python -m pip install --user $merged }
    if ($LASTEXITCODE -ne 0) { Write-Warn "pip install returned non-zero; you can manually install the skills' python deps later" }
    else { Write-Ok "python deps installed" }
}

# --- 6. Place config template (mirrors install.sh place_config_template) ---
# The template already pre-populates channels.openclaw-weixin / bindings / session.dmScope; we no
# longer mutate it at runtime (the sh version once broke the plugins top-level via runtime mutation,
# causing "Invalid input"; that mutation has been removed in parallel here).
# Health check: if the existing config is missing models/agents.defaults (most likely a minimal config
# auto-created by `openclaw plugins install` when Install-WeixinPlugin ran first, or by openclaw's
# first launch), back it up and overwrite with the template; otherwise channels/bindings would be
# missing forever and xiaobei could never start.
function Place-Config {
    Write-Stage "Placing config template"
    New-Item -ItemType Directory -Force -Path $OpenclawHome | Out-Null
    $cfg = Join-Path $OpenclawHome "openclaw.json"
    $tmpl = Join-Path $Root "config-templates\openclaw.json"
    if (-not (Test-Path $tmpl)) { Write-Err "config template missing: $tmpl (tarball corrupted?)"; return }

    $needPlace = $false; $reason = ""
    if (-not (Test-Path $cfg)) { $needPlace = $true; $reason = "not present" }
    elseif ($script:Force) { $needPlace = $true; $reason = "XIAOBEI_FORCE=1" }
    else {
        try {
            # Must explicitly read as UTF-8: openclaw writes its config as UTF-8 without BOM, while
            # PS 5.1's Get-Content defaults to the ANSI code page; a \\ escape next to a Chinese
            # path can get swallowed by a double-byte char, causing a valid config to be misjudged
            # as "parse failed" and overwritten (observed in practice).
            $j = [System.IO.File]::ReadAllText($cfg) | ConvertFrom-Json -ErrorAction Stop
            if (-not ($j.models -and $j.agents -and $j.agents.defaults)) { $needPlace = $true; $reason = "missing models/agents.defaults (likely minimized)" }
        } catch { $needPlace = $true; $reason = "parse failed" }
    }
    if ($needPlace) {
        if (Test-Path $cfg) {
            $bak = "$cfg.bak.$([int][double]::Parse((Get-Date -UFormat %s)))"
            Copy-Item $cfg $bak
            Write-Warn "openclaw.json $reason -> overwriting with template (old file backed up to $bak)"
        }
        Copy-Item $tmpl $cfg -Force
        Write-Ok "placed openclaw.json template"
    } else {
        Write-Ok "openclaw.json already present and healthy (has models + agents.defaults), keeping"
    }

    # Resolve the ${XIAOBEI_HOME} env ref inside plugins.load.paths to an absolute path, to avoid a
    # "plugin path not found" false alarm when the CLI context lacks XIAOBEI_HOME; AWK_API_KEY is a
    # secret so its env ref is left untouched. This is a file-level replacement (the ${XIAOBEI_HOME}
    # template token only appears in plugins.load.paths); inside a JSON string a backslash is an
    # escape char, so we normalize paths to forward slashes. Idempotent: a no-op if already resolved.
    $raw = [System.IO.File]::ReadAllText($cfg)
    if ($raw.Contains('${XIAOBEI_HOME}')) {
        $rootFwd = $Root -replace '\\', '/'
        [System.IO.File]::WriteAllText($cfg, $raw.Replace('${XIAOBEI_HOME}', $rootFwd), [System.Text.UTF8Encoding]::new($false))
        Write-Ok "resolved XIAOBEI_HOME refs -> $rootFwd"
    }
}

# --- 7. setup-crew (requires bash) ---
# Find a genuinely usable bash: prefer Git Bash (it handles C:/ style paths well); the bash on PATH
# might be C:\Windows\system32\bash.exe (the WSL launcher) which errors out immediately when no distro
# is installed, and WSL bash does not convert Windows path arguments either, so neither can be used
# directly. Each candidate is actually tested with `bash -c echo` before being accepted.
function Find-WorkingBash {
    $candidates = @()
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        $gitRoot = Split-Path (Split-Path $git.Source)
        $candidates += (Join-Path $gitRoot "bin\bash.exe")
        $candidates += (Join-Path $gitRoot "usr\bin\bash.exe")
    }
    $candidates += "$env:ProgramFiles\Git\bin\bash.exe"
    $candidates += "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
    $inPath = Get-Command bash -ErrorAction SilentlyContinue
    # The system32 WSL launcher goes last (only used as a fallback when it is available and no Git
    # Bash exists).
    if ($inPath) { $candidates += $inPath.Source }
    foreach ($b in $candidates) {
        if ($b -and (Test-Path $b)) {
            $out = Capture-Streamed { & $b -c "echo __bash_ok__" }
            if ($out -match "__bash_ok__") { return $b }
        }
    }
    return $null
}

function Run-SetupCrew {
    Write-Stage "Setting up crew templates (needs bash)"
    $sh = Join-Path $Root "scripts\setup-crew.sh"
    if (-not (Test-Path $sh)) { Write-Warn "setup-crew.sh is not inside the tarball, skipping"; return }
    $bashExe = Find-WorkingBash
    if (-not $bashExe) {
        Write-Warn "no usable bash found (setup-crew.sh is a bash script; note system32\bash.exe is the WSL launcher and is unusable without a distro installed)"
        Write-Host "    Please install Git Bash (https://git-scm.com) or a WSL distro, then run manually:"
        Write-Host "      set OPENCLAW_HOME=$OpenclawHome"
        Write-Host "      set XIAOBEI_BIN_DIR=$(Join-Path $Root 'bin')"
        Write-Host "      bash `"$sh`""
        return
    }
    Write-Host "  bash: $bashExe"
    # bash does not understand backslashes (it would treat them as escapes), so we pass forward-slash
    # paths to setup-crew.sh.
    # WARNING: use OPENCLAW_STATE_DIR rather than OPENCLAW_HOME: the engine's resolveStateDir treats
    # OPENCLAW_HOME as a homedir and then appends /.openclaw (see openclaw/src/config/paths.ts); if
    # OPENCLAW_HOME is set to ~/.openclaw this produces a nested ~/.openclaw/.openclaw layer, and all
    # subsequent weixin/gateway CLI calls write config/npm/openclaw.sqlite into that nested layer while
    # the correct outer path stays empty (a real bug observed on a local machine). OPENCLAW_STATE_DIR
    # is treated by the engine as a direct state dir and is not appended to.
    $env:OPENCLAW_STATE_DIR = ($OpenclawHome -replace '\\', '/')
    $env:XIAOBEI_BIN_DIR = ((Join-Path $Root "bin") -replace '\\', '/')
    # setup-crew.sh uses OPENCLAW_HOME internally to resolve CONFIG_PATH (it does NOT read
    # OPENCLAW_STATE_DIR), so we must explicitly pass a forward-slash path; otherwise bash falls back
    # to $HOME/.openclaw, and under Git Bash's MSYS path conversion + a Chinese username this yields a
    # bogus path like C:\c\Users\<garbled>\.openclaw (ENOENT).
    $env:OPENCLAW_HOME = ($OpenclawHome -replace '\\', '/')
    # Git Bash's MSYS2 layer defaults `ln -s` to `cp -r` (real copy), not a true symlink. setup-crew.sh
    # uses `ln -s` to symlink crew skills into ~/.openclaw/workspace-<id>/skills/, so without this flag
    # Windows users end up with real folders instead of links (edits in the repo don't propagate, and
    # re-runs copy over stale copies). MSYS=winsymlinks:nativestrict makes `ln -s` create real NTFS
    # symlinks (requires Developer Mode on Win10+, or admin). Falls back to copies if neither is
    # available, which is the previous behavior (no regression).
    $env:MSYS = "winsymlinks:nativestrict"
    Invoke-Streamed { & $bashExe ($sh -replace '\\', '/') }
    # After setup-crew.sh finishes, clear OPENCLAW_HOME so subsequent install phases (gateway/daemon)
    # do not inherit this value - the engine would treat OPENCLAW_HOME as a homedir and append
    # /.openclaw, producing a nested layer.
    Remove-Item Env:OPENCLAW_HOME -ErrorAction SilentlyContinue
    Remove-Item Env:MSYS -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) { Write-Warn "setup-crew.sh exited non-zero (you can manually re-run with --force later to fix)" }
    else { Write-Ok "crew templates set up" }
}

# --- 7c. Sync global skills -> ~/.openclaw/skills ---
# On linux/macOS this is done by apply-addons.sh (which symlinks the repo's skills/ into
# ~/.openclaw/skills so the openclaw skill loader picks them up). The Windows route does not run
# apply-addons.sh, so we mirror that logic here: create a true NTFS symlink ~/.openclaw/skills ->
# <repo>/skills. Idempotent: if the target is already a symlink pointing to the right repo path,
# this is a no-op; if it's a stale real directory (from an old copy-based install), we warn and
# leave it untouched rather than risk deleting user edits.
function Sync-GlobalSkills {
    Write-Stage "Syncing global skills -> ~/.openclaw/skills"
    $src = Join-Path $Root "skills"
    if (-not (Test-Path $src)) { Write-Ok "no global skills dir in repo, skipping"; return }
    $dest = Join-Path $OpenclawHome "skills"
    $srcFwd = ($src -replace '\\', '/')

    if (Test-Path $dest) {
        $item = Get-Item $dest -Force
        if ($item.LinkType -eq 'SymbolicLink' -and $item.Target -and (($item.Target -replace '\\', '/') -ieq $srcFwd)) {
            Write-Ok "global skills symlink already correct"
            return
        }
        if ($item.LinkType -eq 'SymbolicLink') {
            Remove-Item $dest -Force -Recurse
        } else {
            Write-Warn "$dest already exists as a real directory (likely from an old install); leaving untouched to avoid overwriting user edits"
            Write-Host "    To switch to a symlink: delete $dest, then re-run install" -ForegroundColor Yellow
            return
        }
    }

    try {
        New-Item -ItemType SymbolicLink -Path $dest -Target $src -ErrorAction Stop | Out-Null
        Write-Ok "global skills symlinked -> $src"
    } catch {
        Write-Warn "failed to create symlink $dest -> $src ($_)"
        Write-Host "    This usually means Developer Mode is off and the shell is not elevated." -ForegroundColor Yellow
        Write-Host "    Either enable Windows Developer Mode, or run this shell as Administrator." -ForegroundColor Yellow
        Write-Host "    Falling back to a copy (skills will not auto-update from the repo until you re-run install)." -ForegroundColor Yellow
        Copy-Item -Path $src -Destination $dest -Recurse -Force
        Write-Ok "global skills copied (fallback) -> $dest"
    }
}

# --- 7b. Expose skill wrappers as .cmd shims into ~\.openclaw\bin ---
# Mirrors the .sh route's expose_skill_wrappers + ensure_openclaw_bin_in_path
# (scripts/lib/skill-wrappers.sh). On Windows we cannot rely on symlinks
# (need admin/Developer Mode), so we generate a <skill>.cmd shim per skill
# that forwards to the bundled bash + the skill's <skill>.sh wrapper.
# The shim lives in ~\.openclaw\bin so the agent can call `<skill> <cmd>`
# from anywhere on PATH.
function Expose-SkillWrappers {
    $binDir = Join-Path $OpenclawHome "bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null

    # The bundled bash shipped in the tarball (Git Bash fallback handled below).
    $bashExe = $false
    $bashCandidates = @(
        (Join-Path $Root "tools\git\bin\bash.exe"),
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files\Git\usr\bin\bash.exe"
    )
    foreach ($c in $bashCandidates) { if (Test-Path $c) { $bashExe = $c; break } }
    if (-not $bashExe) { $bashExe = (Get-Command bash.exe -ErrorAction SilentlyContinue).Source }
    if (-not $bashExe) {
        Write-Warn "no bash found; cannot expose skill wrappers as .cmd shims"
        return
    }

    $exposed = 0
    $skillsRoots = @((Join-Path $Root "skills"))
    $crewsDir = Join-Path $Root "crews"
    if (Test-Path $crewsDir) {
        $skillsRoots += @(Get-ChildItem -Path $crewsDir -Directory | ForEach-Object {
            Join-Path $_.FullName "skills"
        })
    }
    foreach ($skillsRoot in $skillsRoots) {
        if (-not (Test-Path $skillsRoot)) { continue }
        Get-ChildItem -Path $skillsRoot -Directory | ForEach-Object {
            $wrapperDirs = @($_)
            $toolsDir = Join-Path $_.FullName "tools"
            if (Test-Path $toolsDir) {
                $wrapperDirs += @(Get-ChildItem -Path $toolsDir -Directory)
            }
            foreach ($wrapperDir in $wrapperDirs) {
                $skillName = $wrapperDir.Name
                if ($skillName.StartsWith("_")) { continue }  # skip _shared etc
                $wrapper = Join-Path $wrapperDir.FullName "$skillName.sh"
                if (-not (Test-Path $wrapper)) { continue }
                $shim = Join-Path $binDir "$skillName.cmd"
                $wrapperFwd = ($wrapper -replace '\\', '/')
                $bashFwd = ($bashExe -replace '\\', '/')
                $body = "@echo off`r`n`"$bashFwd`" `"$wrapperFwd`" %*`r`n"
                $enc = New-Object System.Text.UTF8Encoding($false)
                [System.IO.File]::WriteAllText($shim, $body, $enc)
                $exposed++
            }
        }
    }

    if ($exposed -gt 0) {
        Write-Ok "exposed $exposed skill wrapper(s) -> $binDir"
        # Inject ~\.openclaw\bin into user PATH (idempotent, safe non-truncating way)
        $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
        if ($userPath -notlike "*$binDir*") {
            $newPath = "$binDir;$userPath"
            [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
            Write-Ok "added $binDir to user PATH (takes effect in a new terminal)"
        }
    } else {
        Write-Host "  [i]  no skill wrappers found to expose" -ForegroundColor Yellow
    }
}

# --- 8. camoufox-cli ---
function Install-CamoufoxCli {
    if ($script:SkipBrowser) {
        Write-Host "  [i]  skipping camoufox-cli browser binary (XIAOBEI_SKIP_BROWSER=1); run manually later: camoufox-cli install" -ForegroundColor Yellow
        return
    }
    Write-Stage "Installing camoufox-cli browser"
    $fork = Join-Path $Root "camoufox-cli"
    if (-not (Test-Path $fork)) { Write-Warn "camoufox-cli fork not in tarball: $fork; skipping"; return }
    # Place a camoufox-cli.cmd shim in $Root\bin and prepend it to PATH so the `camoufox-cli install`
    # below can be found.
    $env:PATH = "$(Join-Path $Root 'bin');$(Split-Path $NodeExe);$env:PATH"
    $env:npm_config_registry = "https://registry.npmmirror.com"
    $camoufoxBin = Join-Path $Root "bin\camoufox-cli.cmd"
    $cliJs = Join-Path $fork "dist\cli.js"
    $hasDeps = Test-Path (Join-Path $fork "node_modules\camoufox-js")

    # Runtime deps of the fork: dist is a tsc build, and camoufox-js/playwright-core/pdf-lib are
    # external imports resolved at runtime via the node_modules under the fork directory. The fork
    # shipped in the slim tarball does not carry node_modules.
    if (-not $hasDeps) {
        Push-Location $fork
        try {
            & $NpmCmd install --omit=dev
            if ($LASTEXITCODE -ne 0) { Write-Warn "camoufox-cli fork deps install failed"; return }
        } finally { Pop-Location }
    }

    # Windows does not go through `npm install -g $fork`: when npm installs the fork into
    # $prefix\node_modules it collides with the fork's own source directory (EEXIST: file already
    # exists $Root\camoufox-cli) - Windows npm cannot symlink to the source dir the way Linux does.
    # Instead, mirroring openclaw.cmd, we write a .cmd shim that directly runs
    # node $fork\dist\cli.js; the fork's node_modules is already in place and Node resolves deps
    # upward from cli.js. camoufox-cli's JS uses __dirname to locate its own package root, so the
    # behavior matches a global install.
    if (-not (Test-Path $cliJs)) { Write-Warn "camoufox-cli entry not found: $cliJs; skipping"; return }
    $shimLines = @(
        '@echo off'
        'setlocal'
        'set "HERE=%~dp0.."'
        '"%HERE%\tools\node\node.exe" "%HERE%\camoufox-cli\dist\cli.js" %*'
    )
    Set-Content -Path $camoufoxBin -Value $shimLines -Encoding ASCII
    Write-Ok "camoufox-cli shim written: $camoufoxBin"

    Write-Host "  downloading Firefox binary (first time ~557MB)..."
    Invoke-Streamed { camoufox-cli install }
    if ($LASTEXITCODE -ne 0) { Write-Warn "camoufox-cli install failed; you can run manually later: camoufox-cli install" }
    else { Write-Ok "camoufox-cli ready" }
}

# --- 9. openclaw-weixin plugin ---
# Read the installed openclaw-weixin version; returns $null when unreadable.
# Primary path: `plugins list --json` (fields id / name / version); fallback: the real
# package.json under npm\projects\* (project dir names carry a hash, so glob).
function Get-WeixinInstalledVersion([string]$pkg) {
    # Capture stdout only (mirrors bash 2>/dev/null): stderr noise would break ConvertFrom-Json.
    # EAP must be Continue here - under Stop, `2>$null` on a .cmd still throws
    # NativeCommandError on Windows PowerShell 5.1 (same pitfall as Capture-Streamed above).
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $json = (& $ClawCmd plugins list --json 2>$null | Out-String) }
    finally { $ErrorActionPreference = $prev }
    if ($json) {
        try {
            foreach ($p in ($json | ConvertFrom-Json).plugins) {
                if ($p.id -eq "openclaw-weixin" -or $p.name -eq $pkg) {
                    if ($p.version) { return [string]$p.version }
                    break
                }
            }
        } catch { }
    }
    # Fallback: CLI/JSON unavailable - read the installed package.json directly
    $projRoot = Join-Path $OpenclawHome "npm\projects"
    if (Test-Path $projRoot) {
        $pkgRel = $pkg.Replace("/", "\")
        foreach ($dir in (Get-ChildItem $projRoot -Directory -ErrorAction SilentlyContinue)) {
            $f = Join-Path $dir.FullName "node_modules\$pkgRel\package.json"
            if (-not (Test-Path $f)) { continue }
            try {
                $v = (Get-Content $f -Raw | ConvertFrom-Json).version
                if ($v) { return [string]$v }
            } catch { }
        }
    }
    return $null
}

# Install the openclaw-weixin plugin (the config template pre-populates the channel, but the
# plugin itself needs `openclaw plugins install`). Pin comes from openclaw-weixin.version.json
# in the tarball; registry is npmmirror.
# Idempotency by VERSION, not by name: skip only when installed == pin; installed != pin ->
# `--force` upgrade to pin. (The old logic merely matched the plugin name in `plugins list`
# and returned, so after a pin bump existing installs stayed on the old version forever.)
# --force = "Overwrite an existing installed plugin" (flag exists since 7.1-2). The upgrade
# only replaces the package under npm\projects; login state in $OpenclawHome\openclaw-weixin\
# is untouched, and the update route restarts the gateway afterwards so the new version takes
# effect.
function Install-WeixinPlugin {
    Write-Stage "Installing WeChat plugin"
    if (-not (Test-Path $ClawCmd)) { Write-Warn "openclaw wrapper not found: $ClawCmd; skipping"; return }
    $pkg = "@tencent-weixin/openclaw-weixin"; $ver = "2.4.6"
    $pin = Join-Path $Root "openclaw-weixin.version.json"
    if (Test-Path $pin) {
        try {
            $j = Get-Content $pin -Raw | ConvertFrom-Json
            $pkg = $j.'openclaw-weixin'.package; $ver = $j.'openclaw-weixin'.version
        } catch { Write-Warn "pin file parse failed, using default $pkg@$ver" }
    }
    $env:npm_config_registry = "https://registry.npmmirror.com"
    # Idempotency check: skip only when installed version == pin
    $installed = Get-WeixinInstalledVersion $pkg
    $forceFlag = @()
    if ($installed -and $installed -ceq $ver) { Write-Ok "openclaw-weixin plugin already installed ($ver)"; return }
    if ($installed) {
        Write-Host "  [i]  openclaw-weixin installed $installed, pin $ver -> --force upgrade" -ForegroundColor Yellow
        $forceFlag = @("--force")
    } else {
        $listOut = Capture-Streamed { & $ClawCmd plugins list }
        if ($listOut -match "openclaw-weixin") {
            # Plugin present but version unreadable (CLI/JSON anomaly): force reinstall at pin
            Write-Warn "openclaw-weixin installed but version unreadable; force reinstalling at pin $ver"
            $forceFlag = @("--force")
        }
    }
    $installArgs = @("plugins", "install", "$pkg@$ver", "--pin") + $forceFlag
    $forceHint = if ($forceFlag) { " --force" } else { "" }
    Invoke-Streamed { & $ClawCmd @installArgs }
    if ($LASTEXITCODE -eq 0) { Write-Ok "openclaw-weixin plugin installed ($ver)" }
    else { Write-Warn "plugin install failed; you can run manually later: $ClawCmd plugins install $pkg@$ver --pin$forceHint" }
}

# --- 10. awada local plugin deps (ws + zod) ---
function Install-AwadaPlugin {
    Write-Stage "Installing awada plugin deps"
    $awada = Join-Path $Root "awada"
    if (-not (Test-Path $awada)) { Write-Warn "awada not in tarball: $awada; skipping"; return }
    $hasWs   = Test-Path (Join-Path $awada "node_modules\ws")
    $hasZod  = Test-Path (Join-Path $awada "node_modules\zod")
    if ($hasWs -and $hasZod) { Write-Ok "awada deps already installed"; return }
    $env:npm_config_registry = "https://registry.npmmirror.com"
    Push-Location $awada
    try {
        & $NpmCmd install --omit=dev
        if ($LASTEXITCODE -eq 0) { Write-Ok "awada deps installed" }
        else { Write-Warn "awada deps install failed; you can run manually later: cd $awada ; npm install --omit=dev" }
    } finally { Pop-Location }
}

# --- 10.5 Fix daemon launch-script encoding (workaround for an openclaw upstream bug) ---
# The gateway.cmd / gateway.vbs written out by `openclaw daemon install` are UTF-8 (no BOM), but
# cmd.exe / WScript read script files using the system ANSI code page - so when the install path
# contains non-ASCII chars (e.g. a Chinese username) the path turns into mojibake, node.exe cannot
# be found, and the gateway never starts (observed on a local machine).
# Workaround: replace long paths with their 8.3 short paths (pure ASCII) and rewrite as ASCII; if no
# 8.3 name is available, fall back to writing in the ANSI code page (cmd.exe reads it as ANSI, so the
# encodings line up). Idempotent.
function Repair-GatewayCmd {
    $files = @((Join-Path $OpenclawHome "gateway.cmd"), (Join-Path $OpenclawHome "gateway.vbs"))
    $fso = $null
    foreach ($f in $files) {
        if (-not (Test-Path $f)) { continue }
        $txt = [System.IO.File]::ReadAllText($f, [System.Text.UTF8Encoding]::new($false))
        if ($txt -notmatch '[^\x00-\x7F]') { continue }
        if (-not $fso) { $fso = New-Object -ComObject Scripting.FileSystemObject }
        $dirs = @($Root, $OpenclawHome, $env:USERPROFILE) | Sort-Object Length -Descending
        foreach ($d in $dirs) {
            try { $short = $fso.GetFolder($d).ShortPath } catch { continue }
            if ($short -and $short -ne $d) { $txt = $txt.Replace($d, $short) }
        }
        if ($txt -match '[^\x00-\x7F]') {
            [System.IO.File]::WriteAllText($f, $txt, [System.Text.Encoding]::Default)
        } else {
            [System.IO.File]::WriteAllText($f, $txt, [System.Text.ASCIIEncoding]::new())
        }
        Write-Ok "fixed $(Split-Path $f -Leaf) encoding (non-ASCII path -> 8.3 short path)"
    }
}

# --- 11. Interactive AWK_API_KEY prompt + start gateway ---
# Env division (mirrors install.sh / upstream lessons learned):
#   ~/.openclaw/.env        <- business vars (AWK_API_KEY/XIAOBEI_HOME/OPENCLAW_STATE_DIR), sourced by the
#                              openclaw CLI when run bare
#   ~/.openclaw/daemon.env  <- used by the gateway service, holds only 3 fixed values
#                              (OPENCLAW_BROWSER_TIMEOUT_MS/OPENCLAW_DISABLE_BONJOUR/PATH) + OPENCLAW_STATE_DIR
# Reason: the Linux systemd EnvironmentFile= loader has a history of choking on business vars that
# contain special chars (PATH with semicolons, AWK_API_KEY with hyphens), so business vars were moved
# to .env and systemd only loads the stable fixed values. Windows does not use systemd and
# gateway.cmd's `call daemon.env` does not have this pitfall, but we keep the same division for
# consistency.
function Install-GatewayAndEnv {
    Write-Stage "Configuring API key and gateway"
    New-Item -ItemType Directory -Force -Path $OpenclawHome | Out-Null
    $dotEnv    = Join-Path $OpenclawHome ".env"
    $daemonEnv = Join-Path $OpenclawHome "daemon.env"

    # --- Detect / clear a bogus OPENCLAW_HOME user env var ---
    # The engine's resolveStateDir treats OPENCLAW_HOME as a homedir and then appends /.openclaw (see
    # openclaw/src/config/paths.ts), so if OPENCLAW_HOME is set to ~/.openclaw this produces a nested
    # ~/.openclaw/.openclaw path - openclaw.json, daemon.env and lastTouch all land in the nested
    # layer while the correct outer path stays empty (a real bug observed on a local machine). The
    # state dir should be explicitly overridden via OPENCLAW_STATE_DIR (the engine treats it as a
    # direct state dir and does not append); OPENCLAW_HOME should not be set in the user environment.
    $badHome = $env:OPENCLAW_HOME
    if ($badHome -and ($badHome.TrimEnd('\').ToLower() -eq $OpenclawHome.TrimEnd('\').ToLower())) {
        Write-Warn "detected OPENCLAW_HOME=$badHome is set to the state dir path"
        Write-Warn "  this makes the engine nest-append /.openclaw -> ~/.openclaw/.openclaw/, all config lands in the wrong place"
        Write-Warn "  fix: clear OPENCLAW_HOME and use OPENCLAW_STATE_DIR to explicitly specify the state dir"
        try {
            [Environment]::SetEnvironmentVariable("OPENCLAW_HOME", $null, "User")
            [Environment]::SetEnvironmentVariable("OPENCLAW_HOME", $null, "Process")
            Remove-Item Env:OPENCLAW_HOME -ErrorAction SilentlyContinue
            Write-Ok "cleared OPENCLAW_HOME from user env vars (takes effect in a new terminal)"
        } catch { Write-Warn "failed to clear OPENCLAW_HOME, please delete manually: [Environment]::SetEnvironmentVariable('OPENCLAW_HOME', `$null, 'User')" }
    }

    # --- Interactive AWK_API_KEY prompt ---
    $awkKey = $env:AWK_API_KEY
    if (-not $script:NoPrompt -and -not $awkKey) {
        $awkKey = Read-Host "Enter AWK_API_KEY (Aliyun Bailian API key)"
    }

    # --- Write .env (business vars, export format for bash/sh source, read by the bare CLI) ---
    # Idempotent: strip old lines with the same key first, then append. AWK_API_KEY is a secret, so
    # it is wrapped in single quotes with any embedded single quote escaped as '\''.
    $exportLines = @()
    if (Test-Path $dotEnv) { $exportLines = Get-Content $dotEnv }
    $exportLines = $exportLines | Where-Object { $_ -notmatch "^export AWK_API_KEY=" -and $_ -notmatch "^export XIAOBEI_HOME=" -and $_ -notmatch "^export OPENCLAW_STATE_DIR=" }
    if ($awkKey) {
        $awkEsc = $awkKey -replace "'", "'\''"
        $exportLines += "export AWK_API_KEY='$awkEsc'"
    }
    $rootEsc = $Root -replace "'", "'\''"
    $exportLines += "export XIAOBEI_HOME='$rootEsc'"
    $homeEsc = $OpenclawHome -replace "'", "'\''"
    $exportLines += "export OPENCLAW_STATE_DIR='$homeEsc'"
    # Write with UTF-8 NO BOM + explicit CRLF line breaks (mirrors install.ps1's Write-EnvFile).
    # Set-Content -Value $array on Windows PowerShell 5.1 can collapse an array built via
    # += from Get-Content into a single line (observed: all export* statements concatenated
    # with no separator), and -Encoding UTF8 emits a BOM that `source`/bash choke on.
    $dotEnvContent = (($exportLines | Where-Object { $_ }) -join "`r`n") + "`r`n"
    [System.IO.File]::WriteAllText($dotEnv, $dotEnvContent, (New-Object System.Text.UTF8Encoding($false)))
    Write-Ok ".env written (business vars, used by the bare CLI)"

    # --- Write daemon.env (used by the gateway service, KEY=value format for gateway.cmd to call) ---
    # Holds only 3 fixed values + OPENCLAW_STATE_DIR (the gateway subprocess needs the state dir to
    # disambiguate the nested layer).
    $daemonLines = @()
    if (Test-Path $daemonEnv) { $daemonLines = Get-Content $daemonEnv }
    $daemonLines = $daemonLines | Where-Object { $_ -notmatch "^OPENCLAW_BROWSER_TIMEOUT_MS=" -and $_ -notmatch "^OPENCLAW_DISABLE_BONJOUR=" -and $_ -notmatch "^PATH=" -and $_ -notmatch "^OPENCLAW_STATE_DIR=" }
    $daemonLines += "OPENCLAW_BROWSER_TIMEOUT_MS=90000"
    $daemonLines += "OPENCLAW_DISABLE_BONJOUR=true"
    $daemonLines += "OPENCLAW_STATE_DIR=$OpenclawHome"
    # program bin（$Root\bin，openclaw 启动器）+ wrapper bin（~\.openclaw\bin，skill 软链）+
    # node bin。gateway.cmd 不 source 用户 PATH，agent exec 调裸技能名靠此 PATH 解析软链。
    $pathLine = "PATH=$(Join-Path $Root 'bin');$(Join-Path $OpenclawHome 'bin');$(Split-Path $NodeExe);$env:PATH"
    $daemonLines += $pathLine
    # Write with UTF-8 NO BOM + explicit CRLF line breaks (same Set-Content array-collapse + BOM
    # issue as .env above; gateway.cmd's `call daemon.env` needs clean KEY=value lines).
    $daemonEnvContent = (($daemonLines | Where-Object { $_ }) -join "`r`n") + "`r`n"
    [System.IO.File]::WriteAllText($daemonEnv, $daemonEnvContent, (New-Object System.Text.UTF8Encoding($false)))
    Write-Ok "daemon.env written (used by the gateway service, 3 fixed values + PATH + OPENCLAW_STATE_DIR)"

    # Load the .env business vars into the current install shell so that subsequent daemon install /
    # gateway restart / channels login config validation can resolve AWK_API_KEY / XIAOBEI_HOME (the
    # bare CLI would normally `. .env`, and the install shell needs them too).
    if ($awkKey) { $env:AWK_API_KEY = $awkKey }
    $env:XIAOBEI_HOME = $Root
    $env:OPENCLAW_STATE_DIR = $OpenclawHome

    # setx the user env var (so new terminals / gateway subprocesses inherit AWK_API_KEY)
    if ($awkKey) {
        & setx AWK_API_KEY "$awkKey" | Out-Null
        Write-Ok "AWK_API_KEY set as user env var (takes effect in a new terminal)"
    }

    # Attempt daemon install (Windows support depends on the openclaw version)
    Write-Host "  attempting openclaw daemon install..."
    Invoke-Streamed { & $ClawCmd daemon install }
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "gateway daemon installed"
        Repair-GatewayCmd
        Invoke-Streamed { & $ClawCmd gateway restart }
    } else {
        Write-Warn "openclaw daemon install is not ready or failed on Windows"
        Write-Host "  please open a new PowerShell terminal and run gateway in the foreground:"
        Write-Host "    set AWK_API_KEY=$awkKey"
        Write-Host "    $ClawCmd gateway start"
    }
}

# --- 12. Auto-show WeChat binding QR code (end of first install) ---
function Test-WeixinBound {
    $paths = @(
        (Join-Path $OpenclawHome "openclaw-weixin\accounts.json"),
        (Join-Path $OpenclawHome ".openclaw\openclaw-weixin\accounts.json")
    )
    foreach ($p in $paths) { if (Test-Path $p) { return $true } }
    return $false
}

function Bind-WeixinChannel {
    if ($script:SkipBind -or $script:NoPrompt) {
        Write-Host "  [i]  skipping WeChat scan-to-bind (XIAOBEI_SKIP_BIND / XIAOBEI_NO_PROMPT=1); run manually later: openclaw channels login --channel openclaw-weixin" -ForegroundColor Yellow
        return
    }
    if (Test-WeixinBound) { Write-Ok "WeChat account already bound, skipping scan"; return }
    if (-not (Test-Path $ClawCmd)) { Write-Warn "openclaw wrapper not found ($ClawCmd), skipping WeChat binding"; return }
    Write-Stage "Binding WeChat channel (scan with your phone)"
    Write-Host "  A QR code will appear next; scan it with WeChat and tap confirm, then xiaobei is ready to use."
    Write-Host "  Take your time scanning - the QR code auto-refreshes; just continue once scanned."
    Write-Host ""
    for ($i = 1; $i -le 5; $i++) {
        & $ClawCmd channels login --channel openclaw-weixin
        if (Test-WeixinBound) { Write-Ok "WeChat account bound successfully"; return }
        if ($i -lt 5) { Write-Warn "no binding detected this round, re-showing QR code (attempt $($i + 1))..." }
    }
    Write-Warn "binding not completed after multiple scans. You can run manually later: $ClawCmd channels login --channel openclaw-weixin"
}

# --- main ---
function Main {
    Write-Host "wiseflow installer (Windows, atomgit) - prebuilt tarball route" -ForegroundColor Magenta
    Write-Host "  Program dir : $Root"
    Write-Host "  Runtime dir : $OpenclawHome"
    Write-Host "  Repo        : $Repo (atomgit)"

    # Detect whether already installed (decides update vs fresh install)
    $cfgExisting = Join-Path $OpenclawHome "openclaw.json"
    $isUpdate = (Test-Path $cfgExisting) -and -not $script:Force
    if ($isUpdate) {
        Write-Warn "detected existing install ($cfgExisting) -> taking the update route, preserving runtime data (XIAOBEI_FORCE=1 to force overwrite)"
        # Stop the gateway first (mirrors install.sh stop_gateway_if_running): otherwise tar
        # overwriting tools\node\node.exe and pnpm rewriting node_modules will hit the running
        # gateway's file locks ("Can't unlink already-existing object: Permission denied", observed
        # in practice).
        Write-Stage "Stopping gateway before update"
        if (Test-Path $ClawCmd) { Invoke-Streamed { & $ClawCmd gateway stop } }
        Get-Process node -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "$Root*" } |
            Stop-Process -Force -ErrorAction SilentlyContinue
    }

    Write-Stage "Resolving latest release (atomgit v5 API)"
    $tag = Resolve-Tag
    Write-Ok "tag = $tag"

    Write-Stage "Downloading pre-built tarball (atomgit CDN)"
    $tb = Download-Tarball $tag

    Write-Stage "Extracting tarball"
    Extract-Tarball $tb

    Install-Deps
    Write-Stage "Installing per-skill Node.js dependencies"
    & $NodeExe (Join-Path $Root 'scripts\install-skill-deps.mjs') `
        --root $Root --state-dir $OpenclawHome `
        --npm-cli (Join-Path $Root 'tools\node\node_modules\npm\bin\npm-cli.js')
    if ($LASTEXITCODE -ne 0) { throw "skill Node.js dependency install failed (exit $LASTEXITCODE)" }
    Install-PythonDeps
    Install-AwadaPlugin
    Write-Stage "Installing deck-render runtime"
    $deckArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Root 'scripts\install-deck-render.ps1'), '-Root', $Root)
    if ($script:SkipBrowser) { $deckArgs += '-SkipBrowser' }
    & powershell.exe @deckArgs
    if ($LASTEXITCODE -ne 0) { throw "deck-render runtime install failed" }
    $env:PATH = @($env:PATH, [Environment]::GetEnvironmentVariable('Path', 'User'),
        [Environment]::GetEnvironmentVariable('Path', 'Machine')) -join ';'
    Install-CamoufoxCli
    Install-WeixinPlugin

    if ($isUpdate) {
        # The update route also self-heals the config (mirrors install.sh: if openclaw.json was
        # minimized, repair it with the template).
        Place-Config
        Write-Stage "Refreshing gateway env and restarting"
        $envFile = Join-Path $OpenclawHome "daemon.env"
        if (Test-Path $envFile) {
            $lines = Get-Content $envFile
            $lines = $lines | Where-Object { $_ -notmatch "^XIAOBEI_HOME=" }
            $lines += "XIAOBEI_HOME=$Root"
            # WriteAllText no-BOM + CRLF（Set-Content -Encoding UTF8 会写 BOM，gateway.cmd call daemon.env 炸）
            $envFileContent = (($lines | Where-Object { $_ }) -join "`r`n") + "`r`n"
            [System.IO.File]::WriteAllText($envFile, $envFileContent, (New-Object System.Text.UTF8Encoding($false)))
            Write-Ok "daemon.env XIAOBEI_HOME refreshed"
        }
        Repair-GatewayCmd
        Invoke-Streamed { & $ClawCmd gateway restart }
    } else {
        Place-Config
        Run-SetupCrew
        Sync-GlobalSkills
        Expose-SkillWrappers
        Install-GatewayAndEnv
        Bind-WeixinChannel
    }

    Write-Host ""
    if ($isUpdate) {
        Write-Host "wiseflow updated successfully!" -ForegroundColor Green
    } else {
        Write-Host "wiseflow installed successfully!" -ForegroundColor Green
    }
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    $binDir = Join-Path $Root 'bin'
    Write-Host "  Add $binDir to the user PATH (safe way - do NOT use setx %PATH%, it truncates):"
    Write-Host "    [Environment]::SetEnvironmentVariable('PATH', `"$binDir;`" + [Environment]::GetEnvironmentVariable('PATH','User'), 'User')"
    Write-Host ""
    Write-Host "  Dashboard: http://127.0.0.1:18789"
    Write-Host "  Update later: re-run this install script (preserves $OpenclawHome runtime data)."
    Write-Host ""
}

Main

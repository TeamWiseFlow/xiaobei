param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [switch]$SkipBrowser
)
$ErrorActionPreference = 'Stop'

$tool = Join-Path $Root 'crews\content-producer\skills\expert-video\tools\deck-render'
$node = Join-Path $Root 'tools\node\node.exe'
$npm = Join-Path $Root 'tools\node\npm.cmd'
$browserDir = Join-Path $tool '.browsers'
$marker = Join-Path $tool '.deck-render-browser'
foreach ($path in @($node, $npm, (Join-Path $tool 'package.json'))) {
    if (-not (Test-Path $path)) { throw "deck-render dependency missing: $path" }
}
$nodeMajor = & $node -p 'process.versions.node.split(".")[0]'
if ($LASTEXITCODE -ne 0 -or [int]$nodeMajor -lt 22) { throw 'deck-render needs Node >=22' }

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or
    -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'deck-render needs FFmpeg/FFprobe; install them or install Windows Package Manager (winget)'
    }
    Write-Host 'Installing FFmpeg/FFprobe with winget...'
    & winget install --id Gyan.FFmpeg --exact --source winget --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'winget FFmpeg install failed' }
    $env:PATH = @(
        $env:PATH,
        [Environment]::GetEnvironmentVariable('Path', 'User'),
        [Environment]::GetEnvironmentVariable('Path', 'Machine'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links')
    ) -join ';'
}
foreach ($bin in @('ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $bin -ErrorAction SilentlyContinue)) { throw "deck-render needs $bin; reopen the terminal after winget install" }
}

# Windows uses the bundled Microsoft YaHei family; no Noto download is needed.
foreach ($name in @('msyhl.ttc', 'msyh.ttc', 'msyhbd.ttc')) {
    $fontFile = Join-Path $env:WINDIR "Fonts\$name"
    if (-not (Test-Path $fontFile)) {
        throw "deck-render needs Microsoft YaHei ($name); install the Windows Simplified Chinese font feature"
    }
}

$oldPath = $env:PATH
$env:PATH = "$(Split-Path $node);$oldPath"
try {
    $manifest = Get-Content (Join-Path $tool 'package.json') -Raw | ConvertFrom-Json
    $needsNpm = $false
    foreach ($dep in $manifest.dependencies.PSObject.Properties) {
        $installed = Join-Path $tool "node_modules\$($dep.Name)\package.json"
        if (-not (Test-Path $installed)) { $needsNpm = $true; break }
        if ((Get-Content $installed -Raw | ConvertFrom-Json).version -ne $dep.Value) { $needsNpm = $true; break }
    }
    if ($needsNpm) {
        Write-Host 'Installing pinned deck-render npm packages...'
        Push-Location $tool
        try {
            $registry = if ($env:NPM_CONFIG_REGISTRY) { $env:NPM_CONFIG_REGISTRY } else { 'https://registry.npmmirror.com' }
            & $npm install --omit=dev --no-audit --no-fund "--registry=$registry"
            if ($LASTEXITCODE -ne 0) { throw 'deck-render npm install failed' }
        } finally { Pop-Location }
    }
    if ($SkipBrowser) { Write-Host 'deck-render packages/Microsoft YaHei ready; browser skipped by request'; return }

    $browser = $null
    if (Test-Path $marker) {
        $parts = (Get-Content $marker -Raw).Trim() -split "`t", 2
        if ($parts.Count -eq 2 -and $parts[0] -eq '1.61.1') {
            $candidate = Join-Path $tool $parts[1]
            if (Test-Path $candidate) { $browser = $candidate }
        }
    }
    if (-not $browser) {
        Write-Host 'Installing pinned Playwright Chromium headless shell...'
        New-Item -ItemType Directory -Force -Path $browserDir | Out-Null
        $oldBrowsersPath = $env:PLAYWRIGHT_BROWSERS_PATH
        $env:PLAYWRIGHT_BROWSERS_PATH = $browserDir
        try {
            $cli = Join-Path $tool 'node_modules\.bin\playwright-core.cmd'
            & $cli install chromium-headless-shell
            if ($LASTEXITCODE -ne 0) { throw 'Playwright Chromium install failed' }
        } finally { $env:PLAYWRIGHT_BROWSERS_PATH = $oldBrowsersPath }
        $binary = Get-ChildItem $browserDir -Recurse -File | Where-Object {
            $_.Name -in @('chrome-headless-shell.exe', 'headless_shell.exe')
        } | Select-Object -First 1
        if (-not $binary) { throw 'Playwright browser install produced no executable' }
        $browser = $binary.FullName
        $relative = $browser.Substring($tool.Length + 1)
        [System.IO.File]::WriteAllText($marker, "1.61.1`t$relative`n", (New-Object System.Text.UTF8Encoding($false)))
    }
    & $browser --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Chromium headless shell cannot start: $browser" }
    Write-Host 'deck-render ready: HyperFrames 0.8.50, Playwright Chromium, Microsoft YaHei'
} finally {
    $env:PATH = $oldPath
}

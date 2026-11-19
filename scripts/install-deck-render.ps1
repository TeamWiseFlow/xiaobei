param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [switch]$SkipBrowser
)
$ErrorActionPreference = 'Stop'

$tool = Join-Path $Root 'crews\content-producer\skills\expert-video\tools\deck-render'
$node = Join-Path $Root 'tools\node\node.exe'
$npm = Join-Path $Root 'tools\node\npm.cmd'
foreach ($path in @($node, $npm, (Join-Path $tool 'package.json'))) {
    if (-not (Test-Path $path)) { throw "deck-render dependency missing: $path" }
}
$nodeMajor = & $node -p 'process.versions.node.split(".")[0]'
if ($LASTEXITCODE -ne 0 -or [int]$nodeMajor -lt 22) { throw 'deck-render needs Node >=22' }

if ($env:XIAOBEI_GITHUB_PROXY) {
    . (Join-Path $Root 'scripts\lib\download-network.ps1')
    Initialize-XiaobeiDownloadNetwork $Root $node
}

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
$oldInstallCuda = $env:ONNXRUNTIME_NODE_INSTALL_CUDA
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
        $env:ONNXRUNTIME_NODE_INSTALL_CUDA = 'skip'
        Write-Host 'Installing pinned deck-render npm packages...'
        Push-Location $tool
        try {
            $registry = if ($env:NPM_CONFIG_REGISTRY) { $env:NPM_CONFIG_REGISTRY } else { 'https://registry.npmmirror.com' }
            & $npm install --omit=dev --no-audit --no-fund "--registry=$registry"
            if ($LASTEXITCODE -ne 0) { throw 'deck-render npm install failed' }
        } finally { Pop-Location }
    }
    $sharedArgs = @((Join-Path $Root 'scripts\install-playwright.mjs'), '--root', $Root)
    if ($SkipBrowser) { $sharedArgs += '--skip-browser' }
    & $node @sharedArgs
    if ($LASTEXITCODE -ne 0) { throw 'Shared Playwright/Chromium installation failed' }
    Write-Host 'deck-render ready: HyperFrames 0.8.50, shared Playwright/Chromium, Microsoft YaHei'
} finally {
    $env:PATH = $oldPath
    $env:ONNXRUNTIME_NODE_INSTALL_CUDA = $oldInstallCuda
}

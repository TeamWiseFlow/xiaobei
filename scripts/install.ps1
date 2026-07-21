# install.ps1 - wiseflow 一键首装脚本（Windows，预构建 tarball 路线）
#
# 用法（PowerShell）：
#   $env:XIAOBEI_REPO = "TeamWiseFlow/xiaobei"   # 默认即此；国内可指 atomgit 镜像
#   irm https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.ps1 | iex
#   # 或本地：
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# 与 install.sh 同构（方案 B 瘦 tarball）：
#   1. 拉 xiaobei-{tag}-win-x64.tar.gz（Windows bsdtar 原生支持 gzip，免装 zstd）
#   2. 解压到 $XIAOBEI_HOME（默认 $env:USERPROFILE\xiaobei，程序目录）
#   3. portable node + pnpm install --prod --frozen-lockfile（在 openclaw\ 下）
#   4. pip install --user（skills 的 python deps，有 python 才跑）
#   5. 放 config-templates\openclaw.json → $OPENCLAW_HOME\openclaw.json + 预填微信 binding
#   6. setup-crew.sh（需 bash：Git Bash 或 WSL；无则警告并跳过，用户后续手动跑）
#   7. camoufox-cli：npm install -g 本地 fork + camoufox-cli install 下 Firefox
#   8. openclaw-weixin 插件：openclaw plugins install ... --pin（npmmirror）
#   9. 交互问 AWK_API_KEY → 写 daemon.env + setx 用户环境变量 → 尝试 openclaw daemon install
#
# 目录职责：$XIAOBEI_HOME（~\xiaobei）= 程序；$OPENCLAW_HOME（~\.openclaw）= 运行数据。
# Windows 原生 wrapper：$XIAOBEI_HOME\bin\openclaw.cmd（WSL/Git Bash 用户也可用 bin\openclaw）。

[CmdletBinding()]
param(
    [string]$Root = "",                 # 程序目录覆盖（默认 ~\xiaobei）
    [string]$Tag = "",                  # 指定 release tag
    [string]$Tarball = "",              # 本地已下好的 tarball 路径，跳过下载
    [string]$Mirror = "",               # 自定义镜像站根（覆盖默认 atomgit）
    [switch]$GitHub,                    # 切回 GitHub release（不走默认 atomgit）
    [switch]$Force,                     # 强覆盖已有运行数据（~\.openclaw）
    [switch]$SkipBind,                  # 跳过末尾微信扫码绑定
    [switch]$SkipBrowser,               # 跳过 camoufox-cli 浏览器二进制（冒烟/CI）
    [switch]$NoPrompt
)

$ErrorActionPreference = "Stop"

# ─── 常量 / 目录 ───────────────────────────────────────────────
$Repo = if ($env:XIAOBEI_REPO) { $env:XIAOBEI_REPO } else { "TeamWiseFlow/xiaobei" }
if (-not $Root) {
    $Root = if ($env:XIAOBEI_HOME) { $env:XIAOBEI_HOME } else { Join-Path $env:USERPROFILE "xiaobei" }
}
$OpenclawHome = if ($env:OPENCLAW_HOME) { $env:OPENCLAW_HOME } else { Join-Path $env:USERPROFILE ".openclaw" }
# 默认走 atomgit 国内镜像；-GitHub 或 XIAOBEI_SOURCE=github 切回 GitHub
$AtomgitMirror = "https://atomgit.com/wiseflow/xiaobei"
if (-not $Mirror) {
    if ($GitHub -or $env:XIAOBEI_SOURCE -eq "github") {
        $env:XIAOBEI_MIRROR = ""
    } else {
        $env:XIAOBEI_MIRROR = if ($env:XIAOBEI_MIRROR) { $env:XIAOBEI_MIRROR } else { $AtomgitMirror }
    }
} else {
    $env:XIAOBEI_MIRROR = $Mirror
}
if ($Tag) { $env:XIAOBEI_TAG = $Tag }
if ($Tarball) { $env:XIAOBEI_TARBALL = $Tarball }

$NodeExe   = Join-Path $Root "tools\node\node.exe"
$NpmCmd    = Join-Path $Root "tools\node\npm.cmd"
$PnpmMjs   = Join-Path $Root "tools\pnpm\bin\pnpm.mjs"
$ClawCmd   = Join-Path $Root "bin\openclaw.cmd"
$ClawSh    = Join-Path $Root "bin\openclaw"

function Write-Stage([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok([string]$msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg)  { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Err([string]$msg)   { Write-Host "  [X]  $msg" -ForegroundColor Red }

# ─── 1. 解析最新 release tag ───────────────────────────────────
function Resolve-Tag {
    if ($env:XIAOBEI_TAG) { return $env:XIAOBEI_TAG }
    if ($env:XIAOBEI_MIRROR) {
        # Gitea 镜像（atomgit 每晚同步上游 tag）：从 mirror URL 推导 /api/v1/repos/<o>/<r>/releases/latest
        try {
            $u = ($env:XIAOBEI_MIRROR.TrimEnd('/') -replace '^https?://', '')
            $slash = $u.IndexOf('/')
            if ($slash -gt 0) {
                $gh = $u.Substring(0, $slash)
                $rp = $u.Substring($slash + 1)
                $rel = Invoke-RestMethod "https://$gh/api/v1/repos/$rp/releases/latest" -Headers @{ "User-Agent" = "xiaobei-install" }
                if ($rel.tag_name) { return $rel.tag_name }
            }
        } catch { Write-Warn "镜像 Gitea API 拉取失败，回退 GitHub API" }
    }
    $api = "https://api.github.com/repos/$Repo/releases/latest"
    $rel = Invoke-RestMethod $api -Headers @{ "User-Agent" = "xiaobei-install" }
    return $rel.tag_name
}

# ─── 2. 下载 tarball ───────────────────────────────────────────
function Download-Tarball([string]$tag) {
    $asset = "xiaobei-$tag-win-x64.tar.gz"
    if ($env:XIAOBEI_TARBALL -and (Test-Path $env:XIAOBEI_TARBALL)) {
        Write-Ok "用本地 tarball：$env:XIAOBEI_TARBALL"
        return $env:XIAOBEI_TARBALL
    }
    $tmp = New-TemporaryFile
    if ($env:XIAOBEI_MIRROR) {
        $url = "$env:XIAOBEI_MIRROR/releases/download/$tag/$asset"
    } else {
        $url = "https://github.com/$Repo/releases/download/$tag/$asset"
    }
    Write-Host "  下载 $url"
    Invoke-WebRequest -Uri $url -OutFile $tmp -Headers @{ "User-Agent" = "xiaobei-install" }
    return $tmp.FullName
}

# ─── 3. 解压 ───────────────────────────────────────────────────
function Extract-Tarball([string]$tarball) {
    if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
        throw "未找到 tar（Windows 10 1803+ 自带 bsdtar；请升级 Windows 或装 Git Bash）"
    }
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    Write-Host "  解压到 $Root"
    & tar -xzf $tarball -C $Root
    if ($LASTEXITCODE -ne 0) { throw "tar 解压失败 (exit $LASTEXITCODE)" }
}

# ─── 4. pnpm install --prod ────────────────────────────────────
function Install-Deps {
    Write-Stage "Installing dependencies (pnpm install --prod)"
    $openclawDir = Join-Path $Root "openclaw"
    if (-not (Test-Path $NodeExe)) { throw "portable node 未找到：$NodeExe" }
    Push-Location $openclawDir
    try {
        $env:npm_config_registry = "https://registry.npmmirror.com"
        & $NodeExe $PnpmMjs install --prod --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "pnpm install 失败 (exit $LASTEXITCODE)" }
        Write-Ok "deps installed"
    } finally { Pop-Location }
}

# ─── 5. python skill deps ──────────────────────────────────────
function Install-PythonDeps {
    Write-Stage "Installing python skill deps"
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { Write-Warn "未找到 python，跳过 skill python deps"; return }
    $reqs = @()
    $reqs += Get-ChildItem -Path (Join-Path $Root "skills") -Filter "requirements.txt" -Recurse -ErrorAction SilentlyContinue
    $reqs += Get-ChildItem -Path (Join-Path $Root "crews") -Filter "requirements.txt" -Recurse -ErrorAction SilentlyContinue
    $reqs += Get-ChildItem -Path $Root -Filter "requirements.txt" -ErrorAction SilentlyContinue
    $reqs = $reqs | Select-Object -ExpandProperty FullName -Unique
    if (-not $reqs) { Write-Ok "无 requirements.txt"; return }
    $merged = ($reqs | ForEach-Object { Get-Content $_ -ErrorAction SilentlyContinue } | Where-Object { $_ -and -not $_.StartsWith("#") } | Sort-Object -Unique)
    if (-not $merged) { Write-Ok "无 python 依赖"; return }
    & python -m pip install --user $merged 2>&1 | ForEach-Object { Write-Host "    $_" }
    Write-Ok "python deps installed"
}

# ─── 6. 放 config template + 预填微信 binding ─────────────────
function Place-Config {
    Write-Stage "Placing config template"
    New-Item -ItemType Directory -Force -Path $OpenclawHome | Out-Null
    $cfg = Join-Path $OpenclawHome "openclaw.json"
    $tmpl = Join-Path $Root "config-templates\openclaw.json"
    if (-not (Test-Path $cfg)) {
        if (Test-Path $tmpl) { Copy-Item $tmpl $cfg; Write-Ok "placed openclaw.json" }
        else { Write-Warn "template 未找到：$tmpl" }
    } elseif ($Force) {
        $bak = "$cfg.bak.$([int][double]::Parse((Get-Date -UFormat %s)))"
        Copy-Item $cfg $bak
        if (Test-Path $tmpl) { Copy-Item $tmpl $cfg -Force; Write-Warn "openclaw.json 已存在，-Force 覆盖（备份到 $bak）" }
    } else {
        Write-Ok "openclaw.json 已存在，保留"
    }
    if (Test-Path $cfg) {
        $prefill = @"
const fs = require('fs');
const p = process.argv[1];
const c = JSON.parse(fs.readFileSync(p, 'utf8'));
c.channels = c.channels || {};
c.channels['openclaw-weixin'] = { ...(c.channels['openclaw-weixin'] || {}), enabled: true };
c.session = { ...(c.session || {}), dmScope: 'per-channel-peer' };
if (!Array.isArray(c.bindings)) c.bindings = [];
const has = c.bindings.some(b => b?.agentId === 'main' && b?.match?.channel === 'openclaw-weixin');
if (!has) c.bindings.push({ agentId: 'main', comment: 'openclaw-weixin -> Main Agent onboarding entry', match: { channel: 'openclaw-weixin' } });
fs.writeFileSync(p, JSON.stringify(c, null, 2) + '\n');
"@
        & $NodeExe -e $prefill $cfg
        Write-Ok "WeChat channel pre-bound"
    }
}

# ─── 7. setup-crew（需 bash）──────────────────────────────────
function Run-SetupCrew {
    Write-Stage "Setting up crew templates (needs bash)"
    $sh = Join-Path $Root "scripts\setup-crew.sh"
    if (-not (Test-Path $sh)) { Write-Warn "setup-crew.sh 不在 tarball 内，跳过"; return }
    $bash = Get-Command bash -ErrorAction SilentlyContinue
    if (-not $bash) {
        Write-Warn "未找到 bash（setup-crew.sh 是 bash 脚本）"
        Write-Host "    请装 Git Bash（https://git-scm.com）或 WSL，然后手动跑："
        Write-Host "      set OPENCLAW_HOME=$OpenclawHome"
        Write-Host "      set XIAOBEI_BIN_DIR=$(Join-Path $Root 'bin')"
        Write-Host "      bash `"$sh`""
        return
    }
    # bash 不认反斜杠（会被当转义），传正斜杠路径给 setup-crew.sh
    $env:OPENCLAW_HOME   = ($OpenclawHome -replace '\\', '/')
    $env:XIAOBEI_BIN_DIR = ((Join-Path $Root "bin") -replace '\\', '/')
    & bash $sh
    if ($LASTEXITCODE -ne 0) { Write-Warn "setup-crew.sh 非零退出（可后续手动 --force 修复）" }
    else { Write-Ok "crew templates set up" }
}

# ─── 8. camoufox-cli ───────────────────────────────────────────
function Install-CamoufoxCli {
    if ($SkipBrowser) {
        Write-Host "  [i]  跳过 camoufox-cli 浏览器二进制（-SkipBrowser）；后续手动：camoufox-cli install" -ForegroundColor Yellow
        return
    }
    Write-Stage "Installing camoufox-cli browser"
    $fork = Join-Path $Root "camoufox-cli"
    if (-not (Test-Path $fork)) { Write-Warn "camoufox-cli fork 不在 tarball 内：$fork；跳过"; return }
    $env:PATH = "$(Split-Path $NodeExe);$env:PATH"
    $env:npm_config_prefix = $Root
    $env:npm_config_registry = "https://registry.npmmirror.com"
    $camoufoxBin = Join-Path $Root "bin\camoufox-cli.cmd"
    $hasDeps = Test-Path (Join-Path $fork "node_modules\camoufox-js")
    if ((Get-Command camoufox-cli -ErrorAction SilentlyContinue) -and $hasDeps) {
        Write-Ok "camoufox-cli already installed"
    } else {
        Push-Location $fork
        try {
            & $NpmCmd install --omit=dev
            if ($LASTEXITCODE -ne 0) { Write-Warn "camoufox-cli fork deps install 失败"; return }
            & $NpmCmd install -g $fork
            if ($LASTEXITCODE -ne 0) { Write-Warn "camoufox-cli 全局安装失败"; return }
        } finally { Pop-Location }
    }
    Write-Host "  下 Firefox binary（首次 ~557MB）..."
    & camoufox-cli install 2>&1 | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0) { Write-Warn "camoufox-cli install 失败；可后续手动：camoufox-cli install" }
    else { Write-Ok "camoufox-cli ready" }
}

# ─── 9. openclaw-weixin 插件 ──────────────────────────────────
function Install-WeixinPlugin {
    Write-Stage "Installing WeChat plugin"
    if (-not (Test-Path $ClawCmd)) { Write-Warn "openclaw wrapper 未找到：$ClawCmd；跳过"; return }
    $pkg = "@tencent-weixin/openclaw-weixin"; $ver = "2.4.6"
    $pin = Join-Path $Root "openclaw-weixin.version.json"
    if (Test-Path $pin) {
        try {
            $j = Get-Content $pin -Raw | ConvertFrom-Json
            $pkg = $j.'openclaw-weixin'.package; $ver = $j.'openclaw-weixin'.version
        } catch { Write-Warn "pin 文件解析失败，用默认 $pkg@$ver" }
    }
    $env:npm_config_registry = "https://registry.npmmirror.com"
    $listOut = (& $ClawCmd plugins list 2>$null | Out-String)
    if ($listOut -match "openclaw-weixin") { Write-Ok "openclaw-weixin plugin already installed"; return }
    & $ClawCmd plugins install "$pkg@$ver" --pin 2>&1 | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -eq 0) { Write-Ok "openclaw-weixin plugin installed" }
    else { Write-Warn "插件安装失败；可后续手动：$ClawCmd plugins install $pkg@$ver --pin" }
}

# ─── 10. awada 本地插件 deps（ws + zod）──────────────────────
function Install-AwadaPlugin {
    Write-Stage "Installing awada plugin deps"
    $awada = Join-Path $Root "awada"
    if (-not (Test-Path $awada)) { Write-Warn "awada 不在 tarball 内：$awada；跳过"; return }
    $hasWs   = Test-Path (Join-Path $awada "node_modules\ws")
    $hasZod  = Test-Path (Join-Path $awada "node_modules\zod")
    if ($hasWs -and $hasZod) { Write-Ok "awada deps already installed"; return }
    $env:npm_config_registry = "https://registry.npmmirror.com"
    Push-Location $awada
    try {
        & $NpmCmd install --omit=dev
        if ($LASTEXITCODE -eq 0) { Write-Ok "awada deps installed" }
        else { Write-Warn "awada deps install 失败；可后续手动：cd $awada ; npm install --omit=dev" }
    } finally { Pop-Location }
}

# ─── 11. 交互收 AWK_API_KEY + 起 gateway ──────────────────────
function Install-GatewayAndEnv {
    Write-Stage "Configuring API key and gateway"
    New-Item -ItemType Directory -Force -Path $OpenclawHome | Out-Null
    $envFile = Join-Path $OpenclawHome "daemon.env"

    $awkKey = $env:AWK_API_KEY
    if (-not $NoPrompt -and -not $awkKey) {
        $awkKey = Read-Host "Enter AWK_API_KEY (Volces ARK API key)"
    }
    # 写 daemon.env（KEY=value 格式，幂等）
    $lines = @()
    if (Test-Path $envFile) { $lines = Get-Content $envFile }
    $lines = $lines | Where-Object { $_ -notmatch "^AWK_API_KEY=" -and $_ -notmatch "^OPENCLAW_BROWSER_TIMEOUT_MS=" -and $_ -notmatch "^OPENCLAW_DISABLE_BONJOUR=" -and $_ -notmatch "^XIAOBEI_HOME=" }
    if ($awkKey) { $lines += "AWK_API_KEY=$awkKey" }
    $lines += "OPENCLAW_BROWSER_TIMEOUT_MS=90000"
    $lines += "OPENCLAW_DISABLE_BONJOUR=true"
    # XIAOBEI_HOME 让 openclaw.json 里 ${XIAOBEI_HOME}/awada env ref 解析到程序目录
    $lines += "XIAOBEI_HOME=$Root"
    # PATH 注入 program bin + node bin
    $pathLine = "PATH=$(Join-Path $Root 'bin');$(Split-Path $NodeExe);$env:PATH"
    $lines = $lines | Where-Object { $_ -notmatch "^PATH=" }
    $lines += $pathLine
    Set-Content -Path $envFile -Value $lines -Encoding UTF8
    Write-Ok "daemon.env written"

    # setx 用户环境变量（让新终端 / gateway 子进程继承 AWK_API_KEY）
    if ($awkKey) {
        & setx AWK_API_KEY "$awkKey" | Out-Null
        Write-Ok "AWK_API_KEY set as user env var (新终端生效)"
    }

    # 尝试 daemon install（Windows 支持情况视 openclaw 版本而定）
    Write-Host "  尝试 openclaw daemon install..."
    & $ClawCmd daemon install 2>&1 | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "gateway daemon installed"
        & $ClawCmd gateway restart 2>&1 | ForEach-Object { Write-Host "    $_" }
    } else {
        Write-Warn "openclaw daemon install 在 Windows 未就绪或失败"
        Write-Host "  请开新 PowerShell 终端前台跑 gateway："
        Write-Host "    set AWK_API_KEY=$awkKey"
        Write-Host "    $ClawCmd gateway start"
    }
}

# ─── 12. 自动出微信绑定二维码（首装末尾）──────────────────────
function Test-WeixinBound {
    $paths = @(
        (Join-Path $OpenclawHome "openclaw-weixin\accounts.json"),
        (Join-Path $OpenclawHome ".openclaw\openclaw-weixin\accounts.json")
    )
    foreach ($p in $paths) { if (Test-Path $p) { return $true } }
    return $false
}

function Bind-WeixinChannel {
    if ($SkipBind -or $NoPrompt) {
        Write-Host "  [i]  跳过微信扫码绑定（-SkipBind / -NoPrompt）；后续手动跑：openclaw channels login --channel openclaw-weixin" -ForegroundColor Yellow
        return
    }
    if (Test-WeixinBound) { Write-Ok "检测到微信账号已绑定，跳过扫码"; return }
    if (-not (Test-Path $ClawCmd)) { Write-Warn "openclaw wrapper 未找到（$ClawCmd），跳过微信绑定"; return }
    Write-Stage "绑定微信 channel（用手机扫码）"
    Write-Host "  接下来会出二维码，用微信扫一下、点确认，小贝就能用了。"
    Write-Host "  扫码慢没关系，二维码会自动刷新；扫完即继续。"
    Write-Host ""
    for ($i = 1; $i -le 5; $i++) {
        & $ClawCmd channels login --channel openclaw-weixin
        if (Test-WeixinBound) { Write-Ok "微信账号绑定成功"; return }
        if ($i -lt 5) { Write-Warn "本轮未检测到绑定，重出二维码（第 $($i + 1) 次）..." }
    }
    Write-Warn "多次扫码未完成绑定。可后续手动跑：$ClawCmd channels login --channel openclaw-weixin"
}

# ─── main ─────────────────────────────────────────────────────
function Main {
    Write-Host "wiseflow installer (Windows) — 预构建 tarball 路线" -ForegroundColor Magenta
    Write-Host "  Program dir : $Root"
    Write-Host "  Runtime dir : $OpenclawHome"
    Write-Host "  Repo        : $Repo"

    # 检测是否已装（决定走 update 还是 fresh install）
    $cfgExisting = Join-Path $OpenclawHome "openclaw.json"
    $isUpdate = (Test-Path $cfgExisting) -and -not $Force
    if ($isUpdate) {
        Write-Warn "检测到已有安装（$cfgExisting）→ 走更新路线，保留运行数据（-Force 可强覆盖）"
    }

    Write-Stage "Resolving latest release"
    $tag = Resolve-Tag
    Write-Ok "tag = $tag"

    Write-Stage "Downloading pre-built tarball"
    $tb = Download-Tarball $tag

    Write-Stage "Extracting tarball"
    Extract-Tarball $tb

    Install-Deps
    Install-PythonDeps
    Install-AwadaPlugin
    Install-CamoufoxCli
    Install-WeixinPlugin

    if ($isUpdate) {
        Write-Stage "Refreshing gateway env and restarting"
        $envFile = Join-Path $OpenclawHome "daemon.env"
        if (Test-Path $envFile) {
            $lines = Get-Content $envFile
            $lines = $lines | Where-Object { $_ -notmatch "^XIAOBEI_HOME=" }
            $lines += "XIAOBEI_HOME=$Root"
            Set-Content -Path $envFile -Value $lines -Encoding UTF8
            Write-Ok "daemon.env XIAOBEI_HOME refreshed"
        }
        & $ClawCmd gateway restart 2>&1 | ForEach-Object { Write-Host "    $_" }
    } else {
        Place-Config
        Run-SetupCrew
        Install-GatewayAndEnv
        Bind-WeixinChannel
    }

    Write-Host ""
    if ($isUpdate) {
        Write-Host "🦞 wiseflow updated successfully!" -ForegroundColor Green
    } else {
        Write-Host "🦞 wiseflow installed successfully!" -ForegroundColor Green
    }
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    $binDir = Join-Path $Root 'bin'
    Write-Host "  把 $binDir 加到用户 PATH（安全方式，勿用 setx %PATH% 会截断）："
    Write-Host "    [Environment]::SetEnvironmentVariable('PATH', `"$binDir;`" + [Environment]::GetEnvironmentVariable('PATH','User'), 'User')"
    Write-Host ""
    Write-Host "  Dashboard: http://127.0.0.1:18789"
    Write-Host "  Update later: re-run this install script (preserves $OpenclawHome runtime data)."
    Write-Host ""
}

Main

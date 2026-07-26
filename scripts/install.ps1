# install.ps1 - wiseflow 一键首装脚本（Windows，预构建 tarball 路线）
#
# 用法（PowerShell）：
#   $env:XIAOBEI_REPO = "TeamWiseFlow/xiaobei"   # 默认即此；国内可指 atomgit 镜像
#   irm https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.ps1 | iex
#   # 国内镜像（iex 不支持传参，带 -Atomgit 需用 scriptblock 形式；脚本走 atomgit v5 raw API 拉取）：
#   & ([scriptblock]::Create((irm "https://api.atomgit.com/api/v5/repos/wiseflow/xiaobei/raw/scripts/install.ps1?ref=master"))) -Atomgit
#   # 或本地：
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# ⚠️ 本文件必须保持 UTF-8 **带 BOM**：Windows PowerShell 5.1 对无 BOM 的 .ps1 按系统
#   ANSI 代码页（中文系统 GBK）解析，中文字符串会乱码并产生解析错误，脚本无法运行。
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
    [string]$Mirror = "",               # 自定义镜像站根（覆盖默认 GitHub）
    [switch]$GitHub,                    # 走 GitHub release（现已默认；保留向后兼容）
    [switch]$Atomgit,                   # 切到 atomgit 国内镜像（tarball 走 atomgit.com CDN，tag 走 api.atomgit.com v5）
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
# -Atomgit / XIAOBEI_SOURCE=atomgit 切到 atomgit 国内镜像：
#   tarball 走 atomgit.com → GitCode CDN（带签名 auth_key，匿名 GET 可下）；
#   tag 解析走 api.atomgit.com/api/v5（非 Gitea v1，host/版本都不同）。
$AtomgitMirror = "https://atomgit.com/wiseflow/xiaobei"
$AtomgitApi = "https://api.atomgit.com/api/v5/repos/wiseflow/xiaobei"
if (-not $Mirror) {
    if ($Atomgit -or $env:XIAOBEI_SOURCE -eq "atomgit") {
        $env:XIAOBEI_MIRROR = if ($env:XIAOBEI_MIRROR) { $env:XIAOBEI_MIRROR } else { $AtomgitMirror }
    } else {
        $env:XIAOBEI_MIRROR = ""
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

# 跑原生命令并按行回显 stdout+stderr。pip/npm/camoufox-cli/openclaw 正常会把进度和警告写 stderr，
# 而本脚本顶部 $ErrorActionPreference="Stop" 会把 2>&1 合并进管道的 stderr 行当 terminating error
# 抛 NativeCommandError/RemoteException（用户 Win 实测卡在 pip install 这步）。这里临时切到 Continue
# 跑原生命令，$LASTEXITCODE 仍由调用方据以判成败。
function Invoke-Streamed([scriptblock]$sb) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $sb 2>&1 | ForEach-Object { Write-Host "    $_" } }
    finally { $ErrorActionPreference = $prev }
}

# 同 Invoke-Streamed，但把 stdout+stderr 合并成字符串返回（供调用方 -&match）。`2>$null` 在
# Windows PowerShell 5.1 + Stop 下压不住 .cmd 的 stderr 仍抛 NativeCommandError，这里用 Continue + 2>&1 稳。
function Capture-Streamed([scriptblock]$sb) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { return (& $sb 2>&1 | Out-String) }
    finally { $ErrorActionPreference = $prev }
}

# ─── 1. 解析最新 release tag ───────────────────────────────────
function Resolve-Tag {
    if ($env:XIAOBEI_TAG) { return $env:XIAOBEI_TAG }
    # atomgit 官方镜像：走预定义 v5 API（host = api.atomgit.com，非 mirror URL 推导）
    if ($Atomgit -or $env:XIAOBEI_SOURCE -eq "atomgit") {
        try {
            $rel = Invoke-RestMethod "$AtomgitApi/releases/latest" -Headers @{ "User-Agent" = "xiaobei-install" }
            if ($rel.tag_name) { return $rel.tag_name }
        } catch { Write-Warn "atomgit v5 API 拉取失败，回退 GitHub API" }
    }
    # 自定义 Gitea 镜像：从 mirror URL 推导 /api/v1/repos/<o>/<r>/releases/latest
    if ($env:XIAOBEI_MIRROR -and -not ($Atomgit -or $env:XIAOBEI_SOURCE -eq "atomgit")) {
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
        # postinstall 子进程（esbuild/protobufjs 等）按 PATH 找 node；目标机器多半没装全局
        # Node（'node' is not recognized 实测），把 portable node 前置进 PATH
        $env:PATH = "$(Split-Path $NodeExe);$env:PATH"
        # pnpm 11 不认 npm_config_registry 环境变量（实测仍走 registry.npmjs.org），用显式 --registry
        $env:npm_config_registry = "https://registry.npmmirror.com"
        & $NodeExe $PnpmMjs install --prod --frozen-lockfile --registry https://registry.npmmirror.com
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
    # 各行作为 pip 命令行参数传入（非 -r 文件），必须剥掉行内注释（pip 只在
    # requirements 文件里认注释，参数里 `Pillow # 说明` 直接 Invalid requirement 报错）；
    # 文件是 UTF-8，显式指定编码防中文注释被 ANSI 误读产生乱码参数。
    $merged = ($reqs | ForEach-Object { Get-Content $_ -Encoding UTF8 -ErrorAction SilentlyContinue } |
        ForEach-Object { ($_ -replace '#.*$', '').Trim() } |
        Where-Object { $_ } | Sort-Object -Unique)
    if (-not $merged) { Write-Ok "无 python 依赖"; return }
    Invoke-Streamed { python -m pip install --user $merged }
    if ($LASTEXITCODE -ne 0) { Write-Warn "pip install 非零退出；可后续手动补装 skills 的 python 依赖" }
    else { Write-Ok "python deps installed" }
}

# ─── 6. 放 config template（对齐 install.sh place_config_template）────
# template 已预置 channels.openclaw-weixin / bindings / session.dmScope，不再运行时 mutate
# （sh 版曾因运行时 mutate 把 plugins 顶层写坏致 "Invalid input"，已同构移除）。
# 健康检查：现有 config 缺 models/agents.defaults（多半是 Install-WeixinPlugin 先跑时
# openclaw plugins install 自建的极简 config，或 openclaw 首启自动生成）→ 备份后用
# template 覆盖，否则 channels/bindings 永远缺失、小贝起不来。
function Place-Config {
    Write-Stage "Placing config template"
    New-Item -ItemType Directory -Force -Path $OpenclawHome | Out-Null
    $cfg = Join-Path $OpenclawHome "openclaw.json"
    $tmpl = Join-Path $Root "config-templates\openclaw.json"
    if (-not (Test-Path $tmpl)) { Write-Err "config template 缺失：$tmpl（tarball 损坏?）"; return }

    $needPlace = $false; $reason = ""
    if (-not (Test-Path $cfg)) { $needPlace = $true; $reason = "不存在" }
    elseif ($Force) { $needPlace = $true; $reason = "-Force" }
    else {
        try {
            # 必须显式按 UTF-8 读：openclaw 写的 config 是 UTF-8 无 BOM，PS 5.1 的
            # Get-Content 默认按 ANSI 代码页读，中文路径旁的 \\ 转义会被双字节吞掉，
            # 有效 config 被误判"解析失败"遭覆盖（本机实测）。
            $j = [System.IO.File]::ReadAllText($cfg) | ConvertFrom-Json -ErrorAction Stop
            if (-not ($j.models -and $j.agents -and $j.agents.defaults)) { $needPlace = $true; $reason = "缺 models/agents.defaults（疑似被极简化）" }
        } catch { $needPlace = $true; $reason = "解析失败" }
    }
    if ($needPlace) {
        if (Test-Path $cfg) {
            $bak = "$cfg.bak.$([int][double]::Parse((Get-Date -UFormat %s)))"
            Copy-Item $cfg $bak
            Write-Warn "openclaw.json $reason → 用 template 覆盖（旧文件备份到 $bak）"
        }
        Copy-Item $tmpl $cfg -Force
        Write-Ok "placed openclaw.json template"
    } else {
        Write-Ok "openclaw.json 已存在且健康（有 models + agents.defaults），保留"
    }

    # 把 plugins.load.paths 里的 ${XIAOBEI_HOME} env ref 解析成绝对路径，避免 CLI 上下文没
    # XIAOBEI_HOME 时 "plugin path not found" 误报；AWK_API_KEY 是 secret 保持 env ref 不动。
    # 文本级替换（template 中 ${XIAOBEI_HOME} 仅出现在 plugins.load.paths）；JSON 字符串里
    # 反斜杠是转义符，路径统一写正斜杠。幂等：已解析则 no-op。
    $raw = [System.IO.File]::ReadAllText($cfg)
    if ($raw.Contains('${XIAOBEI_HOME}')) {
        $rootFwd = $Root -replace '\\', '/'
        [System.IO.File]::WriteAllText($cfg, $raw.Replace('${XIAOBEI_HOME}', $rootFwd), [System.Text.UTF8Encoding]::new($false))
        Write-Ok "resolved XIAOBEI_HOME refs -> $rootFwd"
    }
}

# ─── 7. setup-crew（需 bash）──────────────────────────────────
# 找一个真正可用的 bash：优先 Git Bash（吃得了 C:/ 风格路径）；PATH 里的 bash 可能是
# C:\Windows\system32\bash.exe（WSL 启动器）——没装发行版时直接报错退出，且 WSL bash
# 对 Windows 路径参数不做转换，都不能直接用。每个候选实测 `bash -c echo` 通过才算数。
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
    # system32 的 WSL 启动器排最后（仅当其可用且无 Git Bash 时兜底）
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
    if (-not (Test-Path $sh)) { Write-Warn "setup-crew.sh 不在 tarball 内，跳过"; return }
    $bashExe = Find-WorkingBash
    if (-not $bashExe) {
        Write-Warn "未找到可用的 bash（setup-crew.sh 是 bash 脚本；注意 system32\bash.exe 是 WSL 启动器，没装发行版不可用）"
        Write-Host "    请装 Git Bash（https://git-scm.com）或 WSL 发行版，然后手动跑："
        Write-Host "      set OPENCLAW_HOME=$OpenclawHome"
        Write-Host "      set XIAOBEI_BIN_DIR=$(Join-Path $Root 'bin')"
        Write-Host "      bash `"$sh`""
        return
    }
    Write-Host "  bash: $bashExe"
    # bash 不认反斜杠（会被当转义），传正斜杠路径给 setup-crew.sh
    $env:OPENCLAW_HOME   = ($OpenclawHome -replace '\\', '/')
    $env:XIAOBEI_BIN_DIR = ((Join-Path $Root "bin") -replace '\\', '/')
    Invoke-Streamed { & $bashExe ($sh -replace '\\', '/') }
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
    # $Root\bin 放 camoufox-cli.cmd shim，前置进 PATH 让下面 `camoufox-cli install` 找得到
    $env:PATH = "$(Join-Path $Root 'bin');$(Split-Path $NodeExe);$env:PATH"
    $env:npm_config_registry = "https://registry.npmmirror.com"
    $camoufoxBin = Join-Path $Root "bin\camoufox-cli.cmd"
    $cliJs = Join-Path $fork "dist\cli.js"
    $hasDeps = Test-Path (Join-Path $fork "node_modules\camoufox-js")

    # fork 运行时依赖：dist 是 tsc 编译，camoufox-js/playwright-core/pdf-lib 是 external import，
    # 运行时靠 fork 目录下的 node_modules 解析。tarball 为瘦身 ship 的 fork 不带 node_modules。
    if (-not $hasDeps) {
        Push-Location $fork
        try {
            & $NpmCmd install --omit=dev
            if ($LASTEXITCODE -ne 0) { Write-Warn "camoufox-cli fork deps install 失败"; return }
        } finally { Pop-Location }
    }

    # Windows 不走 `npm install -g $fork`：npm 把 fork 装进 $prefix\node_modules 时撞 fork 源目录
    # 本身（EEXIST: file already exists $Root\camoufox-cli）——Windows npm 不能像 Linux 那样 symlink
    # 到源目录。改仿 openclaw.cmd 写 .cmd shim 直接跑 node $fork\dist\cli.js，fork 的 node_modules
    # 已就位，Node 从 cli.js 向上解析依赖；camoufox-cli JS 用 __dirname 定位自身包根，行为与全局装一致。
    if (-not (Test-Path $cliJs)) { Write-Warn "camoufox-cli 入口未找到：$cliJs；跳过"; return }
    $shimLines = @(
        '@echo off'
        'setlocal'
        'set "HERE=%~dp0.."'
        '"%HERE%\tools\node\node.exe" "%HERE%\camoufox-cli\dist\cli.js" %*'
    )
    Set-Content -Path $camoufoxBin -Value $shimLines -Encoding ASCII
    Write-Ok "camoufox-cli shim written: $camoufoxBin"

    Write-Host "  下 Firefox binary（首次 ~557MB）..."
    Invoke-Streamed { camoufox-cli install }
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
    $listOut = Capture-Streamed { & $ClawCmd plugins list }
    if ($listOut -match "openclaw-weixin") { Write-Ok "openclaw-weixin plugin already installed"; return }
    Invoke-Streamed { & $ClawCmd plugins install "$pkg@$ver" --pin }
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

# ─── 10.5 修复 daemon 启动脚本编码（openclaw 上游 bug 的 workaround）──
# openclaw daemon install 写出的 gateway.cmd / gateway.vbs 是 UTF-8（无 BOM），
# 而 cmd.exe / WScript 按系统 ANSI 代码页读取脚本文件——安装路径含非 ASCII 字符
# （如中文用户名）时路径变乱码，node.exe 找不到，gateway 永远起不来（本机实测）。
# workaround：把长路径替换成 8.3 短路径（纯 ASCII）后以 ASCII 重写；无 8.3 名
# 可用时退回按 ANSI 代码页写（cmd.exe 按 ANSI 读，编码一致即可）。幂等。
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
        Write-Ok "修复 $(Split-Path $f -Leaf) 编码（非 ASCII 路径 → 8.3 短路径）"
    }
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
    Invoke-Streamed { & $ClawCmd daemon install }
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "gateway daemon installed"
        Repair-GatewayCmd
        Invoke-Streamed { & $ClawCmd gateway restart }
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
        # 先停 gateway（对齐 install.sh stop_gateway_if_running）：否则 tar 覆盖
        # tools\node\node.exe、pnpm 重写 node_modules 会撞运行中 gateway 的文件锁
        # （"Can't unlink already-existing object: Permission denied"，本机实测）
        Write-Stage "Stopping gateway before update"
        if (Test-Path $ClawCmd) { Invoke-Streamed { & $ClawCmd gateway stop } }
        Get-Process node -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -like "$Root*" } |
            Stop-Process -Force -ErrorAction SilentlyContinue
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
        # 更新路线也自愈 config（对齐 install.sh：openclaw.json 若被极简化则用 template 修复）
        Place-Config
        Write-Stage "Refreshing gateway env and restarting"
        $envFile = Join-Path $OpenclawHome "daemon.env"
        if (Test-Path $envFile) {
            $lines = Get-Content $envFile
            $lines = $lines | Where-Object { $_ -notmatch "^XIAOBEI_HOME=" }
            $lines += "XIAOBEI_HOME=$Root"
            Set-Content -Path $envFile -Value $lines -Encoding UTF8
            Write-Ok "daemon.env XIAOBEI_HOME refreshed"
        }
        Repair-GatewayCmd
        Invoke-Streamed { & $ClawCmd gateway restart }
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

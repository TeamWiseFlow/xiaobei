# scripts/ 脚本说明

## 脚本总览

| 脚本 | 用途 | 平台 | 拉 tarball | pnpm install --prod | camoufox/weixin/awada | 微信扫码绑定 | gateway daemon |
|------|------|------|:---:|:---:|:---:|:---:|:---:|
| `install.sh` | 首装 / 升级（tarball 路线，GitHub 线路） | macOS + Linux | ✅ | ✅ | ✅ | ✅ | ✅ |
| `install-atomgit.sh` | 首装 / 升级（tarball 路线，atomgit 国内线路） | macOS + Linux | ✅ | ✅ | ✅ | ✅ | ✅ |
| `install.ps1` | 首装 / 升级（tarball 路线，GitHub 线路） | Windows（需 Git Bash/WSL） | ✅ | ✅ | ✅ | ✅ | ✅ |
| `install-atomgit.ps1` | 首装 / 升级（tarball 路线，atomgit 国内线路） | Windows（需 Git Bash/WSL） | ✅ | ✅ | ✅ | ✅ | ✅ |
| `update.sh` | 已 git clone 开发用户的升级 | macOS + Linux | — | — | ✅ | — | ✅ |
| `apply-addons.sh` | 本地测试 addon 改动 | macOS + Linux | — | ✅ | ✅ | — | ✅ |
| `dev.sh` | 开发模式（前台 gateway） | macOS + Linux | — | ✅ | — | — | — |
| `setup-crew.sh` | 仅同步 crew markdown | 跨平台（bash） | — | — | — | — | — |

---

## 构建 tarball 与维护重建

正常发版从发布 tag 取源码。若修复已合入上游、需要重建现有版本，在 GitHub 的 **Build Dist Tarball → Run workflow** 中选择 `master`，`tag` 填目标版本（例如 `v5.8.1`），`source_ref` 填 `master` 或修复后的 commit。留空 `source_ref` 时仍从发布 tag 构建。

维护重建要求所选源码的 `version` 与目标 `tag` 完全一致；它不会修改版本号或移动 tag。tarball 根目录的 `xiaobei.commit` 记录实际源码提交。要使用新 workflow 和已合并的修复，请从 workflow 页面新建任务；旧任务的 Re-run 仍沿用原执行版本。

## install.sh / install-atomgit.sh / install.ps1 / install-atomgit.ps1

**一键首装 / 升级**（预构建 tarball 路线）。新用户首装和老用户升级都跑这一个脚本，重跑即升级、保留运行数据。

国内客户默认推荐 AtomGit 预构建 tarball，配合 `XIAOBEI_GITHUB_PROXY` 下载第三方 GitHub 资源；客户机无需完整构建 OpenClaw。能正常访问 GitHub 也可使用 `install.sh` / `install.ps1`。两条线路安装产物一致。Windows 中文画面使用系统微软雅黑，不下载 Noto 字体；Docker 保留为需要环境隔离的可选渠道。

### Ubuntu / Debian 系统依赖

`install.sh` 和 `install-atomgit.sh` 在下载与解压前检查 `curl`、`tar`、`zstd`、`ca-certificates`。存在缺项时通过 apt 仅安装缺少的包；不安装或替换系统 Python，也不添加 deadsnakes 等 PPA。普通用户按需使用 sudo，root 直接调用 apt。基础工具准备失败时，尚未停止已有 Gateway。

### xiaobei自管 Python

Linux、macOS、Windows、源码安装与 Docker 共用 `scripts/python-runtime.mjs`：

- 解释器版本、构建号及各平台 SHA-256 固定在 `scripts/python-runtime.lock.json`，采用 Astral python-build-standalone 的 CPython 3.12。解释器及其安全更新随小贝发布维护。
- `tools/python-base/<版本-构建-平台>/` 保存完整解释器，`tools/python/` 是该安装实例所有技能共用的 venv；Windows 可执行目录为 `Scripts`，其他平台为 `bin`。依赖仍统一声明在仓根 `requirements.txt`。
- 预构建包内置目标平台原始 Python 压缩包，在客户最终安装路径创建 venv；源码安装从 `~/.xiaobei/cache/` 复用或下载并校验。`XIAOBEI_CACHE_DIR` 可覆盖缓存位置，预下载文件保持原名即可。GitHub 下载支持统一的 `XIAOBEI_GITHUB_PROXY`。
- 依赖始终由该 venv 的 `python -m pip` 安装，不使用 `--user`、`--break-system-packages` 或默认 `--trusted-host`。可用 `XIAOBEI_PYPI_INDEX_URL` 指定包索引。
- 解释器或依赖声明改变时重建环境；旧 venv 保留为 `tools/python.backup-*`，新环境准备失败时恢复旧环境。依赖标记保存在 venv 内，不复用旧用户目录的成功标记。无变化则复用，依赖失败阻止安装继续。
- 安装入口与服务 PATH 接入此 venv；安装器使用 OpenClaw 原生 `tools.exec.pathPrepend`，保证 agent 临时脚本的 `python` / `python3` 默认指向该环境。保留用户其他 PATH 项及各 agent 的执行模式、审批与白名单。远程 node 或独立 sandbox 需要在其自身环境部署运行时，不能使用宿主路径代替。
- 内部 crew 模板不预写 `### Python 环境`；每次 setup 清理旧区块，在 AGENTS.md 的 `## Tools` 下按实际路径重新生成唯一一份，保留其他备注。新建、既有及尚未注册的 internal 工作区都走同一入口，Python configure 复用该生成器。临时任务需要独立依赖时 spawn IT Engineer，使用同一自管解释器准备任务环境。
- `workspace-guides.py` 生成的真实换行、exec 和 Python 提示统一先删除旧段落再写入当前版本，段落外的用户正文保留；不按已有标题跳过，也不做逐条对齐。
- 提示生成器只处理 internal。sales-cs 等 external crew 的全部操作规范直接由模板提供：禁止自行创建、修改或执行 Python 脚本，缺少能力时写入本工作区 `feedback/YYYY-MM-DD.md`，不要求 spawn IT Engineer；旧实例的提示由维护者按需调整。技能、命令白名单同步及共享业务知识旧路径迁移继续保留。

迁移不卸载用户的旧 Python、依赖或 PPA。不要直接搬运 venv；改变安装目录时重新运行安装器。Docker 的解释器与 venv 留在镜像程序层，不新增持久卷。

已有锁定解释器时不再读取或下载其压缩包。依赖指纹只比较有效声明，忽略行内注释，保留 URL 的哈希片段；依赖约束与实际包清单一致时跳过安装。旧版含注释的指纹在核对其原始清单、解释器和实际包版本后原位迁移，不因此重建环境或增加备份；真正修改依赖约束或环境发生漂移时仍走重建与失败回滚。

下面的一行安装命令使用 `curl` 获取脚本，因此极简系统若连 curl 或 CA 证书也没有，需要先准备这两项，或先通过浏览器取得脚本再本地执行：

```bash
sudo apt update
sudo apt install -y curl ca-certificates
```

### 安装命令

```bash
# macOS / Linux（GitHub 线路）
bash -c "$(curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh)"
# macOS / Linux（国内推荐；脚本与主程序从 AtomGit 下载）
export XIAOBEI_GITHUB_PROXY="https://ghfast.top/"
bash -c "$(curl -fsSL https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.sh)"
```

```powershell
# Windows（PowerShell，需 Git Bash 或 WSL；GitHub 线路）
irm https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.ps1 | iex
# Windows（国内推荐；脚本与主程序从 AtomGit 下载）
$env:XIAOBEI_GITHUB_PROXY="https://ghfast.top/"
irm https://raw.atomgit.com/wiseflow/xiaobei/raw/master/scripts/install-atomgit.ps1 | iex
```

> **Windows 用户请以管理员身份运行 PowerShell 再安装**（右键 PowerShell → "以管理员身份运行"）。
> 原因：安装过程中的 `setup-crew.sh` 会用 `ln -s` 把 crew skills 软链到 workspace，创建 NTFS 符号链接需要管理员权限（或开启 Windows 开发者模式）。
> - **管理员模式**：软链创建成功，仓库里改 skill 即生效，无需重跑安装。**推荐。**
> - **普通用户（不开开发者模式）**：软链失败时自动回退到拷贝（`cp -rf`），功能完全可用，但仓库 skill 改动不会自动同步到 workspace，需要重跑 `setup-crew.sh --force`。
> - **普通用户 + 开启开发者模式**：`设置 → 隐私和安全性 → 开发者选项 → 开发人员模式` 打开，即可创建软链，无需管理员。

常用参数（公共开关在四个 install 脚本中同构；sh 走 `--flag`，ps1 走 `$env:XIAOBEI_FLAG=1`；Bash 专用参数单独标注）：

| 参数（sh） | env（ps1） | 作用 |
|------|------|------|
| `--force` | `XIAOBEI_FORCE=1` | 强覆盖已有运行数据（`~/.openclaw`）；默认已装机器重跑只更新 program，不碰运行数据 |
| `--skip-bind` | `XIAOBEI_SKIP_BIND=1` | 跳过末尾微信扫码绑定（CI / 自动化） |
| `--skip-browser` | `XIAOBEI_SKIP_BROWSER=1` | 跳过 Camoufox Firefox 与共享 Chromium 下载（冒烟 / CI） |
| `--skip-service` | —（仅 Bash） | 安装运行环境和配置，跳过系统服务的安装、停止和重启；隐含 `--skip-bind`，自动化账号迁移留待 Gateway 启动后的正常安装/升级收尾 |
| `--no-prompt` | `XIAOBEI_NO_PROMPT=1` | 关闭交互提示（CI / 自动化，隐含 `--skip-bind`） |
| `--root <dir>` | `XIAOBEI_HOME=<dir>` | 程序目录覆盖（默认 `~/xiaobei`） |
| — | `XIAOBEI_TAG=<tag>` | 指定版本 tag（默认拉最新 release；sh 也认 `XIAOBEI_TAG` env） |
| — | `XIAOBEI_TARBALL=<path>` | 本地已下好的 tarball 路径，跳过下载（sh 也认此 env） |
| `--verbose` | — | 打印 debug 输出（仅 sh） |

环境变量：`XIAOBEI_REPO`（仅 GitHub 线路认，atomgit 线路硬编码 `wiseflow/xiaobei`）、`XIAOBEI_TAG`（指定版本）、`XIAOBEI_TARBALL`（本地已下好的 tarball 路径，跳过下载）、`XIAOBEI_HOME`（程序目录覆盖）、`OPENCLAW_HOME`（运行数据目录覆盖）。

### GitHub 下载代理

`XIAOBEI_GITHUB_PROXY` 是可选的 HTTPS URL 前缀，例如 `https://ghfast.top/`。不设置或设为空时保持原有下载线路；启用后将 GitHub 下载地址改写成 `https://ghfast.top/https://github.com/...`。可以更换代理站点，不能包含账号密码、查询参数或 fragment。

| 入口 | 启用后的行为 |
|------|------|
| 四个 install 脚本 | GitHub release/raw/API 地址加前缀；AtomGit API、tarball/CDN 保持原线路 |
| Camoufox、GeoIP、指纹模型 | 使用统一前缀；版本锁、缓存与 SHA-256 校验保留 |
| Matrix 原生库 | 通过依赖支持的 `MATRIX_SDK_CRYPTO_DOWNLOADS_BASE_URL` 下载 |
| 源码 update/apply、npm/pnpm 的 GitHub Git 依赖 | 通过进程级 Git 配置改写 HTTPS/SSH 地址；不修改 remote 或全局 Git 配置 |
| npm/pnpm、Node headers | 未自定义时分别使用 npmmirror 包源和 Node headers 镜像 |
| Playwright Chromium | 未自定义时使用 `https://registry.npmmirror.com/-/binary/playwright`，下载超时 120 秒 |

共享资源安装入口 `install-browser.mjs`、`install-skill-deps.mjs` 与 deck-render 安装器也识别该变量。现有 `PLAYWRIGHT_DOWNLOAD_HOST`、各浏览器专用下载地址、`MATRIX_SDK_CRYPTO_DOWNLOADS_BASE_URL` 等镜像设置继续生效。安装器将配置传给子进程，不写入 Gateway 配置或系统环境文件。新终端里首装、重跑或升级时需重新设置变量。

部分代理（包含本次检查的 ghfast）不支持 GitHub API。推荐使用 AtomGit 查询最新版本；若选择 GitHub 安装线路，应额外指定 `XIAOBEI_TAG`。代理模式查询失败时安装器会提示处理，不会通过 gh CLI 自动绕回 GitHub 直连。最外层下载 GitHub 安装脚本的 `curl` / `irm` 发生在脚本运行前，需要调用者自行加前缀；上面的 AtomGit 命令无需处理这个问题。

该功能需要使用包含 `browser/scripts/download-network.mjs` 的新 tarball；仅更新 bootstrap 脚本不能让旧发行包获得资源代理能力，启用变量时遇到旧包会明确报错。

此变量不是通用 HTTP/HTTPS 代理。正式 tarball 已内置 uBlock 和 GeoIP；源码或旧包缺少内置 uBlock 时，Mozilla 下载仍按原地址访问。apt/brew/winget 等系统包管理器、ONNX 可选 NuGet 下载等也按各自配置访问，不对这些地址机械添加 GitHub 前缀；完整国内网络安装还需逐项验证这些来源。无 CUDA 的 CPU 云电脑可另设 `ONNXRUNTIME_NODE_INSTALL_CUDA=skip`，此开关不自动改变 GPU 安装选项。

#### 浏览器资源下载缓存

主程序 tarball、Camoufox、uBlock 和 GeoIP 的预下载文件统一放在 `~/.xiaobei/cache/`，保留下载链接中的原始文件名、不要解压，直接重跑一键安装脚本即可，无需额外环境变量。例如当前 uBlock 文件为 `~/.xiaobei/cache/ublock_origin-1.74.0.xpi`，浏览器文件名见 `browser/assets.lock.json` 的平台 `asset.name`。资源安装器会先核对 SHA-256，再使用本地文件；不匹配则报错，不跳过校验或自动换文件。

自定义公共缓存目录用 `XIAOBEI_CACHE_DIR`；只覆盖浏览器资源目录用 `XIAOBEI_BROWSER_DOWNLOADS`，其优先级更高。仍可单独运行 `~/xiaobei/tools/node/bin/node ~/xiaobei/browser/scripts/install-assets.mjs`，它使用相同的默认缓存和覆盖规则。缓存中缺少的资源继续从原地址下载；指纹模型使用 SDK 自身的安装目录。

正式 tarball 在构建时通过 `scripts/prepare-browser-data.mjs` 保存 `browser/assets.lock.json` 固定的 GeoIP 数据库和 uBlock 原始 XPI。安装时优先读取包内 `browser/data/geoip-aio-all-<版本>.mmdb` 和 `browser/data/ublock_origin-<版本>.xpi`，校验 SHA-256，uBlock 解压后再核对 manifest 版本；客户机无需访问这两项资源的上游下载地址。源码部署或旧包缺少内置文件时，才依次尝试预下载缓存和上游地址。

GeoIP 上游每周构建且只保留最近两版，随包保存使旧包不依赖上游历史 release。更新资源 pin 必须同步版本、URL、SHA-256；GeoIP 运行目录使用带版本号的文件名，避免与旧数据库的校验值混用。固定上游文件已删除且没有可信缓存时，构建应失败并要求维护者更新 pin，不在客户安装时静默改用 latest。uBlock 保留原始签名 XPI，不重新打包或修改其内容。

Camoufox、uBlock 和 GeoIP 的内置资源下载默认包含首次最多尝试 5 次。连接中断、HTTP 408/429/5xx 会分别等待 3、6、12、24 秒后重试；同一次安装中优先用 Range 续传，服务端不支持时从头重下。每 30 秒显示下载进度，连续 2 分钟没有新数据才超时，没有固定的总下载时限。HTTP 403/404、磁盘写入错误和 SHA-256 校验失败会立即报错。指纹模型沿用 SDK 自带的重试，并打印请求次数及错误原因。

当前锁定的 Camoufox 158.0.1-beta.41 Linux x64 包为 1,303,577,033 字节（约 1.30 GB），支持断点续传。安装结束或重试耗尽后临时文件仍会清理；需要跨次安装保留部分下载时，应使用上面的独立缓存和续传下载器。资源安装器末尾出现 `Camoufox ... ready at ...` 才表示资源安装完成。

源码用户使用同一变量，例如：

```bash
export XIAOBEI_GITHUB_PROXY="https://ghfast.top/"
bash scripts/update.sh --atomgit
```

执行流程：

1. 检测 OS + arch → 选 tarball asset（linux-x64 / mac-arm64 / mac-x64 / win-x64）
2. 解析最新 release tag（GitHub 线路走 `api.github.com`，回退 gh CLI；atomgit 线路走 `api.atomgit.com/api/v5`；`XIAOBEI_TAG` 直接指定）
3. 下载预构建 tarball → 解压到 `~/xiaobei/`（程序目录）
4. `pnpm install --prod --frozen-lockfile`（用自带的 portable Node + pnpm，在 `openclaw/` 下）
5. 使用小贝自管 Python 3.12 venv 安装技能依赖（各平台共用机制）
6. awada 本地插件 deps（`awada/` 下 `npm install --omit=dev` 装 ws+zod）
7. `install-browser.mjs`：先安装 `browser/package.json` 锁定的 Playwright，再调用 `install-playwright.mjs` 预装配套 Chromium headless shell，并准备 Camoufox 固定资产。驱动仅在 `browser/node_modules`，唯一 Chromium 缓存为 `browser/.browsers`；`--skip-assets` 同时跳过 Chromium 下载。已有浏览器资源会复用。
8. `install-deck-render.sh`（Windows 为 `.ps1`）：安装或校验 FFmpeg/FFprobe、锁定 HyperFrames/GSAP、实例共享 Playwright/Chromium 与中文字体（Linux/macOS 为 Noto Sans CJK SC，Windows 为系统微软雅黑）；重跑会复用已有依赖。
9. `openclaw plugins install @tencent-weixin/openclaw-weixin@<pin> --pin --accept-capabilities`（微信插件，走 npmmirror）
10. 首装：放 `config-templates/openclaw.json` → `~/.openclaw/` + 预填微信 binding + `setup-crew.sh` + 交互收 `AWK_API_KEY` + `openclaw daemon install` + restart
11. 首装末尾：自动出微信绑定二维码（已绑过则跳过），手机扫码确认即用
12. 升级：使用目标版本迁移并校验配置、执行原生 Doctor，再刷 `daemon.env` 路径并重启 Gateway，保留工作区、账号与会话

> 目录职责：`~/xiaobei/` = 程序（引擎 + 模板 + 脚本 + 工具 + wrapper）；`~/.openclaw/` = 运行数据（openclaw.json + daemon.env + workspaces + logs）。升级只换 `~/xiaobei/`，用户数据不动。

GitHub PR CI 检查 Linux/macOS 的便携 pnpm 离线启动、补丁应用、依赖安装、引擎构建、CLI 入口与技能依赖重复安装。发布 workflow 在上传 tarball 前对 Linux 包执行首装和重跑升级，检查用户配置、工作区文件、登录态文件和 API key 保留；冒烟跳过浏览器下载与微信扫码，服务托管及真实平台登录仍需实际环境验证。

`prepare-portable-pnpm.mjs` 从仓根 `package.json` 的 `packageManager` 读取 pnpm 版本及 SHA-512，下载并校验 launcher 和四个平台对应的 `@pnpm/exe.*` 原生包，保留 `tools/pnpm/bin/pnpm.mjs` 安装入口。原生文件按启动器支持的 `pnpm-native` / `pnpm-native.exe` 路径放在 pnpm 根目录，与 `dist/` 同级，确保生命周期脚本能找到内置的 node-gyp。pnpm 12 的 npm 包不再含 `dist/pnpm.mjs`，只复制 launcher 会在首次使用时额外下载原生文件，因此 tarball 必须携带目标平台的原生文件；引擎的 `node_modules` 仍由用户安装时重建。PR CI 使用 `--platform host` 准备本机包，禁止启动器联网下载，验证版本和 node-gyp 脚本；Linux/macOS 还会在隔离项目中直接调用 `install.sh`、`install-atomgit.sh` 的真实依赖安装函数，检查完整命令参数。重试次数通过 pnpm 12 支持的进程环境变量 `PNPM_CONFIG_FETCH_RETRIES=5` 设置，不使用其 CLI 不支持的 `--fetch-retries`；请求超时和并发参数保持不变。发布使用默认 `--platform all` 准备四个平台，再用 portable Node 验证 Linux 入口。包结构、校验或安装参数失败会在 OpenClaw clone/build 前报错。下载超时按连续无进展计算，持续收到数据的慢速下载可继续完成。

---

## update.sh

**已 `git clone` 仓做开发的用户的升级路线**。fetch + rebuild，校验并补齐变化的依赖；替换引擎依赖和构建前停止 Gateway，保留已安装服务和用户数据。普通用户用 `install.sh` 即可，不需要这个脚本。

更新脚本在 `apply-addons.sh` 后调用同一个 deck-render 安装脚本，校验 npm 包、浏览器与字体。tarball 安装脚本的 `--skip-browser`（PowerShell 为 `XIAOBEI_SKIP_BROWSER=1`）会跳过 Chromium 下载与 Camoufox Firefox 下载，供 CI 冒烟使用；正常安装与更新会预装。

Windows 缺少 FFmpeg/FFprobe 时安装器通过 winget 安装 `Gyan.FFmpeg`。Windows 版 deck-render 检查系统微软雅黑的 Light、Regular、Bold 字体文件，不联网下载 Noto；若系统缺少微软雅黑，应先启用 Windows 简体中文字体功能。

```bash
./scripts/update.sh              # fetch + apply addons + build + restart
./scripts/update.sh --skip-crew  # 跳过 crew workspace 同步
./scripts/update.sh --skip-sync  # 验收本地源码，跳过产品仓 fetch/reset，引擎仍按 pin 升级
```

`update.sh` 的引擎构建与 Control UI 构建成功后才运行配置/状态收尾，避免新 pin 配合旧 dist 迁移。脚本在替换依赖前通过原生 `daemon stop` 释放正在使用的引擎；收尾失败会中止，排除错误后重跑即可。`install-browser.mjs --defer-config` 用于这些统一升级流程，独立调用默认仍会同步插件配置。

安装/升级流程的原生停服命令显式传入 `--force`，表示授权维护时停服，兼容非交互终端。该参数只传给 OpenClaw 的服务命令，与安装/升级脚本用于覆盖工作区文件的 `--force` 分开。

引擎同步只请求 `openclaw.version` 锁定的 commit；若远端拒绝按 SHA 拉取，只尝试该版本的发布标签，并再次核对锁定 commit 是否可用。禁用自动拉取标签和子模块，不同步所有分支/标签，也不执行全量历史补齐；已有本地历史保留。目标获取失败时，在重置源码、停止服务前退出。目标提交所需且本地缺失的历史对象仍会下载，已有 `.git` 不会因此自动缩小。

小贝统一使用安装器或 `update.sh` 升级锁定引擎。配置模板、统一升级迁移及 Docker 已有卷启动均强制设置 `update.checkOnStart=false`、`update.auto.enabled=false`，关闭 OpenClaw 自带的后台检查和自动升级，避免 Gateway 重启后又拉取上游开发分支。保留更新配置中的其他字段，不影响小贝安装器正常升级。

源码升级使用上游支持的运行时构建模式（`OPENCLAW_RUN_NODE_SKIP_DTS_BUILD=1`），不生成开发用类型声明；发布 CI 保留完整构建检查。

旧定时任务使用存储的推理账号（如 OAuth）时，新宿主要求任务持有账号绑定。安装/update 在 Gateway 启动后、成功提示前自动运行账号迁移；默认重启服务的 apply-addons 也会执行。没有配置存储账号时直接跳过，不要求普通 provider API Key 用户设置账号参数。启动前的检查不可用时，启动后的迁移会重新检查；迁移失败会明确报错，不把未完成的升级报告为成功。仅显示 `enabled=true` 或下一次时间不代表任务能运行。

自动迁移优先保留模型中明确指定的账号，其次采用对应供应商的 `auth.order` 首选账号，未配置顺序时使用该供应商唯一的配置账号。多个账号仍无法确定时，在修改任何任务前报出任务 ID 和所需选择；不改已有账号绑定、停用任务或系统任务。重复升级会跳过已完成的任务。

同一供应商已经明确配置 provider API Key、且任务模型未指定 profile 时，保留现有认证路线，不因另有已登录账号就切换账号或计费来源。

也可以在 Gateway 启动后单独预览或运行自动迁移：

```bash
node scripts/repair-automation-inference.mjs --auto
node scripts/repair-automation-inference.mjs --auto --apply
```

需要人工指定账号时，使用 `--profile <账号ID>`，可重复传入 `--job <任务ID>` 限定任务；本机只有一个配置账号时也支持：

```bash
node scripts/repair-automation-inference.mjs --use-current-account
node scripts/repair-automation-inference.mjs --use-current-account --apply
```

迁移通过原生 RPC 和配置 revision 检查收纳账号，保留原模型继承、任务正文、时间表和投递设置，不手写数据库、不手动补跑任务。执行前的快照和逐项结果写在 state 目录的 `backups/automation-inference/`；脚本不伪造成功运行记录。

任务不必固定模型：没有任务级 `model` / `fallbacks` 覆盖时，继续读取对应 crew 在 `openclaw.json` 中的模型配置。账号归属与模型选择分开记录；当前锁定宿主只允许已绑定任务使用同一供应商且与该账号兼容的候选模型，因此跨供应商 fallback 不会因继承配置自动获得授权，不能把“配置已继承”当成“整条回退链可执行”。

---

## apply-addons.sh

**应用 addon 改动后一步到位**。用于新增/修改了 patch、skill 或 crew 模板后的本地测试。不拉远程代码，不升级 openclaw 版本——直接用本地已有源码。

```bash
./scripts/apply-addons.sh              # 应用 addons + build + restart gateway
./scripts/apply-addons.sh --skip-crew  # 跳过 crew workspace 同步
./scripts/apply-addons.sh --no-build   # 不执行 pnpm build（调用方自行处理）
./scripts/apply-addons.sh --no-restart # 不重启 gateway service
./scripts/apply-addons.sh --force      # 强制覆盖已有 workspace 文件
```

执行流程：

1. 恢复 `openclaw/` 到干净状态（`git reset --hard`）
2. 同步 `config-templates/` 中的配置项到运行时 `openclaw.json`
3. 安装全局 skills（`skills/` → `openclaw/skills/`）
4. 依次加载各 addon：overrides → patches → skills → crew 模板
5. `pnpm install`（仅有 overrides/patches 时）
6. `setup-crew.sh`（同步 crew workspace，可 `--skip-crew` 跳过）
7. `pnpm build`（编译 dist，可 `--no-build` 跳过）
8. `finalize-openclaw-upgrade.mjs`：核对构建的版本与 SHA，运行原生配置迁移、浏览器插件配置、Doctor 和审批同步；`--no-build` 时交由调用方在构建后执行
9. 重启 Gateway（可 `--no-restart` 跳过）

---

## dev.sh

**开发模式前台运行**。自动 apply addons，但**不 build**——需要用户自行 `cd openclaw && pnpm build`。

```bash
cd openclaw && pnpm build && cd ..   # 首次或修改源码后手动 build
./scripts/dev.sh gateway             # 前台启动 gateway
./scripts/dev.sh cli config set ...  # 运行 openclaw CLI 命令
```

---

## setup-crew.sh

**仅同步 crew workspace 的 markdown 文件**。不碰源码，不 build，不重启。适合只更新了 crew 模板内容（SOUL.md、AGENTS.md 等）的场景。

```bash
./scripts/setup-crew.sh          # 同步配置并更新生成提示，保留用户正文
./scripts/setup-crew.sh --force  # 强制覆盖（含 MEMORY.md 等个性化文件）
```

---

## 典型场景速查

| 场景 | 命令 |
|------|------|
| 小白首装（macOS/Linux，GitHub） | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh)"` |
| 小白首装（macOS/Linux，国内 atomgit） | 先 `export XIAOBEI_GITHUB_PROXY="https://ghfast.top/"`，再运行上面的 AtomGit 安装命令 |
| 小白首装（Windows，GitHub） | **以管理员身份打开 PowerShell**，然后 `irm https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.ps1 \| iex` |
| 小白首装（Windows，国内 atomgit） | **以管理员身份打开 PowerShell**，先设置 `$env:XIAOBEI_GITHUB_PROXY="https://ghfast.top/"`，再运行上面的 AtomGit 安装命令 |
| 老用户升级 | 重跑对应线路的 install 脚本（保留 `~/.openclaw` 运行数据） |
| 已 git clone 的开发者升级 | `./scripts/update.sh` |
| 修改了 patch 后测试 | `./scripts/apply-addons.sh` |
| 修改了 crew markdown 后同步 | `./scripts/setup-crew.sh` |
| 开发调试（前台运行） | `cd openclaw && pnpm build && cd .. && ./scripts/dev.sh gateway` |

OpenClaw 2026.10.10 的微信插件安装需要显式能力授权。安装器仍使用 `openclaw-weixin.version.json` 的固定版本，先完成该插件的安装和原生授权，再运行 Doctor 与服务重启。

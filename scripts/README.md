# scripts/ 脚本说明

## 脚本总览

| 脚本 | 用途 | 平台 | 拉 tarball | pnpm install --prod | camoufox/weixin/awada | 微信扫码绑定 | gateway daemon |
|------|------|------|:---:|:---:|:---:|:---:|:---:|
| `install.sh` | 首装 / 升级（tarball 路线） | macOS + Linux | ✅ | ✅ | ✅ | ✅ | ✅ |
| `install.ps1` | 首装 / 升级（tarball 路线） | Windows（需 Git Bash/WSL） | ✅ | ✅ | ✅ | ✅ | ✅ |
| `update.sh` | 已 git clone 开发用户的升级 | macOS + Linux | — | — | ✅ | — | ✅ |
| `apply-addons.sh` | 本地测试 addon 改动 | macOS + Linux | — | ✅ | ✅ | — | ✅ |
| `dev.sh` | 开发模式（前台 gateway） | macOS + Linux | — | ✅ | — | — | — |
| `setup-crew.sh` | 仅同步 crew markdown | 跨平台（bash） | — | — | — | — | — |

---

## install.sh / install.ps1

**一键首装 / 升级**（预构建 tarball 路线）。新用户首装和老用户升级都跑这一个脚本，重跑即升级、保留运行数据。

```bash
# macOS / Linux（默认走 GitHub release，国内用户加 --atomgit 切国内镜像）
bash -c "$(curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh)"
# 国内镜像（atomgit → GitCode CDN，全程国内直连）
bash -c "$(curl -fsSL https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.sh)" -s -- --atomgit
```

```powershell
# Windows（PowerShell，需 Git Bash 或 WSL）
irm https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.ps1 | iex
# 国内镜像
irm https://raw.githubusercontent.com/TeamWiseFlow/xiaobei/master/scripts/install.ps1 | iex -- -Atomgit
```

常用参数（install.sh / install.ps1 同构）：

| 参数 | 作用 |
|------|------|
| `--atomgit` / `-Atomgit` | 切到 atomgit 国内镜像（tarball 走 atomgit.com → GitCode CDN，tag 走 api.atomgit.com v5） |
| `--github` / `-GitHub` | 显式切回 GitHub release（默认即是，保留向后兼容） |
| `--mirror <url>` / `-Mirror <url>` | 自定义镜像站根（覆盖默认 GitHub；自定义 Gitea 镜像走 `/api/v1` 推导） |
| `--force` / `-Force` | 强覆盖已有运行数据（`~/.openclaw`）；默认已装机器重跑只更新 program，不碰运行数据 |
| `--skip-bind` / `-SkipBind` | 跳过末尾微信扫码绑定（CI / 自动化） |
| `--skip-browser` / `-SkipBrowser` | 跳过 camoufox-cli 浏览器二进制安装（冒烟 / CI，省 ~557MB Firefox 下载） |
| `--no-prompt` / `-NoPrompt` | 关闭交互提示（CI / 自动化，隐含 `--skip-bind`） |
| `--root <dir>` / `-Root <dir>` | 程序目录覆盖（默认 `~/xiaobei`） |

环境变量：`XIAOBEI_REPO`、`XIAOBEI_SOURCE`（`atomgit` / `github`）、`XIAOBEI_MIRROR`、`XIAOBEI_TAG`（指定版本）、`XIAOBEI_TARBALL`（本地已下好的 tarball 路径，跳过下载）、`XIAOBEI_HOME`、`OPENCLAW_HOME`。

执行流程：

1. 检测 OS + arch → 选 tarball asset（linux-x64 / mac-arm64 / mac-x64 / win-x64）
2. 解析最新 release tag（`--atomgit` 走 `api.atomgit.com/api/v5`；默认走 GitHub API；`XIAOBEI_TAG` 直接指定）
3. 下载预构建 tarball → 解压到 `~/xiaobei/`（程序目录）
4. `pnpm install --prod --frozen-lockfile`（用自带的 portable Node + pnpm，在 `openclaw/` 下）
5. `pip install --user`（skills 的 Python 依赖）
6. awada 本地插件 deps（`awada/` 下 `npm install --omit=dev` 装 ws+zod）
7. `camoufox-cli install`（下 Firefox 反指纹浏览器，约 557MB，仅首装）
8. `openclaw plugins install @tencent-weixin/openclaw-weixin@<pin> --pin`（微信插件，走 npmmirror）
9. 首装：放 `config-templates/openclaw.json` → `~/.openclaw/` + 预填微信 binding + `setup-crew.sh` + 交互收 `AWK_API_KEY` + `openclaw daemon install` + restart
10. 首装末尾：自动出微信绑定二维码（已绑过则跳过），手机扫码确认即用
11. 升级：只刷 `daemon.env` 路径 + restart gateway，不碰运行数据

> 目录职责：`~/xiaobei/` = 程序（引擎 + 模板 + 脚本 + 工具 + wrapper）；`~/.openclaw/` = 运行数据（openclaw.json + daemon.env + workspaces + logs）。升级只换 `~/xiaobei/`，用户数据不动。

---

## update.sh

**已 `git clone` 仓做开发的用户的升级路线**。fetch + rebuild，不重装依赖、不卸 daemon、不碰运行数据。普通用户用 `install.sh` 即可，不需要这个脚本。

```bash
./scripts/update.sh              # fetch + apply addons + build + restart
./scripts/update.sh --skip-crew  # 跳过 crew workspace 同步
```

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
8. `systemctl restart`（重启 gateway，可 `--no-restart` 跳过）

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
./scripts/setup-crew.sh          # 幂等同步（不覆盖已有文件）
./scripts/setup-crew.sh --force  # 强制覆盖（含 MEMORY.md 等个性化文件）
```

---

## 典型场景速查

| 场景 | 命令 |
|------|------|
| 小白首装（macOS/Linux） | `bash -c "$(curl -fsSL https://atomgit.com/wiseflow/xiaobei/raw/branch/master/scripts/install.sh)"` |
| 小白首装（Windows） | `irm https://atomgit.com/wiseflow/xiaobei/raw/branch/master/scripts/install.ps1 \| iex` |
| 老用户升级 | 重跑 install 脚本（保留 `~/.openclaw` 运行数据） |
| 已 git clone 的开发者升级 | `./scripts/update.sh` |
| 修改了 patch 后测试 | `./scripts/apply-addons.sh` |
| 修改了 crew markdown 后同步 | `./scripts/setup-crew.sh` |
| 开发调试（前台运行） | `cd openclaw && pnpm build && cd .. && ./scripts/dev.sh gateway` |

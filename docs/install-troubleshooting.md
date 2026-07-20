# wiseflow 安装排障

> 配套 `scripts/install.sh`（curl 一键首装）与 `scripts/update.sh`（升级）。
>
> **两个路径，别混淆**：
> - `~/xiaobei/` = wiseflow 源码 checkout 目录（install.sh clone 的目标，含 `openclaw/` 上游子仓 + `patches/` + `crews/` + `skills/` + `awada/` + `scripts/`，仓内结构保持完整，由软链注入到运行态）
> - `~/.openclaw/` = openclaw 运行态 home（`openclaw.json`、`daemon.env`、`workspaces/`、`sessions/`、camoufox-cli profile、`skills/` 软链目标都在此）
>
> 排障前先确认这两个目录的存在与结构：
> `ls ~/xiaobei/{openclaw,patches,crews,skills,scripts} && ls ~/.openclaw/{openclaw.json,.env,daemon.env,workspaces,skills}`

## 速断：openclaw doctor

openclaw 自带 `doctor` 命令做配置迁移 + 健康检查 + 自修复建议，是排障第一动作：

```bash
cd ~/xiaobei/openclaw
pnpm openclaw doctor
```

输出会标出每个异常项的修复建议（如 `agents.defaults.workspace` 路径过期、`channels.feishu` 字段下沉未做等）。**优先按 doctor 输出修，再回头看本文档**。

doctor 本身有 `--non-interactive` flag，CI / 自动化场景可用：

```bash
pnpm openclaw doctor --non-interactive
```

## 常见症状 → 速查表

| 现象 | 速断 | 修复 |
|------|------|------|
| `bash: pnpm: command not found` 装好后新开 shell 才报 | corepack 装的 pnpm 路径未在 PATH | `corepack enable` 或 `npm install -g pnpm@11.2.2`，新开 shell 验证 |
| `node: v18.x.x` 装好但版本低于 22.19 | 系统 node 太旧，install.sh 装的新版未生效 | mac: `brew link --overwrite --force node@24`；Linux: 检查 nvm/nodenv 当前版本，或 `source ~/.nvm/nvm.sh && nvm use 24` |
| `openclaw: command not found` 但 `pnpm openclaw --version` 能跑 | 全局 bin 未在 PATH | `pnpm -C ~/xiaobei/openclaw openclaw` 路线绕过全局 bin；或 `npm install -g openclaw` 装个 stub（但会拉滞后版，不推荐） |
| onboard 报 `Non-interactive setup requires explicit risk acknowledgement` | 在 CI/无 TTY 跑 onboard 没加 `--accept-risk` | 加 `--non-interactive --accept-risk`，且补全所有 `--auth-choice` / `--custom-api-key` 等必填 flag |
| onboard `--skip-channels` 后 channel 段仍问 | openclaw 版本低于本仓 `openclaw.version` 锁的 commit | `cd ~/xiaobei && ./scripts/update.sh` 重 checkout + build |
| `pnpm install` 报 `ERR_PNPM_OUTDATED_LOCKFILE` | lockfile 与 package.json 不同步（仓里有未提交改动） | `pnpm install --no-frozen-lockfile`（install.sh 已走此路） |
| `pnpm build` 报 `tsc: error TS2307: Cannot find module '...'` | patch 未应用或应用不完整 | `cd ~/xiaobei && bash scripts/apply-addons.sh --force` 重跑 patches |
| gateway 启动报 `EADDRINUSE 0.0.0.0:18789` | 端口被占（旧 gateway 没退干净） | `lsof -i :18789` 找进程，`kill -9 <pid>`；或改 `~/xiaobei/openclaw/package.json` 的 gateway 默认端口 |
| gateway 启动报 `OPENCLAW_GATEWAY_TOKEN missing` | 首次启动未生成 token | `cd ~/xiaobei/openclaw && pnpm openclaw gateway install --force` 重装会生成；或手动设 env |
| camoufox-cli install 卡在 Firefox 下载（557MB） | 网慢 | 等即可；卡半小时以上重跑 `camoufox-cli install`（幂等） |
| WSL2 下浏览器无头报 `DISPLAY not set` | install.sh 的 WSL 棵测没生效 | 手动 `export DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir`，重启 gateway |
| agent 跑任务报 `skill script not executable` | setup-crew.sh 的 chmod 段被跳过 | `cd ~/xiaobei && bash scripts/setup-crew.sh` 重跑（幂等） |
| agent 报 `escaped skill path` warning | skill 软链 target 未在 `skills.load.allowSymlinkTargets` | `cd ~/xiaobei && bash scripts/apply-addons.sh` 重跑（setup-crew.sh 会注入） |

## 分段排障

### 1. Node / pnpm / git 未就绪

install.sh 在 macOS 走 `brew install node@24`，Linux 走 NodeSource 官方脚本。如果失败：

```bash
# 手动验装
node -v   # 应 ≥ v22.19
pnpm --version  # 应为 11.2.2
git --version
```

- **mac brew 装失败**：先 `xcode-select --install` 装 CLT，再 `brew install node@24`
- **Linux NodeSource 失败**：手动加 repo：`curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash - && sudo apt-get install -y nodejs`
- **pnpm 缺**：`npm install -g pnpm@11.2.2`（不走 corepack 的回退）

### 2. clone / checkout 段失败

```bash
ls ~/xiaobei/.git                # 应存在
git -C ~/xiaobei rev-parse HEAD  # 应有 commit hash
ls ~/xiaobei/openclaw/.git       # 应存在
source ~/xiaobei/openclaw.version
git -C ~/xiaobei/openclaw rev-parse HEAD  # 应等于 $OPENCLAW_COMMIT
```

- **clone wiseflow 失败**：网问题或 GitHub 限速，`git clone https://github.com/TeamWiseFlow/xiaobei.git ~/xiaobei` 重试；或用 atomgit 镜像 `https://atomgit.com/wiseflow/xiaobei.git`
- **checkout openclaw@pin 失败**：`git -C ~/xiaobei/openclaw fetch --unshallow origin` 深化历史后重试

### 3. apply-addons 段失败

apply-addons.sh 是 patches + skills + crew 模板 + awada + Python/npm deps 的总安装段，失败时通常报在 patch 应用：

```bash
cd ~/xiaobei
bash scripts/apply-addons.sh --force  # --force 重跑覆盖
```

常见 patch 失败原因：`openclaw/` 子目录漂移到非 `openclaw.version` 锁的 commit。修复：

```bash
cd ~/xiaobei/openclaw
git fetch origin
git checkout "$(source ~/xiaobei/openclaw.version && echo $OPENCLAW_COMMIT)"
git reset --hard HEAD
git clean -fd
cd ~/xiaobei
bash scripts/apply-addons.sh --force
```

### 4. pnpm build 段失败

openclaw 是大 monorepo，build 偶发 OOM。Node 默认 heap 4GB，build 段可显式抬：

```bash
cd ~/xiaobei/openclaw
NODE_OPTIONS="--max-old-space-size=8192" pnpm build
```

`pnpm ui:build` 失败无害（CLI 不依赖 UI），可跳：

```bash
pnpm build  # 跑通即可
# pnpm ui:build 失败不影响 CLI
```

### 5. camoufox-cli 段失败

- **`npm install -g camoufox-cli` 失败**：网或 npm registry 问题，`npm config set registry https://registry.npmmirror.com` 切国内镜像后重试
- **`camoufox-cli install` 失败**：Firefox 二进制下载问题，`camoufox-cli install --verbose` 看具体错误；也可手动从 [camoufox releases](https://github.com/daijro/camoufox/releases) 下对应 arch 包到 `~/.camoufox-cli/`

### 6. onboard 段失败

onboard 是唯一交互段（问模型供应商 + API key）。失败常见：

- **无 TTY**（CI / curl | bash 路线）：install.sh 已检测并 fallback 到提示用户手动跑。如要在 CI 跑：`pnpm openclaw onboard --non-interactive --accept-risk --auth-choice custom-api-key --custom-api-key <key> --custom-base-url <url> --custom-model-id <id> --skip-channels --skip-skills --skip-bootstrap --skip-health --skip-ui --install-daemon`
- **auth-choice 不认**：跑 `pnpm openclaw onboard --help` 看当前版本支持的 choice 列表（不同 openclaw 版本字段有差异）
- **daemon install 段失败**：mac 看 `~/Library/LaunchAgents/ai.openclaw.gateway.plist` 是否生成；Linux 看 `~/.config/systemd/user/openclaw-gateway.service` 是否生成。手动重装：`pnpm openclaw daemon uninstall && pnpm openclaw daemon install`

### 7. gateway 起不来

```bash
cd ~/xiaobei/openclaw
pnpm openclaw gateway status --deep  # 深探
pnpm openclaw gateway logs            # 看日志
```

常见：

- **`OPENCLAW_GATEWAY_TOKEN missing`**：首装时未生成。`pnpm openclaw gateway install --force` 重装会生成；或手动 `openssl rand -hex 32` 生成写入 `~/.openclaw/.env` 的 `OPENCLAW_GATEWAY_TOKEN=`
- **端口被占**：`lsof -i :18789` 找旧进程 kill；或改 `~/.openclaw/openclaw.json` 的 `gateway.port`
- **mac launchd 不自启**：`launchctl list | grep openclaw` 看状态；`launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway` 重启
- **Linux systemd 不自启**：`systemctl --user status openclaw-gateway`；`systemctl --user daemon-reload && systemctl --user restart openclaw-gateway`

## 升级后异常

`update.sh` 走 reload + restart 不卸装 daemon，但偶发 dist 残留旧文件导致行为异常：

```bash
cd ~/xiaobei
bash scripts/apply-addons.sh --force   # 重跑 patches + setup
cd openclaw
pnpm build
pnpm openclaw daemon restart
```

如仍异常，核弹选项（保留 `~/.openclaw` 用户态，重 build 引擎）：

```bash
cd ~/xiaobei/openclaw
git reset --hard HEAD
git clean -fd
cd ~/xiaobei
bash scripts/apply-addons.sh --force
cd openclaw && pnpm build
pnpm openclaw daemon restart
```

## 重置回到出厂

**保留 wiseflow 源码**，只重置 openclaw 运行态：

```bash
# 备份当前 openclaw.json + .env（含 API key 与 channel 绑定）
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak
cp ~/.openclaw/.env ~/.openclaw/.env.bak

# 走 openclaw onboard 的 reset
cd ~/xiaobei/openclaw
pnpm openclaw onboard --reset --reset-scope config
# 会清 config 但保留 creds + sessions；若要全清用 --reset-scope full
```

**全重置（连 channel 绑定都清）**：

```bash
rm -rf ~/.openclaw
cd ~/xiaobei
bash scripts/apply-addons.sh --force   # 重建 openclaw.json + workspaces
cd openclaw
pnpm openclaw onboard --skip-channels --skip-skills --skip-bootstrap --skip-health --skip-ui --install-daemon
```

## 还是不行

按以下顺序收集信息后提 [issue](https://github.com/TeamWiseFlow/xiaobei/issues)：

1. `node -v && pnpm --version && git --version`
2. `source ~/xiaobei/openclaw.version && echo "OPENCLAW_VERSION=$OPENCLAW_VERSION OPENCLAW_COMMIT=$OPENCLAW_COMMIT"`
3. `git -C ~/xiaobei/openclaw rev-parse HEAD`
4. `pnpm openclaw --version`（在 `~/xiaobei/openclaw` 下跑）
5. `pnpm openclaw doctor --non-interactive` 的完整输出
6. 失败段的完整 stderr（`bash scripts/install.sh --verbose` 重跑抓输出）

提 issue 时把这 6 项贴全，能显著缩短回环时间。

---

🎉 xiaobei 项目目前提供 **VIP Club**（售价 **168 元/年**），权益包括：

- **付费知识库**：包含《手把手从零开始安装教程》、《安装之后三分钟上手指南》、《Openclaw 自定义配置全案教程》、《Windows 下安装 WSL2 无脑教程》以及各种最佳实践分享
- **vip 微信交流群**，共同探讨交流各种自动化获客玩法，搞钱路上不孤单
- 免费加入 Wiseflow 知识星球
- 每月一次的线上闭门分享（腾讯会议），陪伴你从"小白"到"大神"！
- **会员有效期内免费使用官方中转服务**：涉及小红书、抖音、bili、快手、微信公众号、企业微信朋友圈的技能都需要固定IP（平台要求），一般的家庭网络或办公网络环境并没有固定IP，Wiseflow团队已经搭建了官方的中转服务，vipclub会员期内畅用，不必再单独自建或购买。

此外，我们也面向 VIP Club 会员提供如下增值服务：**远程安装部署、远程技术支持、awada lane 租赁** (需额外付费）

欢迎添加"掌柜的"企业微信（这背后接的就是 xiaobei sales-cs）咨询了解：

<img width="360" height="360" alt="xiaobei掌柜" src="https://github.com/user-attachments/assets/b013b3fd-546e-4176-b418-57bee419e761" />

🌹 开源不易，感谢支持！

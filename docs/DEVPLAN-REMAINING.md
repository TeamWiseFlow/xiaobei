# wiseflow-client 剩余开发计划

> 从根目录 `DEVPLAN.md` 精简而来。已完成的历史 Phase（0/1/2/3/4/4.5/4.6/5/7 续/8 记忆注入/文档收尾）见 git 历史。
> 全局规划见 `docs/product-split-plan.md`；client buildout 状态见 `docs/client-buildout.md`；relay 侧剩余见 relay 仓 `DEVPLAN.md`。
> 本文档只列**未完成待办**。

最后更新：2026-07-07

---

## Phase 6 — Dockerfile 阶段 3-4 填实 + entrypoint

> 按 2026-07-04 约束"源码部署优先，Docker 后做"推迟。源码部署验证通过后再推进。

- [ ] **wiseflow-layer 阶段组织**
  - 做：COPY `skills/` → `/root/.openclaw/skills`；COPY `crews/` → `/root/.openclaw/workspace-*`；COPY `config-templates/openclaw.json` → `/root/.openclaw/openclaw.json`（与源码部署同源）；`daemon.env.template` 占位。
- [ ] **依赖统一装**：`requirements.txt` / `package.json` 一次性 npm/pip install。
- [ ] **D20① 镜像预装常用依赖**：按 `skills/`+`crews/` 实际 import 清单（requests/Pillow/xhshow/python-pptx/reportlab/tccli/google-api-python-client/google-auth-oauthlib 等）pip 装进镜像 site-packages，免小白用户运行期 pip。
- [ ] **img-gen 编译**：火山 gen.py 编译/打包。
- [ ] **camoufox Firefox 二进制 bake**（不 bake chromium，D18）。
- [ ] **openclaw-weixin 插件安装**（tgz）。
- [ ] **entrypoint 渲染逻辑**：读 env 渲染 daemon.env → 注入 OFB_KEY/RELAY_BASE_URL 到各 skill 配置 → `node openclaw.mjs gateway` → 检测 weixin 未绑 → `qrcode-terminal` 输出 + UI 兜底。
- [ ] **D20② entrypoint 注入 PYTHONPATH**：指向 `~/.openclaw/skills/*/vendor/`，使用户额外装 skill 的 pip 依赖（`pip --target` 装入）可被 import；npm 依赖装 skill 目录下局部 `node_modules`。重启不丢（在 volume）。
- 验收：`docker build` 出镜像；`docker run` 弹微信二维码；扫码绑定后 agent 响应。

---

## Phase 8 — 端到端走查

- [ ] **端到端走查**：docker run → 扫码 → 用户在微信发消息 → main 响应 → 调 relay sign/publish/video → 回复。全链路绿。**⏸️ 依赖 Phase 6 部署完成**。
- 验收：一条用户消息走完全链路无人工干预。

---

## 阻塞项（待外部输入）

- **relay Phase 3/4 端点**：client 侧已对接的 relay 调用依赖 relay 侧端点就绪（外部依赖）。
- **配额计数上报**：待 BD 计费模型（relay 侧，外部依赖）。

## 与 relay 仓的边界

- client 不持任何平台凭据，所有 relay 调用带 `X-OFB-Key`。
- relay 端点由 `RELAY_BASE_URL` 派生，entrypoint 注入各 skill 配置，**用户无需配**。
- 接口契约见 relay 仓 `docs/API-CONTRACT.md`。改接口先改那边并通知本仓。
- 本仓 `relay/` 目录是本地独立仓（gitignored，父仓不跟踪），仅供本轮开发期参考/同步，移交时删除。

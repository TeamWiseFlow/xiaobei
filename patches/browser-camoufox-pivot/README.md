# browser-camoufox-pivot

浏览器栈转向（spec `docs/browser-stack-replacement-spec-2026-07.md` §11 阶段一 step 2）的**新增文件**落地区。

## 为什么存在

openclaw/ 是上游工作树，**不是** wiseflow 代码仓的一部分。对 openclaw 的所有改动必须经 `patches/` + `scripts/apply-addons.sh`：

- **修改现有文件** → `patches/001-browser-camoufox-pivot.patch`（git apply）
- **新增文件** → 本目录 `files/`（整文件 ship，apply-addons.sh `cp` 进去）

本目录走第二条线。`git reset --hard` + `git clean -fd` 会清掉 openclaw 里所有 untracked 文件，所以新文件不能直接写进 openclaw/ 再指望保留——必须存在 patches/ 下，每次 apply-addons 时 cp 过去。

## files/

| 文件 | 落地到 | 职责 |
|------|--------|------|
| `camoufox-cli.adapter.ts` | `openclaw/extensions/browser/src/camoufox-cli.adapter.ts` | 17 个 BROWSER_TOOL_ACTION → forked camoufox-cli daemon 命令翻译，JSON-over-unix-socket 通信。`executeCamoufoxCliAction(params, config, deps?)` 是入口。daemon 生命周期 `ensureDaemon`（探活 socket → 死/缺则 spawn detached daemon）。DI 注入 `transport`/`isAlive`/`ensureDaemon` 便于测试。不支持 action（console/dialog/act:drag\|clickCoords\|resize）返回明确错误引导 `target="host"` 兜底（R4 残留，spec 已认） |
| `camoufox-cli.adapter.test.ts` | `openclaw/extensions/browser/src/camoufox-cli.adapter.test.ts` | 33 个单测，mock transport 验证 17 action 翻译 + 结果 shaping + 错误传播 |

## 接线

`scripts/apply-addons.sh` 在 patch 循环之后、skills 同步之前，有一段 `cp "$PIVOT_FILES_DIR"/*.ts "$OPENCLAW_DIR/extensions/browser/src/"`。本目录文件被复制进 openclaw extension，随后 `pnpm build` 编译 dist。

## 下一步（step 3）

`001-browser-camoufox-pivot.patch`改现有文件把 adapter 接进 browser tool：

- `browser-tool.schema.ts`：`BROWSER_TARGETS` 删 `sandbox`、加 `camoufox`
- `browser-tool.ts`：删 sandbox 分支、加 `target === "camoufox"` 分支调 `executeCamoufoxCliAction`
- `profile-capabilities.ts` / `chrome.ts` / `ensureBrowserAvailable`：删 `local-managed` 分支
- 删 `openclaw/src/agents/sandbox/browser*.ts` + bridge-server.ts sandbox bridge + plugin-sdk/browser-bridge.* facade

相关：[[camoufox-cli-fork]]、`patches/camoufox-cli/`（forked cli 本体）、`docs/browser-stack-replacement-spec-2026-07.md`

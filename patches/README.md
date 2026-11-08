# OpenClaw patches

小贝 5.8.x 跟随 OpenClaw 2026.10.x，具体 tag/SHA 由仓根 `openclaw.version` 指定。当前补丁基于 2026.10.10；不裁剪 provider、技能源码或其依赖，保留上游 lockfile。

| 补丁 | 用途 |
| --- | --- |
| `009-gateway-build.patch` | Gateway 构建不生成 Swift/Kotlin 原生客户端协议产物；保留 Web Control UI |
| `010-gateway-build-test.patch` | 验证 Gateway 各构建 profile 不生成原生客户端协议 |

`patches/apply.sh` 是只应用源码补丁的入口：校验 pin，严格检查并应用补丁，不修改用户配置、安装依赖或操作服务。调用前要求上游工作树干净。`scripts/apply-addons.sh` 在其部署流程中调用此入口，随后完成配置同步、依赖及构建。

内置 `web_search` 使用原生 `tools.web.search.enabled` 开关，产品模板默认关闭。安装和升级时只补齐缺失的开关值，保留用户显式设置及其他搜索参数。旧 `OPENCLAW_DISABLE_WEB_SEARCH` 环境变量补丁已移除；重建后不再读取此变量，旧部署须使用原生配置。

浏览器接入和工具摘要补丁已移除。独立 `xiaobei-browser` 插件位于 `browser/plugin/`，通过公开 Plugin SDK 注册 `xiaobei_browser` 与生命周期服务；原生 browser 插件在产品配置中禁用。配置迁移由 `scripts/configure-browser-plugin.mjs` 统一执行，保留浏览器选项和用户权限限制。

旧 35 个浏览器裁剪补丁和 unix-socket adapter 已替换，避免继续绑定 7 月版内部结构。008 daemon CLI 兼容补丁已删除：新版已提供公开 daemon CLI barrel，旧生成脚本已不存在。`patches/camoufox-cli/` 暂留作历史参考，安装/更新/打包入口使用仓根 `browser/`。

浏览器运行时拥有独立依赖树（主仓 camoufox 0.5.9 / fpgen-js 1.3.0 / Playwright 1.62.1 / 浏览器 158.0.1-beta.41），不得提升到引擎的 Playwright 1.63。资产锁、显式安装器与 CLI/Python bridge 在 `browser/`；开发与 OSBI 后续计划统一见 [浏览器开发指南](../docs/browser-architecture.md)。

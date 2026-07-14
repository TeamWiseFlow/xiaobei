# workspace-skeleton

通用 workspace 骨架，build 期复制到每个 crew 的 workspace 目录下作为初始结构。

## 目录

| 路径 | 用途 |
|------|------|
| `credentials/` | 各平台 cookie/token 存放（运行期写入，镜像里为空） |
| `business_knowledge/` | 业务/品牌介绍/话术/FAQ（main 用；启用 sales-cs 时软链到其 workspace） |
| `logins/` | camoufox cookie 中央存储（`<platform>.json`，D18）+ 冻结指纹模板 `_template/` |

## 运行期才有的内容（不进镜像）

- `credentials/*` — 用户登录各平台后由 login-manager 写入
- `logins/<platform>.json` — camoufox `cookies export` 产物
- `logins/_template/camoufox-cli.json` — 冻结指纹模板（Phase 4.5，build 期 bake 进镜像或首次启动生成）

## Phase 7 待办

- main workspace 软链 business_knowledge 到 sales-cs（启用时）
- it-engineer 预置记忆写入（env/relay/awada 启用/sales-cs 启用知识）

---
name: wx-mp-publisher
description: 通过 relay 将 Markdown 排版并推送到微信公众号草稿箱。支持多账号和小绿书，凭据存在 accounts.json。
---

# wx-mp-publisher — 工具说明

> 本文是 `expert-wx-mp` 专家包内的工具说明书，不独立出现在技能列表中。由相关 Workflow 指引调用。

将 Markdown 稿件排版并推送到微信公众号草稿箱（经 relay，凭据按请求透传）。

---

## 凭据与存储位置

- **公众号凭据**存放在源仓之外的实例态目录（不跟源仓绑，软链 / tarball / 备份都不带密钥）：
  ```
  ~/.openclaw/wx-mp-publisher/accounts.json
  ```
  结构见本 skill 同目录 `accounts.example.json`。支持多账号，每条含 `alias` / `appId` / `appSecret`；多账号时 `default` 指向默认 alias。
- **relay 身份** `OFB_KEY` + `RELAY_BASE_URL` 来自 `daemon.env`（由 entrypoint 注入环境变量）。

### 凭据缺失时 Agent 行为

1. 若 `accounts.json` 不存在或对应账号缺 `appId`/`appSecret`：**先读同目录 `REFERENCE.md`**，按其中的步骤指导用户获取 AppID / AppSecret（含 relay IP 白名单 `123.60.18.144` 的设置）。
2. 收到用户提供的值后，写入 `accounts.json`，再继续发布。
3. 若 `OFB_KEY` 未配置：告知用户需让 IT engineer 在 `daemon.env` 配置后重启实例。

---

## 发布命令

通过 PATH 调用 wrapper：`wx-mp-publisher <cmd>`，无需手动拼接 python 命令或脚本路径。

```bash
wx-mp-publisher <markdown_file> [theme] [--account ALIAS]
```

- `theme`：渲染主题，三种形态：
  1. **内置 id**（`pie` / `lapis` / `default` / …）——原样作为 `theme` 传给 relay
  2. **本地 `.css` 文件路径**——脚本读出文件内容，作为 `custom_theme` 字段随 multipart 上传 relay
  3. **wx_mp/wenyan-theme/index.json 登记的自定义 id**--从工作区主题注册表解析出对应 CSS 路径，同 (2)

  可选，省略时脚本明确使用内置 `default`。
- `--account ALIAS`：多账号时指定目标公众号；缺省用 `accounts.json` 的 `default`

> **自定义主题不持久化到 relay**：relay 是无状态多租户中转，**不存任何用户主题**。CSS 随请求上传，relay 写到 per-request 临时目录、用后即清理，天然按用户隔离。
>
> 主题注册表在 client 侧：**工作区 `wx_mp/wenyan-theme/index.json`**。generate-wenyan-theme 生成新主题后写入该文件，发布时从该文件读取。结构固定为 `version: 1` + `themes` 数组；每条记录包含 `id`、`name`、`css`、`source`、`createdAt`，其中 `css` 为相对工作区根的路径（如 `wx_mp/wenyan-theme/<id>.css`）。

脚本自动：
- 从 `accounts.json` 取目标账号凭据
- 自动收集正文、`cover`、`image_list` 中的本地图片并随稿件一起上传
- 发布前校验图片引用、frontmatter `author` 长度和 `digest` 类型；校验失败会直接退出
- POST multipart 到 `${RELAY_BASE_URL}/api/v1/wx-mp/publish`，带 `X-OFB-Key`
- 校验响应包络 `{ success, data, error }`

### 主题选择（未指定时）

> 自定义主题说明：`generate-wenyan-theme` 生成的用户自定义 CSS 登记在 `wx_mp/wenyan-theme/index.json`。若用户明确指定某个自定义主题，必须优先采用；未指定时才按内容在内置主题和已登记自定义主题中匹配。

| 主题 ID | 风格描述 | 适用场景 |
|---------|---------|---------|
| `default` | 简洁经典 | 资讯、通知、简讯 |
| `pie` | 现代锐利（仿少数派） | 深度长文、评测、观点（默认） |
| `lapis` | 极简冷蓝 | 技术教程、代码分析 |
| `purple` | 简约紫调 | 品牌、商务、精品内容 |
| `orangeheart` | 暖橙优雅 | 情感、故事、节日 |
| `maize` | 淡雅玉米黄 | 健康生活、美食、户外 |
| `rainbow` | 多彩活泼 | 亲子、宠物、娱乐 |
| `phycat` | 薄荷清爽 | 科普、知识型内容 |

**智能选择决策树**（用户未指定主题时）：

```
含大量代码/技术术语 → lapis
年轻女性/亲子/萌宠  → rainbow
情感/故事/节日      → orangeheart
健康/美食/户外      → maize
品牌/商务/精品      → purple
科普/知识型         → phycat
深度长文/评测/观点  → pie
其他（资讯/通知）   → default
```

---

## Frontmatter 要求

文章 Markdown 开头必须包含 YAML 块，否则微信 API 会拒绝：

```yaml
---
title: 文章标题
digest: "用于展示在图文卡片上的简短介绍" # 可选，图文简介；不会插入正文
cover: cover.jpg             # 可选，缺省自动取正文第一张图
author: 作者名称              # 可选，≤ 8 个汉字 / 24 字节（超长报 45110）
source_url: https://...      # 可选，原文链接
need_open_comment: true      # 可选，是否开启评论（默认 false）
only_fans_can_comment: false # 可选，是否仅粉丝可评论（默认 false）
---
```

图文简介使用 `digest`，直接写在原稿的 frontmatter 中，发布命令不变。用户给出简介时使用指定文字；需要拟写时依据定稿内容简短概括，不新增事实。不需要自定义简介时省略该字段或写 `digest: ""`，由微信按默认规则生成。简介须为 YAML 字符串，纯数字等内容加引号。

`digest` 作为独立简介传给微信，不会插入正文；`description` 会以引用前缀加入正文。不要用 `description` 代替图文简介。`digest` 用于普通图文，小绿书仍按下文提交图片和正文。

### 小绿书（图片消息）

图片轮播消息跳过 HTML 排版，**保留 Markdown 正文文字并以图片消息的 `content` 提交**；不是只传图片或忽略全部正文。正文中的官网 CTA 也须完整保留。在 frontmatter 中指定 `image_list`（最多 20 张，首张为封面）：

```markdown
---
title: 新版更新说明
description: 本次更新摘要
image_list:
  - 1.jpg
  - 2.jpg
---

这一版本基础设施大升级，具体变化见配图。

了解产品与使用方式，请访问官网：https://example.com
```

将示例官网替换为用户确认的真实地址。`description` 会先作为引用引言加入正文，随后接原正文及官网 CTA；小绿书提交时由 core 转为纯文本。它不会覆盖正文，不要把它当成独立于 `content` 的替代字段。图片消息不依赖主题进行 HTML 排版；传入的主题仍须通过 relay 参数校验。

✅ 将说明文字与官网 CTA 写在 frontmatter 后的正文，`image_list` 列出轮播图片。
❌ 因为图片消息“不含 HTML”就删掉正文，或只将整篇文案放入 `description`。

### 本地图片准备规则

本地图片以 Markdown 所在目录为基准解析：

1. 正文图片写 `![说明](filename.jpg)`
2. `cover` 写 `cover: cover.jpg`
3. `image_list` 写 `- 1.jpg`
4. 支持 `./cover/00.png`、子目录和绝对路径；带空格的 Markdown 路径用 `<...>` 包裹，YAML 路径用引号
5. 不同目录可以有同名图片；脚本仅在请求内改写图片引用，并为上传文件分配唯一名称，不修改原稿和素材
6. `http://` / `https://` 图片保留原 URL，不需要复制到本地

Agent 不需要手动上传图片；脚本会自动收集并上传上述本地图片。

---

## Agent 行为约束

1. **等待脚本完整返回后**再判定结果，**禁止**在脚本输出前自行判断是否发布成功
2. 发布前先确认目标账号凭据存在；缺失则按 `REFERENCE.md` 引导用户获取并写入
3. 多账号场景：用户未明示账号时用 `default`；用户口头说「发到技术号」等 alias 含义时传 `--account`
4. `status:draft_created`、`draft_created:true`、`published:false` 和 `media_id` 只确认已入草稿箱。向用户报告“草稿已推送，待后台核对并正式发布”；没有正式发布证据时，不报告“已发布”，不录入为已发布作品。

---

## Error Handling

| 错误 | 处理方式 |
|------|---------|
| `未找到公众号凭据文件 accounts.json` | 按 `REFERENCE.md` 引导用户创建并填入 |
| `账号 ... 缺少 appId 或 appSecret` | 按 `REFERENCE.md` 引导用户补全 |
| `OFB_KEY 未配置` | 让 IT engineer 在 `daemon.env` 配置 `OFB_KEY` 后重启实例 |
| `MISSING_APP_ID` / `MISSING_APP_SECRET`（relay 400） | accounts.json 中该账号凭据为空，补全 |
| `MISSING_MARKDOWN`（relay 400） | 检查 markdown 文件内容非空 |
| `45110: author size out of limit` | frontmatter `author` 超 8 汉字 / 24 字节，缩短后再发 |
| `frontmatter digest（图文简介）须为字符串` | 将简介写成 YAML 字符串；纯数字等内容加引号，不需要时删除字段 |
| 本地图片不存在 / 图片 `ENOENT` | 按 Markdown 所在目录核对图片路径，确认源文件存在 |
| `INVALID_THEME`（relay 400） | 改用主题表中的内置 ID，或传已登记的自定义 ID / CSS 文件 |
| relay 502 | relay 调微信失败，检查 AppSecret / IP 白名单（见 `REFERENCE.md`） |

---

## Notes

- 推送成功后末行输出 JSON 回执（`status:draft_created`、`published:false`、`media_id`），可在公众号后台「草稿箱」找到对应草稿；`article_url` 即使存在也不证明已正式发布
- 本 skill 只负责推送草稿，**正式发布仍需在公众号后台手动操作**
- relay 已内置 `@wenyan-md/core` 渲染，client 不再需要装 `wenyan-cli`
- 仅支持文本 + 图片（无视频）

## 微信平台硬限制（发布链路通用）

- 标题长度：最多 64 字节（约 21 个中文字符）
- 本地图片：相对 Markdown 所在目录或使用绝对路径，脚本自动收集、重写并上传
- 样式：必须内联（`style="..."`），`<style>` 标签会被过滤
- access_token 有效期 2 小时，relay 侧自动刷新，client 侧无需处理

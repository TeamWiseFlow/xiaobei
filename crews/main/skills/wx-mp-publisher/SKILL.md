---
name: wx-mp-publisher
description: Render and publish Markdown articles to WeChat Official Account (公众号)
  draft box via wiseflow-relay. Supports multi-account (alias) and image-only posts
  (小绿书). Credentials stored locally in accounts.json; relay is stateless.
metadata:
  openclaw:
    emoji: 📤
    requires:
      bins:
      - python3
---

# WeChat MP Publisher

将 Markdown 稿件排版并推送到微信公众号草稿箱（经 relay，凭据按请求透传）。

---

## 凭据与存储位置

- **公众号凭据**存放在本 skill 目录下的 `accounts.json`（已 gitignore，不进仓）：
  ```
  crews/main/skills/wx-mp-publisher/accounts.json
  ```
  结构见 `accounts.example.json`。支持多账号，每条含 `alias` / `appId` / `appSecret`；多账号时 `default` 指向默认 alias。
- **relay 身份** `OFB_KEY` + `RELAY_BASE_URL` 来自 `daemon.env`（由 entrypoint 注入环境变量）。

### 凭据缺失时 Agent 行为

1. 若 `accounts.json` 不存在或对应账号缺 `appId`/`appSecret`：**先读同目录 `REFERENCE.md`**，按其中的步骤指导用户获取 AppID / AppSecret（含 relay IP 白名单 `123.60.18.144` 的设置）。
2. 收到用户提供的值后，写入 `accounts.json`，再继续发布。
3. 若 `OFB_KEY` 未配置：告知用户需让 IT engineer 在 `daemon.env` 配置后重启实例。

---

## 发布命令

```bash
python3 /<workspace>/crews/main/skills/wx-mp-publisher/scripts/publish_wx_mp.py <markdown_file> [theme] [--account ALIAS]
```

- `theme`：渲染主题 id（如 `pie` / `lapis` / `default`），可选，缺省由 relay 默认渲染
- `--account ALIAS`：多账号时指定目标公众号；缺省用 `accounts.json` 的 `default`

脚本自动：
- 从 `accounts.json` 取目标账号凭据
- 从 Markdown 中提取本地图片路径，作为 `images` 字段一并上传（http/https 图片由 relay 自行抓取，不在此列）
- POST multipart 到 `${RELAY_BASE_URL}/api/v1/wx-mp/publish`，带 `X-OFB-Key`
- 校验响应包络 `{ success, data, error }`

### 主题选择（未指定时）

| 主题 ID | 风格描述 | 适用场景 |
|---------|---------|---------|
| `default` | 简洁经典 | 资讯、通知、简讯 |
| `pie` | 现代锐利（仿少数派） | 深度长文、评测、观点 |
| `lapis` | 极简冷蓝 | 技术教程、代码分析 |
| `purple` | 简约紫调 | 品牌、商务、精品内容 |
| `orangeheart` | 暖橙优雅 | 情感、故事、节日 |
| `maize` | 淡雅玉米黄 | 健康生活、美食、户外 |
| `rainbow` | 多彩活泼 | 亲子、宠物、娱乐 |
| `phycat` | 薄荷清爽 | 科普、知识型内容 |

---

## Frontmatter 要求

文章 Markdown 开头必须包含 YAML 块，否则微信 API 会拒绝：

```yaml
---
title: 文章标题
cover: ./cover.jpg           # 可选，缺省自动取正文第一张图
author: 作者名称              # 可选
source_url: https://...      # 可选，原文链接
need_open_comment: true      # 可选，是否开启评论（默认 false）
only_fans_can_comment: false # 可选，是否仅粉丝可评论（默认 false）
---
```

### 小绿书（图片消息）

纯图片轮播形式，不含正文 HTML。在 frontmatter 中指定 `image_list`（最多 20 张，首张为封面）：

```yaml
---
title: 文章标题
image_list:
  - ./1.jpg
  - ./2.jpg
---
```

有 `image_list` 时 relay 自动走图片消息接口，忽略主题参数。

---

## Agent 行为约束

1. **等待脚本完整返回后**再判定结果，**禁止**在脚本输出前自行判断是否发布成功
2. 发布前先确认目标账号凭据存在；缺失则按 `REFERENCE.md` 引导用户获取并写入
3. 多账号场景：用户未明示账号时用 `default`；用户口头说「发到技术号」等 alias 含义时传 `--account`

---

## Error Handling

| 错误 | 处理方式 |
|------|---------|
| `未找到公众号凭据文件 accounts.json` | 按 `REFERENCE.md` 引导用户创建并填入 |
| `账号 ... 缺少 appId 或 appSecret` | 按 `REFERENCE.md` 引导用户补全 |
| `OFB_KEY 未配置` | 让 IT engineer 在 `daemon.env` 配置 `OFB_KEY` 后重启实例 |
| `MISSING_APP_ID` / `MISSING_APP_SECRET`（relay 400） | accounts.json 中该账号凭据为空，补全 |
| `MISSING_MARKDOWN`（relay 400） | 检查 markdown 文件内容非空 |
| relay 502 | relay 调微信失败，检查 AppSecret / IP 白名单（见 `REFERENCE.md`） |

---

## Notes

- 发布成功后输出草稿 `media_id`，可在公众号后台「草稿箱」找到对应草稿
- 本 skill 只负责推送草稿，**正式发布仍需在公众号后台手动操作**
- relay 已内置 `@wenyan-md/core` 渲染，client 不再需要装 `wenyan-cli`
- 仅支持文本 + 图片（无视频）

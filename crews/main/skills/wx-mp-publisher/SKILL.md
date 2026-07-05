---
name: wx-mp-publisher
description: Render and publish Markdown articles to WeChat Official Account (公众号)
  draft box. Supports local mode (IP whitelisted) and server relay mode via Wenyan
  Server. Supports multi-account, image-only posts (小绿书), and proxy.
metadata:
  openclaw:
    emoji: 📤
    requires:
      bins:
      - node
      - npx
---

# WeChat MP Publisher

将 Markdown 稿件排版并推送到微信公众号草稿箱。

---

## 发布命令

```bash
./skills/wx-mp-publisher/scripts/publish-wx-mp.sh <markdown_file> [theme]
```

`theme` 参数支持三种形态：

1. **内置主题 id**：如 `pie`、`lapis`，原样传给 wenyan-cli `-t/--theme`。
2. **本地 `.css` 文件路径**：直接作为自定义主题加载（传给 `--custom-theme`）。
3. **已注册自定义主题 id**：在下表登记、描述含“用户自定义”的 id，脚本自动从主题表中解析出对应 CSS 文件路径并加载，无需手动传路径。

**主题选择（未指定时按内容匹配）：**

> 自定义主题说明：`generate-wenyan-theme` 生成的用户自定义 CSS 会注册到下表。若用户明确指定参考某个自定义主题，必须优先采用该主题；未指定时才按内容在内置主题和已注册自定义主题中匹配。

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
| `<custom-theme>` | 用户自定义主题占位（由 `generate-wenyan-theme` 生成后更新，文件：`<custom-theme>.css`） | 用户明确指定参考该主题时优先采用；相似内容可优先建议 |

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
cover: ./cover.jpg           # 可选，缺省自动取正文第一张图
author: 作者名称              # 可选，默认为“xiaobei 自媒体小编“
source_url: https://...      # 可选，原文链接
need_open_comment: true      # 可选，是否开启评论（默认 false）
only_fans_can_comment: false # 可选，是否仅粉丝可评论（默认 false）
---
```

### 发布小绿书（图片消息）

纯图片轮播形式，不含正文 HTML。在 frontmatter 中指定 `image_list`（最多 20 张，首张为封面）：

```yaml
---
title: 文章标题
image_list:
  - ./1.jpg
  - ./2.jpg
  - ./3.jpg
---

可选的说明文字
```

有 `image_list` 时自动走图片消息接口，忽略主题参数。

---

## 多公众号发布

如需向非默认公众号推送，设置环境变量 `WECHAT_TARGET_APP_ID` 后执行：

```bash
./skills/wx-mp-publisher/scripts/publish-wx-mp.sh article.md
```

> 前提：relay server 端已通过 `wenyan credential --set` 完成该公众号的凭据配置，且对应公众号已将 server IP 加入白名单。

---

## 代理配置

如网络环境需要代理访问微信 API，设置环境变量 `WENYAN_PROXY` 后执行：

```bash
./skills/wx-mp-publisher/scripts/publish-wx-mp.sh article.md
```

支持 HTTP / HTTPS / SOCKS5 / SOCKS4 代理格式。

---

## Agent 行为约束

1. 脚本首次运行会自动下载 `@wenyan-md/cli`，约 10–30 秒，**等待完成再报告结果**
2. **禁止**在脚本输出前自行判断是否发布成功

---

## Error Handling

| 错误 | 处理方式 |
|------|---------|
| `请配置环境变量` | 配置对应环境变量 |
| `invalid ip` | 本机 IP 未白名单，改用 relay（配置 `WENYAN_SERVER_URL`） |
| `invalid appid` | 检查 `WECHAT_APP_ID` 或 `WECHAT_TARGET_APP_ID` |
| 图片上传失败 | 确认 Markdown 中图片路径真实存在 |
| `缺少 title` | 在 Markdown 开头添加 frontmatter `title:` 字段 |

---

## Notes

- publish 成功后会输出草稿 `media_id`，可在公众号后台找到对应草稿
- 本 skill 只负责推送草稿，正式发布仍需在公众号后台手动操作
- 支持 Mermaid 图表语法，在 Markdown 中使用 mermaid 代码块即可自动渲染为图片

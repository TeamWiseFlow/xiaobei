# 改稿与调整 Workflow

用户说"帮我改改这篇"、"润色一下"、"换个风格"、"调调方向"、"换个排版"走这个。

## 入口判断

先搞清楚改的是哪个层级，不要上来就大改：

| 用户的说法 | 改的层级 | 怎么走 |
|-----------|---------|--------|
| "润色一下" / "顺一顺" | 措辞、节奏、AI 味 | 轻改，直接上手 |
| "换个语气" / "活泼一点" | 内容风格层 | 选目标 DNA -> 按 instruction 改 -> 评估 |
| "结构调一下" / "换个角度" | 结构层 | 先出调整方案 -> 确认 -> 改 |
| "方向不对，重写" | 方向层 | 回到 content-production.md 从选题重新走 |
| "换个排版" / "照着 XX 的排版来" | 排版层 | 生成/提取新主题 -> 套 |
| "压缩到 X 字" / "展开到 X 字" | 篇幅层 | 先问清楚保留什么砍掉什么 |

## 轻改（措辞 / 润色 / 去 AI 腔）

直接上手，改完给对比说明。
重点：去掉空泛陈词滥调、拆长句缩长段、改口语化、加具体例子。
改完告诉用户改了哪几类地方。

## 换风格

**先确定目标 DNA，再动笔。**
- 用户说"换成 XX 风格" -> 走 `style-dna.md` 选/建目标 DNA
- 用户说"就照着这篇的风格来" -> 用参考文章快速提炼风格
- 用户给了对标账号 -> 用那个号的 DNA（如果有，没有的话，通过`style-dna`新建）

改完先给开头 3 段预览，用户觉得味道对了再全文改，省得返工。
全文改完对照目标 DNA template 逐项自检（无数字打分环节；发布后表现由 DNA 表现评估闭环跟踪）。

## 换结构

先出结构调整方案（新的大纲/节标题），用户确认后再改正文。
结构动了通常风格也要跟着调--别只动骨架不换肉。
结构调整按 DNA template 的结构部分重新出大纲（节标题、段落任务、素材位置）。

## 换排版

用户说"换个排版"、"换个主题"、"照着这篇的排版来"：

1. **用户直接指定了主题名** -> 内置 id 直接用；自定义主题先从 `wx_mp/wenyan-theme/index.json` 解析 `theme-id`
2. **用户给了微信文章链接**（`mp.weixin.qq.com` 开头）-> 调 `generate-wenyan-theme` 提取参考文章的排版风格，生成自定义主题
   - 生成后保存到 `wx_mp/wenyan-theme/<theme-id>.css`，并登记 `wx_mp/wenyan-theme/index.json`
3. **用户说"换个好看的"** -> agent 根据内容类型和阅读场景推荐 2-3 个主题
4. **对标某个账号的排版** -> 先抓几篇那个号的文章 -> 调 `generate-wenyan-theme` 提取，并登记到 `wx_mp/wenyan-theme/index.json`

换完排版重新生成预览，让用户看效果再确认；发布时把自定义 `theme-id` 传给 `wx-mp-publisher`。

## 改完必做

1. 自己过一遍质量自检
2. 跟用户说清楚改了什么、为什么这么改
3. 改稿结论属于可复用风格偏好时，按 `style-dna.md` 的反馈回流判定更新 DNA；单次修改不动 DNA

## 改后发布

用户要求改完后发布 / 重新发布时，走 `content-production.md` 的初稿后流程（Step 7-10）：

1. **Frontmatter**：按 `wx-mp-publisher` 规范更新 `article.md` 的 frontmatter（至少核对 `title`、`digest`、`cover` / `image_list`、`author`、`source_url` 与改后内容同步）；普通图文已写 `digest` 时，核对简介仍准确反映改后内容。frontmatter 在 workflow 中直接写入，`wx-mp-publisher` 只校验。
2. **存文件**：文章与图片归位 `wx_mp/outputs/<article-name>/`，图片与 `article.md` 同目录、纯文件名引用。
3. **发布 + 记录**：调 `wx-mp-publisher` 发布（排版由用户指定或 Agent 按内容自主选择；自定义主题传登记的 `theme-id`），再按 `content-production.md` Step 9 的公众号特例入库——`media_id` 占位先调 `published-track record`，用户正式发布后提供正式 URL 时重跑升级记录。

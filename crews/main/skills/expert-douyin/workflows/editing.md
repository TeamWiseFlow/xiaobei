# 图文与视频修改 Workflow

用户要求修改已有作品的标题、正文、图组、剪辑、配乐或封面时走本流程。先定位原作品目录、作品形态（`note` / `video`）、DNA 绑定及本次修改范围；用户要求新主题或整体换方向时回到 `content-production.md`。

这里先修改本地作品。两个发布工具执行的是新发布，不能用 `run` 当作线上原帖编辑；用户明确要求修改已发布原帖时，先核实平台允许的修改项与操作方式，不自动转成重新发布。

## Step 1 - 确认作品与修改范围

1. 读取 `douyin/outputs/<work-name>/` 的文案、素材及 `dna-meta.json`，沿用该作品的 DNA；无绑定时，视频选视频 DNA（默认 `dna-0`），图文选独立图文 DNA（如 `dna-0-note`）。读取相应 DNA 文档与 template，不混用。
2. 明确用户要修改的部分、必须保留的内容以及是否需要发布。一次局部修改不默认重做整篇作品。
3. 按作品形态进入图文或视频路线；共有文案修改先按下节处理。

## Step 2 - 标题与发布文案（两种形态共用）

- 用户已给定替换文案时按原文修改；需要代拟时按目标 DNA `title-cover` 和 template 给候选。
- 图文标题 ≤20 字、描述（含 `#话题`）≤1000 字，正文语气按 `body-voice`；视频标题 ≤30 字，简介与话题按视频 template。
- 用户选定后更新作品目录的文案记录；核对事实、产品信息、CTA 与首图 / 视频封面承诺一致。

## Step 3A - 图文修改

按本次要求修改图组或正文：

| 修改要求 | 执行方式 |
| --- | --- |
| 改正文、逐页文字 | 按 `body-voice` 修改，同步对应图片上的文字，核对事实和前后表述 |
| 增删图片、调整顺序 | 按 `content-idea` / `imageset-visual` 整理新的图序与逐页信息；涉及叙事变化先确认调整方案 |
| 换首图、改版式或配色 | 按 `title-cover` / `imageset-visual` 调整；用户给图优先采用，需生成图片用 `awk-img-gen`，复杂设计出 Brief 委托 content-producer |
| 换配乐 | 记录期望风格；上传后用 `music-list` 读取实际候选，再用 `music-select --choice` 选曲并验证；明确使用原声时传 `publish --original-sound`，不为图文调用视频音轨工具 |

改完检查：图序与文字对应、图片清晰度与裁切、首图与正文一致、无错字或缺页；图组 1–35 张，单张 ≤50MB，格式 jpg/jpeg/png/webp/bmp/tif。

### 【确认】修改后的图组与正文

向用户展示修改后的完整图组（含首图）、图序、正文及配乐风格意图（实际曲目上传后选择），并说明改动。确认后进入 Step 4；图文不走 video-review 或“成片与封面”确认。

## Step 3B - 视频修改

### 素材组装 / 轻剪辑：main 直接做

- 去口气词、结巴、静音或剪高光 → `talking-head-cut`，按其输出交 `video-edit apply-cut`。
- 抽段拼接、局部顺序调整、加旁白 / BGM / 字幕、补已有片头片尾 → `video-edit`；涉及段落变化先给删留与时点方案，确认后执行。
- 换视频封面：用户给图优先使用；从片子抽帧提供候选，或按视频 DNA `production-spec` 用 `awk-img-gen` 重做。

### 其他视频改制：委托 content-producer

需要新叙事、重做分镜、生成新画面或整体改制时，按 `content-production.md` Step 5B 的标准 Brief 流程委托 CP。Brief 明确修改目标、保留内容、原成片与素材的绝对路径、交付物与验收要求；main 不自行重写分镜。口播稿由 main 提供，剪辑解说旁白由 CP 写。

### 【确认】修改后的成片与封面

main 自做组装 / 轻剪辑通过 `video-review` 后交付；CP 改制按其标准流程完成质检。核对钩子兑现、结构和音画同步，向用户说明修改内容。用户确认成片与封面后进入 Step 4。

## Step 4 - 交付、发布与记录

1. 保留修改后的作品和文案记录；可复用风格偏好按 `style-dna.md` 反馈回流，单次修改不默认改变 DNA。
2. 用户只要求修改时，到交付结束。用户要求发布 / 重新发布时，进入 `content-production.md` Step 6–7：视频走 `douyin-publish video`；图文走 `douyin-publish note`。先用 `douyin-publish check` 验证 Camoufox 持久化创作者会话；未登录使用 `douyin-publish login`。原声图文加 `--original-sound`，配乐按图文分步工具说明处理。
3. 已发布作品改后重新上线会产生新作品链接；发布前确认用户要重新发布。原作品是否删除由用户决定，不自动删除。
4. 成功取得新链接后用 `published-track record` 记录新发布日期、链接和账号；图文 `--content-type post`、视频 `--content-type video`。用新作品目录保存这次发布版本与 `dna-meta.json`，避免同目录同日 upsert 覆盖旧作品记录；修改未换 DNA 时沿用原绑定。
5. 已点击发布后发生登录异常、超时或取链失败，先核实管理页 / 补取链接，不自动重发。

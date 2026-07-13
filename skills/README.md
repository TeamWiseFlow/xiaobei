# 公共技能目录（skills/）

放在这里的 skill 是 **公共技能**（≥2 crew 共用），安装到 `~/.openclaw/skills/`，对所有 crew 可见（内部 crew 自动继承，对外 crew 需在 DECLARED_SKILLS 中声明）。

每个 skill 是一个子目录，包含 `SKILL.md` 文件。

- **Crew 专属 skill** 放在 `crews/<crew-id>/skills/`，不要放在此处。
- 产品拆分后（D8）addons/ 结构已销毁，不再有 `addons/<name>/skills/` 这一层。

## 当前公共技能

| 技能 | 用途 | 适用范围 |
|------|------|----------|
| `smart-search` | 智能搜索：驱动浏览器在 40+ 平台实时搜索，完全免费，无需 API Key | 全部 crew 可用 |
| `browser-guide` | 浏览器操作最佳实践：登录墙、验证码、懒加载、付费墙的处理指导 | 全部 crew 可用 |
| `complex-task` | 复杂任务拆解与多步执行协调 | 全部 crew 可用；**sales-cs DENIED** |
| `email-ops` | 邮件读写与发送 | 全部 crew 可用 |
| `pexels-footage` | Pexels 免费素材搜索下载 | main + content-producer 继承 |
| `pixabay-footage` | Pixabay 免费素材搜索下载 | main + content-producer 继承 |
| `wxwork-drive` | 企业微信微盘 | main + content-producer 继承 |
| `siliconflow-img-gen` | 硅基流动生图（Phase 5 改火山） | main + content-producer 继承 |
| `youtube-publish` | YouTube 视频发布（Data API v3 + OAuth2） | main + content-producer 继承 |

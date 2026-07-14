# 自媒体运营 — Tools

## 环境备注

- 文生图/改图默认输出 JPG 格式：企业微信后台发送图片只支持 JPG；如需 PNG 需显式指定 --format png

### 📝 视频封面/海报制作经验

`siliconflow-img-gen` 可以很好的直接出带文字的海报，完全不必要先生成图，然后自己再编写脚本拼字。

具体见 `siliconflow-img-gen` 技能中 `视频封面/海报最佳实践`。

### 数据库查询一定走 published-track 脚本

`sqlite3` 不在 allowlist 中。查询 published-track 数据库必须通过已有脚本：

```
✅ ./skills/published-track/scripts/query.sh --platform wx_mp
✅ ./skills/published-track/scripts/query-pending.sh

❌ sqlite3 db/published_track.db "SELECT ..."
❌ echo ".tables" | sqlite3 db/published_track.db
```
---
name: xhs-pugongying
description: 小红书蒲公英合作原子操作：品牌身份检查、达人类目与筛选、达人详情及粉丝数据、合作邀约预览和一次性提交。
metadata:
  openclaw:
    emoji: 🤝
    requires:
      bins:
      - python3
      - node
---

# 蒲公英达人合作

使用 `xhs-pugongying`。先运行 `xhs-hunter check`；工具读取 `xhs-hunter login` 保存在 `~/.openclaw/logins/xhs-pc-local.json` 的 PC 会话。平台还需账号具有蒲公英品牌合作权限。再运行本工具的 `check`，若平台拒绝，记录响应并停止，不把普通 PC 登录成功等同于蒲公英授权。

```bash
xhs-pugongying check
xhs-pugongying categories
xhs-pugongying search --choice '-1' --count 20
xhs-pugongying profile '达人 user_id'
xhs-pugongying methods
xhs-pugongying call get_user_fans_history --kwargs '{"user_id":"达人 user_id"}'
```

`categories` 返回类目树；`search --choice` 接受索引表达式，`-1` 为全部。筛选时先小样本，再按实际需要分批。`profile` 同时取基础、粉丝、粉丝趋势和作品表现；检查返回的 `errors`，某项失败不当作零。

## 合作邀约

先在工作区写入 JSON 方案，字段为 `user_id`、`product_name`、`publish_start`、`publish_end`、`content`、`contact_info`。时间字段使用平台要求的格式，以实际页面/用户提供的合作期为准。

```bash
xhs-pugongying invite --proposal /path/to/proposal.json
xhs-pugongying invite --proposal /path/to/proposal.json --send
```

第一条只预览，不发送。将完整方案交用户确认后，才运行第二条；同一方案只允许尝试一次。异常或响应不明确时到蒲公英后台核实，不能自动重试。工具在本机私有日志中保存不含邀约正文和联系方式的提交尝试摘要。流程见 `../../workflows/pugongying-cooperation.md`。

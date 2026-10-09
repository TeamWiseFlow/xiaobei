---
name: xhs-qianfan
description: 小红书千帆合作原子操作：分销商类目、候选列表、总览、合作品类、合作店铺、商品及粉丝数据查询。
metadata:
  openclaw:
    emoji: 🛍️
    requires:
      bins:
      - python3
      - node
---

# 千帆分销商合作

使用 `xhs-qianfan`。先运行 `xhs-hunter check`；它复用 `xhs-hunter login` 保存在 `~/.openclaw/logins/xhs-pc-local.json` 的 PC 会话。千帆接口位于蒲公英站点，账号需要相应分销业务权限；再运行本工具的 `check`，拒绝时停止并报告实际响应。

```bash
xhs-qianfan check
xhs-qianfan categories
xhs-qianfan search --choice '-1' --count 20
xhs-qianfan profile '分销商 buyer_id'
xhs-qianfan methods
xhs-qianfan call get_user_cooperation --kwargs '{"user_id":"分销商 buyer_id"}'
```

`categories` 返回可筛选的分销类目；`search` 按类目索引与数量取候选。`profile` 汇总总览、合作品类、店铺、商品和粉丝数据；检查返回的 `errors`，每项只按实际返回评价。

当前接口只有筛选和查询，没有发起合作或发送消息的方法。形成合作建议后，将目标、商品、预算、佣金与时间等方案交用户审核；如需实际联络，使用用户指定的渠道。详见 `../../workflows/qianfan-cooperation.md`。

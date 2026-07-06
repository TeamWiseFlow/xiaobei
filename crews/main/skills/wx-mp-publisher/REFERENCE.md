# 公众号 AppID / AppSecret 获取指引

> 本文件供 Agent 在用户缺少凭据时读取，据以下步骤指导用户获取 AppID / AppSecret，并写入 `accounts.json`。

## 前置

- relay 服务 IP：`123.60.18.144`（`openclaw-for-business.com` 的 relay 服务地址，官方增值服务）
- 用户需有公众号管理员微信号

## 获取步骤

1. 打开 [https://developers.weixin.qq.com/platform](https://developers.weixin.qq.com/platform)
2. 用**与公众号同一管理员**的微信号扫码登录
3. 首页下方「我的业务」中点「公众号」
4. 选择要授权 Agent 推送文章的公众号
5. 在该页能看到 **AppID**，复制后发给 Agent
6. 同一页面「开发秘钥」中：
   1. 先编辑「API IP 白名单」，填入 `123.60.18.144`
   2. 点 **AppSecret** —— 注意 **AppSecret 只显示一次**，复制好发给 Agent
   3. Agent 确认收到后再点关闭
   4. 若操作失误，可点「重置」重新生成

## 写入 accounts.json

Agent 收到 AppID + AppSecret 后，写入 `crews/main/skills/wx-mp-publisher/accounts.json`：

```json
{
  "default": "main",
  "accounts": [
    { "alias": "main", "appId": "wx...", "appSecret": "..." }
  ]
}
```

- 多账号：在 `accounts` 数组里多加一条，每条取一个易沟通的 `alias`（如 `main` / `tech` / `brand`）
- 多账号时 `default` 必填，指向默认使用的 alias
- 单账号 `default` 可留空字符串 `""`（脚本会自动用唯一账号）

## 安全

- `accounts.json` 已在 `.gitignore` 中，不会进 git
- AppSecret 等同于密码，不要贴到聊天群 / issue / 日志里

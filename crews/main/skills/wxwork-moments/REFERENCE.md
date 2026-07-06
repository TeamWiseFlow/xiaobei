# 企业微信 corp_id / corp_secret 获取指引

> 本文件供 Agent 在用户缺少凭据时读取，据以下步骤指导用户获取企业 ID + corp_secret，并写入 `daemon.env`。
> 同一份凭据同时被 `wxwork-moments`（朋友圈）和 `wxwork-drive`（微盘）使用。

## 前置

- relay 服务 IP：`123.60.18.144`（`openclaw-for-business.com` 的 relay 服务地址，官方增值服务）
- 用户需为企业微信管理员

## 获取步骤

### 1. 企业 ID（corp_id）

1. 打开 [https://work.weixin.qq.com/wework_admin](https://work.weixin.qq.com/wework_admin)
2. 扫码登录企业微信 web 管理后台
3. 左侧导航栏点「我的企业」
4. 页面最下方能看到「企业ID」→ 复制发给 Agent

### 2. 自建应用 + 可信 IP（corp_secret 来源）

1. 仍企业微信 web 管理后台 → 左侧「应用管理」→「应用管理」→ 最下方「自建」中点「创建应用」
2. 进入新建的应用 → 最下方「开发者接口」中选「企业可信 IP」，点「配置」，添加 `123.60.18.144`
3. 应用详情页能看到 **Secret**（即 corp_secret）→ 复制发给 Agent（只显示一次，注意保存）

### 3. 给应用开通微盘 / 客户联系权限

- **微盘**：后台 → 左侧「协作」→ 微盘 → 右侧上部「API」图标（图标很小，仔细看）→ 点开 → 「可调用接口的应用」里添加上一步创建的应用
- **客户联系**（朋友圈用）：后台 → 左侧「客户与上下游」→ 客户联系 → 右侧上部「API」图标 → 点开 → 「可调用接口的应用」里添加同一个应用

## 写入 daemon.env + 重启

Agent 收到 corp_id + corp_secret 后，**不要自己直接改 daemon.env**。两条路：

- **推荐**：把 corp_id / corp_secret 交给 **IT engineer**，由 IT engineer 写入 `daemon.env` 的 `WXWORK_CORP_ID` / `WXWORK_CORP_SECRET`，再用 `gateway` MCP 工具应用配置 + 重启 Gateway。
- **用户自助**：编辑 `daemon.env`，填入：
  ```
  WXWORK_CORP_ID=<企业ID>
  WXWORK_CORP_SECRET=<应用 Secret>
  ```
  然后重启实例（具体重启方式见部署文档 / 问 IT engineer）。

> ⚠️ 写入 daemon.env 后**必须重启实例**才生效。

## 安全

- corp_secret 等同于密码，不要贴到聊天群 / issue / 日志里
- relay 不落盘凭据，只在请求作用域内使用；tokenCache 按 `(corp_id, corp_secret)` 分桶

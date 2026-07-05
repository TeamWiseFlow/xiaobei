# Feishu Work Channel Setup

## 用户侧需要完成：

### 1.创建飞书应用
1. 访问 飞书开放平台（https://open.feishu.cn/?lang=zh-CN），用飞书账号登录
2. 点击「创建企业自建应用」
3. 填写应用名称和描述，选择图标
4. 创建完成后，进入应用详情

### 2.获取应用凭证
在「凭证与基础信息」页面，复制：
- App ID（格式如 cli_xxx）
- App Secret
- 将 APP ID 和 APP Secret 告知 main agent

⚠️ 重要： 请妥善保管 App Secret，不要分享给他人！

### 3.配置权限
在「权限管理」页面，点击「批量导入」，粘贴以下 JSON：
```
{
  "scopes": {
    "tenant": [
      "bitable:app",
      "contact:contact.base:readonly",
      "docs:doc",
      "docs:document.media:upload",
      "docx:document",
      "docx:document.block:convert",
      "docx:document:create",
      "docx:document:readonly",
      "docx:document:write_only",
      "drive:drive",
      "drive:drive.metadata:readonly",
      "drive:drive.search:readonly",
      "drive:drive:version:readonly",
      "im:message",
      "im:message.group_at_msg:readonly",
      "im:message.p2p_msg:readonly",
      "im:message:readonly",
      "im:message:send_as_bot",
      "im:resource",
      "sheets:spreadsheet",
      "wiki:wiki",
      "wiki:wiki:readonly"
    ],
    "user": []
  }
}
```

### 4.启用机器人能力
在「应用能力 → 机器人」页面：
1. 开启机器人能力
2. 配置机器人名称

### 5.配置事件订阅
在「事件与回调」-> 「事件配置」页面：
1. 选择「使用长连接接收事件」（WebSocket 模式）
2. 添加事件：im.message.receive_v1（接收消息）

### 6。发布应用
1. 在「版本管理与发布」页面创建版本
2. 提交审核并发布
3. 等待管理员审批（企业自建应用通常自动通过）

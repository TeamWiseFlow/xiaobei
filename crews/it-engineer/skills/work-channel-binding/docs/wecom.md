# WeCom Work Channel Setup

## 前置：安装 WeCom OpenClaw channel plugin

用户确认安装或升级后，由 IT Engineer 运行：

```bash
WISEFLOW_CONFIRM_WECOM_INSTALL=confirmed work-channel-binding install-wecom
```

安装器从仓根 `openclaw-weixin.version.json` 读取 `@wecom/wecom-openclaw-plugin` 的版本和校验值。插件 ID 为 `wecom-openclaw-plugin`，渠道 ID 为 `wecom`。后续绑定使用 `channels.wecom.accounts.<accountId>` 下的 `botId` 和 `secret`，配置后按技能的生效流程验证。

## 用户侧需要完成：

### 一、创建智能机器人

登录企业微信管理后台（https://work.weixin.qq.com/），以长连接方式创建智能机器人，获取Bot ID和Secret

操作步骤如下：
- 1、打开企业微信客户端或者登录网页版（https://work.weixin.qq.com/），进入工作台->智能机器人，点击创建机器人->手动创建；
- 2、进入创建页面后，选择API模式创建（页面提示「如需使用自有系统获取成员与机器人的聊天并输出回复，可切换至API模式创建」）；
- 3、在API配置页面，选择连接方式为「使用长连接」（无需域名/IP即可接收消息并返回结果，区别于URL回调方式）；
- 4、配置完成后，页面将自动生成并展示Bot ID和Secret，妥善保存该信息（后续关联OpenClaw需使用）；
- 5、补充配置机器人可见范围，其余项保持默认即可，API模式暂不支持预览与调试，直接保存机器人配置。
- 6、将Bot ID和Secret 告知 main agent

⚠️ 重要： 请妥善保管 App Secret，不要分享给他人！

- 7、等待main agent完成绑定后，回到企业微信机器人创建页面，保存并创建。即可在企业微信中与智能机器人正常对话。

如配置完成后未能找到机器人，可在以下路径中找到：工作台->智能机器人->详情->去使用->发消息

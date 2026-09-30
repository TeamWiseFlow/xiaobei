---
name: douyin-login
description: 抖音独立 API 会话初始化、扫码与短信登录、状态检查。
---

# 独立 API 登录

使用 `~/.openclaw/douyin-api/session.json`，权限 0600。会话包括 Cookie、UA、设备档案及同一次登录的安全材料。读取采集、发布、私信、互动和直播均使用此会话。

先运行 `douyin-login relay-check` 和 `douyin-login status`。会话不存在时，请 IT engineer 在受控运行目录准备 `config.json`，或通过 `DOUYIN_API_CONFIG` 指定配置路径。配置需要当前协议参数、UA、设备档案及初始化材料。不得将凭据、动态材料、实现代码或其来源写进工作区/代码仓；不要从旧浏览器 profile 或 Cookie 导出文件复制会话。

```bash
douyin-login init
douyin-login challenge --body-file /受控目录/一次性设备挑战.json
douyin-login qr --output /受控目录/douyin-qr.png
douyin-login poll --timeout 120
douyin-hunter check
douyin-engagement check
```

把二维码图片交给用户扫码。`poll` 复用同一 API 状态，处理登录重定向后验证本人资料；收到确认的 UID 才算登录完成。初始化中断后用 `douyin-login bootstrap` 续接。扫码等待超时可以再次 `poll`；二维码过期重新 `qr`。初始化与挑战材料未齐、Relay 上下文过期或平台要求二次验证时停止并交 IT engineer 处理，不用随机值伪造设备/会话，不把读取成功视作写操作材料齐全。

用户明确选择短信登录时，手机号和验证码放在受控本机文件：

```bash
douyin-login sms-send --phone-file /受控目录/phone.txt --confirm
douyin-login sms-login --code-file /受控目录/code.txt
```

短信发送默认预览；用户已要求发送后才加 `--confirm`。手机号、验证码、QR token、ticket、私钥及配套短期材料不得写入报告或聊天。完成后删除手机号、验证码及二维码文件。

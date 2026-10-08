---
name: douyin-login
description: 抖音独立 API 会话初始化与重新登录、扫码和短信登录、登录 MFA 验证及有效期检查。
---

# 独立 API 登录

使用 `~/.openclaw/douyin-api/session.json`，权限 0600；设置 `DOUYIN_API_SESSION` 时使用指定入口。重新登录后该入口保存新会话文件的位置，全部抖音工具自动读取同一新会话，实际路径由 `status.session_file` 返回。采集、发布、私信、互动和直播共用此会话。Relay 提供设备配置、协议配置与加密运行句柄；客户端直接请求平台并保存 Cookie，不启动浏览器。

## 首次扫码登录

先运行 `douyin-login relay-check` 和 `douyin-login status`。Relay 检查应返回 `automatic_login: true`。会话不存在时直接初始化；无需准备 `config.json`、私钥或一次性挑战文件，也不要安排其他智能体生成这些材料。

```bash
douyin-login init
douyin-login qr --output /受控目录/douyin-qr.png
```

`init` 自动完成匿名设备注册、设备挑战与响应处理，成功返回 `next: qr`。把 `qr` 生成的图片交给用户扫码，然后运行：

```bash
douyin-login poll --timeout 120
```

程序处理登录重定向并查询本人资料；返回 `logged_in: true` 和已确认 UID 后，才能使用平台业务工具。再执行 `douyin-hunter check` 和 `douyin-engagement check`。

`status` 中的 `cookie_present` 只表示主站作用域内存在未过期会话 Cookie；`identity_verified` 表示有效会话已通过本人身份读取并缓存 UID，`logged_in` 与此一致。只有 Cookie 而没有 UID，且没有未完成验证、runtime 未过期时，执行 `douyin-hunter check` 验证现有会话；过期二维码不代表账号已登出，不要仅因此重新初始化。

已有账号需要刷新互动安全材料时执行 `douyin-login refresh`。工具先读取本人身份，再续接当前会话的安全握手；账号、UA 和会话密钥保持绑定，不重新扫码。只保存加密运行句柄、材料名称清单和秒级有效期，不手工补材料值。互动工具提示材料缺少或即将过期时先执行此刷新；账号发生变化或刷新失败时停止写操作。

## 彻底清空本地账号与换号

用户要求彻底清空本地账号时，先结束抖音业务请求和未完成的登录流程，再删除会话入口、`status.session_file` 指向的实际文件、同一账号含凭据的备份和登录临时文件；保留业务数据及其他平台会话。默认登录目录内的 `sessions/login-*`、`session.abandoned-*` 也可能保存历史会话，清空要求覆盖它们。换号或用户明确要求重新登录时执行 `douyin-login restart --confirm`，再获取二维码或按用户选择发起短信登录；登录后核对 UID。该命令保留旧诊断为私有备份，在新的仓外文件中调用 `passport.initialize`，弃用旧 runtime、Cookie、QR、短信与 MFA 状态，所有工具自动切换。它不会发送短信或验证码。直接重复 `init` 只复用原状态，不会换号；需要保留多个账号时可分别设置仓外 `DOUYIN_API_SESSION`，各账号工具使用对应入口，旧会话以 0600 权限保存。

## 登录超时与重新登录

客户端同时保存 Relay 返回的 runtime 和秒级 `runtime_expires_at`。未完成登录从首次初始化起固定 15 分钟；轮询、新句柄和计算重试均不延期。成功平台登录后 Relay 返回较长有效期，仍须真实 `self` 确认 UID。MFA 最多 600 秒，以及二维码、验证码、安全材料各自的有效期仍需满足；runtime 有效不代表这些材料有效。

`status.runtime_expired: true` 或错误 `RUNTIME_EXPIRED` 时停止原登录与业务请求，向用户提示“本次登录已超时，请重新登录”，保留原响应供私有诊断。普通 `init` 不会自动重置。用户明确选择重新登录后执行：

```bash
douyin-login restart --confirm
```

不带 `--confirm` 只预览。完成后按用户选择执行扫码或短信流程，不自动重发之前的短信或验证码，也不重用旧验证码。无论期限是否已到，`LOGIN_STEP_RESULT_UNKNOWN` 都不能作为自动重发的依据。旧会话缺少有效期时不要解码句柄或自行计算期限；后续 Relay 返回有效期或 `RUNTIME_EXPIRED` 后按上述规则处理。

## 中断与状态

- runtime 未过期时，初始化中断后再次运行 `init` 或 `bootstrap` 自动续接；已有初始化会话不会重复初始化。
- `QR_WAIT_TIMEOUT` 表示本次等待结束，继续 `poll`；`QR_EXPIRED` 才重新 `qr` 并交给用户扫码。遇到临时限频，程序自动退避，保留同一二维码。
- 会话缺失时 `status` 返回 `next: init`，属于正常首次使用状态。
- 旧版人工准备的未登录状态由 `init` 自动备份后重新初始化，不导入其中的材料。旧状态已含账号会话时返回 `API_SESSION_LEGACY_REQUIRES_NEW_PATH`，保留原登录；用户要从头测试时执行 `restart --confirm`。
- `LOGIN_ACTION_PENDING` / `LOGIN_MFA_ACTION_PENDING` 表示上一次动作尚未结束，按 `status` 和原命令续接，不并行换步骤。`LOGIN_STEP_RESULT_UNKNOWN` 表示请求已发出但未保存结果，停止重复发送并向用户报告。
- `LOGIN_MFA_REQUIRED` 表示登录需要身份验证；扫码入口停止重复 `poll`，执行 `mfa-prepare`；普通短信入口停止重复 `sms-login`，执行 `sms-mfa-prepare`。保持同一有效会话，不手工删 `login_flow`、改 token 或换二维码处理有效挑战；两种 MFA 和创作者发布验证不能混用。扫码确认、Cookie 数量、验证 ticket 均不能作为登录成功证据。
- 同一阶段持续 `SIGN_FAILED` 时先执行 `status` 后报告研发，保留会话，不连续重试或编辑中间状态。若已有平台响应落盘，重复 `poll` 只会重交该响应，不会取得新的平台状态；它不是验证码过期的证据。
- Relay 或平台错误只报告稳定错误码，不要求用户编写协议材料，不伪造 token。`write_materials_ready: false` 时不能执行要求完整安全材料的写操作。

## 扫码登录 MFA

遇到 `LOGIN_MFA_REQUIRED` 后执行 `douyin-login mfa-prepare`。程序把原已保存扫码响应交 Relay 处理，不重新请求平台；自动保存挑战 ID、方式和新运行句柄。所有后续命令自动使用当前挑战，无需手工传 ID、手机号、票据或 QR token。

向用户说明 `verification.methods` 中实际可选的方式，按用户选择执行对应分支：

| 方式 | 操作 |
| --- | --- |
| `mobile_sms_verify` | `douyin-login mfa-send --method mobile_sms_verify --confirm`；等待用户验证码后，将 4–6 位数字写入仓外 0600 文件，执行 `douyin-login mfa-code --code-file /受控目录/code.txt` |
| `mobile_up_sms_verify` | `douyin-login mfa-send --method mobile_up_sms_verify --confirm`；读取返回的 `user_action_file`，仅向该用户提供平台号码和短信内容，等待用户确认已用本人手机发出，再执行 `douyin-login mfa-confirm --confirm` |
| `face_verify` | `douyin-login mfa-face-prepare --output /受控目录/douyin-face.png`；把二维码交用户用抖音完成身份验证，用户反馈完成后执行 `douyin-login mfa-face-check` |

短信发送和上行短信确认默认预览；用户已选择/要求相应动作才使用 `--confirm`。不自行组合平台请求或改验证方式。`awaiting-code` / `awaiting-up-sms` / `awaiting-face` 都是等待用户的暂停点；人脸未完成时仍返回 `awaiting-face`，等待用户反馈后再显式检查，不持续自动轮询。重复发送入口只恢复已完成步骤的提示或返回中断状态，不重新发送短信；需要再次导出同一人脸二维码，可重复原 `mfa-face-prepare --output ...`。

状态到 `ticket-issued` 后执行 `douyin-login mfa-resume`，程序续接原扫码、重定向并读取本人 UID。只有返回 `logged_in: true` 才完成登录。若已到 `login-confirmed` 但本人资料读取失败，再执行同一 `mfa-resume` 只重试 `self`，不重发扫码或验证码。

`status` 只读本地摘要。遇到计算失败且响应已保存且 runtime 未过期时，重执行同一 MFA 命令会复用原响应，不再次发平台请求；命令、验证码文件内容和当前会话必须保持一致。`LOGIN_MFA_EXPIRED` 表示挑战过期，保留状态并向用户说明；用户决定重新登录后执行 `restart --confirm`，不续用已过期二维码。其他拒绝或结果未知时停止并报告，不自动重新发送、换方式或重建会话。

上行短信内容及人脸 URI 只落到 `user_action_file`，人脸二维码和验证码文件均按凭据保管；不输出原始 URI、票据或挑战到日志/报告。登录完成后删除这批交互文件。技能及签名计算仍分别在客户端和 Relay，不使用浏览器。

## 短信登录

`douyin-publish` 返回 `PLATFORM_VERIFICATION_REQUIRED` 时是创作者二次验证要求，不能用下面的短信登录命令替代。保留当前账号/API 会话和未知发布任务，交研发接入绑定原挑战的专门验证流程；App 验证不保证同步至该 API 会话，不因此重新初始化或重发作品。

普通短信登录返回 2046 时，停止重复 `sms-send` / `sms-login`，保留同一有效会话。收到 `LOGIN_MFA_REQUIRED` 后执行 `douyin-login sms-mfa-prepare`，按实际 `verification.methods` 和用户选择处理；`scene: sms_login` 只表示本次短信入口，不推断平台内部场景。旧流程若保留完整原响应，`sms-mfa-prepare` 仅重交原计算，不重新请求平台；缺失原响应时不重发短信来补材料。

短信 MFA 的三种方式与上方扫码 MFA 相同，但命令分别使用 `sms-mfa-send`、`sms-mfa-code`、`sms-mfa-confirm`、`sms-mfa-face-prepare`、`sms-mfa-face-check`。参数及用户确认规则相同，挑战、方式和原短信登录提交由程序绑定，不能套用扫码 `mfa-*`。到 `ticket-issued` 后执行 `douyin-login sms-mfa-resume`，程序续接原短信登录和重定向，再读取真实 `self`；这一步不发送新的短信。已到 `login-confirmed` 但 `self` 失败时，重复同一入口只重试身份读取。

`LOGIN_VERIFICATION_FLOW_UNSUPPORTED` / `type: UNSUPPORTED` / `next: report-verification` 表示没有受支持的续接方式；保留诊断并向研发报告安全摘要，不发验证请求。裸 `LOGIN_VERIFICATION_REQUIRED` 且 `next: sms-mfa-prepare` 可按上段处理已保存原响应；仍无可用摘要时停止。2046 本身不能证明账号被封禁。遇到 `RUNTIME_EXPIRED` 按登录超时流程处理，不直接请求 Relay、编辑挂起状态或换二维码绕过验证。

用户明确选择短信登录时，将手机号与六位验证码放在受控本机文件：

```bash
douyin-login sms-send --phone-file /受控目录/phone.txt --confirm
douyin-login sms-login --code-file /受控目录/code.txt
```

短信发送默认预览；用户已要求发送后才加 `--confirm`。手机号、验证码、二维码 token、运行句柄、ticket 和 Cookie 不写入报告或聊天。完成后删除手机号、验证码及二维码文件。会话及其计算实现、来源信息均不得放进代码仓；不要导入旧浏览器 profile 或 Cookie 导出文件。

本登录工具归 douyin-hunter 包，供采集和 expert-bd 互动复用；expert-douyin 发布与本人取数使用独立 Camoufox profile，不经本工具或 login-manager。

# IT Engineer Agent — Workflow

> - **定位**：main + sales-cs 的 **sub-agent**，**无 channel**（不直接面对用户）
> - **入口**：被 main `sessions_spawn` 调用；不接受微信 / 飞书 / awada 直发
> - **职责**：运维 / 部署 / 升级 / 排故 / 渠道配置（awada / Feishu / WeCom） / 启用停用 crew
> - **数据底座**：MEMORY.md 顶部"运维知识"章节

## xiaobei 程序升级与服务重启

升级流程和服务重启流程详见 MEMORY.md，按其中步骤执行即可。

## 答疑流程

```
1. 理解用户的问题（如果不清楚，追问一个关键细节）
2. 给出简明答案
3. 如果需要操作，提供完整可执行步骤
4. 主动问：这样解释清楚了吗？还有其他疑问吗？
```

## SEO 优化

SEO 技术优化与巡检属于 IT Engineer 职责范围，具体操作调用 `seo` 技能执行。

## 云计算资源管理

通过 CLI 管理云资源属于 IT Engineer 职责范围：
- 腾讯云资源操作 → 调用 `tccli` 技能
- 阿里云 skill 搜索与发现 → 调用 `alicloud-find-skills` 技能

## 网站合规

ICP 备案与合规属于 IT Engineer 职责范围：
- ICP 备案指导 → 调用 `icp-filing` 技能
- Apple 国区 ICP 豁免申请 → 调用 `icp-exemption` 技能

## 渠道配置（对外 crew 启用与工作 channel 绑定）

当用户或 main agent 要求启用对外 crew（如 sales-cs）或绑定工作渠道时，按如下流程
调用对应技能。**不把技能执行细节在本文件展开**，只声明何时用哪个技能。

### 启用 sales-cs + 配置 awada channel

用户要求启用 sales-cs / 让 sales-cs 能联系外部用户 → 先建议配置 awada channel，
获得确认后调用 `awada-channel-setup` 技能完成（装依赖 → 写 openclaw.json → 重启
Gateway → 验证）。

### 绑定飞书工作 channel

用户要求配置飞书工作 channel / main agent 建议配置工作 channel 且用户选飞书 →
调用 `work-channel-binding` 技能（Feishu 流程）。

### 绑定企业微信工作 channel

用户要求配置企业微信工作 channel / 用户选 WeCom → 调用 `work-channel-binding`
技能（WeCom 流程，含插件安装）。


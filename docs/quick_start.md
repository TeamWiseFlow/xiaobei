# 部署后怎么用（推荐流程）

## 初次安装后的入口

xiaobei 默认只保证一个入口即可最小化使用：

```text
openclaw-weixin -> Main Agent
```

安装后先完成微信登录和配对：

```bash
openclaw channels login --channel openclaw-weixin
openclaw pairing list openclaw-weixin
openclaw pairing approve openclaw-weixin <id>
```

然后直接在微信私聊 Main Agent。

> 当前 Weixin channel 支持 direct chats 和 media，不默认承诺微信群能力。

## 推荐上手三步走

### 第一步：让 Main Agent 完成 onboard

```text
你（微信私聊 Main Agent）：
我刚完成 xiaobei 安装，帮我完成初始化。我的公司/品牌是 <名称>，主营 <业务>，我希望先解决 <第一个目标>。
```

Main Agent 会：

- 介绍 xiaobei team 的使用方式；
- 记录业务/品牌背景；
- 判断是否需要招募对内 crew；
- 在必要时引导配置 Feishu 或 WeCom 工作 channel。

初始团队状态：

- Main Agent：微信入口和系统控制面；
- IT Engineer：Main Agent 的系统运维 subagent；
- HRBP：默认未启用，首次需要 external crew 时再启用。

### 第二步：通过 Main Agent 招募对内 Crew

例如启用新媒体运营：

```text
你：
帮我招募一个新媒体小编，用 main 模板，ID 就叫 main。
```

Main Agent 会展示方案，等待确认。确认后完成实例化。

如果该 crew 有 `BOOTSTRAP.md`，Main Agent 会代为完成首次问询，例如：

- 运营哪些平台；
- 是否做微信公众号/企微朋友圈；
- 是否需要 IP 白名单或中转模式；
- 品牌资料、目标受众、发布节奏、审核流程。

开始使用：

```text
你：
@main 帮我写一篇关于 <选题> 的公众号文章，面向 <目标读者>。
```

### 第三步：按需配置工作 channel

fresh install 不预置 Feishu / WeCom。以下情况 Main Agent 会建议配置工作 channel：

- 对内 crew 数量较多；
- 用户额外招募第二个对内 crew 后团队开始复杂；
- 首次需要 external crew；
- 用户频繁希望直接联系某个 specialist。

流程：

```text
你：
帮我配置工作 channel。

Main Agent：
你想用 Feishu 还是 WeCom？
```

随后 Main Agent 会按教程引导你准备 bot id / secret / account id，写入对应 channel account，并修改 `openclaw.json` 的 binding。Main Agent 不会在摘要中回显 secret。修改后需要你确认是否重启 Gateway。

## External Crew

对外 crew（客服、销售、社群接待等）不由 Main Agent 直接创建。

首次需要 external crew 时：

1. Main Agent 提醒需要启用 HRBP；
2. 推荐先配置 Feishu 或 WeCom 工作 channel；
3. HRBP 负责 external crew 生命周期；
4. 对外服务 channel（如 awada）按 external crew 场景单独设计。

## IT Engineer 日常运维

IT Engineer 无默认 direct channel，通过 Main Agent 调用：

```text
你：
@it-engineer 帮我做一次系统巡检，重点检查模型/API 配置、channel binding、最近异常日志。
```

升级系统：

```text
你：
@it-engineer 帮我把系统升级到最新版本。
```

## 3 分钟速查

```text
# 初始 onboard
你：我刚完成安装，帮我完成 xiaobei 初始化。

# 招募对内 crew
你：帮我招募一个新媒体小编，用 main 模板。

# 使用 IT Engineer
你：@it-engineer 做一次系统巡检。

# 配置工作 channel
你：帮我配置工作 channel。

# 查看团队状态
你：帮我看一下现在有哪些 crew 在运行。
```

# 生产部署

```bash
./scripts/install.sh
```

日后升级同样执行：

```bash
./scripts/install.sh
```

> `install.sh` 是幂等的——重复执行只更新有变化的部分，不会覆盖用户数据。

## 常用命令

```bash
./scripts/dev.sh gateway              # 开发模式启动
./scripts/dev.sh gateway --port 18789 # 指定端口
./scripts/install.sh                  # 生产部署 / 升级（幂等）
./scripts/install.sh --skip-crew      # 仅重装 daemon，跳过 crew 同步
./scripts/install.sh --skip-weixin    # 跳过 openclaw-weixin 插件安装
./scripts/apply-addons.sh             # 重新应用补丁 + 全局技能 + awada 注入
./scripts/setup-crew.sh               # 重新同步 Agent 系统配置
./scripts/setup-crew.sh --force       # 覆盖已有 workspace
```

## Addon 开发

详见 **[addon_development.md](./addon_development.md)**。

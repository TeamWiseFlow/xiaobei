# 小贝 — Memory

## 平台策略与品牌上下文

<!-- 由 BOOTSTRAP 首次收集写入，后续运行中持续更新 -->

## crew 列表

小贝的背后是一支专业的AI团队，成员和分工如下：

- **main agent（小贝）**：DEFAULT 角色，绑 openclaw-weixin 通道
- **content-producer**：复杂内容制作crew（如专业视频制作、整体视觉输出），简单的图文海报、短视频等由main agent直接调用相关技能完成。
- **it-engineer**：系统运维（subagent 调用；找它处理部署 / 升级 / 排故）
- **sales-cs**：销售客服，绑 awada 通道；**默认 seed 不在 openclaw.json**，启用走 `sales-cs-enablement` 技能（检查 awada → channel 选择 → 派 IT engineer 配置 → 初始化AGENTS.md/IDENTITY.md/SOUL.md → 软链 `business_knowledge.md` + `business_knowledge/`）；启用后的调整走 `sales-cs-review` 技能
- 旧版产品中的 selfmedia-operator / business-developer / designer / hrbp 全部合入main agent（小贝）

## 已启用的定时任务

> 本段登记 main agent 当前已启用的所有定时任务（cron）。**默认全部未启用**——启用需
> spawn IT engineer 设 cron。停用时同步从本段移除并让 IT engineer 撤 cron。
>
> 启用路径：
> - **每日新媒体平台数据复盘**：内容已在 HEARTBEAT.md 中，需 spawn IT engineer 设
>   cron 后启用。
> - **BD / IR 定时模式**：用户确认启用某模式后，从 `HEARTBEAT_TEMPLATE.md` 复制对应
>   段落到 `HEARTBEAT.md`，再 spawn IT engineer 设 cron。各模式 cron 表达式见
>   `HEARTBEAT.md` 中对应段的「执行时间 / 频率」。

| 任务名 | 工作条块 | cron 表达式 | 启用日期 | 状态 |
|--------|----------|-------------|----------|----------|
| _（默认空，启用后由 main agent 登记）_ | | | | |

<!-- 启用示例（勿预填）：
| 每日新媒体数据复盘 | 新媒体运营 | 17 8 * * * | 2026-07-06 | 启用 |
| Lead Hunting | BD | 0 9,21 * * * | 2026-07-06 | 启用 |
| Investor Hunting | IR | 0 10 * * 1-5 | 2026-07-06 | 启用 |
-->

## Notes

<!-- 运行中持续更新 -->

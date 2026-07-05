# 小贝 — Memory

>
> **产品定位**：OPC / 中小微企业老板的 AI 搞钱搭子。
> **对用户自称**：**小贝**。

## 平台策略与品牌上下文

<!-- 由 BOOTSTRAP 首次收集写入，后续运行中持续更新 -->

## 产品拆分后 crew 拓扑（2026-07-04）

> 本节为产品拆分（client + relay 双仓）后，main 自身的"团队成员清单"备忘。

- **main（小贝本人）**：DEFAULT 角色，绑 openclaw-weixin 通道
- **content-producer**：视频 / 图像内容生产（subagent 调用）
- **it-engineer**：系统运维（subagent 调用；找它处理部署 / 升级 / 排故）
- **sales-cs**：销售客服，绑 awada 通道；**默认 seed 不在 openclaw.json**，启用时让 it-engineer 改 enabled + 软链 `business_knowledge/`
- 旧 Pro 仓的 selfmedia-operator / business-developer / designer / hrbp 全部合入本仓 crew（无独立 crew）

## sales-cs 启用 / 软链 / HRBP 优化知识

- **启用流程**（用户要求启用 sales-cs 时）：
  1. 跟用户确认是否真要启用（外部通道，一开就要有人来聊天的）
  2. 让 it-engineer 走 `awada-channel-setup` 技能：
     - 装依赖
     - 写 openclaw.json 加 sales-cs agent
     - 重启 Gateway
     - 验证（awada 通道连通）
  3. 让 it-engineer 软链 `business_knowledge/` 目录到 sales-cs workspace
  4. 用户微信扫码绑定 awada 通道
- **HRBP 优化知识**（Pro 仓经验保留）：
  - EXTERNAL_CREW_REGISTRY.md 是 HRBP 维护的"已招募外部 crew 注册表"
  - main 启用 sales-cs 时**不**直接写 openclaw.json——通过 it-engineer 走 `awada-channel-setup` 技能（避免与 HRBP 状态冲突）
  - sales-cs 的 `business_knowledge/` 软链是 HRBP 业务知识库（公司产品 / 客户案例 / 行业话术），不放在 main 的 MEMORY
- **典型启用后流程**：
  - 用户问"能不能让销售主动联系我" → 答"需要先启用 sales-cs 通道（awada），我可以帮你委派 it-engineer 启用"
  - 用户问"销售现在在不在" → 答"sales-cs 默认未启用，启用流程是 X，要不要我帮你开？"

## Notes

<!-- 运行中持续更新 -->

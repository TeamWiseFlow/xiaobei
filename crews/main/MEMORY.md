# 小贝 — Memory

## 平台策略与品牌上下文

<!-- 由 BOOTSTRAP 首次收集写入，后续运行中持续更新 -->

## 产品拆分后 crew 拓扑（2026-07-04）

> 本节为产品拆分（client + relay 双仓）后，main 自身的"团队成员清单"备忘。

- **main agent（小贝本人）**：DEFAULT 角色，绑 openclaw-weixin 通道
- **content-producer**：视频 / 图像内容生产（subagent 调用）
- **it-engineer**：系统运维（subagent 调用；找它处理部署 / 升级 / 排故）
- **sales-cs**：销售客服，绑 awada 通道；**默认 seed 不在 openclaw.json**，启用时让 it-engineer 改 enabled + 软链 `business_knowledge/`
- 旧版产品中的 selfmedia-operator / business-developer / designer / hrbp 全部合入main agent（小贝本人）

## Notes

<!-- 运行中持续更新 -->

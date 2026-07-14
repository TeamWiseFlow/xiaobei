---
name: exp-invite
description: >
  Invite a qualified customer into the experience group when they want to
  understand the product form further after seeing demo materials. The invite
  is sent as an awada control message, and the customer status is updated to
  exp_invited to prevent duplicate invitations.
---

# exp-invite

> 技能目前为示例。启用前需根据实际业务调整。

## 用途
当客户希望进一步了解产品形态、看完 demo 后仍有较大疑问，且明确同意加入体验群时，发送体验群邀请。

## 客户标识提取规则
此处需要同时传入两个标识符，各自职责不同：

```bash
exp-invite \
  --peer "<[CustomerDB].peer>" \
  --user-id-external "<Sender.id>"
```

- `--peer`：来自 `[CustomerDB].peer`，用于 DB 查询和写库
- `--user-id-external`：来自消息上下文 Sender 块的 `id` 字段（awada 原始用户 ID），用于 awada 平台路由邀请动作

## 行为规则

### 主动邀请限制
对于 `business_status` 不为 `free` 的用户（如 `exp_invited`、`subs`、`club`）：
- **不要主动邀请**他们进入体验群
- 应回到主流程 3.7，继续主动引导

### 允许再次邀请的情况
如果客户**明确要求**再次拉入群或再次 invite，可以使用 `--force` 参数强制发送邀请：
- 客户可能忘记接受之前的邀请
- 客户可能主动退出后想重新加入

```bash
exp-invite \
  --peer "<[CustomerDB].peer>" \
  --user-id-external "<Sender.id>" \
  --force
```

### business_status 更新规则
- 若 `business_status` 为空或 `free`：更新为 `exp_invited`
- 若已有值（`exp_invited`/`subs`/`club`）且使用 `--force`：**不更新** business_status，仅发送邀请

### 邀请消息格式
邀请消息是 awada 控制消息，不是自然语言：

```text
/invite//<user_external_id>//风暴眼（wiseflow情报小站）
```

awada-channel 会将其转为拉群动作。

## 返回约定
- 成功：标准输出 invite 控制消息
- 已邀请过且未指定 --force：输出 `ALREADY_INVITED`，并以非 0 状态退出

## 当前体验群名称
- `风暴眼（wiseflow情报小站）`

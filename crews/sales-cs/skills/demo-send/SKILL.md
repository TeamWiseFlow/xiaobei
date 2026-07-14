---
name: demo-send
description: >
  Send product demo material to a free-status customer when they
  ask about concrete usage, want to understand the product form, or need a
  first visual reference before deeper sales qualification.
---

# demo-send

> 技能目前为示例。启用前需根据实际业务调整。

## 用途
当客户属于 `free` 状态，且提出具体使用问题、想先看看产品形态、或需要一个直观参考时，发送 demo 材料。

## 调用方式

使用 `message` 工具发送预存在微信网盘中的 demo 文件：

```
message(action="sendAttachment", file_name="<文件名>")
```

> **错误示例**（禁止使用）：
> ```
> message(action="sendAttachment", filename="...", filePath="...")
> ```
> 参数名必须是 `file_name`（带下划线），不得传 `filePath` 或 `filename`。`file_name` 对应微信网盘中已存的文件名，不是本地路径。

**可用文件**：
- `wiseflow5x.mp4` — 小贝（xiaobei）系统演示视频

**示例**：
```
message(action="sendAttachment", file_name="wiseflow5x.mp4")
```

## 完整发送流程

1. 直接调用 `message(action="sendAttachment", file_name="...")` 发送文件（**本 turn 不输出任何文字**）
2. 工具返回后，在最后一个 turn 统一输出完整回复：说明已发送 demo + 追问客户的具体需求或应用场景 + 提醒官网/GitHub 主页获取最新信息

> **重要**：不要在调用工具前生成任何文字（包括"我先给您发一份..."之类的介绍语），否则客户会收到多条内容相近的消息。

## 调用后必须做的事
发送 demo 后，**必须立刻追问客户的具体需求或应用场景**，不得只发完就结束。

---
name: icp-filing
description:
  ICP 备案指南助手。提供备案流程、材料清单、服务商选择、时间线、常见问题、
  域名查询指引、各省备案号前缀、备案底部 HTML 代码生成。
  当用户提到 ICP 备案、网站备案、域名备案时触发。
metadata:
  openclaw:
    emoji: 🏛️
    requires:
      bins:
        - python3
---

# ICP 备案指南助手

## 概述

提供中国网站 ICP 备案全流程指导：材料清单、流程步骤、域名查询指引、各省备案号前缀、备案底部 HTML 代码。

## 触发场景

- 用户提到 ICP 备案、网站备案、域名备案
- 用户需要准备备案材料
- 用户询问备案流程或时间线
- 用户需要生成备案底部 HTML 代码

## 命令列表

| 命令 | 功能 |
|------|------|
| `checklist [personal\|company]` | 备案材料清单（默认企业） |
| `flow` | 备案流程步骤 |
| `query <domain>` | 域名备案查询指引 |
| `province [省名]` | 各省 ICP 备案号前缀 |
| `footer <备案号>` | 生成备案底部 HTML 代码 |

## 使用方式

```bash
icp-filing checklist company
icp-filing flow
icp-filing query example.com
icp-filing province 广东
icp-filing footer "京ICP备2024001234号-1"
```

## 备案号格式

```
[省份简称]ICP备[8位数字]号-[网站序号]
```

例如：京ICP备2024001234号-1

## 常见问题

- **备案期间网站能访问吗？** 不能，备案期间网站须关闭或设置"网站建设中"页面
- **个人可以备案吗？** 可以，但不能涉及商业内容
- **备案需要多长时间？** 约 10-25 个工作日
- **一个主体可以备案多个网站吗？** 可以
- **手机号有要求吗？** 须为备案省份的号码

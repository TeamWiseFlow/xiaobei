---
name: icp-exemption
description:
  生成 Apple 国区 ICP 豁免申请附件 PDF。当用户提到 ICP 备案、Apple 国区下架、ICP 豁免申请、
  App Store 中国区合规、申请例外批准等相关内容时，立即触发此 skill。收集用户的 Team ID、
  账户持有人姓名、App ID 等信息，调用脚本生成符合 Apple 要求的正式申请附件 PDF 文件。
metadata:
  openclaw:
    emoji: 📄
    requires:
      bins:
        - python3
---

# Apple 国区 ICP 豁免申请附件生成器

## 概述

此 skill 用于生成 Apple App Store 中国大陆地区 ICP 备案豁免申请所需的正式附件 PDF。

## 前置依赖

- Python 3.8+ 及 `reportlab` 库（`pip install reportlab`）
- 中文字体包（如 `fonts-wqy-zenhei`），需提前安装：
  ```bash
  sudo apt-get install fonts-wqy-zenhei
  ```

## 触发场景

- 用户提到 ICP 备案/豁免/例外
- 用户的 App 在国区被下架，需要申请豁免
- 用户需要准备 Apple 中国区合规材料
- 用户提到 "申请例外批准"、"ICP 相关申诉" 等

## 信息收集

在生成 PDF 前，需要向用户收集以下信息：

### 必填信息

1. **Team ID**（团队 ID）— 在 App Store Connect → 账户 → 会员资格 中查看
2. **账户持有人法定姓名**（中文全名，与证件一致）
3. **App ID**（应用 ID）— 在 App Store Connect 的 App 详情页中查看
4. **申请日期**（默认今天，用户可更改）

### 信息收集方式

直接在对话中逐一询问，或一次性询问所有信息：

```
请提供以下信息来生成 ICP 豁免申请附件：
1. Team ID（例如：ABCD123456）
2. 账户持有人法定姓名
3. App ID（例如：1234567890）
4. 申请日期（格式：YYYY年MM月DD日，留空则使用今天）
```

## PDF 生成步骤

收集好所有信息后，运行以下命令生成 PDF：

```bash
icp-exemption \
  --team-id "TEAM_ID" \
  --name "法定姓名" \
  --app-id "APP_ID" \
  --date "YYYY年MM月DD日"
```

默认输出到当前目录下的 `ICP豁免申请附件.pdf`，可通过 `--output` 指定路径。

生成后使用 `present_files` 将 PDF 提供给用户下载。

## 注意事项

- 生成的 PDF 需要用户**手写签名**后再提交
- 一个 App 对应一份附件，多个 App 需分别生成
- 提醒用户核实所有信息与 App Store Connect 账户完全一致
- PDF 使用中文，符合 Apple 中国区审核团队要求

## 申请说明

生成附件后，告知用户提交流程：

1. 打印或在平板上手写签名
2. 扫描/拍照保存为 PDF
3. 登录 App Store Connect，找到被下架的 App
4. 点击「联系我们」→「ICP 相关问题」
5. 上传签名后的附件，说明 App 不联网或仅使用 Apple 服务
6. 提交等待 3-7 个工作日审核

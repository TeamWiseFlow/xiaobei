---
name: init-workspace
description: 为单项设计任务创建标准目录结构和 brief 模板。每次接到设计需求时首先调用。
metadata:
  openclaw:
    emoji: 📁
---

# Init Workspace

为每一项设计任务创建独立的文件夹和 brief 模板。

## 用法

```bash
/home/wukong/wiseflow-pro/crews/content-producer/skills/init-workspace/scripts/init.sh <任务名>
```

示例：

```bash
/home/wukong/wiseflow-pro/crews/content-producer/skills/init-workspace/scripts/init.sh xiaobei-launch-poster
```

## 产出

在 `design_assets/` 下创建 `YYYY-MM-DD-<任务名>/` 目录，包含：

```
design_assets/YYYY-MM-DD-<任务名>/
├── brief.md        # 设计需求模板（待填写）
├── prompts.json    # 生图参数记录
├── source/         # 原始素材（参考图、品牌资产等）
└── output/         # 成品输出
```

## 使用时机

每项设计任务开始前**必须**调用此脚本，确保所有产出有独立归档。

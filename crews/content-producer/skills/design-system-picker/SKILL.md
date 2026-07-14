---
name: design-system-picker
description: 根据风格描述从内置设计系统库中匹配最合适的设计系统，提供设计规范供后续设计工作使用。
metadata:
  openclaw:
    emoji: 🎨
---

# Design System Picker

从内置设计系统库中匹配最合适的设计系统，为后续网页/界面设计提供风格规范基础。

> **路径规则**：本 skill 调用的脚本和文件用**相对 skill 自身的相对路径**（`./scripts/...` / `./design-systems/...`），不依赖仓部署位置。openclaw 加载 skill 时注入 skill 根目录，agent 直接用相对路径即可。

---

## 用法

### 搜索匹配

```bash
./scripts/pick.sh "<风格描述>"
```

示例：

```bash
./scripts/pick.sh "科技感暗色主题"
./scripts/pick.sh "类似 Stripe 的金融风格"
./scripts/pick.sh "温暖亲和的生活服务"
```

### 读取设计系统详情

搜索到匹配结果后，读取对应的设计系统文件获取完整规范：

```
读取 ./design-systems/<file>
```

例如匹配到 Stripe，则读取 `./design-systems/stripe.md`。

---

## 内置设计系统

| 设计系统 | 风格关键词 | 适用场景 |
|---------|----------|---------|
| Stripe | 紫色渐变、优雅、金融科技 | SaaS 产品页、支付/金融科技落地页 |
| Vercel | 黑白极简、精密、Geist | 开发者工具、技术产品官网 |
| Linear | 超极简、紫色点缀、精确 | 项目管理、效率工具 |
| Notion | 暖色极简、衬线标题、柔和 | 知识管理、内容平台 |
| Apple | 极致留白、电影级影像 | 消费电子、高端品牌官网 |
| Supabase | 暗色翡翠绿、代码优先 | 数据库/后端服务、开源工具 |
| Shopify | 暗色电影感、霓虹绿 | 电商平台、商业服务 |
| Figma | 多彩活泼、专业、创意 | 创意工具、设计平台 |
| Spotify | 鲜明绿、大胆排版 | 媒体/娱乐平台 |
| Tesla | 极致减法、全屏影像 | 汽车/硬件、极简品牌 |
| Framer | 黑蓝、动效优先 | 网站构建、交互展示 |
| Airbnb | 暖色珊瑚、摄影驱动 | 旅游/生活服务、社区平台 |
| BMW | 巴伐利亚蓝、暗色奢华、金属质感 | 奢侈品牌、高端产品 |
| IBM | 企业蓝、Carbon 系统、数据密集 | 企业级产品、B2B 服务、数据平台 |
| Starbucks | Siren 绿、温暖社区、自然质感 | 生活品牌、餐饮/零售、社区平台 |

---

## 使用时机

每项设计任务开始时，在 brief 确认后、进入具体设计前**必须**调用此技能确定设计系统。设计系统选定后，所有后续 HTML/CSS 产出的色彩、字体、间距、组件样式都应遵循该设计系统的规范。

---

## 自定义设计系统

如果用户提供的风格描述与内置设计系统均不匹配，应基于用户描述自行构建设计系统，输出格式参照内置 DESIGN.md 的标准结构：

1. Visual Theme & Atmosphere
2. Color Palette & Roles
3. Typography Rules
4. Component Stylings
5. Layout Principles
6. Depth & Elevation
7. Do's and Don'ts
8. Responsive Behavior

---

## 探索更多设计系统

内置设计系统无法覆盖所有风格需求。当内置库中没有合适匹配，或用户指定了特定品牌/风格参考时，可从上游仓库 [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) 中查找并导入：

### 查找流程

1. 访问 `https://github.com/VoltAgent/awesome-design-md` 查看完整设计系统列表
2. 也可直接访问 `https://getdesign.md/<brand-name>/design-md` 查看特定品牌的设计系统（如 `https://getdesign.md/starbucks/design-md`）
3. 选取匹配的设计系统后，将内容下载为 `./design-systems/<name>.md`

### 导入流程

找到合适的设计系统后，必须完成以下两步才能使用：

**1. 添加设计系统文件**

将 DESIGN.md 内容保存到 `./design-systems/<name>.md`，确保遵循标准的 8 段结构。如果不完整，应基于下载内容补全缺失段落。

**2. 注册到索引**

在 `./design-systems/index.json` 中添加条目：

```json
{
  "id": "<name>",
  "name": "<Brand Name>",
  "category": "<category>",
  "keywords": ["关键词1", "关键词2", ...],
  "description": "一句话风格描述",
  "colorPrimary": "#HEX",
  "darkMode": true/false,
  "bestFor": "适用场景描述",
  "file": "<name>.md"
}
```

完成后即可通过 `./scripts/pick.sh` 搜索到该设计系统。
# Workflow：Brand Visual（品牌视觉体系构建）

任务类型：为品牌建立可复用的视觉规范（色彩 / 字体 / 组件 / 间距 / 阴影 / 响应式 / 护栏）。Step 1/2/3/6/7 按 `expert-design` SKILL.md 的通用骨架执行，本文只写本类型的 brief 必含字段与 Step 5 差异。

## Step 2：brief 必含字段

- 品牌定位（行业、目标客群、核心价值）
- 风格方向（1–3 个关键词，如"专业 + 科技 + 温暖"）
- 现有品牌资产（Logo、已有色彩偏好、字体文件；给绝对路径）
- 应用场景（官网 / APP / 社交媒体 / 印刷品…）——决定 token 粒度与暗色表面是否必需

## Step 5：构建完整 DESIGN.md（八段）

1. Visual Theme & Atmosphere：设计哲学、情感基调、密度
2. Color Palette & Roles：语义名 + hex + 功能角色
3. Typography Rules：字体族 + 完整层级表
4. Component Stylings：核心组件样式 + 状态
5. Layout Principles：间距系统、网格、留白哲学
6. Depth & Elevation：阴影系统、表面层级
7. Responsive Behavior：断点、触控目标、折叠策略
8. Do's and Don'ts：设计护栏

## Step 5 另编写组件预览页（preview.html）

- 展示色彩色板、字体层级、按钮 / 卡片 / 输入框等核心组件
- 包含亮色与暗色两种表面
- 所有样式走 CSS custom properties，便于直接复用到后续页面

## 交付

DESIGN.md + preview.html 落 `output/`；把 DESIGN.md 核心信息（品牌色、字体、护栏）同步到 MEMORY.md 的 Brand Assets 区——**同步前须经甲方确认**。回报绝对路径 + 视觉 review 结论。

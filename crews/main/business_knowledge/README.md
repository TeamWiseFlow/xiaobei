# business_knowledge/ — 业务知识支撑材料

> 这是 `business_knowledge.md`（**单文件**，位于上级目录）的**支撑文件夹**。
> 业务知识**正文**写在 `../business_knowledge.md` 里；本文件夹只放**引用型材料**：
> 产品截图、价目表截图、案例素材、合同模板、客户名单、资质证书等。

## 定位

- ✅ 放：图片、PDF、截图、二进制素材、过长的附录（不便内联进 md 的）
- ❌ 不放：业务知识正文（正文进 `business_knowledge.md`）
- ❌ 不放：可被 `campaign_assets/` 收纳的运营素材（运营素材归 `campaign_assets/`）

## 命名约定

建议按用途命名，便于在 `business_knowledge.md` 里引用：

```
business_knowledge/
├── README.md              # 本说明
├── pricing-2026.png       # 价目表截图
├── case-xxx.md            # 案例附录
└── ...
```

在 `business_knowledge.md` 中引用：`见 business_knowledge/pricing-2026.png`。

## 治理

- 由 **main agent** 维护，落盘前征得用户同意（与 `business_knowledge.md` 同治理边界）。
- sales-cs workspace 通过软链访问本文件夹（与 `business_knowledge.md` 一同软链）。

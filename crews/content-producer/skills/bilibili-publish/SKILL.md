---
name: bilibili-publish
description: Publish videos to Bilibili (B站) via relay proxy. One-step multipart
  upload: video + metadata → relay → B站 Open Platform. No local
  BILIBILI_APP_ID / BILIBILI_APP_SECRET required; uses OFB_KEY + RELAY_BASE_URL.
metadata:
  openclaw:
    emoji: 📺
    requires:
      bins:
      - python3
      env:
      - RELAY_BASE_URL
      - OFB_KEY
    primaryEnv: OFB_KEY
    homepage: https://www.volcengine.com/docs/82379/1541523
---

# B站视频发布（bilibili-publish，relay 代理版）

> **架构**：relay 一站式代理。
> - skill 内**不持** BILIBILI_APP_ID / BILIBILI_APP_SECRET
> - skill 内**不做** OAuth2 授权 / token 刷新 / MD5 签名 / 分块上传
> - 单一 multipart POST → relay → B站 Open Platform

---

## 前置条件

1. 环境变量 `RELAY_BASE_URL`（默认 `https://relay.wiseflow.example.com`，entrypoint 注入；用户无需配置）
2. 环境变量 `OFB_KEY`（产品方发放；entrypoint 注入）
3. 视频文件准备好（mp4）

---

## 使用方式

```bash
python3 /abs/path/to/crews/content-producer/skills/bilibili-publish/scripts/publish_bilibili.py \
  --title "视频标题" \
  --video video.mp4 \
  --tid 122 \
  --tags AI,科技,工具
```

带封面和描述：

```bash
python3 /abs/path/to/.../publish_bilibili.py \
  --title "视频标题" \
  --video video.mp4 \
  --cover cover.jpg \
  --desc "视频描述" \
  --tid 122 \
  --tags AI,科技
```

---

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--title` | 是 | 视频标题，最多 80 字 |
| `--video` | 是 | 视频文件路径（mp4） |
| `--cover` | 否 | 封面图路径（jpg/png）；不提供则 B站自动截取 |
| `--desc` | 否 | 视频描述 |
| `--tid` | 否 | 分区 ID，默认 122（野生技术协会） |
| `--tags` | 是 | 逗号分隔标签，最多 10 个，每个最多 20 字 |
| `--copyright` | 否 | 1=自制（默认），2=转载 |

---

## 常用分区 ID

| tid | 分区 |
|-----|------|
| 122 | 野生技术协会 |
| 36 | 知识 · 科技 |
| 95 | 数码 |
| 207 | 资讯 |
| 21 | 日常 |
| 76 | 美食制作 |

---

## Relay 调用契约

**Endpoint**：`POST ${RELAY_BASE_URL}/api/v1/publish/bilibili/submit`

**Headers**：
- `X-OFB-Key: ${OFB_KEY}`（relay 鉴权）
- `Content-Type: multipart/form-data; boundary=...`（自动生成）

**Body**（multipart/form-data）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | text | 是 | 视频标题 |
| `desc` | text | 否 | 视频描述 |
| `tid` | text | 是 | 分区 ID（数字字符串） |
| `tags` | text | 是 | 逗号分隔标签 |
| `copyright` | text | 是 | 1 或 2 |
| `video` | file | 是 | 视频文件（mp4） |
| `cover` | file | 否 | 封面图（jpg/png） |

**Response**：JSON

```json
{
  "ok": true,
  "bvid": "BV1xxx",
  "url": "https://www.bilibili.com/video/BV1xxx"
}
```

错误时：
```json
{"ok": false, "error": "BILI_UPLOAD_FAILED", "msg": "..."}
```

---

## Agent 工作流

1. 准备视频文件 + 标题 + 分区 + 标签
2. 运行 `publish_bilibili.py`（自动完成 multipart 组装 + HTTP POST）
3. 检查 stdout JSON 输出：
   - `{"ok": true, "bvid": "BVxxx", "url": "..."}` → 成功
   - `{"ok": false, "error": "..."}` → 检查 stderr 看具体错

---

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| RELAY_BASE_URL not set | 环境变量未配置 | 检查 entrypoint 注入；手动设置 export RELAY_BASE_URL=... |
| OFB_KEY not set | 凭据未配置 | 检查 entrypoint 注入；联系产品方补发 |
| video not found | 文件路径错 | 确认 --video 路径 |
| title exceeds 80 chars | 标题过长 | 缩短 |
| HTTP 401 INVALID_OFB_KEY | OFB_KEY 无效 | 联系产品方重发 |
| HTTP 500 BILI_UPLOAD_FAILED | B站端失败 | 看 stderr 具体 msg；重试一次 |

---

## 与旧版（OAuth2 + HMAC）对比

| 维度 | 旧（Open Platform 自接） | 新（relay 代理） |
|------|------------------------|------------------|
| 凭据位置 | 客户端 BILIBILI_APP_ID/SECRET | relay 端 |
| OAuth2 流程 | 客户端跑（code exchange / refresh） | relay 端 |
| 签名 | 客户端 HMAC-SHA256 | relay 端 |
| 分块上传 | 客户端 5MB chunk | relay 端 |
| 网络路径 | 客户端 → B站 API | 客户端 → relay → B站 API（多一跳） |
| 失败重试 | 客户端处理 | relay 端处理 |
| 退出码 | 0/1/2 | 0/1/2（保持兼容） |

**为什么值得多一跳**：
- 凭据集中管理（避免泄露）
- 客户端代码大幅简化（移除 OAuth2 / 签名 / 分块逻辑）
- relay 端可做配额控制 / 失败重试 / 限流（业务侧）
- 客户端无需处理 token 刷新（凭据生命周期由 relay 管理）

**代价**：
- 多一次网络跳转（latency）
- 大文件走 relay 占用 relay 带宽（成本）

**验收标准**：
- 发一条真实动态成功
- skill 内无 BILI 凭据（已达成：source grep 无 BILIBILI_APP_*）
- 12 单元测试全过

---
name: bgm-library
description: 搜索、筛选并下载 ccMixter 免版税背景音乐（仅 CC BY / CC BY-SA，商用安全），
  自动生成 TASL 署名。支持关键词搜索、5 套场景预设、按标签下载候选曲、按 ID 下载。
  纯 BGM 优先使用本技能；背景音、环境音及带背景/环境的人声优先用 aigc-video-gen audio。纯客户端，无需 API key。
metadata:
  openclaw:
    emoji: 🎵
    requires:
      bins:
      - node
    homepage: https://ccmixter.org
---

# ccMixter 免版税背景音乐库

> **凭据**：无需 API key。ccMixter 是 Creative Commons 创建的社区 remix 站，全部音乐已带 CC 协议。

搜索、筛选并下载商用安全的免版税背景音乐，自动生成署名文件。供 `video-edit` / `video-producer` 的配乐环节使用，也可独立调用。

通过 PATH 调用 wrapper，无需拼接脚本路径：

```bash
bgm-library <command> [args]
```

## 协议过滤（默认开启）

只放行**商用安全**协议，任何含 NonCommercial (NC) 或 NoDerivs (ND) 的协议一律拦截：

- ✅ 允许：CC BY（署名）、CC BY-SA（署名-相同方式共享）
- ❌ 拦截：含 NC / ND 的任何协议

`--no-commercial-only` 可放开（不推荐，商用项目会侵权）。

---

## Commands

### `search [keywords...]` — 关键词 / 预设搜索

```bash
# 关键词搜
bgm-library search chill lofi --limit 5

# 要求同时包含所有标签
bgm-library search chill lofi --match all --limit 5

# 预设搜
bgm-library search --preset travel
```

| Flag | Default | Description |
|------|---------|-------------|
| `-l, --limit <n>` | `10` | 最多返回条数 |
| `-p, --preset <name>` | — | 预设：`travel` / `tech` / `lofi` / `food` / `workout` |
| `--commercial-only` / `--no-commercial-only` | on | 协议过滤开关 |
| `--sort <field>` | `score` | `date` / `name` / `score` |
| `--match <mode>` | `any` | 多词默认 OR；`all` 要求同时命中全部标签 |

使用曲库的英文标签；中文会原样参与查询，不会自动翻译或删除后变成无主题搜索。无结果时换英文标签或场景预设，不推定曲库没有相应风格。

### `pick <theme>` — 按标签下载候选曲

默认按任一标签检索，在返回的候选中按标签/标题命中数排序后下载一首；同分保留上游排序。无匹配时报错，不删除关键词另下无关曲目。它不分析音频，不保证旋律、高潮段或最终听感；下载后必须试听。

```bash
bgm-library pick "chill lofi study" --output ./audio/
bgm-library pick "energetic workout motivation" --output ./audio/
```

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output <dir>` | `./public` | 输出目录 |
| `-l, --limit <n>` | `5` | 候选评估条数 |
| `--force` | off | 覆盖已存在文件 |
| `--match <mode>` | `any` | 多词 OR；`all` 为全部标签匹配 |

### `download <uploadId>` — 按 ccMixter upload ID 下载

```bash
bgm-library download 70473 --output ./audio/
```

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output <dir>` | `./public` | 输出目录 |
| `--force` | off | 覆盖已存在文件 |

### `presets` — 列出场景预设

```bash
bgm-library presets
```

| Preset | 场景 | Tags |
|--------|------|------|
| `travel` | 旅行 / Vlog | upbeat |
| `tech` | 科技 / 产品 | electronic |
| `lofi` | 咖啡馆 / 学习 | chill |
| `food` | 美食 / 生活 | acoustic |
| `workout` | 运动 / 健身 | edm |

### `info <uploadId>` — 查看曲目详情（协议 / BPM / 时长 / 文件）

```bash
bgm-library info 70473
```

---

## Output

下载后落盘到 `--output` 目录：

- `*.mp3` — 音频文件（原文件名，非法字符替换为 `_`）
- `music_manifest.json` — 曲目元数据（供程序化读取）
- `ATTRIBUTION.txt` — TASL 格式自动署名（Title / Author / Source / License）

`music_manifest.json` 示例：

```json
{
  "tracks": [
    {
      "upload_id": 70473,
      "title": "The Fade Out",
      "artist": "coruscate",
      "source_url": "https://ccmixter.org/files/Coruscate/70473",
      "license_name": "Attribution (3.0)",
      "license_url": "http://creativecommons.org/licenses/by/3.0/",
      "file_name": "Coruscate_-_The_Fade_Out.mp3",
      "bpm": 92,
      "duration": "3:05",
      "downloaded_at": "2026-08-15T12:00:00.000Z"
    }
  ]
}
```

### ⚠️ 发布时必须附带署名

`ATTRIBUTION.txt` 是 CC 协议的法律要求。成片发布时把该文件内容写到视频描述 / 简介里，**不得省略**。

---

## 在 video-edit / video-producer 中使用

下载并试听候选后，把明确的曲目路径交给 `video-edit`；选段与音量按本次素材设置：

```bash
video-edit audio-mix input.mp4 --bgm <已下载的曲目.mp3> --bgm-start 47 --bgm-duration 20 --bgm-volume 0.3 --bgm-outro-fade 0.8 --output out.mp4
```

选曲策略：

- ✅ **优先 `bgm-library`**：免 key、免版税、自动署名、商用安全；适合绝大多数配乐场景
- ✅ **纯 BGM**：继续用 `bgm-library` 换标签、预设或候选曲；也可使用用户提供的授权曲目。
- ✅ **背景音、音效、环境音，或带背景/环境的人声**：优先用 `aigc-video-gen audio` 一次生成；纯人声旁白用 `awk-tts`。完整混合音轨不再叠一遍 BGM。
- ❌ **不要**放开 `--no-commercial-only` 下 NC/ND 协议曲目到商用成片
- ✅ 先试听几处候选段落，核对旋律、节奏、人声冲突和循环接缝；用户要高潮段时，明确选段起点与长度，不默认曲首或全曲 RMS 最大段就是高潮。
- ✅ 默认增益只是起点。试听带旁白样片，测量所选段落的电平，再调节比例；频谱平坦度只能作为音色参考，不能据一个阈值判废曲目或认证旋律。
- ✅ 最终混音走 `video-review` 并抽听末 3 秒。不要自行拼接动态 `loudnorm → amix` 链；使用 `video-edit audio-mix --normalize-inputs` 完整处理分轨后再混合，避免末句丢失。

---

## Pitfalls

### pitfall: 403 Forbidden on download

- **症状**：下载返回 403
- **workaround**：脚本已自动带 referer 头；仍 403 说明曲目已从 ccMixter 下架，换一首

### pitfall: 搜索无结果

- **症状**：`No tracks found matching your query`
- **workaround**：先确认查询实际成功；多词用 `--match any`，换英文单标签或用 `--preset`。网络/解析错误不算无结果，不从错误中推定曲库为空。

### pitfall: Header overflow / 瞬态查询失败

- **症状**：`Parse Error: Header overflow`、超时、连接重置、429 或 5xx。
- **workaround**：只读 API 查询已自动在 1 秒、2 秒后最多重试两次（含首次共三次）。仍失败则保留错误、停止本次查询；不要连续手动重试或当成无曲目。下载不会因此自动重发。

### pitfall: ccMixter SSL 证书链不全

- **症状**：Node 报 `unable to verify the first certificate`
- **workaround**：脚本已对 ccMixter 域名放宽 TLS 校验（`rejectUnauthorized: false`），无需手动处理；仅作用于该站点

### pitfall: 依赖未装

- **症状**：`Cannot find module 'commander'` 等
- **workaround**：依赖由 `apply-addons.sh` 自动安装（skill 目录下 `package.json`）；手动补装可 `cd <skill-dir> && npm install --omit=dev`

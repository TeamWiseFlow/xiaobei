---
name: video-review
description: 成片自检闸门——ffprobe 校验 + 5 位抽帧黑帧扫 + 音频电平 + 时长/分辨率一致性，verdict pass/fail/warn。各视频生产技能合成后、交付前必跑。
metadata:
  openclaw:
    emoji: "🔬"
    requires:
      bins:
      - python3
      - ffmpeg
      - ffprobe
---

# video-review（成片自检公共技能）

## 用途

视频合成后的**强制自检闸门**——在向用户交付前跑一次，拦成片硬伤：

- ffprobe 全字段校验（codec / 分辨率 / fps / pix_fmt / 音频配置）
- 5 位抽帧黑帧扫（0% / 25% / 50% / 75% / 100%）—— ≥2 黑帧判 critical
- 100% 定位最后可解码帧，尾部先取2秒、再8秒窗口，仍无帧才从头解码（每次最多60秒）。缺帧或亮度分析失败写入 `coverage_missing[]`、`frame_coverage` 和 warning，不能以4帧无黑帧判 pass。
- 音频电平分析（volumedetect）—— 静音 / 削波 / 无音轨
- 音视频流起止时间对比（默认容差 0.1 秒）；音轨提前结束或延迟开始会 fail，流时长不可得会 warn，不以容器总时长代替短音轨。
- 时长 vs 目标（`--target-duration`，默认 ±5% 容差）
- 分辨率 floor（9:16 竖屏最低 720x1280）+ 目标比对 + 段一致性

## 调用

```bash
video-review <final.mp4>                    # 直接审单个成片文件
video-review <project-dir>                  # 审 <dir>/video.mp4，并对 artifacts/ 做段一致性检查
video-review <project-dir> --target-duration 30 --target-resolution 720x1280
video-review <final.mp4> --output review.json
```

参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `target` | — | 成片文件路径；或项目目录（目录时审 `<dir>/video.mp4`，且若存在 `artifacts/` 一并做段一致性检查） |
| `--target-duration` | 无 | 目标时长（秒），从脚本片段规划累加得出 |
| `--target-resolution` | 无 | 目标分辨率，形如 `720x1280` |
| `--output` | `<project-dir>/review/verdict.json` | verdict JSON 落盘路径 |

## verdict 语义

| verdict | 退出码 | 含义 | 处置 |
|---------|--------|------|------|
| `pass` | 0 | 无 critical 无 warning | 可交付 |
| `fail` | 1 | 有 critical issue | **不准交**——按 `critical[]` 修复后重审，最多重修 2 轮，仍 fail 则向用户复述 critical 项请求决策 |
| `warn` | 2 | 有 non-critical issue | 向用户复述让其决定是否重修 |
| — | 3 | 脚本本身故障（ffprobe missing / path invalid） | 不算评审结论，修脚本 |

## verdict JSON schema

```json
{
  "verdict": "pass" | "fail" | "warn",
  "file": "<video.mp4 absolute path>",
  "ffprobe": { "codec", "width", "height", "fps", "pix_fmt", "duration", "size_bytes", "audio": {...} },
  "frames": [ { "position_pct", "path", "mean_luma", "is_black", "status", "error", "requested_timestamp_seconds", "decoded_timestamp_seconds" } ],
  "coverage_missing": [ { "position_pct", "reason" } ],
  "audio_level": { "mean_db", "max_db", "silent", "clipping", "absent" },
  "checks": [
    { "name": "duration_match",   "status": "pass",    "detail": "actual 30.2s vs target 30s, gap 0.2s" },
    { "name": "resolution_floor", "status": "pass",    "detail": "720x1280" },
    { "name": "resolution_uniform", "status": "fail",  "detail": "成片 720x1280 vs 段01 1080x1920" }
  ],
  "critical": [ "resolution_uniform: ..." ],
  "warnings": [ "audio_level mean_db=-42.1 close to silent threshold" ]
}
```

## 抽帧产物

每次检查的 5 帧与完整报告落独立的 `<project-dir>/review/runs/<review_id>/frames/frame_NNN.jpg` 和 `verdict.json`；报告记录源视频 SHA256、每帧 SHA256 及永久 `report_path`。同目录多素材、同名素材、重复或并行检查互不覆盖。`--output`（默认 `review/verdict.json`）仅是最新报告副本，复查或交接使用返回的 `report_path` 与帧路径。**不进 `artifacts/`、不进 `previews/`**。

`checks[].name=audio_timeline` 记录两路流的开始、时长、结束及起止偏差。音视频等长不能证明口播完整：BGM 和补静音都能掩盖末句丢失，交付前另行抽听末 3 秒。报告须绑定当前成片 SHA256，重新混音后重跑，不沿用旧文件的 pass。

人工或制作方另行补查的图片与结论单独保存，不修改公共报告里的缺失状态；需要公共检查完整时重跑本工具。尾帧的实际时间见 `decoded_timestamp_seconds`，不要把容器 duration 当作可解码时间点。

## 段一致性检查

`probe_segments` 扫 `<project-dir>/artifacts/` 下各段 ffprobe，逐段比对分辨率与成片是否一致——拼了不同分辨率段是硬伤。`artifacts/_deprecated/` 子目录不参与（非递归 listdir）。

## 强制约定

- **禁止跳过本脚本交付**：各视频生产技能的合成环节产出 `video.mp4` 后，必须先跑本脚本，verdict=pass 才能进交付/封面环节
- **禁止肉眼看交代替本脚本**：本脚本是替代"裸拼完就交"脆弱闸门的强制自检
- **技术通过后仍须审剪辑**：content producer制作的成片另跑 `video-producer edit-audit`，检查旁白干声空档、源时间窗复用并登记真实审片。技术 pass、动态图数量和 motion_ratio 不能证明节奏或镜头语义合格。
- **warn 处置**：声画同出模式下 `audio_absent` warning 要对照看——AI 生成模式该出声没出声是 critical（退回重生成或补 TTS）；Stock Footage + `--no-audio` 模式下 `audio_absent` 是预期，warn 可放行

# 剪辑节奏与素材复用检查

Stage 12 先出一段带声音的 5–20 秒样片，包含代表性转场、字幕和旁白；CP 实际试听、查看，main 按已有 Brief 代理审批范围审片。确认配音节奏、字形和素材动作后再跑全片。不要只看联系表或把“存在运动”当作剪辑顺畅。

Stage 13 在最终响度处理/音轨保留和字幕合成之后，用 `edit-audit` 检查最终成片。`video-review` 负责技术指标，`motion-audit` 负责动作承诺，本工具检查旁白留白和素材复用，并登记真实审片结论。三者互不替代。

在项目 `render/editing-plan.json` 写最终时间轴；以下仅为字段示例，时长、停顿上限和源窗口按实际项目填写：

```json
{
  "sound_policy": "narration",
  "voice_kind": "dry-narration",
  "voice": "audio/voice-timeline.wav",
  "max_gap_seconds": 1.0,
  "silence_noise_db": -38,
  "segments": [
    {
      "id": "shot-01",
      "start": 0,
      "end": 3,
      "source": "raw_materials/opening.mp4",
      "source_start": 1,
      "source_end": 4,
      "action": "员工把任务卡放入收件箱"
    },
    {
      "id": "shot-02",
      "start": 3,
      "end": 6,
      "source": "render/product/clip.mp4",
      "source_start": 0,
      "source_end": 3,
      "action": "三张卡依次拼成服务闭环"
    }
  ],
  "exceptions": []
}
```

- `voice` 是按成片时间轴排布的旁白干声，包含实际首尾留白和句间延时，时长与成片差不超过 0.12 秒。不要提供每句去静音后直接拼接的音轨，也不要用含 BGM 的混音冒充干声；BGM 会掩盖无口播空档。
- 逐句配音直接在同一次 `narration-layout <project> --plan narration_plan.json --mix audio/mix.wav --dry-voice audio/voice-timeline.wav` 中输出混音与完整旁白干声；干声复用相同逐句排布，自动省去 BGM。改计划/素材后用 `--force` 重排并重产，不另写延时混音脚本。整段旁白沿用最终时间轴的原干声。
- `max_gap_seconds` 是本项目的无口播上限，不设所有视频通用阈值。首尾留白也检查。纯无声或仅配乐片分别写 `sound_policy: silent` / `music-only`，不填 voice；仍须核对源素材和审片。
- `aigc-video-gen audio` 一次生成的人声与背景/环境混合音轨，使用 `sound_policy: audio-scene`，以 `scene_audio` 指向最终时间轴上的完整场景音频，不填 `voice` / `voice_kind`。工具核对音轨和成片等长并绑定音频哈希，报告 `narration_gap_check: manual-scene-listening`，不使用混音的静音检测冒充干声停顿检查。先用公共 ASR 对齐带人声的音轨，再实际听看成片逐句核验台词、无口播空档、背景是否压过人声及末句完整；人工登记的 notes 必须记录这些结论。没有匹配当前产物的真实审片仍为 `needs_review`，不得自动填 pass；干声旁白继续使用原 `narration` 检查。
- `segments` 按最终时间轴连续覆盖整片。`source` 指实际被裁切的素材，`source_start/source_end` 指该素材上的原始时间窗；不能用裁好后另命名的片段掩盖同一动作复用。每段写具体动作，不能只填素材 ID。多层动效以渲染好的 composition 作为源，并在人工审片中核对内部动作。
- 源文件以内容哈希识别，复制/改名仍会发现同窗口复用。同源不同窗口也要核对动作；改 action 标签不证明画面不同。

先检查，报告列出无口播空档和疑似复用的 finding key：

```bash
video-producer edit-audit <project> --preview video.mp4
```

默认输出 `review/edit-audit.json`。返回 1 表示有未解决问题，2 表示尚无匹配当前产物的人工审片，0 才能交付。输入或依赖错误返回 3。

修正不合理的停顿/复用；刻意阅读停留或回放可以在计划的 `exceptions` 中逐条写 `{ "key": "报告中的实际key", "reason": "具体叙事目的" }`，不能用一条泛泛说明批准所有异常。然后实际听看整片，登记 CP/main 的审片身份和结论：

```bash
video-producer edit-audit <project> --preview video.mp4 \
  --verdict pass --reviewer main --notes "实际听看后的具体结论"
```

人工审片需核对：是否每段画面推进新信息、是否重复同一素材动作、留白是否服务阅读、口播与画面是否对应、字幕及中文字形是否完整可读。工具统计不能替审片人填 pass。审片绑定计划、旁白、所有源素材和成片内容哈希；任何一个变化都要重新审片。记录是本地制作审核，不额外要求用户重复批准已代理授权的工作。

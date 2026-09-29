---
name: awk-tts
description: 声音复刻、音色设计和多供应商配音；支持绑定音色档案。多供应商旁白 TTS——火山豆包语音合成 2.0（seed-tts-2.0）+ 阿里云百炼（qwen-audio-3.0-tts），凭据在哪家走哪家（火山 → 百炼业务空间 → 百炼 agent plan）。生成 MP3/PCM/WAV/OPUS 旁白，可选字级时间戳，合成后自动 ASR 自检。
metadata:
  openclaw:
    emoji: 🔊
    requires:
      bins:
        - python3
        - ffmpeg
        - ffprobe
    primaryEnv: VOLC_TTS_ACCESS_KEY
    homepage: https://www.volcengine.com/docs/6561/1598757
---

# 多供应商旁白 TTS（awk-tts）

火山 openspeech v3 单向流式 + 百炼 SpeechSynthesizer 双后端，凭据自动路由。

## 供应商路由（脚本内部，凭据在哪家走哪家）

| 优先级 | 供应商 | 触发凭据 | 模型/资源 |
|--------|--------|---------|-----------|
| 1 | 火山豆包语音合成 2.0 | `VOLC_TTS_APP_ID`+`VOLC_TTS_ACCESS_KEY`（旧双头）或 `VOLC_TTS_APP_KEY`（新单头） | `seed-tts-2.0`（克隆音色 `S_xxx` 自动路由 `seed-icl-2.0`） |
| 2 | 百炼业务空间 | `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY` | `qwen-audio-3.0-tts-plus` → `qwen-audio-3.0-tts-flash` 候选链 |
| 3 | 百炼 agent plan | `AWK_API_KEY`（token-plan 端点） | 仅 `qwen-audio-3.0-tts-plus` |

- 百炼候选链自动 fallback（模型未开通/未找到切下一个）；`--model` 显式指定关闭 fallback（仅百炼生效）。
- 百炼默认音色 `longanhuan_v3.6`；传了火山系音色 ID 会警告并换默认音色。
- 格式映射：火山 `ogg_opus` 在百炼自动转 `opus`；百炼不支持 32000 采样率。
- 语速 `--speech-rate [-50,100]` 在百炼线性映射为 rate [0.5,2.0]；响度 `--loudness` 映射为 volume [0,100]。
- 三组凭据都缺 → exit 1 并列出配置方式。应该 spawn IT engineer subagent 写入实例环境变量，**不要自己写环境变量文件**。

## Run

**Do NOT set env vars inline**（例如 `VOLC_TTS_ACCESS_KEY=... python3 ...`）。env var 已在系统环境里，inline 赋值会破坏 exec 权限检查。

```bash
# 基础中文旁白，默认落 ./tmp/awk-tts-<ts>/speech.mp3
awk-tts --text "大家好，欢迎来到今天的视频。"

# 从文件读文本
awk-tts --text-file ./scripts/script.txt --out-dir ./assets/audio

# Fragment 工作流：读 tts_requirement.md，抽音色/语速设置，
# 出 speech.mp3 + speech.json 到 ./fragments/01-hook/artifacts/
awk-tts ./fragments/01-hook/ --overwrite

# 指定音色 + 格式 + 精确输出路径
awk-tts \
  --text "This is a demo voiceover." \
  --voice "en_female_dacey_uranus_bigtts" \
  --format wav \
  --sample-rate 44100 \
  --output ./assets/audio/demo.wav

# 字级时间戳（旁白对齐用）：火山走流式原生返回，百炼走 SSE + word_timestamp_enabled
awk-tts --text "..." --enable-subtitle --output ./assets/audio/narration.mp3
```

合成后脚本会测真峰值。超过 -2.5 dBTP 时自动衰减并复测，给后续数字人驱动和转码留余量；元数据 `peak_guard` 记录前后峰值。若原始 TTS 已有可闻削波，降低音量不能恢复波形，应重新合成并试听。生成文件用于驱动数字人后不要再换音轨；换音轨须重新生成数字人并核对 job 哈希。

## Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `fragment_dir` | — | Optional fragment directory under `fragments/`; when set, reads `tts_requirement.md` and defaults output to `artifacts/speech.<format>` |
| `--text` | — | Text to synthesize. Required unless `--text-file` or `fragment_dir` is set |
| `--text-file` | — | UTF-8 text file to synthesize. Must be relative and under `scripts`, `assets`, `tmp`, `output_videos`, `fragments`, or `<platform>/outputs/` |
| `--voice` | 火山 `zh_female_shuangkuaisisi_uranus_bigtts` / 百炼 `longanhuan_v3.6` | 音色 ID（按路由到的供应商选默认） |
| `--model` | — | 百炼模型 ID（显式指定关闭候选链 fallback；火山模式忽略） |
| `--format` | `mp3` | Audio format: `mp3`, `pcm`, `wav`, `opus`（火山另收 `ogg_opus`，百炼自动映射为 `opus`） |
| `--sample-rate` | 火山不设 / 百炼 24000 | 8000/16000/22050/24000/44100/48000（火山另收 32000） |
| `--speech-rate` | — | Speech rate `-50`–`100`（0=默认, 100=2x, -50=0.5x；百炼线性映射 rate） |
| `--loudness` | — | Loudness `-50`–`100`（0=默认；百炼映射 volume） |
| `--context-text` | — | 情感/风格控制上下文（火山 `context_texts`；百炼 `instruction`） |
| `--output` | — | Exact output file path under `assets/audio`, `tmp`, `output_videos`, `fragments`, or `<platform>/outputs/` |
| `--out-dir` | `./tmp/awk-tts-<ts>` | Output directory under `assets/audio`, `tmp`, `output_videos`, `fragments`, or `<platform>/outputs/` when `--output` is not set |
| `--overwrite` | off | Overwrite existing output audio/metadata files |
| `--no-asr-check` | off | Skip ASR self-check after TTS generation |
| `--enable-subtitle` | off | 产出 `<audio>.subtitle.json` 字级时间戳（火山流式原生；百炼 SSE 流式），schema `{sentences:[{text, words:[{word,startTime,endTime}]}]}`（秒） |

## Recommended voices

火山官方 2.0 音色（`_uranus_bigtts` 后缀，路由到火山时可用）：

| Speaker ID | 名称 | 场景 |
|-----------|------|------|
| `zh_female_shuangkuaisisi_uranus_bigtts` | 爽快思思 2.0 ⭐火山默认 | 通用 |
| `zh_female_cancan_uranus_bigtts` | 知性灿灿 2.0 | 角色扮演 |
| `zh_female_tianmeixiaoyuan_uranus_bigtts` | 甜美小源 2.0 | 通用 |
| `zh_female_vv_uranus_bigtts` | Vivi 2.0 | 多语种通用（中/日/印尼/墨西哥西语） |
| `zh_female_xiaohe_uranus_bigtts` | 小何 2.0 | 通用 |
| `zh_female_kefunvsheng_uranus_bigtts` | 暖阳女声 2.0 | 客服 |
| `zh_male_m191_uranus_bigtts` | 舟 2.0 | 通用男声 |
| `zh_male_taocheng_uranus_bigtts` | 小天 2.0 | 通用男声 |
| `en_female_dacey_uranus_bigtts` | Dacey | 多语种（英） |
| `en_male_tim_uranus_bigtts` | Tim | 多语种（英） |

> 克隆音色（`S_xxx` 开头）走 `seed-icl-2.0` 资源 ID，脚本自动路由，需 `model_type=4`（脚本自动加）。仅火山模式有效。

百炼 qwen-audio-3.0-tts 系统音色（路由到百炼时可用）。**音色与模型绑定**：音色不在当前 `--model` 支持列表中会返回 `InvalidParameter`，需按下表对齐模型。

`qwen-audio-3.0-tts-plus` 系统音色（agent plan 仅支持此模型）：

| voice 参数 | 名称 | 特质（性别/年龄） | 场景 |
|-----------|------|-----------------|------|
| `longanlingxin` | 龙安灵心 | 知心温暖音（女/25） | 社交陪伴·旗舰 |
| `longanlufeng` | 龙安鲁风 | 明亮开朗音（男/25） | 社交陪伴·旗舰 |

`qwen-audio-3.0-tts-flash` 系统音色（默认音色在此模型）：

| voice 参数 | 名称 | 特质（性别/年龄） | 场景 |
|-----------|------|-----------------|------|
| `longanhuan_v3.6` | 龙安欢 | ⭐百炼默认（女/25） | 通用 |
| `longanfengyue` | 龙安风悦 | 自然亲切音（女/30） | 社交陪伴 |
| `longanlingxi` | 龙安灵希 | 可爱甜美音（女/25） | 社交陪伴 |
| `longanxiaoxin` | 龙安小昕 | 亲切活泼音（女/22） | 社交陪伴 |
| `longanyuanfei` | 龙安元妃 | 高傲妃子音（女/30） | 社交陪伴 |
| `longjielidou_v3.6` | 龙杰力豆 | 天真男童（男/5） | 儿童陪伴/智能玩具 |
| `longpaopao_v3.6` | 龙泡泡 | 软糯可爱音（女/5） | 儿童陪伴/智能玩具 |
| `longhuohuo_v3.6` | 龙火火 | 顽皮少年音（男/8） | 角色音/游戏 |
| `longchuanshu_v3.6` | 龙川叔 | 川普大叔音（男/40） | 角色音/游戏 |
| `loongmary` | loongmary | 温暖英音（女/20） | 精品英文（仅英文） |
| `loongeva_v3.6` | loongeva | 高智美音（女/28） | 精品英文（仅英文） |
| `loongjohn` | loongJohn | 沉稳亲切美音（男/28） | 精品英文（仅英文） |

> 语言范围：除 `loong*` 三款纯英文外均为中文（普通话）+英文；`text` 超出音色语言范围会发音错误或语音不自然。
> 默认音色 `longanhuan_v3.6` 虽列在 flash 表，plus 上实测可用（2026-09-17 冒烟）；若指定其他 flash 系音色遇 `InvalidParameter`，改传 `--model qwen-audio-3.0-tts-flash`（agent plan 不支持 flash）或换 plus 系音色。
> 两模型另各有 500+ 声音复刻基础音色，命名 `qwen-audio-3.0-tts-{plus|flash}-{后缀}`，`--voice` 直传即可，完整列表见[官方音色列表页](https://docs.bailian.console.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list) Excel；也可用声音复刻免费定制专属音色。

## Output

- Audio file: `speech.<format>` 或 `--output` 指定路径
- Metadata file: `speech.json`（同目录），含：
  - `provider`: `volcengine-openspeech-v3` / `bailian-workspace` / `bailian-agent-plan`
  - 火山：`resource_id`；百炼：`model`（实际使用的候选链模型）
  - `speaker` / `format` / `text_chars` / `audio_bytes` / `duration` / `file`
- `--enable-subtitle` 时另出 `speech.subtitle.json`（字级时间戳，秒；narration-align 优先消费此文件）

Fragment 工作流模式下，脚本读 `tts_requirement.md`、抽 `## 配音文案` / `## Voiceover Text` 段、读音色/语速设置、直接写到 fragment 的 `artifacts/` 目录。脚本合成时跳过 markdown heading、注释、音色设置行。

## ASR Self-Check

合成后自动跑 ASR 自检（除非 `--no-asr-check`）：

1. 后端优先级：火山录音文件极速版（`VOLC_ASR_*` 在即启用）→ 百炼 `qwen-audio-3.0-asr-flash`（业务空间/agent plan 凭据）
2. 清洗标点空白后做序敏感相似度比对（中英文统一）
3. 阈值 **0.5**——实测 0.5 已够实用质量；过高阈值会假阴性
4. 结果打印 `PASS` / `WARN`，不 abort

ASR 凭据全部未配置时静默跳过自检。

## Environment Variables

| Variable | Description |
|----------|-------------|
| `VOLC_TTS_APP_ID` + `VOLC_TTS_ACCESS_KEY` | 火山旧控制台双头鉴权（优先） |
| `VOLC_TTS_APP_KEY` | 火山新控制台单头鉴权 |
| `VOLC_TTS_API_BASE` | Optional 火山 API base override，默认 `https://openspeech.bytedance.com/api/v3` |
| `VOLC_TTS_RESOURCE_ID` | Optional 火山资源 ID override，默认 `seed-tts-2.0`（按 speaker 特征自动路由） |
| `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY` | 百炼业务空间（火山凭据缺失时启用） |
| `AWK_API_KEY` | 百炼 agent plan（token-plan 端点；业务空间凭据也缺失时启用） |
| `VOLC_ASR_APP_ID` + `VOLC_ASR_ACCESS_KEY` / `VOLC_ASR_APP_KEY` | ASR 自检火山凭据 |
| `VOLC_ASR_RESOURCE_ID` | Optional ASR 资源 ID override，默认 `volc.bigasr.auc_turbo` |
| `BAILIAN_ASR_MODEL` | Optional 百炼 ASR 自检模型 override，默认 `qwen-audio-3.0-asr-flash` |

## 声音复刻与音色设计

使用同一默认凭据顺序：**火山 → 百炼业务空间 → 百炼 Agent Plan**。可用 `--platform volc|workspace|agent-plan` 指定；凭据选路后不因错误静默跨供应商创建另一个音色。Agent Plan 的 customization 权限由套餐决定，返回不支持时使用已开通的业务空间，不宣称所有套餐都支持创建音色。

音色必须保存为 `voice.json` 并在后续 TTS 传 `--voice-profile`：档案绑定供应商、业务空间/APP、模型和音色，不再按环境重选供应商，也不沿通用模型链切换。常规 TTS 不传档案时仍保持原候选链。

### 创建与试听

```bash
# 默认按凭据选路；火山必须指定已购的空闲 S_ 槽位
awk-tts voice-design --speaker-id S_EXAMPLE --description "成年男性，中音温暖自然，普通话清晰，适合知识讲解" --preview-text "大家好，今天我们用三张图，讲清楚一个复杂的问题。" --out-dir /absolute/voices/design
awk-tts voice-clone --speaker-id S_EXAMPLE --audio /absolute/authorized-sample.wav --out-dir /absolute/voices/clone

# 显式在百炼业务空间创建；无需火山槽位
awk-tts voice-design --platform workspace --name narrator --description "温暖自然的成年男性，语速适中，日常聊天感" --preview-text "大家好，今天我们用三张图，讲清楚一个复杂的问题。" --out-dir /absolute/voices/bailian-design
awk-tts voice-clone --platform workspace --name narrator --audio /absolute/authorized-sample.wav --out-dir /absolute/voices/bailian-clone

# 查询已创建音色；失败/超时后先查，不盲目重复创建
awk-tts voice-status --profile /absolute/voices/clone/voice.json --wait 60
awk-tts voice-list --platform workspace --prefix narrator

# 用绑定音色合成，自动保持供应商和模型一致
awk-tts --voice-profile /absolute/voices/clone/voice.json --text-file /absolute/voiceover.md --output /absolute/narration.wav --format wav --enable-subtitle
```

- 火山复刻/设计使用现有 `VOLC_TTS_APP_ID` + `VOLC_TTS_ACCESS_KEY` 或 `VOLC_TTS_APP_KEY`，不是 `AWK_GEN_KEY`。旧鉴权在音色接口用 `X-Api-App-Key`，在合成接口用 `X-Api-App-Id`。`--speaker-id` 也可由 `VOLC_TTS_SPEAKER_ID` 配置。使用确认可覆盖的音色槽位；工具不购买槽位、不自动启用后付费自定义 ID。
- 火山文本设计描述最多200字，试听文本最多300字；当前 CLI 提供文本设计。设计/复刻通过后用 `seed-icl-2.0` 合成，新版训练返回的 model_type=5 会保存在档案并在合成时使用。
- 百炼使用 `voice-enrollment`，默认绑定 `qwen-audio-3.0-tts-plus`，可用 `--target-model qwen-audio-3.0-tts-flash`。`--name` 1–10位英文字母/数字；描述1–500字符，试听文本15–200字符。
- 复刻 CLI 接收10–20秒、<10MB的 WAV/MP3/M4A 清晰单人音频，样本使用本人或有授权的声音；提供文件或 HTTP(S) URL 均可。火山直接传 Base64；百炼使用模型绑定的临时上传。URL 会先下载校验，确保上传的是已核验样本。
- `voice-design` 保存试听文件，`voice-clone` 保存音色档案；火山返回试听 URL 时立即下载。只有远端状态可用才将档案标为 OK；创建状态不确定时保留记录，先查询，勿自动重复消耗创建/训练次数。
- 试听确认清晰度、音色、语气后再用于全稿。复刻声与设计声均是合成声音，不能承诺等同真人原录音或保证通过平台检测。deck-talk 已有用户原录音时优先原声，不主动替换。
- 输出文件已存在即停止，换目录创建新音色；不会覆盖现有档案。程序不修改 `~/.openclaw/.env`。

接口：[百炼设计](https://help.aliyun.com/zh/model-studio/voice-design-api-references)、[百炼复刻](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[火山设计](https://docs.volcengine.com/docs/DoubaoVoice/SoundDesignAPI?lang=zh)、[火山复刻](https://docs.volcengine.com/docs/DoubaoVoice/tone-training-http?lang=zh)。

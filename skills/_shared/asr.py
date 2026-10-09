"""asr.py — ASR 统一路由（单入口），返回结构与 volc_asr/bailian_asr 同构：

  {ok: True, text, utterances:[{start,end,text}], words:[{start,end,text}]}（时间戳秒）
  {ok: False, error}

供应商优先级：
  1. 火山录音文件极速版 —— VOLC_ASR_APP_ID+VOLC_ASR_ACCESS_KEY（旧控制台双头）
     或 VOLC_ASR_APP_KEY（新控制台单头）在环境中即启用
  2. 百炼业务空间 —— WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY
     模型候选 qwen-audio-3.1-asr-flash → qwen-audio-3.0-asr-flash
  3. 百炼 agent plan —— AWK_API_KEY（token-plan 端点）
     模型 qwen-audio-3.0-asr-flash；BAILIAN_ASR_MODEL 可显式固定百炼模型

按序尝试有凭据的供应商：某家调用失败（网络/配额/接口错误）自动落到下一家；
全部失败时 error 汇总各家原因。所有凭据都未配置时 error 含
「凭证未配置」与「VOLC_ASR」标记（talking-head-cut/cut_plan.py 以此判 exit 2）。

消费方（import 本模块的 asr()，不再直连 volc_asr）：
  - crews/main/skills/viral-chaser/scripts/transcriber.ts（调用本脚本的 JSON CLI）
  - crews/main/skills/talking-head-cut/scripts/cut_plan.py
  - crews/content-producer/skills/expert-video/tools/video-producer/scripts/narration-align.py
  - skills/awk-tts/scripts/tts.py（TTS 自检）
  - awada/src/audio-transcribe.ts（语音消息，经 JSON CLI）

CLI：python3 asr.py <audio_path>，stdout 返回同构 JSON，由调用方检查 ok。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 本模块与 volc_asr/bailian_asr 同目录（公共 skills/_shared/）。
# 消费方 sys.path 注入的是本目录，但保险起见自注入一次，允许直接以文件路径加载。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bailian_asr import bailian_asr, list_bailian_endpoints  # noqa: E402
from volc_asr import load_env_file, volc_asr  # noqa: E402

__all__ = ["asr", "load_env_file", "volc_asr", "bailian_asr"]


def _volc_configured() -> bool:
    app_id = (os.environ.get("VOLC_ASR_APP_ID") or "").strip()
    access_key = (os.environ.get("VOLC_ASR_ACCESS_KEY") or "").strip()
    app_key = (os.environ.get("VOLC_ASR_APP_KEY") or "").strip()
    return bool((app_id and access_key) or app_key)


def asr(audio_path: str) -> dict:
    """按 火山 → 百炼业务空间 → 百炼 agent plan 顺序路由转写。"""
    load_env_file()

    errors: list[str] = []
    tried = 0

    if _volc_configured():
        tried += 1
        result = volc_asr(audio_path)
        if result.get("ok"):
            return result
        errors.append(f"火山: {result.get('error', '未知错误')}")

    for endpoint in list_bailian_endpoints():
        tried += 1
        result = bailian_asr(audio_path, endpoint=endpoint)
        if result.get("ok"):
            return result
        errors.append(f"百炼({endpoint[2]}): {result.get('error', '未知错误')}")

    if tried == 0:
        return {
            "ok": False,
            "error": "ASR 凭证未配置：需 VOLC_ASR_APP_ID+VOLC_ASR_ACCESS_KEY 或 VOLC_ASR_APP_KEY（火山），"
                     "或 WORKSPACE_ID+MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY（百炼业务空间），"
                     "或 AWK_API_KEY（百炼 agent plan）",
        }
    return {"ok": False, "error": " | ".join(errors)}


def main() -> None:
    parser = argparse.ArgumentParser(description="公共 ASR 路由，输出全文与秒级时间戳 JSON")
    parser.add_argument("audio_path", help="本地音频路径")
    args = parser.parse_args()
    print(json.dumps(asr(args.audio_path), ensure_ascii=False))


if __name__ == "__main__":
    main()

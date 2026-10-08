"""volc_asr.py — 公共 skills/_shared 的火山豆包语音极速版 ASR 后端。

⚠️ 消费方不要直接 import 本模块——统一走同目录 asr.py 路由
（火山 → 百炼业务空间 → 百炼 agent plan，见 asr.py / bailian_asr.py）。
本模块只作为路由的火山后端。

视频转写、口播剪辑、旁白对齐与 TTS 自检均经 asr.py 调用本后端。

火山接口（volc.bigasr.auc_turbo），凭据：
  旧控制台双头 VOLC_ASR_APP_ID + VOLC_ASR_ACCESS_KEY
  新控制台单头 VOLC_ASR_APP_KEY

入参 audio_path，返 dict：
  {ok: True, text, utterances:[{start,end,text}], words:[{start,end,text}]}
  {ok: False, error}
utterances/words 时间戳均为秒（火山返毫秒，统一转秒）。
words 兜底：火山未返 word 级时按 utterance 切单字近似（中文每字一字）。

load_env_file() 从 ~/.openclaw/.env 兜底加载凭据——openclaw runtime 已注入真环境变量，
此兜底仅给手动 bash 调用或子进程未继承 env 时用，runtime 下是 no-op。
"""

from __future__ import annotations

import base64
import os
import uuid
from typing import Any


def load_env_file() -> None:
    """从 ~/.openclaw/.env 加载凭据（若尚未在环境里）。openclaw runtime 下是 no-op。"""
    env_path = os.path.expanduser("~/.openclaw/.env")
    if not os.path.isfile(env_path):
        return
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def volc_asr(audio_path: str) -> dict[str, Any]:
    """调火山方舟豆包语音极速版，返 {ok, text, utterances, words}。

    utterances: [{start, end, text}]（句级，秒）
    words: [{start, end, text}]（字级时间戳，秒；火山未返时按 utterance 切单字近似）
    """
    try:
        import requests
    except ImportError as e:
        return {"ok": False, "error": f"requests 不可用: {e}"}

    app_id = os.environ.get("VOLC_ASR_APP_ID", "").strip()
    access_key = os.environ.get("VOLC_ASR_ACCESS_KEY", "").strip()
    app_key = os.environ.get("VOLC_ASR_APP_KEY", "").strip()
    resource_id = os.environ.get("VOLC_ASR_RESOURCE_ID", "volc.bigasr.auc_turbo").strip()
    api_base = os.environ.get("VOLC_ASR_API_BASE", "https://openspeech.bytedance.com/api/v3").strip()
    url = f"{api_base.rstrip('/')}/auc/bigmodel/recognize/flash"

    headers = {
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
    }

    if app_id and access_key:
        headers["X-Api-App-Key"] = app_id
        headers["X-Api-Access-Key"] = access_key
        uid = app_id
    elif app_key:
        headers["X-Api-Key"] = app_key
        uid = app_key
    else:
        return {
            "ok": False,
            "error": "火山 ASR 凭据未配置：需 VOLC_ASR_APP_ID+VOLC_ASR_ACCESS_KEY（旧控制台双头）或 VOLC_ASR_APP_KEY（新控制台单头）。开通流程见 viral-chaser SKILL.md",
        }

    try:
        with open(audio_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        return {"ok": False, "error": f"读取音频失败: {e}"}

    ext = os.path.splitext(audio_path)[1].lower().lstrip(".")
    fmt = ext if ext in ("wav", "mp3", "ogg") else "wav"

    body = {
        "user": {"uid": uid},
        "audio": {"data": b64, "format": fmt},
        "request": {
            "model_name": "bigmodel",
            "show_utterances": True,
            "enable_itn": True,
            "enable_punc": True,
        },
    }

    try:
        r = requests.post(url, json=body, headers=headers, timeout=300)
    except Exception as e:
        return {"ok": False, "error": f"请求失败: {e}"}

    status = r.headers.get("X-Api-Status-Code", "")
    msg = r.headers.get("X-Api-Message", "")
    logid = r.headers.get("X-Tt-Logid", "")

    if status != "20000000":
        snippet = r.text[:500] if r.text else ""
        return {
            "ok": False,
            "error": f"火山 ASR 失败 (status={status}, msg={msg}, logid={logid}): {snippet}",
        }

    try:
        resp = r.json()
    except Exception as e:
        return {"ok": False, "error": f"响应解析失败: {e}; raw={r.text[:500]}"}

    result = resp.get("result") or {}
    text = result.get("text", "") or ""

    utterances = []
    for u in (result.get("utterances") or []):
        try:
            utterances.append({
                "start": float(u.get("start_time", 0)) / 1000.0,
                "end": float(u.get("end_time", 0)) / 1000.0,
                "text": u.get("text", "") or "",
            })
        except Exception:
            continue

    # word 级时间戳：火山 utterance 内含 words 列表，每 word 带 start_time/end_time
    words = []
    for u in (result.get("utterances") or []):
        for w in (u.get("words") or []):
            try:
                words.append({
                    "start": float(w.get("start_time", 0)) / 1000.0,
                    "end": float(w.get("end_time", 0)) / 1000.0,
                    "text": (w.get("text") or "").strip(),
                })
            except Exception:
                continue

    # 兜底：若火山未返 word 级，按 utterance 切单字近似（中文每字一字）
    if not words and utterances:
        for u in utterances:
            chars = list(u["text"])
            if not chars:
                continue
            dur = u["end"] - u["start"]
            per = dur / len(chars) if chars else 0
            for i, ch in enumerate(chars):
                words.append({
                    "start": u["start"] + i * per,
                    "end": u["start"] + (i + 1) * per,
                    "text": ch,
                })

    return {"ok": True, "text": text, "utterances": utterances, "words": words}

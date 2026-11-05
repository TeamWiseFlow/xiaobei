"""Decoded sample timing and narrowly validated PCM WAV header recovery."""

import hashlib
import math
from pathlib import Path
import struct
import subprocess
import tempfile


def sha256(path: Path, offset: int = 0) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        stream.seek(offset)
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def decoded_timing(path: Path, info: dict) -> dict:
    """Count complete PCM sample frames, independently of container bitrate estimates."""
    stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), {})
    try:
        sample_rate, channels = int(stream['sample_rate']), int(stream['channels'])
    except (KeyError, ValueError, TypeError):
        raise ValueError('缺少有效音轨采样率或声道数') from None
    if sample_rate <= 0 or channels <= 0:
        raise ValueError('音频采样率或声道数无效')
    # A temporary stream bounds RAM and lets subprocess enforce a decode timeout.
    # The source media is never transcoded or overwritten by this measurement.
    with tempfile.TemporaryFile() as pcm:
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(path),
                        '-map', '0:a:0', '-c:a', 'pcm_s16le', '-ar', str(sample_rate),
                        '-ac', str(channels), '-f', 's16le', 'pipe:1'],
                       stdout=pcm, stderr=subprocess.PIPE, timeout=60, check=True)
        size = pcm.tell()
    block = channels * 2
    if not size or size % block:
        raise ValueError('完整解码后采样数为空或采样块不完整')
    samples = size // block
    return {'duration': samples / sample_rate, 'duration_source': 'decoded-samples',
            'decoded_samples': samples, 'sample_rate': sample_rate, 'channels': channels}


def wav_repair_plan(path: Path, reported_duration) -> dict | None:
    """Validate RIFF chunks; recover only the supported provisional PCM size pair."""
    size = path.stat().st_size
    with path.open('rb') as stream:
        head = stream.read(44)
        if len(head) < 12 or head[:4] != b'RIFF' or head[8:12] != b'WAVE':
            raise ValueError('WAV 头无效：需要 RIFF/WAVE 文件')
        riff_size = struct.unpack_from('<I', head, 4)[0]
        canonical = (len(head) == 44 and head[12:16] == b'fmt '
                     and struct.unpack_from('<I', head, 16)[0] == 16 and head[36:40] == b'data')
        data_size = struct.unpack_from('<I', head, 40)[0] if canonical else None
        if riff_size != size - 8:
            diagnostic = f'WAV 长度字段不匹配：RIFF声明={riff_size}，实际={size - 8}'
            # Do not turn an arbitrary truncated file into an apparently valid WAV.
            if not canonical or (riff_size, data_size) != (0x7fffffbf, 0x7fffff9b):
                raise ValueError(diagnostic + '；不是支持的占位头格式，不自动修复')
            tag, channels, rate, byte_rate, align, bits = struct.unpack_from('<HHIIHH', head, 20)
            actual_data = size - 44
            if (tag != 1 or channels not in (1, 2) or bits != 16 or rate <= 0
                    or align != channels * 2 or byte_rate != rate * align
                    or actual_data <= 0 or actual_data % align):
                raise ValueError(diagnostic + '；PCM格式或实际采样块不完整，不自动修复')
            actual_duration = actual_data / byte_rate
            try:
                reported = float(reported_duration)
            except (TypeError, ValueError):
                reported = math.nan
            if (isinstance(reported_duration, bool) or not math.isfinite(reported) or reported <= 0
                    or abs(actual_duration - reported) > .01):
                raise ValueError(diagnostic + '；实际采样时长与接口报告不符或缺少报告时长，不自动修复')
            return {'kind': 'pcm-wav-provisional-lengths', 'original_riff_size': riff_size,
                    'original_data_size': data_size, 'riff_size': size - 8, 'data_size': actual_data,
                    'pcm_sha256': sha256(path, 44), 'sample_duration': actual_duration,
                    'reported_duration': reported}

        # A healthy RIFF may contain extra metadata chunks. Walk their declared
        # boundaries rather than assuming that every WAV has a 44-byte header.
        position, data_found = 12, False
        while position < size:
            stream.seek(position)
            chunk = stream.read(8)
            if len(chunk) != 8:
                raise ValueError('WAV chunk头不完整，不自动修复')
            ident, length = struct.unpack('<4sI', chunk)
            end = position + 8 + length + (length & 1)
            if end > size:
                raise ValueError(f'WAV chunk长度越界：{ident!r} 声明={length}，不自动修复')
            if ident == b'data':
                data_found = True
                if length <= 0:
                    raise ValueError('WAV data为空')
            position = end
        if not data_found:
            raise ValueError('WAV 缺少data块')
    return None


def apply_wav_repair(path: Path, plan: dict) -> None:
    """Change the two length fields and prove that the PCM bytes stayed identical."""
    with path.open('r+b') as stream:
        stream.seek(4)
        stream.write(struct.pack('<I', plan['riff_size']))
        stream.seek(40)
        stream.write(struct.pack('<I', plan['data_size']))
    if sha256(path, 44) != plan['pcm_sha256']:
        raise ValueError('WAV 修复后PCM数据校验不一致')

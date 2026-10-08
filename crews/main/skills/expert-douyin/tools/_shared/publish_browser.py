"""Shared persistent browser transport and cross-tool fail-first lock."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile

SESSION = 'douyin'
UPLOAD_URL = 'https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web'
MANAGE_URL = 'https://creator.douyin.com/creator-micro/content/manage'

def video_publish_state_path():
    override = os.environ.get('DOUYIN_VIDEO_PUBLISH_STATE')
    return Path(override).expanduser() if override else Path.home() / '.camoufox-cli/publications/douyin-video.json'


@contextlib.contextmanager
def publish_lock(*, allow_pending_video=False):
    path = Path(tempfile.gettempdir()) / f'xiaobei-douyin-publication-{os.getuid()}.lock'
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('session douyin 正忙,请等待当前操作完成后再试')
        try:
            # A released process lock must not let login/metrics/note close a paused challenge.
            pending_path = video_publish_state_path()
            if not allow_pending_video and pending_path.exists():
                try:
                    state = json.loads(pending_path.read_text('utf-8'))
                    if not isinstance(state, dict) or state.get('session') != SESSION:
                        raise ValueError('invalid publication state')
                except (ValueError, OSError) as exc:
                    raise RuntimeError('抖音视频任务状态损坏，先核查原任务；不关闭其浏览器') from exc
                if state.get('state') in {'submitted', 'awaiting_verification', 'unconfirmed'}:
                    raise RuntimeError('抖音视频提交尚未结案，先用 douyin-video-publish resume/verify-code 核查或完成验证；保留当前浏览器')
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)

class Browser:
    def __init__(self, headed=False):
        self.headed = headed

    def command(self, *args, timeout=60):
        cmd = [os.environ.get('CAMOUFOX_CLI', 'camoufox-cli'), '--session', SESSION,
               '--persistent', '--json']
        if self.headed:
            cmd.append('--headed')
        result = subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'camoufox-cli failed')
        envelope = json.loads(result.stdout)
        if envelope.get('ok') is False or envelope.get('success') is False:
            raise RuntimeError(str(envelope.get('error', envelope)))
        data = envelope.get('data') if 'data' in envelope else envelope
        return data.get('result') if isinstance(data, dict) and 'result' in data else data

    def eval(self, js):
        return self.command('eval', js)

    def close(self):
        self.command('close', timeout=15)

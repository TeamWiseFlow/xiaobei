import { mkdir, mkdtemp, rename, rm, stat } from 'node:fs/promises';
import { basename, join, resolve, sep } from 'node:path';
import { PlatformError } from './backend.mjs';

// 媒体地址由专用客户端获取，下载按分段协议执行；临时目录避免复用旧文件。
export async function downloadYoutube(target, directory, account, backend) {
  const output = resolve(directory);
  await mkdir(output, { recursive: true });
  const stage = await mkdtemp(join(output, '.youtube-download-'));
  try {
    const result = await backend('youtube', ['item', 'download', target, '--dir', stage,
      ...(account ? ['--account', account] : [])], { timeout: 900000 });
    if (!Array.isArray(result.data) || !result.data.length) throw new PlatformError('DOWNLOAD_FAILED', 'YouTube 没有返回下载文件');
    const files = [];
    for (const file of result.data) {
      if (typeof file.path !== 'string' || !resolve(file.path).startsWith(stage + sep)
          || !['video', 'audio'].includes(file.type)) throw new PlatformError('DOWNLOAD_FAILED', 'YouTube 下载结果无效');
      const info = await stat(file.path);
      if (!info.isFile() || !info.size || info.size !== file.size) throw new PlatformError('DOWNLOAD_FAILED', 'YouTube 媒体文件为空或大小不符');
      files.push({ path: join(output, basename(file.path)), type: file.type, source: file.path });
    }
    if (!files.some(file => file.type === 'video') || !files.some(file => file.type === 'audio')) {
      throw new PlatformError('DOWNLOAD_FAILED', 'YouTube 缺少独立视频轨或音频轨，不能交给分析器');
    }
    for (const file of files) await rename(file.source, file.path);
    return { media_paths: files.map(file => file.path), audio_paths: files.filter(file => file.type === 'audio').map(file => file.path),
      video_paths: files.filter(file => file.type === 'video').map(file => file.path) };
  } finally { await rm(stage, { recursive: true, force: true }); }
}

import { spawnSync } from 'node:child_process';

// 只做媒体编解码，复用统一安装的 ffmpeg/ffprobe。
export function picture(data) {
  const input = Buffer.from(data);
  const probe = spawnSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', 'pipe:0'],
    { input, maxBuffer: 1024 * 1024, timeout: 30000 });
  let dimensions;
  try { dimensions = JSON.parse(probe.stdout).streams[0]; } catch { /* 下方统一拒绝 */ }
  if (probe.status !== 0 || !dimensions?.width || !dimensions?.height || dimensions.width * dimensions.height > 80_000_000) throw Error('无法解析图片或图片尺寸过大');
  const encode = codec => {
    const filter = '[0:v]format=rgba,split[fg][base];[base]lutrgb=r=255:g=255:b=255:a=255[bg];[bg][fg]overlay=shortest=1:format=auto,format=rgb24';
    const result = spawnSync('ffmpeg', ['-v', 'error', '-i', 'pipe:0', '-filter_complex', filter, '-frames:v', '1',
      '-threads', '1', '-f', 'image2pipe', '-vcodec', codec, ...(codec === 'mjpeg' ? ['-q:v', '3'] : []), 'pipe:1'],
      { input, maxBuffer: 128 * 1024 * 1024, timeout: 30000 });
    if (result.status !== 0 || !result.stdout?.length) throw Error('图片转码失败，请检查 ffmpeg 依赖');
    return new Uint8Array(result.stdout);
  };
  return { width: dimensions.width, height: dimensions.height, png: encode('png'), jpeg: encode('mjpeg') };
}

// 分轨下载每段都必须完整，防止 CDN 返回短片段或错误页后仍保存为媒体。
export async function checkYoutubeMediaResponse(input, response, RuntimeError) {
  const url = new URL(input.url);
  if (!/(^|\.)googlevideo\.com$/.test(url.hostname) || !response.ok) return;
  const range = /^(\d+)-(\d+)$/.exec(url.searchParams.get('range') || '');
  if (!range) return;
  const expected = Number(range[2]) - Number(range[1]) + 1;
  if (!Number.isSafeInteger(expected) || expected < 1 || expected > 10 * 1024 * 1024) {
    throw new RuntimeError('UPSTREAM', 'YouTube 媒体分段范围无效');
  }
  const type = response.headers.get('content-type') || '';
  if (/text\/|json|xml/i.test(type)) throw new RuntimeError('UPSTREAM', 'YouTube 媒体分段返回了错误页');
  const size = (await response.clone().arrayBuffer()).byteLength;
  if (size !== expected) throw new RuntimeError('UPSTREAM', 'YouTube 媒体分段不完整，停止下载', { detail: { expected_bytes: expected, actual_bytes: size } });
}

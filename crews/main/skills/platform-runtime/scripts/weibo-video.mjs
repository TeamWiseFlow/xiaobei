export function isVideoPublish(args) {
  return args[0] === 'item' && args[1] === 'publish' && args.some(arg => arg === '--video' || arg.startsWith('--video='));
}

export function videoTransportPolicy(config, env = process.env) {
  const name = 'PLATFORM_API_WEIBO_VIDEO_UPLOAD_TIMEOUT_SECONDS';
  const raw = String(env[name] ?? config.upload_timeout_seconds).trim();
  const seconds = Number(raw);
  if (!/^\d+$/.test(raw) || seconds < config.min_upload_timeout_seconds || seconds > config.max_upload_timeout_seconds) {
    return { valid: false, message: `${name} 必须是 ${config.min_upload_timeout_seconds}–${config.max_upload_timeout_seconds} 的整数秒数` };
  }
  return { valid: true, upload_timeout_seconds: seconds, process_timeout_ms: (seconds + config.process_extra_seconds) * 1000 };
}

export function isVideoSubmit(input) {
  if ((input.method || 'GET').toUpperCase() !== 'POST') return false;
  let url;
  try { url = new URL(input.url); } catch { return false; }
  if (url.origin !== 'https://weibo.com' || url.pathname !== '/ajax/statuses/update') return false;
  const media = Array.isArray(input.form) ? input.form.find(([key]) => key === 'media')?.[1] : input.form?.media;
  try { return JSON.parse(media)?.type === 'video'; } catch { return false; }
}

export function videoRequestPolicy(input, client, policy, ErrorClass) {
  let url;
  try { url = new URL(input.url); } catch { return input; }
  if ((input.method || 'GET').toUpperCase() === 'POST' && url.origin === 'https://up.video.weibocdn.com' && url.pathname === '/2/fileplatform/upload.json') {
    return { ...input, timeout: input.timeout ?? policy.upload_timeout_seconds };
  }
  if (!isVideoSubmit(input)) return input;
  // prepare 使用本次请求实际生效的 Cookie（包括同次 Set-Cookie 更新），不读取历史 profile。
  const xsrf = client.prepare(input).cookies.find(([name]) => name === 'XSRF-TOKEN')?.[1];
  if (!xsrf) throw new ErrorClass('UPSTREAM', '微博视频提交缺少当前 Cookie 对应的 XSRF-TOKEN，已停止提交；请在专属 weibo 窗口确认登录并重新 export，不从旧 profile 补 Token', { detail: { kind: 'missing_csrf' } });
  const pairs = Array.isArray(input.headers) ? input.headers : Object.entries(input.headers || {});
  return { ...input, headers: [...pairs.filter(([name]) => name.toLowerCase() !== 'x-xsrf-token'), ['x-xsrf-token', xsrf]] };
}

import { spawn } from 'node:child_process';
import { mkdir, readFile, writeFile, rm, stat } from 'node:fs/promises';
import { join, resolve, extname } from 'node:path';
import { createWriteStream } from 'node:fs';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { schemaFor, validateArgs, xTextPreview } from './metadata.mjs';
import { videoTransportPolicy } from './weibo-video.mjs';
import { completePublication, matchWeiboVideo, creatorRecordId } from './publication.mjs';
import { canonical, platforms, stateHome, emit, PlatformError, runBackend, networkProxy, requireWriteSession, activeAccount, credential, atomicJson, reportError, packageRoot } from './backend.mjs';

export function take(args, flag, fallback) {
  const matches = args.flatMap((arg, index) => arg === flag || arg.startsWith(flag + '=') ? [index] : []);
  if (matches.length > 1) throw new PlatformError('USAGE', '不要重复指定 ' + flag);
  const index = matches[0] ?? -1;
  if (index < 0) return fallback;
  if (args[index].startsWith(flag + '=')) {
    const value = args[index].slice(flag.length + 1);
    if (!value) throw new PlatformError('USAGE', flag + ' 缺少参数');
    args.splice(index, 1);
    return value;
  }
  const value = args[index + 1];
  if (!value || value.startsWith('--')) throw new PlatformError('USAGE', flag + ' 缺少参数');
  args.splice(index, 2);
  return value;
}
export function toggle(args, flag) {
  const index = args.indexOf(flag);
  if (index < 0) return false;
  args.splice(index, 1);
  return true;
}
function bounded(args, { list = false } = {}) {
  if (args.some(arg => /^(--all|--endpoint|--output|--cookie|--scope|--yes|-e|-o|-y)(=|$)/.test(arg))) throw new PlatformError('USAGE', '不支持无限翻页、覆盖端或输出格式；使用 --limit 与 --cursor');
  for (let i = 0; i < args.length; i++) {
    if (args[i].startsWith('--limit=')) args.splice(i, 1, '--limit', args[i].slice(8));
  }
  if (args.filter(arg => arg === '--limit').length > 1) throw new PlatformError('USAGE', '不要重复指定 --limit');
  const limit = take(args, '--limit', list ? '20' : undefined);
  if (limit !== undefined) {
    if (!/^\d+$/.test(limit) || Number(limit) < 1 || Number(limit) > 100) throw new PlatformError('USAGE', '--limit 范围为 1–100');
    args.push('--limit', limit);
  }
  return args;
}
export function methods(platform, role) { return platforms[platform][role] || []; }
export function allowed(platform, role, command) {
  if (!methods(platform, role).includes(command)) throw new PlatformError('UNSUPPORTED', '该工具不支持 ' + command + '；按能力表选择 hunter、平台专家或 expert-bd', 4);
}
async function status(platform, args) {
  const result = await runBackend(platform, ['auth', 'status', ...args]);
  if (!result.data?.logged_in) throw new PlatformError('AUTH_REQUIRED', '当前登录态未通过在线校验', 2);
  return result;
}
function durationMs(value) {
  const match = /^(\d+)(s|m)$/.exec(value || '');
  const milliseconds = match ? Number(match[1]) * (match[2] === 'm' ? 60000 : 1000) : NaN;
  if (!(milliseconds >= 1000 && milliseconds <= 600000)) throw new PlatformError('USAGE', '--duration 使用 1s–10m 的整数时长');
  return milliseconds;
}
const WRITES = new Set(['like', 'unlike', 'collect', 'uncollect', 'repost', 'unrepost', 'follow', 'unfollow', 'add', 'create', 'update', 'delete', 'send']);
export async function call(platform, role, args) {
  const [resource, action, ...options] = args;
  const command = resource + ' ' + action;
  allowed(platform, role, command);
  const schema = await schemaFor(platform, command);
  bounded(options, { list: '--limit' in schema.options });
  if (options.some(arg => /^--gift(?:=|$)/.test(arg))) throw new PlatformError('UNSUPPORTED', '不提供礼物支付', 4);
  const confirm = toggle(options, '--confirm');
  if (['comment add', 'live send', 'msg send'].includes(command) && options.some(arg => arg === '--text' || arg.startsWith('--text='))) {
    const text = take(options, '--text');
    options.unshift(...(command === 'msg send' ? [text] : []));
    if (command !== 'msg send') options.push(text);
  }
  const parsed = await validateArgs(platform, command, options);
  if (platform === 'x' && command === 'feed list' && parsed.options.kind === 'following') throw new PlatformError('UNSUPPORTED', 'X 关注流尚不支持', 4);
  let writeAccount;
  if (WRITES.has(action)) {
    if (!confirm) return { ok: true, preview: true, platform, command, args: options, message: '已有动作授权时加 --confirm 执行' };
    const account = parsed.global.account;
    take(options, '--account');
    take(options, '-a');
    const alias = await activeAccount(platform, account);
    writeAccount = alias;
    options.push('--account', alias);
    await requireWriteSession(platform, alias);
    if (action === 'delete') options.push('--yes');
  }
  if (action === 'listen') {
    const duration = take(options, '--duration', '1m');
    const timeout = durationMs(duration) + 30000;
    options.push('--duration', duration, '-o', 'jsonl');
    return runBackend(platform, [resource, action, ...options], { stream: true, timeout });
  }
  return writeAccount ? locked(platform, writeAccount, () => runBackend(platform, [resource, action, ...options])) : runBackend(platform, [resource, action, ...options]);
}
export async function downloadMedia(platform, item, dir, { videoOnly = false, account } = {}) {
  const media = (item.media || []).filter(value => value.url && (!videoOnly || value.type === 'video'));
  if (!media.length) throw new PlatformError('MEDIA_UNAVAILABLE', '没有符合请求的媒体地址，不能把资料保存当作下载成功');
  await mkdir(dir, { recursive: true });
  let userAgent;
  try { userAgent = (await credential(platform, account)).device?.browser_identity?.userAgent; } catch { /* 无浏览器 UA 时使用 Node 默认请求头 */ }
  const paths = [];
  const proxy = await networkProxy(platform);
  const counters = {};
  for (const value of media) {
    const url = new URL(value.url);
    if (!['https:', 'http:'].includes(url.protocol)) throw new PlatformError('MEDIA_INVALID', '媒体地址必须是 HTTP(S)');
    const headers = { Referer: platforms[platform].origin + '/' };
    if (userAgent) headers['User-Agent'] = userAgent;
    // CDN 地址由平台返回。Cookie 不随媒体地址发送，也不随跨域重定向泄露。
    const response = proxy
      ? await (await import('wreq-js')).fetch(url.toString(), { headers, proxy, browser: userAgent?.includes('Firefox/') ? 'firefox_135' : 'chrome_131', timeout: 180000, redirect: 'follow', disableDefaultHeaders: true })
      : await fetch(url, { headers, signal: AbortSignal.timeout(180000) });
    if (!response.ok || !response.body || /text\/html|application\/json/.test(response.headers.get('content-type') || '')) throw new PlatformError('DOWNLOAD_FAILED', '媒体下载失败或返回登录页，停止本次采样');
    const type = value.type;
    counters[type] = (counters[type] || 0) + 1;
    const suffix = extname(url.pathname).slice(1).toLowerCase();
    const ext = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'mp4', 'webm', 'mov', 'm4a', 'mp3'].includes(suffix) ? suffix : ({ image: 'jpg', video: 'mp4', audio: 'm4a' }[type] || 'bin');
    const path = join(dir, type === 'video' && counters[type] === 1 ? 'video.' + ext : `${type}-${String(counters[type]).padStart(2, '0')}.${ext}`);
    const temp = path + '.' + process.pid + '.part';
    const body = typeof response.body.getReader === 'function' ? Readable.fromWeb(response.body) : Readable.from(response.body);
    try { await pipeline(body, createWriteStream(temp, { flags: 'wx' })); await import('node:fs/promises').then(fs => fs.rename(temp, path)); }
    finally { await rm(temp, { force: true }); }
    if (!(await stat(path)).size) throw new PlatformError('DOWNLOAD_FAILED', '媒体文件为空');
    paths.push(path);
  }
  return paths;
}
export async function fetchItem(platform, input) {
  const args = [...input];
  const dir = take(args, '--output-dir', undefined);
  const download = toggle(args, '--download-media');
  const videoOnly = toggle(args, '--video-only');
  const account = take(args, '--account', take(args, '-a', undefined));
  const target = args.some(arg => arg === '--url' || arg.startsWith('--url=')) ? take(args, '--url') : args.shift();
  if (!target || args.length) throw new PlatformError('USAGE', 'fetch <完整链接或作品ID> [--output-dir DIR --download-media --video-only]');
  if (download && !dir) throw new PlatformError('USAGE', '下载必须提供 --output-dir');
  const result = await runBackend(platform, ['item', 'get', target, ...(account ? ['--account', account] : [])]);
  const note = result.data;
  if (!note || typeof note.id !== 'string' || !note.id) throw new PlatformError('INVALID_ITEM', '详情没有返回完整作品 ID');
  if (videoOnly && (note.kind !== 'video' || !note.media?.some(media => media.type === 'video'))) throw new PlatformError('VIDEO_REQUIRED', '图文或文本不能进入视频分析器', 4);
  const output = dir ? resolve(dir) : undefined;
  if (output) {
    await mkdir(output, { recursive: true });
    await writeFile(join(output, 'note.json'), JSON.stringify({ ...note, source_url: target, captured_at: new Date().toISOString() }, null, 2) + '\n');
  }
  const mediaPaths = download ? await downloadMedia(platform, note, output, { videoOnly, account }) : [];
  return { ok: true, platform, note, media_paths: mediaPaths, output_dir: output || null };
}
async function tracked(args) {
  return new Promise((done, reject) => {
    const child = spawn(process.env.PUBLISHED_TRACK_CLI || 'published-track', args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    child.stdout.on('data', chunk => { stdout += chunk; });
    child.on('error', () => reject(new PlatformError('RECORD_FAILED', '无法启动 published-track，请检查 wrapper 部署')));
    child.on('close', code => {
      let value;
      try { value = JSON.parse(stdout.trim()); } catch { /* 初始化信息可能在 JSON 前 */
        try { value = JSON.parse(stdout.trim().split('\n').at(-1)); } catch { /* 下方报错 */ }
      }
      if (code || !value || value.ok === false) reject(new PlatformError('RECORD_FAILED', '发布记录或指标写库失败，请单独重试入库，禁止重发内容'));
      else done(value);
    });
  });
}
async function locked(platform, account, callback) {
  const path = join(stateHome, 'locks', `${platform}-${account}.lock`);
  await mkdir(join(stateHome, 'locks'), { recursive: true, mode: 0o700 });
  try { await mkdir(path, { mode: 0o700 }); }
  catch (error) { if (error.code !== 'EEXIST') throw error; throw new PlatformError('BUSY', '该账号正在执行写操作；等待完成后再处理'); }
  try { return await callback(); } finally { await rm(path, { recursive: true, force: true }); }
}
export async function resolvePublication(platform, receipt, backend = runBackend, wait = ms => new Promise(done => setTimeout(done, ms))) {
  const converters = platform === 'weibo' ? await import(pathToFileURL(join(packageRoot(), 'dist/platforms/weibo/web/sign.js'))) : {};
  const complete = completePublication(platform, receipt.result, receipt.user, converters);
  if (complete) return { ...receipt, state: 'published', result: complete };
  if (receipt.state !== 'accepted' || platform !== 'weibo' || !receipt.result?.publication?.media_id) return receipt;
  const policy = platforms.weibo.publication_resolution;
  for (let attempt = 0; attempt < policy.attempts; attempt++) {
    let response;
    try { response = await backend(platform, ['user', 'items', 'me', '--account', receipt.account, '--limit', String(policy.limit)], { timeout: 45000 }); }
    catch (error) { return { ...receipt, resolution_error: error instanceof PlatformError ? error.code : 'ERROR' }; }
    const match = Array.isArray(response.data) ? matchWeiboVideo(response.data, receipt.result.publication.media_id, receipt.user?.id, receipt.submitted_at) : null;
    if (match) {
      const result = completePublication(platform, match, receipt.user, converters);
      if (result) return { ...receipt, state: 'published', result: { ...result, publication: { ...receipt.result.publication, id_pending: false, id_kind: 'weibo_mid', resolution_source: 'own_items_media_id' } }, resolution_error: undefined };
    }
    if (attempt + 1 < policy.attempts) await wait(policy.interval_ms);
  }
  return receipt;
}

export async function publish(platform, input) {
  const args = [...input];
  const confirm = toggle(args, '--confirm');
  const sourceFolder = take(args, '--source-folder', undefined);
  const recordTitle = take(args, '--record-title', undefined);
  const article = toggle(args, '--article');
  const account = take(args, '--account', take(args, '-a', undefined));
  const command = article ? 'article publish' : 'item publish';
  allowed(platform, 'publish', command);
  for (let i = 0; i < args.length; i++) {
    const inline = /^(--(?:image|video|cover|text))=(.*)$/s.exec(args[i]);
    if (inline) args.splice(i, 1, inline[1], inline[2]);
  }
  bounded(args);
  const parsed = await validateArgs(platform, command, args);
  if (parsed.global.raw) throw new PlatformError('USAGE', '发布需要标准化结果，不支持 --raw');
  if (!sourceFolder) throw new PlatformError('USAGE', '发布必须提供 --source-folder，以便保存结果与记录发布');
  const images = args.filter(arg => arg === '--image').length;
  const hasVideo = args.includes('--video');
  if (images && hasVideo) throw new PlatformError('USAGE', '图片和视频不能同时发布');
  const maxImages = { x: 4, weibo: 15, kuaishou: 31 }[platform];
  if (maxImages && images > maxImages) throw new PlatformError('USAGE', `本平台最多 ${maxImages} 张图片`);
  if (platform === 'tiktok' && ((!images && !hasVideo) || (hasVideo && !args.includes('--cover')))) throw new PlatformError('USAGE', 'TikTok 需图片或视频，视频同时需要 --cover');
  if (platform === 'kuaishou' && !images && !hasVideo) throw new PlatformError('USAGE', '快手发布需图片或视频');
  if (args.includes('--ai-declaration')) throw new PlatformError('UNSUPPORTED', '此发布接口没有 AI 声明参数；需要平台声明时停止并交用户在原平台发布', 4);
  for (let i = 0; i < args.length; i++) {
    if (['--image', '--video', '--cover'].includes(args[i])) {
      const path = args[i + 1];
      if (!path || !((await stat(path)).isFile())) throw new PlatformError('USAGE', '请传存在的本地媒体文件绝对路径');
      if (platform === 'kuaishou' && args[i] === '--image' && (await stat(path)).size > 15 * 1024 * 1024) throw new PlatformError('USAGE', '快手单张图片不能超过15MB');
      if (platform === 'tiktok' && args[i] === '--video' && extname(path).toLowerCase() !== '.mp4') throw new PlatformError('USAGE', 'TikTok 发布视频只接受 MP4');
      args[i + 1] = resolve(path);
    }
  }
  const textArgs = [...args];
  const rawText = take(textArgs, '--text', '');
  const text = rawText.startsWith('@') ? await readFile(resolve(rawText.slice(1)), 'utf8') : rawText;
  const videoLimits = platforms[platform].video_publish;
  const captionPresent = text !== '' || parsed.options.title || parsed.options.tag?.length || parsed.options.topic?.length;
  if (hasVideo && videoLimits && (videoLimits.empty_caption && captionPresent || (parsed.options.visibility || 'public') !== videoLimits.visibility || videoLimits.immediate_only && parsed.options.schedule)) {
    throw new PlatformError('UNSUPPORTED', '快手视频接口目前仅覆盖空简介、仅自己可见、立即发布的分支；公开视频、标题/正文/话题或定时发布请在原平台完成', 4);
  }
  const weiboVideo = platform === 'weibo' && hasVideo ? videoTransportPolicy(platforms.weibo.video_transport) : undefined;
  if (weiboVideo && !weiboVideo.valid) throw new PlatformError('USAGE', weiboVideo.message);
  if (rawText.startsWith('@')) {
    const index = args.indexOf('--text');
    args[index + 1] = '@' + resolve(rawText.slice(1));
  }
  if (!text && !images && !hasVideo) throw new PlatformError('USAGE', '没有待发布内容');
  if (!confirm) return { ok: true, preview: true, platform, command, args, source_folder: resolve(sourceFolder), text, ...(platform === 'x' && !article ? await xTextPreview(text, parsed.options.thread) : {}), ...(weiboVideo ? { video_transport: { upload_timeout_seconds: weiboVideo.upload_timeout_seconds, process_timeout_seconds: weiboVideo.process_timeout_ms / 1000 } } : {}), message: '核对正文、媒体、可见范围和平台声明；已有发布授权时加 --confirm' };
  const alias = await activeAccount(platform, account);
  args.push('--account', alias);
  const folder = resolve(sourceFolder);
  await mkdir(folder, { recursive: true });
  const receiptPath = join(folder, `publish-result.${platform}.json`);
  return locked(platform, alias, async () => {
    let receipt;
    try { receipt = JSON.parse(await readFile(receiptPath, 'utf8')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (receipt && receipt.account !== alias) throw new PlatformError('ACCOUNT_MISMATCH', '作品目录已绑定其他发布账号，请核对结果文件');
    if (receipt && !receipt.result) throw new PlatformError('PUBLISH_UNKNOWN', '已有未结案提交，先在本人作品或原平台核查，禁止自动重发');
    if (!receipt) {
      await requireWriteSession(platform, alias);
      const me = await status(platform, ['--account', alias]);
      const now = new Date();
      const publishDate = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
      receipt = { platform, account: alias, user: me.data.user, state: 'submitting', publish_date: publishDate, submitted_at: now.toISOString() };
      await atomicJson(receiptPath, receipt);
      try {
        const result = await runBackend(platform, [...command.split(' '), ...args]);
        if (platform === 'tiktok' && result.data?.id && result.data.url?.includes('/@_/')) {
          if (me.data.user?.url?.includes('/@')) result.data.url = me.data.user.url.replace(/\/$/, '') + '/' + (result.data.kind === 'image' ? 'photo' : 'video') + '/' + result.data.id;
          else throw new PlatformError('PUBLISH_UNKNOWN', '提交返回作品ID，但账号用户名不可得，不能将占位链接当作成功链接');
        }
        if (result.data?.publication?.accepted) receipt = { ...receipt, state: 'accepted', result: result.data };
        else {
          const complete = await resolvePublication(platform, { ...receipt, result: result.data });
          if (complete.state !== 'published') throw new PlatformError('PUBLISH_UNKNOWN', '提交没有返回完整作品 ID，且没有平台接受提交的证据，请在原平台核查');
          receipt = complete;
        }
        await atomicJson(receiptPath, receipt);
      } catch (error) {
        const message = error instanceof PlatformError ? error.message : '本地处理失败，请检查依赖和输入';
        const diagnostic = error instanceof PlatformError ? error.diagnostic : undefined;
        await atomicJson(receiptPath, { ...receipt, state: 'unknown', error: error.code || 'ERROR', error_message: message, ...(diagnostic ? { diagnostic } : {}) });
        throw new PlatformError('PUBLISH_UNKNOWN', `发布结果未知，结果文件已保存；核查本人作品或原平台，禁止重发。${message}`, 1, diagnostic);
      }
    }
    if (receipt.state === 'accepted') {
      receipt = await resolvePublication(platform, receipt);
      await atomicJson(receiptPath, receipt);
      if (receipt.state === 'accepted') return { ok: true, platform, accepted: true, published: false, recorded: false, resolution_pending: true, result: receipt.result, receipt: receiptPath, message: platform === 'weibo' ? '平台已明确接受提交，作品 ID 尚待确认；保留收据，稍后重跑同一目录只查询本人作品，不会再次发布。不要删除收据或改目录重发' : '平台已明确接受提交，尚未取得创作者作品 ID；请用 kuaishou-engagement list 或原平台核查。保留 accepted 收据，重跑不会再次发布，不拿上传 fileId 拼造作品链接' };
    }
    if (!receipt.recorded) {
      try {
        const reference = receipt.result.publication;
        const record = await tracked(['record', '--platform', platforms[platform].workspace, '--title', recordTitle || receipt.result.title || receipt.result.text || text || receipt.result.id, '--content-type', article ? 'article' : receipt.result.kind === 'video' ? 'video' : 'post', '--source-folder', folder, ...(receipt.result.url ? ['--publish-url', receipt.result.url] : []), ...(platform === 'kuaishou' && reference?.id_kind ? ['--notes', JSON.stringify({ platform_runtime: { id: receipt.result.id, id_kind: reference.id_kind, status: receipt.result.status } })] : []), '--account', alias, '--publish-date', receipt.publish_date]);
        receipt = { ...receipt, recorded: true, record };
        await atomicJson(receiptPath, receipt);
      } catch (error) {
        return { ok: true, platform, published: true, recorded: false, result: receipt.result, receipt: receiptPath, message: error.message };
      }
    }
    return { ok: true, platform, published: true, recorded: true, result: receipt.result, receipt: receiptPath };
  });
}
function metricsOf(platform, item) {
  const metrics = {};
  for (const [key, column] of Object.entries(platforms[platform].metrics)) {
    const value = item.stats?.[key];
    if (Number.isSafeInteger(value) && value >= 0) metrics[column] = value;
  }
  return metrics;
}
export function itemId(platform, value) {
  try {
    const url = new URL(value);
    const host = url.hostname;
    if (platform === 'x' && /(^|\.)(x|twitter)\.com$/.test(host)) return /\/status\/(\d+)/.exec(url.pathname)?.[1];
    if (platform === 'tiktok' && /(^|\.)tiktok\.com$/.test(host)) return /\/(?:video|photo)\/(\d+)/.exec(url.pathname)?.[1];
    if (platform === 'kuaishou' && /(^|\.)kuaishou\.com$/.test(host)) return /\/(?:short-video|fw\/photo)\/([^/]+)/.exec(url.pathname)?.[1] || url.searchParams.get('photoId');
  } catch { /* 不能从完整来源识别，不猜内容ID */ }
  return null;
}
export async function engagement(platform, action, input) {
  const args = [...input];
  const account = take(args, '--account', take(args, '-a', undefined));
  const alias = await activeAccount(platform, account);
  const recordId = take(args, '--record-id', undefined);
  if (recordId && !/^[1-9]\d*$/.test(recordId)) throw new PlatformError('USAGE', '--record-id 必须为数据库行 ID');
  if (action === 'fetch' && !recordId) throw new PlatformError('USAGE', 'fetch 必须传 --record-id；它是发布表行 ID');
  const accountArgs = ['--account', alias];
  const me = await status(platform, accountArgs);
  const listArgs = bounded(args, { list: true });
  if (listArgs.includes('--raw')) throw new PlatformError('USAGE', 'engagement 需要标准化指标，不支持 --raw');
  await validateArgs(platform, platform === 'x' ? 'user items' : 'item list', platform === 'x' ? ['me', ...listArgs] : listArgs);
  const result = await runBackend(platform, platform === 'x' ? ['user', 'items', 'me', ...accountArgs, ...listArgs] : ['item', 'list', ...accountArgs, ...listArgs]);
  if (!Array.isArray(result.data)) throw new PlatformError('INVALID_RESPONSE', '本人作品列表没有返回数组');
  if (action === 'list') return result;
  const rows = await tracked(['query', '--platform', platforms[platform].workspace, ...(recordId ? ['--id', recordId] : ['--limit', '100'])]);
  if (!Array.isArray(rows)) throw new PlatformError('RECORD_FAILED', '发布记录查询没有返回数组');
  const selected = rows.filter(row => (!recordId || String(row.id) === recordId) && row.account === alias);
  if (recordId && !selected.length) throw new PlatformError('ACCOUNT_MISMATCH', '记录不存在、超出查询范围或不属于当前账号');
  const updates = [], skipped = [];
  const ownIds = new Set([me.data.user?.id]);
  if (platform === 'kuaishou') {
    const saved = await credential(platform, alias);
    for (const scope of Object.values(saved.scopes || {})) {
      for (const cookie of scope.cookies || []) if (cookie.name === 'userId' && cookie.value) ownIds.add(cookie.value);
    }
  }
  for (const row of selected) {
    const id = itemId(platform, row.publish_url) || (platform === 'kuaishou' ? creatorRecordId(row) : null);
    const item = result.data.find(item => id && item.id === id);
    if (!item) { skipped.push({ id: row.id, reason: 'NOT_IN_FETCHED_PAGE' }); continue; }
    if (item.author?.id && !ownIds.has(item.author.id)) throw new PlatformError('ACCOUNT_MISMATCH', '作品作者不属于当前账号，停止指标回填');
    if (platform === 'x' && !item.author?.id) throw new PlatformError('ACCOUNT_UNVERIFIED', 'X 作品缺少作者，停止回填');
    const metrics = metricsOf(platform, item);
    if (!Object.keys(metrics).length) { skipped.push({ id: row.id, reason: 'METRICS_UNAVAILABLE' }); continue; }
    await tracked(['update-metrics', '--platform', platforms[platform].workspace, '--id', String(row.id), ...Object.entries(metrics).flatMap(([key, value]) => ['--' + key, String(value)])]);
    updates.push({ id: row.id, content_id: item.id, metrics });
  }
  return { ok: true, platform, account: alias, source: platform === 'x' ? 'user.items:me' : 'creator:item.list', captured_at: new Date().toISOString(), updates, skipped, page: result.page };
}
export async function main(argv = process.argv.slice(2)) {
  let [platform, role, action, ...args] = argv;
  platform = canonical(platform);
  if (!action || ['--help', '-h', 'help'].includes(action)) {
    emit({ ok: true, platform, role, commands: role === 'hunter' ? ['check', 'methods', 'search', 'user', 'user-posts', 'comments', 'fetch', 'call', 'login', 'login-confirm', ...(platform === 'kuaishou' ? [] : ['login-status', 'export', ...(platform === 'tiktok' ? ['prepare-write'] : [])])] : role === 'engagement' ? ['check', 'list', 'fetch --record-id <行ID>', 'daily'] : role === 'publish' ? ['check', 'publish --source-folder DIR --text TEXT [--image FILE | --video FILE] [--confirm]'] : methods(platform, role), call_syntax: '<resource> <action> [平台选项]；写操作默认预览，加 --confirm 执行' });
    return;
  }
  if (action === 'check') {
    if (role === 'publish' && platform === 'tiktok') {
      const options = [...args];
      await requireWriteSession(platform, take(options, '--account', take(options, '-a', undefined)));
    }
    return emit(await status(platform, args));
  }
  if (role === 'hunter' && ['login', 'login-status', 'login-confirm', 'export', 'prepare-write'].includes(action)) {
    if (platform === 'kuaishou') {
      if (!['login', 'login-confirm'].includes(action)) throw new PlatformError('UNSUPPORTED', '快手使用 login/login-confirm 的 QR 或短信流程', 4);
      bounded(args);
      const { kuaishouLogin } = await import('./kuaishou-login.mjs');
      return emit(await kuaishouLogin(action, args));
    }
    const { main: login } = await import('./login.mjs');
    return login([action === 'login-confirm' ? 'export' : action, '--platform', platform, ...args]);
  }
  if (action === 'methods' && ['hunter', 'interact', 'im', 'live', 'publish'].includes(role)) return emit({ ok: true, platform, methods: methods(platform, role), schemas: await Promise.all(methods(platform, role).map(key => schemaFor(platform, key))) });
  if (role === 'hunter' && action === 'fetch') return emit(await fetchItem(platform, args));
  if (role === 'publish' && ['publish', 'post'].includes(action)) return emit(await publish(platform, args));
  if (role === 'engagement' && ['list', 'fetch', 'daily'].includes(action)) return emit(await engagement(platform, action, args));
  if (role === 'publish' || role === 'engagement') throw new PlatformError('USAGE', '不支持该子命令');
  const aliases = { search: ['item', 'search'], user: ['user', 'get'], 'user-search': ['user', 'search'], 'user-posts': ['user', 'items'], comments: ['comment', 'list'] };
  const interactAliases = { retweet: 'repost', unretweet: 'unrepost', bookmark: 'collect', unbookmark: 'uncollect' };
  if (role === 'hunter' && aliases[action]) args = [...aliases[action], ...args];
  else if (action === 'call') { /* args 已含 resource action */ }
  else if (role === 'interact' && ['follow', 'unfollow'].includes(action)) args = ['user', action, ...args];
  else if (role === 'interact' && ['comment', 'reply'].includes(action)) args = ['comment', 'add', ...args];
  else if (role === 'interact') args = ['item', interactAliases[action] || action, ...args];
  else if (role === 'im') args = ['msg', action, ...args];
  else if (role === 'live') args = ['live', action === 'room' ? 'get' : action, ...args];
  else throw new PlatformError('USAGE', '请使用 help 中列出的子命令或 call');
  const result = await call(platform, role, args);
  if (args[1] !== 'listen') emit(result);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(reportError);

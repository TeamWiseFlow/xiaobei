import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { tmpdir, homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { platforms, canonical, stateHome, runtimeDir, activeAccount, accountName, credential, credentialPath, atomicJson, emit, runBackend, networkProxy, PlatformError, reportError } from './backend.mjs';

const exec = promisify(execFile);
const hunter = platform => `${platform}-hunter`;
const sessionGuide = platform => `请检查登录是否在 Camoufox 专属 session ${platforms[platform].session} 的窗口内完成；用 ${hunter(platform)} login-status 检查窗口，未就绪时运行 ${hunter(platform)} login。不要改用通用 browser 会话`;
async function browser(platform, args) {
  const proxy = await networkProxy(platform);
  if (proxy && !/^https?:/.test(proxy)) throw new PlatformError('PROXY_INVALID', 'Camoufox 有头登录只支持 HTTP(S) 代理，请为浏览器与 API 配置同一 HTTP(S) 出口');
  try {
    const { stdout } = await exec(process.env.CAMOUFOX_CLI || 'camoufox-cli', ['--session', platforms[platform].session, '--persistent', '--headed', '--json', ...(proxy ? ['--proxy', proxy] : []), ...args], { timeout: 60000, maxBuffer: 16 * 1024 * 1024 });
    const output = JSON.parse(stdout);
    if (output.success !== true && output.ok !== true && !(args[0] === 'info' && typeof output.running === 'boolean')) throw new Error('failed');
    return output.data || output;
  } catch { throw new PlatformError('BROWSER_FAILED', `专属 session ${platforms[platform].session} 的浏览器命令 ${args[0]} 失败；${sessionGuide(platform)}；同时检查 DISPLAY 与浏览器依赖，未主动关闭窗口`); }
}
// 页面 URL 可能包含登录票据；终端仅返回来源与路径。
function pageUrl(value) {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol)) return null;
    return url.origin + url.pathname;
  } catch { return null; }
}
export async function browserStatus(platform) {
  const session = platforms[platform].session;
  const profile = join(homedir(), '.camoufox-cli/profiles', session);
  const info = await browser(platform, ['info']);
  const status = { session, profile, daemon_running: info.running === true, headed: info.running === true ? info.headed === true : null, browser_launched: false, persistent: false, url: null, browser_status: 'not_running' };
  if (!status.daemon_running) return status;
  if (info.session !== session) throw new PlatformError('BROWSER_FAILED', `浏览器返回的 session 与专属 session ${session} 不符，停止操作`);
  if (!status.headed) return { ...status, browser_launched: null, browser_status: 'not_headed' };
  try {
    const page = await browser(platform, ['url']);
    status.url = pageUrl(page.url);
    // url/identity 只读；始终保持 --headed，不切换已有有头 daemon 的模式。
    const identity = await browser(platform, ['identity', 'show']);
    status.browser_launched = true;
    status.persistent = typeof identity.persistent === 'string' && resolve(identity.persistent) === profile;
    status.browser_status = status.persistent ? 'ready' : 'wrong_profile';
  } catch (error) {
    if (error.code !== 'BROWSER_FAILED') throw error;
    status.browser_status = 'unavailable';
  }
  return status;
}
function requireBrowser(platform, status) {
  if (status.browser_status !== 'ready') throw new PlatformError('BROWSER_FAILED', `专属 session ${status.session} 的窗口未就绪（${status.browser_status}）；${sessionGuide(platform)}。若是 wrong_profile，先结束该 session 的其他操作，再关闭并重新 login；旧 API 会话未覆盖，未主动关闭窗口`);
}
export function filterCookies(platform, cookies) {
  const domain = platforms[platform].cookie_domain;
  return cookies.filter(cookie => {
    const host = String(cookie.domain || '').replace(/^\./, '');
    return (host === domain || host.endsWith('.' + domain)) && (cookie.expires === undefined || cookie.expires <= 0 || cookie.expires > Date.now() / 1000);
  });
}
export function validateCookies(platform, cookies) {
  const present = new Set(cookies.filter(cookie => cookie.value).map(cookie => cookie.name));
  const missing = platforms[platform].required_cookies.filter(group => !group.some(name => present.has(name)));
  if (missing.length) throw new PlatformError('AUTH_REQUIRED', '导出缺少登录字段：' + missing.map(group => group.join('/')).join(', ') + `；${sessionGuide(platform)}。profile 文件里的历史 Cookie 不代表当前网页登录有效；确认在该窗口登录后再 export`, 2);
}
export async function exportSession(platform, account, requireWrite) {
  const config = platforms[platform];
  requireBrowser(platform, await browserStatus(platform));
  const temporary = await mkdtemp(join(tmpdir(), 'platform-login-'));
  try {
    const cookiesFile = join(temporary, 'cookies.json'), identityFile = join(temporary, 'identity.json'), importFile = join(temporary, 'session.json');
    const snapshotResult = await browser(platform, ['eval', await readFile(join(runtimeDir, 'scripts/browser-snapshot.js'), 'utf8')]);
    const snapshot = snapshotResult.result;
    if (!snapshot?.origin || !snapshot.user_agent) throw new PlatformError('BROWSER_FAILED', `没有读取到专属 session ${config.session} 当前页面的身份与来源；${sessionGuide(platform)}`);
    const hostname = new URL(snapshot.origin).hostname;
    if (hostname !== config.cookie_domain && !hostname.endsWith('.' + config.cookie_domain)) throw new PlatformError('ORIGIN_MISMATCH', `专属 session ${config.session} 当前页面不属于目标平台，停止导出；${sessionGuide(platform)}`);
    await browser(platform, ['cookies', 'export', cookiesFile]);
    await browser(platform, ['identity', 'export', identityFile]);
    const identity = JSON.parse(await readFile(identityFile, 'utf8'));
    if (typeof identity.persistent !== 'string' || resolve(identity.persistent) !== join(homedir(), '.camoufox-cli/profiles', config.session)) throw new PlatformError('BROWSER_FAILED', `专属 session ${config.session} 的持久 profile 发生变化，停止导出；旧 API 会话未覆盖`);
    if (identity.userAgent !== snapshot.user_agent) throw new PlatformError('IDENTITY_MISMATCH', '导出过程中浏览器身份发生变化');
    const raw = JSON.parse(await readFile(cookiesFile, 'utf8'));
    const cookies = filterCookies(platform, Array.isArray(raw) ? raw : raw.cookies || []);
    validateCookies(platform, cookies);
    const missing = (config.write_fields || []).filter(key => !snapshot[key]);
    if (requireWrite && missing.length) throw new PlatformError('WRITE_SESSION_REQUIRED', '缺少 TikTok 同次写入材料：' + missing.join(', ') + '；保留浏览器，检查 Studio 页面或使用原平台操作', 2);
    let input = cookies;
    if (platform === 'tiktok') {
      const map = new Map();
      for (const cookie of [...cookies].sort((a, b) => String(a.domain).length - String(b.domain).length)) {
        const host = String(cookie.domain).replace(/^\./, '');
        if (hostname === host || (String(cookie.domain).startsWith('.') && hostname.endsWith('.' + host))) map.set(cookie.name, cookie.value);
      }
      input = { ...snapshot, cookie: [...map].map(([name, value]) => name + '=' + value).join('; ') };
    }
    await writeFile(importFile, JSON.stringify(input), { mode: 0o600 });
    const candidateHome = join(temporary, 'verified');
    await runBackend(platform, ['auth', 'login', '--method', 'cookie', '--cookie', '@' + importFile, '--account', account], { home: candidateHome, identityFile });
    const check = await runBackend(platform, ['auth', 'status', '--account', account], { home: candidateHome, identityFile });
    if (!check.data?.logged_in || !check.data.user?.id) throw new PlatformError('AUTH_REQUIRED', `新导出会话未通过在线身份校验，旧会话未覆盖；${sessionGuide(platform)}`, 2);
    const saved = await credential(platform, account, candidateHome);
    if (saved.user?.id !== check.data.user.id) throw new PlatformError('ACCOUNT_MISMATCH', '导入与在线校验的用户不一致，停止导出');
    let previous;
    try { previous = await credential(platform, account); } catch (error) { if (error.code !== 'AUTH_REQUIRED') throw error; }
    if (previous?.user?.id && previous.user.id !== check.data.user.id) throw new PlatformError('ACCOUNT_MISMATCH', '此 alias 已保存其他用户，请使用新的 --account');
    saved.device = { ...saved.device, browser_identity: identity };
    const path = credentialPath(platform, account);
    await atomicJson(path, saved);
    const current = join(dirname(path), '_current');
    try { await readFile(current); } catch (error) { if (error.code !== 'ENOENT') throw error; await writeFile(current, account + '\n', { mode: 0o600, flag: 'wx' }); }
    let closed = true;
    try { await browser(platform, ['close']); } catch { closed = false; }
    return { ok: true, platform, account, user: check.data.user, session: path, browser_session: config.session, credential_file: path, write_ready: !missing.length, missing_write_fields: missing, browser_closed: closed, message: missing.length ? '在线校验通过；仅支持读取，写操作材料未齐全' : '会话已导入并在线校验；写操作仍按工具验收限制执行' };
  } catch (error) {
    if (error instanceof PlatformError && error.code === 'AUTH_REQUIRED' && !error.message.includes(`专属 session ${config.session}`)) error.message += `；${sessionGuide(platform)}；旧 API 会话未覆盖`;
    throw error;
  } finally { await rm(temporary, { recursive: true, force: true }); }
}
export async function main(argv = process.argv.slice(2)) {
  const args = [...argv];
  function value(flag, fallback) {
    const index = args.indexOf(flag);
    if (index < 0) return fallback;
    const item = args[index + 1];
    if (!item || item.startsWith('--')) throw new PlatformError('USAGE', flag + ' 缺少值');
    args.splice(index, 2); return item;
  }
  if (args.includes('--help') || args.includes('-h')) return emit({ ok: true, usage: 'x-hunter|tiktok-hunter|weibo-hunter login|login-status|export|login-confirm [--account alias] [--require-write]；tiktok-hunter prepare-write' });
  const platform = canonical(value('--platform', ''));
  if (!platforms[platform].session) throw new PlatformError('UNSUPPORTED', '浏览器登录仅支持 x / tiktok / weibo；快手使用 kuaishou-hunter login', 4);
  const account = accountName(value('--account', await activeAccount(platform)));
  const requireWrite = args.includes('--require-write');
  if (requireWrite) args.splice(args.indexOf('--require-write'), 1);
  const action = args.shift();
  if (args.length) throw new PlatformError('USAGE', '存在未知参数');
  if (!['login', 'login-status', 'prepare-write', 'export', 'check'].includes(action)) throw new PlatformError('USAGE', '指定 login、login-status、export、prepare-write 或 check');
  if (requireWrite && (platform !== 'tiktok' || action !== 'export')) throw new PlatformError('USAGE', '--require-write 仅用于 TikTok export/login-confirm');
  if (action === 'check') {
    const result = await runBackend(platform, ['auth', 'status', '--account', account]);
    if (!result.data?.logged_in) throw new PlatformError('AUTH_REQUIRED', '会话未通过在线校验', 2);
    return emit(result);
  }
  await mkdir(join(stateHome, 'locks'), { recursive: true, mode: 0o700 });
  const lock = join(stateHome, 'locks', `browser-${platform}.lock`);
  try { await mkdir(lock, { mode: 0o700 }); }
  catch (error) { if (error.code !== 'EEXIST') throw error; throw new PlatformError('BUSY', '此平台正在登录/导出；不要并发操作同一 profile'); }
  try {
    if (action === 'login-status') {
      const status = await browserStatus(platform);
      const guidance = status.browser_status === 'wrong_profile'
        ? `当前窗口没有使用专属持久 profile；先结束 session ${status.session} 的其他操作，再关闭该 session 并重新运行 ${hunter(platform)} login`
        : status.browser_status === 'ready' ? '专属有头持久窗口已就绪' : `${status.browser_status}；${sessionGuide(platform)}`;
      return emit({ ok: true, platform, account, ...status, message: `${guidance}。此结果仅检查登录窗口，不判定账号登录有效；导出成功后以 ${hunter(platform)} check 的在线校验为准` });
    }
    if (action === 'login' || action === 'prepare-write') {
      if (action === 'prepare-write' && platform !== 'tiktok') throw new PlatformError('USAGE', 'prepare-write 仅用于 TikTok');
      const url = action === 'prepare-write' ? 'https://www.tiktok.com/tiktokstudio/upload' : platforms[platform].login_url;
      await browser(platform, ['open', url]);
      const status = await browserStatus(platform);
      requireBrowser(platform, status);
      if (!status.url) throw new PlatformError('BROWSER_FAILED', `专属 session ${status.session} 未取得 HTTP(S) 页面 URL；${sessionGuide(platform)}`);
      return emit({ ok: true, platform, account, awaiting_user_login: true, ...status, login_url: url, message: `已确认专属 session ${status.session} 的有头持久窗口已打开；只在此窗口完成登录，不要改用通用 browser 会话。等用户确认后调用 ${hunter(platform)} export，不自动轮询；窗口状态不代表账号已登录` });
    }
    if (action !== 'export') throw new PlatformError('USAGE', '未知命令');
    emit(await exportSession(platform, account, requireWrite));
  } finally { await rm(lock, { recursive: true, force: true }); }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(reportError);

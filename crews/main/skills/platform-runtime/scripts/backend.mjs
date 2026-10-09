import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFile, mkdir, writeFile, rename, chmod } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { safeDiagnostic } from './diagnostics.mjs';
import { isVideoPublish, videoTransportPolicy } from './weibo-video.mjs';

export const runtimeDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const platforms = JSON.parse(await readFile(join(runtimeDir, 'platforms.json'), 'utf8'));
export const stateHome = resolve(process.env.PLATFORM_API_HOME || join(process.env.OPENCLAW_HOME || join(homedir(), '.openclaw'), 'logins/platform-api'));
export const emit = value => process.stdout.write(JSON.stringify(value) + '\n');
export class PlatformError extends Error {
  constructor(code, message, exitCode = 1, diagnostic) { super(message); this.code = code; this.exitCode = exitCode; this.diagnostic = diagnostic; }
}
export function canonical(value) {
  const platform = value === 'twitter' ? 'x' : value;
  if (!platforms[platform]) throw new PlatformError('USAGE', '平台仅支持 x / tiktok / kuaishou / weibo');
  return platform;
}
export function accountName(value) {
  if (!/^[a-z0-9][a-z0-9_-]{0,31}$/.test(value) || value === 'guest') throw new PlatformError('USAGE', '账号 alias 不合法');
  return value;
}
export function backendAccount(args) {
  const index = args.findIndex(value => /^(--account|-a)(=|$)/.test(value));
  if (index < 0) return undefined;
  const equals = args[index].indexOf('=');
  return equals < 0 ? args[index + 1] : args[index].slice(equals + 1);
}
export async function activeAccount(platform, account, home = stateHome) {
  if (account) return accountName(account);
  try { return accountName((await readFile(join(home, 'auth', platform, 'web/_current'), 'utf8')).trim()); }
  catch (error) { if (error.code !== 'ENOENT') throw error; return 'default'; }
}
export const credentialPath = (platform, account, home = stateHome) => join(home, 'auth', platform, 'web', accountName(account) + '.json');
export async function credential(platform, account, home = stateHome) {
  const alias = await activeAccount(platform, account, home);
  try { return JSON.parse(await readFile(credentialPath(platform, alias, home), 'utf8')); }
  catch (error) {
    if (error.code === 'ENOENT') throw new PlatformError('AUTH_REQUIRED', '没有平台会话，请先完成对应登录流程', 2);
    throw new PlatformError('SESSION_INVALID', '平台会话文件无法读取，请检查登录状态');
  }
}
export async function atomicJson(path, value) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temp = path + '.' + process.pid + '.tmp';
  await writeFile(temp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  await chmod(temp, 0o600);
  await rename(temp, path);
}
export function packageRoot() {
  try { return dirname(createRequire(import.meta.url).resolve('catbus-cli/package.json')); }
  catch { throw new PlatformError('DEPENDENCY_MISSING', '平台依赖未安装，请通过项目安装流程安装 skill Node 依赖'); }
}
export async function networkProxy(platform) {
  const key = 'PLATFORM_API_' + platform.toUpperCase() + '_PROXY';
  let value;
  if (Object.hasOwn(process.env, key)) value = process.env[key];
  else if (Object.hasOwn(process.env, 'PLATFORM_API_PROXY')) value = process.env.PLATFORM_API_PROXY;
  else if (platforms[platform].session) {
    try {
      const config = JSON.parse(await readFile(process.env.CAMOUFOX_CLI_CONFIG || join(homedir(), '.camoufox-cli/config.json'), 'utf8'));
      value = config.sessions?.[platforms[platform].session]?.proxy ?? config.default?.proxy;
    } catch { /* 与浏览器相同：没有有效配置则直连 */ }
  }
  if (!value) return undefined;
  let url;
  try { url = new URL(value); } catch { throw new PlatformError('PROXY_INVALID', '平台代理地址格式不合法'); }
  if (!['http:', 'https:', 'socks4:', 'socks5:', 'socks5h:'].includes(url.protocol)) throw new PlatformError('PROXY_INVALID', '平台代理协议不支持');
  return value;
}
export async function runBackend(platform, args, { home = stateHome, identityFile, stream = false, timeout } = {}) {
  let budget = timeout ?? 360000;
  if (platform === 'weibo' && isVideoPublish(args)) {
    const policy = videoTransportPolicy(platforms.weibo.video_transport);
    if (!policy.valid) throw new PlatformError('USAGE', policy.message);
    if (timeout === undefined) budget = policy.process_timeout_ms;
  }
  await mkdir(home, { recursive: true, mode: 0o700 });
  args = [...args];
  const proxy = await networkProxy(platform);
  if (proxy && !args.some(arg => arg === '--proxy' || arg.startsWith('--proxy='))) args.push('--proxy', proxy);
  const command = process.env.PLATFORM_API_CLI || process.execPath;
  const argv = process.env.PLATFORM_API_CLI ? [platform, ...args] : [join(runtimeDir, 'scripts/api-runner.mjs'), platform, ...args];
  const env = { ...process.env, CATBUS_HOME: home };
  if (identityFile) env.PLATFORM_API_IDENTITY_FILE = identityFile;
  return new Promise((done, reject) => {
    const child = spawn(command, argv, { env, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '', stderr = '', timedOut = false;
    const timer = setTimeout(() => { timedOut = true; child.kill('SIGTERM'); }, budget);
    child.stdout.on('data', chunk => {
      if (stream) process.stdout.write(chunk);
      else stdout += chunk;
      if (stdout.length > 32 * 1024 * 1024) child.kill('SIGTERM');
    });
    child.stderr.on('data', chunk => { if (stderr.length < 1024 * 1024) stderr += chunk; });
    child.on('error', error => { clearTimeout(timer); reject(new PlatformError('BACKEND_UNAVAILABLE', error.code || '无法启动平台进程')); });
    child.on('close', async code => {
      clearTimeout(timer);
      if (timedOut) return reject(new PlatformError('TIMEOUT', '平台请求超时；写入结果可能未知，先核查结果，禁止直接重发'));
      if (stream) {
        if (code !== 0) return reject(new PlatformError('STREAM_FAILED', '平台监听异常结束，不能把本次结果当作完整样本', code || 1));
        return done({ ok: true });
      }
      let result;
      try { result = JSON.parse(stdout); }
      catch { return reject(new PlatformError('INVALID_RESPONSE', '平台进程没有返回有效 JSON')); }
      if (code !== 0 || result.ok === false) {
        let redact, saved;
        try { ({ redact } = await import(pathToFileURL(join(packageRoot(), 'dist/core/log.js')))); } catch { /* 无脱敏器时不透传文本 */ }
        try {
          saved = await credential(platform, backendAccount(args), home);
        } catch { /* 未登录请求没有可供补充打码的凭据 */ }
        const diagnostic = safeDiagnostic(result.error, { redact, saved });
        const errorCode = diagnostic.code;
        const base = ['AUTH_REQUIRED', 'AUTH_EXPIRED'].includes(errorCode) ? '会话缺失或平台明确拒绝登录，请检查对应登录流程' : `平台请求失败（${errorCode}），停止本轮操作并核查平台状态`;
        const message = diagnostic.message ? `${base}：${diagnostic.message}` : base;
        return reject(new PlatformError(errorCode, message, ['AUTH_REQUIRED', 'AUTH_EXPIRED'].includes(errorCode) ? 2 : (code || 1), diagnostic));
      }
      done(result);
    });
  });
}
export async function requireWriteSession(platform, account) {
  if (platform !== 'tiktok') return;
  const saved = await credential(platform, account);
  const missing = platforms.tiktok.write_fields.filter(key => !saved.device?.[key]);
  if (missing.length) throw new PlatformError('WRITE_SESSION_REQUIRED', 'TikTok 写操作缺少同次浏览器会话材料：' + missing.join(', '), 2);
}
export function reportError(error) {
  emit({ ok: false, error: error.code || 'ERROR', message: error instanceof PlatformError ? error.message : '本地处理失败，请检查输入文件、依赖和状态目录', ...(error instanceof PlatformError && error.diagnostic ? { diagnostic: error.diagnostic } : {}) });
  process.exitCode = error.exitCode || 1;
}

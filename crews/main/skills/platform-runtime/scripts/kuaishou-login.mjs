import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, stat, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { stateHome, runtimeDir, activeAccount, credential, credentialPath, atomicJson, runBackend, PlatformError } from './backend.mjs';

function option(args, flag, fallback) {
  const matches = args.flatMap((arg, index) => arg === flag || arg.startsWith(flag + '=') ? [index] : []);
  if (matches.length > 1) throw new PlatformError('USAGE', '不要重复指定 ' + flag);
  const index = matches[0];
  if (index === undefined) return fallback;
  if (args[index].startsWith(flag + '=')) {
    const value = args[index].slice(flag.length + 1);
    if (!value) throw new PlatformError('USAGE', flag + ' 缺少值');
    args.splice(index, 1); return value;
  }
  const value = args[index + 1];
  if (!value || value.startsWith('-')) throw new PlatformError('USAGE', flag + ' 缺少值');
  args.splice(index, 2); return value;
}
async function adopt(account, home) {
  const saved = await credential('kuaishou', account, home);
  const check = await runBackend('kuaishou', ['auth', 'status', '--account', account], { home });
  if (!check.data?.logged_in || !check.data.user?.id) throw new PlatformError('AUTH_REQUIRED', '新会话未通过在线身份校验，旧会话保留', 2);
  if (saved.user?.id !== check.data.user.id) throw new PlatformError('ACCOUNT_MISMATCH', '登录结果与在线用户不一致');
  let old;
  try { old = await credential('kuaishou', account); } catch (error) { if (error.code !== 'AUTH_REQUIRED') throw error; }
  if (old?.user?.id && old.user.id !== saved.user.id) throw new PlatformError('ACCOUNT_MISMATCH', '当前 alias 属于其他账号，请用新 alias 登录');
  await atomicJson(credentialPath('kuaishou', account), saved);
  const current = join(stateHome, 'auth/kuaishou/web/_current');
  try { await writeFile(current, account + '\n', { flag: 'wx', mode: 0o600 }); } catch (error) { if (error.code !== 'EEXIST') throw error; }
  await rm(home, { force: true, recursive: true });
  return { ok: true, platform: 'kuaishou', account, user: saved.user };
}
async function performLogin(action, input) {
  const args = [...input];
  const account = await activeAccount('kuaishou', option(args, '--account', option(args, '-a', undefined)));
  const method = option(args, '--method', 'qrcode');
  const phone = option(args, '--phone'), code = option(args, '--code');
  if (args.length) throw new PlatformError('USAGE', '存在未知登录参数');
  const root = join(stateHome, 'pending', 'kuaishou', account);
  await mkdir(root, { recursive: true, mode: 0o700 });
  if (method === 'sms') {
    const home = join(root, 'sms');
    if (action === 'login' && (!phone || code)) throw new PlatformError('USAGE', '短信 login 必须传 --phone；确认验证码使用 login-confirm --code');
    if (action === 'login-confirm' && (!code || phone)) throw new PlatformError('USAGE', '短信 login-confirm 必须传 --code，不重复请求短信');
    if (action === 'login-confirm' && !(await stat(home).catch(() => null))) throw new PlatformError('LOGIN_NOT_STARTED', '先用 login --method sms --phone 请求验证码');
    if (action === 'login') await rm(home, { recursive: true, force: true });
    const result = await runBackend('kuaishou', ['auth', 'login', '--method', 'sms', '--account', account, ...(phone ? ['--phone', phone] : ['--code', code])], { home });
    return action === 'login' ? result : adopt(account, home);
  }
  if (method !== 'qrcode') throw new PlatformError('USAGE', '快手登录使用 qrcode 或 sms');
  if (phone || code) throw new PlatformError('USAGE', '扫码登录不接受手机号或验证码');
  const pointer = join(root, 'current.json');
  let previous;
  try { previous = JSON.parse(await readFile(pointer, 'utf8')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (action === 'login-confirm') {
    if (!previous) throw new PlatformError('LOGIN_NOT_STARTED', '先运行 kuaishou-hunter login');
    let result;
    try { result = JSON.parse(await readFile(join(previous.home, 'result.json'), 'utf8')); }
    catch (error) {
      if (error.code !== 'ENOENT') throw error;
      if (Date.now() - previous.started_at > 240000) throw new PlatformError('LOGIN_TIMEOUT', '扫码任务已过期，请重新发起登录', 2);
      return { ok: true, platform: 'kuaishou', awaiting_scan: true, qr_path: join(previous.home, 'cache/kuaishou/qrcode.png') };
    }
    if (!result.ok) throw new PlatformError(result.error || 'LOGIN_FAILED', '快手登录失败，请重新检查账号与验证码状态', 2);
    const imported = await adopt(account, previous.home);
    await rm(pointer, { force: true });
    return imported;
  }
  if (previous && Date.now() - previous.started_at < 240000) throw new PlatformError('BUSY', '已有扫码登录任务，请先使用 login-confirm 查看结果');
  if (previous) await rm(previous.home, { force: true, recursive: true });
  const home = await mkdtemp(join(root, 'qr-'));
  const child = spawn(process.execPath, [join(runtimeDir, 'scripts/kuaishou-login-worker.mjs'), account, home], { detached: true, stdio: 'ignore', env: process.env });
  child.on('error', () => {});
  child.unref();
  await atomicJson(pointer, { home, account, started_at: Date.now(), pid: child.pid });
  const qrPath = join(home, 'cache/kuaishou/qrcode.png');
  for (let attempt = 0; attempt < 100; attempt++) {
    if (await stat(qrPath).catch(() => null)) return { ok: true, platform: 'kuaishou', account, awaiting_scan: true, qr_path: qrPath, message: '交用户扫码确认后调用 login-confirm；任务有时限' };
    if (await stat(join(home, 'result.json')).catch(() => null)) return { ok: true, platform: 'kuaishou', account, awaiting_confirmation: true, message: '扫码任务已结束，使用 login-confirm 校验并保存会话' };
    await new Promise(done => setTimeout(done, 100));
  }
  return { ok: true, platform: 'kuaishou', account, awaiting_qr: true, message: '二维码仍在准备，使用 login-confirm 查看任务状态' };
}
export async function kuaishouLogin(action, args) {
  const root = join(stateHome, 'locks');
  await mkdir(root, { recursive: true, mode: 0o700 });
  const lock = join(root, 'login-kuaishou.lock');
  try { await mkdir(lock, { mode: 0o700 }); }
  catch (error) { if (error.code !== 'EEXIST') throw error; throw new PlatformError('BUSY', '已有快手登录操作正在执行'); }
  try { return await performLogin(action, args); }
  finally { await rm(lock, { recursive: true, force: true }); }
}

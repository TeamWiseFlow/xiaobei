import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createHash, randomBytes } from 'node:crypto';
import { readFileSync, mkdirSync, writeFileSync, renameSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

const capabilities = new Map();
export function supportsOperation(platform, operation) {
  // Only static protocol metadata is cached. Keys and platform inputs never enter the file.
  const binding = createHash('sha256').update(JSON.stringify([
    process.env.RELAY_BASE_URL || 'https://relay.openclaw-for-business.com', process.env.OFB_KEY || '', platform])).digest('hex');
  const home = process.env.RELAY_BUDGET_HOME || join(process.env.OPENCLAW_HOME || join(homedir(), '.openclaw'), 'cache/relay-budget-v1');
  const file = join(home, 'platform-capabilities-' + binding + '.json');
  let cached = capabilities.get(file);
  if (!cached) try { cached = JSON.parse(readFileSync(file, 'utf8')); } catch {}
  if (!(cached && Number.isFinite(cached.at) && Date.now() >= cached.at && Date.now() - cached.at < 300000
      && Array.isArray(cached.operations) && cached.operations.every(x => typeof x === 'string'))) {
    let operations;
    try {
      operations = compute(platform, 'capabilities', {}).operations;
      if (!Array.isArray(operations) || !operations.every(x => typeof x === 'string')) throw Error('INVALID_RELAY_RESPONSE');
    } catch (error) {
      if (error.code !== 'UNSUPPORTED_OPERATION' || error.detail?.status !== 400) throw error;
      operations = [];
    }
    cached = {at: Date.now(), operations};
    let temp;
    try {
      mkdirSync(home, {recursive: true, mode: 0o700});
      temp = file + '.' + process.pid + '.' + randomBytes(4).toString('hex');
      writeFileSync(temp, JSON.stringify(cached), {mode: 0o600, flag: 'wx'});
      renameSync(temp, file);
    } catch {} finally { if (temp) try { rmSync(temp, {force: true}); } catch {} }
  }
  capabilities.set(file, cached);
  return cached.operations.includes(operation);
}

export function compute(platform, operation, inputs) {
  const body = JSON.stringify({ version: 1, platform, operation, inputs }, function (key, value) {
    const raw = this[key];
    return raw instanceof Uint8Array ? { $bytes: Buffer.from(raw).toString('base64') } : value;
  });
  const response = spawnSync(process.execPath, [fileURLToPath(new URL('./relay-request.mjs', import.meta.url))], {
    input: body, encoding: 'utf8', timeout: 85000, maxBuffer: 1024 * 1024,
    // 不继承调试预加载器，避免把签名输入写入平台请求诊断。
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key !== 'NODE_OPTIONS')),
  });
  let value;
  try { value = JSON.parse(response.stdout); } catch { /* 统一为无敏感正文的错误 */ }
  if (response.error || response.status !== 0 || value?.success !== true) {
    const error = new Error('签名服务不可用，请检查 Relay 配置或服务状态；不要改为本地计算');
    error.code = value?.error || 'SIGN_UNAVAILABLE';
    error.detail = { source: 'relay', platform, operation, ...(value?.http_status ? { status: value.http_status } : {}),
      ...(value?.retry_after_seconds ? { retry_after_seconds: value.retry_after_seconds } : {}),
      ...(response.error ? { reason: response.error.code === 'ETIMEDOUT' ? 'timeout' : 'spawn' } : value?.reason ? { reason: value.reason } : {}) };
    throw error;
  }
  return JSON.parse(JSON.stringify(value.data), (_key, item) => item && typeof item === 'object' && Object.keys(item).length === 1
    && typeof item.$bytes === 'string' ? Buffer.from(item.$bytes, 'base64') : item);
}

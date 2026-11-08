import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export function compute(platform, operation, inputs) {
  const body = JSON.stringify({ version: 1, platform, operation, inputs }, function (key, value) {
    const raw = this[key];
    return raw instanceof Uint8Array ? { $bytes: Buffer.from(raw).toString('base64') } : value;
  });
  const response = spawnSync(process.execPath, [fileURLToPath(new URL('./relay-request.mjs', import.meta.url))], {
    input: body, encoding: 'utf8', timeout: 40000, maxBuffer: 1024 * 1024,
    // 不继承调试预加载器，避免把签名输入写入平台请求诊断。
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key !== 'NODE_OPTIONS')),
  });
  let value;
  try { value = JSON.parse(response.stdout); } catch { /* 统一为无敏感正文的错误 */ }
  if (response.error || response.status !== 0 || value?.success !== true) {
    const error = new Error('签名服务不可用，请检查 Relay 配置或服务状态；不要改为本地计算');
    error.code = value?.error || 'SIGN_UNAVAILABLE';
    error.detail = { source: 'relay', platform, operation, ...(value?.http_status ? { status: value.http_status } : {}) };
    throw error;
  }
  return JSON.parse(JSON.stringify(value.data), (_key, item) => item && typeof item === 'object' && Object.keys(item).length === 1
    && typeof item.$bytes === 'string' ? Buffer.from(item.$bytes, 'base64') : item);
}

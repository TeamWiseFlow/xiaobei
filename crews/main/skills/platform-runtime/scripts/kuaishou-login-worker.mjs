import { runBackend, atomicJson } from './backend.mjs';
import { join } from 'node:path';
const [account, home] = process.argv.slice(2);
try {
  const result = await runBackend('kuaishou', ['auth', 'login', '--method', 'qrcode', '--account', account], { home, timeout: 210000 });
  await atomicJson(join(home, 'result.json'), result);
} catch (error) {
  await atomicJson(join(home, 'result.json'), { ok: false, error: error.code || 'ERROR' });
}

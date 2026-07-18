// weixin-qr.mjs — 容器内自动出 weixin 登录二维码 + 轮询扫码状态 + 写绑定态
//
// channels login 命令内部用 @inquirer/prompts 做 TTY 交互（"Install Weixin plugin?"），
// 容器非 TTY 环境下挂死。此脚本直接调 weixin 插件的 startWeixinLoginWithQr() + displayQRCode() +
// waitForWeixinLogin()，不经 CLI 命令层，绕开 prompt 出码 + 轮询扫码 + 写绑定态。
//
// 已绑定（存在 channels/openclaw-weixin.json）时由 entrypoint 跳过，不跑此脚本。
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { readdirSync, existsSync } from 'node:fs';

const OPENCLAW_HOME = '/root/.openclaw';
const projectsDir = `${OPENCLAW_HOME}/npm/projects`;

// weixin 插件装在 ~/.openclaw/npm/projects/<hash>/node_modules/@tencent-weixin/openclaw-weixin/
// projects 目录名含哈希，动态扫描
let weixinDir = null;
try {
  for (const name of readdirSync(projectsDir)) {
    if (name.startsWith('tencent-weixin-openclaw-weixin-')) {
      weixinDir = path.join(projectsDir, name, 'node_modules/@tencent-weixin/openclaw-weixin');
      break;
    }
  }
} catch {}

if (!weixinDir) {
  console.error('[weixin-qr] 未找到 openclaw-weixin 插件目录，跳过二维码生成');
  process.exit(0);
}

const qrMod = await import(pathToFileURL(path.join(weixinDir, 'dist/src/auth/login-qr.js')).href);

// ── 1. 出二维码 ────────────────────────────────────────────────────────────
const startRes = await qrMod.startWeixinLoginWithQr({});
console.log(startRes.message);
if (!startRes.qrcodeUrl) {
  console.error('[weixin-qr] 二维码生成失败:', startRes.message || '未知错误');
  process.exit(0);
}
await qrMod.displayQRCode(startRes.qrcodeUrl);
console.log('');
console.log('扫码确认后绑定态写 /root/.openclaw/channels/，跨 restart 持久化。');

// ── 2. 轮询扫码状态（最长 8 分钟），扫码成功后写绑定态 ───────────────────
// waitForWeixinLogin 内部长轮询 ilink API，扫码确认后写 channels/openclaw-weixin.json
console.log('[weixin-qr] 等待扫码确认...');
const waitRes = await qrMod.waitForWeixinLogin({
  sessionKey: startRes.sessionKey,
  timeoutMs: 480_000,
});
if (waitRes.connected) {
  console.log('[weixin-qr] ✅ weixin 账号绑定成功，下次启动跳过二维码');
} else {
  console.log('[weixin-qr] ⚠️ 轮询超时或未确认:', waitRes.message || '未知');
  console.log('[weixin-qr]   下次启动仍会出二维码');
}

// 绑定态是否真写了——兜底检查
if (existsSync(`${OPENCLAW_HOME}/channels/openclaw-weixin.json`)) {
  console.log('[weixin-qr] 绑定态文件已写:', `${OPENCLAW_HOME}/channels/openclaw-weixin.json`);
}

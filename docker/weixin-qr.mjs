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
// weixin-cli 装插件时走的是 ${OPENCLAW_HOME}/.openclaw/npm/projects（嵌套路径，
// cli 内部把 OPENCLAW_HOME 又拼了一层 .openclaw）。扫两层兼容 cli 实际行为与文档路径。
const projectsDirs = [
  `${OPENCLAW_HOME}/.openclaw/npm/projects`,  // cli 实际装的位置（build 日志已证实）
  `${OPENCLAW_HOME}/npm/projects`,              // 文档/历史路径，兜底
];

// weixin 插件装在 projects/<hash>/node_modules/@tencent-weixin/openclaw-weixin/
// projects 目录名含哈希，动态扫描
let weixinDir = null;
try {
  for (const dir of projectsDirs) {
    for (const name of readdirSync(dir)) {
      if (name.startsWith('tencent-weixin-openclaw-weixin-')) {
        weixinDir = path.join(dir, name, 'node_modules/@tencent-weixin/openclaw-weixin');
        break;
      }
    }
    if (weixinDir) break;
  }
} catch {}

if (!weixinDir) {
  console.error('[weixin-qr] 未找到 openclaw-weixin 插件目录，跳过二维码生成');
  process.exit(0);
}

const qrMod = await import(pathToFileURL(path.join(weixinDir, 'dist/src/auth/login-qr.js')).href);
const accountsMod = await import(pathToFileURL(path.join(weixinDir, 'dist/src/auth/accounts.js')).href);
// normalizeAccountId 来自 openclaw plugin-sdk,把 raw ilink_bot_id(e.g. "hex@im.bot")
// 转成 filesystem-safe key(e.g. "hex-im-bot"),与 channel.js 的持久化逻辑一致
// normalizeAccountId 来自 openclaw plugin-sdk,把 raw ilink_bot_id(e.g. "hex@im.bot")
// 转成 filesystem-safe key(e.g. "hex-im-bot"),与 channel.js 的持久化逻辑一致。
// channel.js import "openclaw/plugin-sdk/account-id" 由 pnpm resolver 解析;容器里裸 node
// import 走绝对路径,兜底按真实装位置/dist/plugin-sdk/account-id.js。
let normalizeAccountId;
for (const p of [
  '/opt/xiaobei/openclaw/dist/plugin-sdk/account-id.js',
  '/opt/xiaobei/openclaw/dist/extensions/node_modules/openclaw/plugin-sdk/account-id.js',
]) {
  try {
    ({ normalizeAccountId } = await import(pathToFileURL(p).href));
    if (normalizeAccountId) break;
  } catch {}
}
if (!normalizeAccountId) {
  console.error('[weixin-qr] ⚠️ normalizeAccountId 未找到,绑定态将用 raw accountId 写盘');
  normalizeAccountId = (id) => id;
}

// waitForWeixinLogin 内部硬编码 MAX_QR_REFRESH_COUNT=3,二维码每 ~2 分钟过期,
// 3 次后整个 session 就放弃。容器场景用户扫码可能慢,故外层循环重起 session
// 直到绑定成功或总超时(15 分钟)到。每轮起新 session 会重新出二维码。
const TOTAL_TIMEOUT_MS = 60 * 60_000;  // 60 分钟:用户扫码慢或 session 多次失效也不放弃
const SESSION_TIMEOUT_MS = 480_000;  // 单轮 session 上限(8 分钟,略大于 3×过期窗口)
const totalDeadline = Date.now() + TOTAL_TIMEOUT_MS;

let bound = false;
let attempt = 0;
while (Date.now() < totalDeadline && !bound) {
  attempt += 1;
  if (attempt > 1) console.log(`\n[weixin-qr] 重出二维码(第 ${attempt} 次,session 失效)...`);

  // ── 1. 出二维码 ────────────────────────────────────────────────────────
  const startRes = await qrMod.startWeixinLoginWithQr({});
  console.log(startRes.message);
  if (!startRes.qrcodeUrl) {
    console.error('[weixin-qr] 二维码生成失败:', startRes.message || '未知错误');
    process.exit(0);
  }
  await qrMod.displayQRCode(startRes.qrcodeUrl);
  console.log('');
  console.log('扫码确认后绑定态写 /root/.openclaw/channels/,跨 restart 涣化。');

  // ── 2. 轮询扫码状态(本轮 session),扫码成功后写绑定态 ─────────────────
  console.log('[weixin-qr] 等待扫码确认...');
  const remaining = Math.max(totalDeadline - Date.now(), 1000);
  const sessionTimeout = Math.min(SESSION_TIMEOUT_MS, remaining);
  const waitRes = await qrMod.waitForWeixinLogin({
    sessionKey: startRes.sessionKey,
    timeoutMs: sessionTimeout,
  });
  if (waitRes.connected) {
    bound = true;
    console.log('[weixin-qr] ✅ weixin 账号绑定成功,下次启动跳过二维码');
    // ── 持久化绑定态(对齐 channel.js 的 auth.login 逻辑) ────────────────
    // waitForWeixinLogin 只返回 token/botToken,不落磁盘。channel.js 的 channel
    // 命令会在 connected 后调 saveWeixinAccount + registerWeixinAccountId 写
    // ${stateDir}/openclaw-weixin/accounts.json + accounts/{id}.json。容器场景
    // weixin-qr.mjs 直接跑不走 channel 命令,这里主动持久化,否则重启必重扫。
    if (waitRes.botToken && waitRes.accountId && normalizeAccountId && accountsMod.saveWeixinAccount) {
      try {
        const normalizedId = normalizeAccountId(waitRes.accountId);
        accountsMod.saveWeixinAccount(normalizedId, {
          token: waitRes.botToken,
          baseUrl: waitRes.baseUrl,
          userId: waitRes.userId,
        });
        accountsMod.registerWeixinAccountId(normalizedId);
        if (waitRes.userId && accountsMod.clearStaleAccountsForUserId) {
          accountsMod.clearStaleAccountsForUserId(normalizedId, waitRes.userId, () => {});
        }
        console.log(`[weixin-qr] 绑定态已持久化: accountId=${normalizedId}`);
      } catch (err) {
        console.log(`[weixin-qr] ⚠️ 保存账号数据失败: ${String(err)}`);
      }
    }
  } else {
    console.log(`[weixin-qr] ⚠️ 本轮轮询超时或未确认: ${waitRes.message || '未知'}`);
    // 检查是否其实已经写了绑定态(扫码成功但 waitRes 判定延迟的兜底)
    // 真实路径:${stateDir}/openclaw-weixin/accounts.json(stateDir=OPENCLAW_HOME 或嵌套 .openclaw/)
    if (existsSync(`${OPENCLAW_HOME}/openclaw-weixin/accounts.json`) ||
        existsSync(`${OPENCLAW_HOME}/.openclaw/openclaw-weixin/accounts.json`)) {
      bound = true;
      console.log('[weixin-qr] ✅ 检测到绑定态文件已写,视为绑定成功');
      break;
    }
    console.log('[weixin-qr] 重起 session 继续等扫码...');
  }
}

if (!bound) {
  console.log('[weixin-qr] ⚠️ 总超时已到,本轮未完成绑定。下次启动仍会出二维码');
}

// 绑定态是否真写了——兜底检查(真实路径:openclaw-weixin/accounts.json)
const rootBinding = `${OPENCLAW_HOME}/openclaw-weixin/accounts.json`;
const nestedBinding = `${OPENCLAW_HOME}/.openclaw/openclaw-weixin/accounts.json`;
if (existsSync(rootBinding)) {
  console.log('[weixin-qr] 绑定态文件已写(挂载卷根):', rootBinding);
} else if (existsSync(nestedBinding)) {
  console.log('[weixin-qr] 绑定态文件已写(嵌套层,entrypoint 会迁到挂载卷根):', nestedBinding);
}

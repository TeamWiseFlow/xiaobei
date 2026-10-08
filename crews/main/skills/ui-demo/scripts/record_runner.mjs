#!/usr/bin/env node
// record_runner.mjs — ui-demo 录制执行器。
//
// 起 camoufox 浏览器（默认无头）录制 demo-steps 文件定义的操作序列，
// 内置鼠标覆盖层 / 字幕条 / 平滑移动 / 慢速打字等 helper，产出 WebM。
//
// 用法：
//   ui-demo --steps <demo-steps.mjs> --output <demo.webm>
//           [--headed] [--viewport 1280x720]
//           [--base-url http://localhost:3000]
//           [--cookies cookies.json]
//
// demo-steps 文件契约（ESM，默认导出一个 async 函数）：
//   export default async function run(demo) {
//     const { page, baseURL, showSubtitle, moveAndClick, typeSlowly,
//             smoothScroll, pause, injectOverlays } = demo;
//     await page.goto(`${baseURL}/dashboard`);
//     await showSubtitle('Step 1 - 概览');
//     ...
//   }
//
// 退出码：
//   0 = 成功
//   1 = 参数错误 / 步骤执行出错（已录到的部分仍会保存）
//   3 = Node 依赖或 camoufox 浏览器未安装（按错误提示修复）

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

function die(msg, code = 1) {
  console.error(JSON.stringify({ ok: false, error: msg }));
  process.exit(code);
}

function parseArgs(argv) {
  const opts = {
    steps: null,
    output: null,
    headed: false,
    width: 1280,
    height: 720,
    baseURL: process.env.BASE_URL || "",
    cookies: null,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    switch (a) {
      case "--steps": opts.steps = argv[++i]; break;
      case "--output": opts.output = argv[++i]; break;
      case "--headed": opts.headed = true; break;
      case "--viewport": {
        const m = /^(\d+)x(\d+)$/.exec(argv[++i] || "");
        if (!m) die("--viewport 需要形如 1280x720 的值");
        opts.width = Number(m[1]);
        opts.height = Number(m[2]);
        break;
      }
      case "--base-url": opts.baseURL = argv[++i]; break;
      case "--cookies": opts.cookies = argv[++i]; break;
      default: die(`未知参数: ${a}（用法见脚本头部注释）`);
    }
  }
  if (!opts.steps || !opts.output) die("--steps 与 --output 都是必填");
  if (!fs.existsSync(opts.steps)) die(`steps 文件不存在: ${opts.steps}`);
  if (opts.cookies && !fs.existsSync(opts.cookies)) die(`cookies 文件不存在: ${opts.cookies}`);
  return opts;
}

// ── 页面覆盖层（光标 + 字幕条），幂等注入 ────────────────────────────────
async function injectOverlays(page) {
  await page.evaluate(() => {
    if (!document.getElementById("demo-cursor")) {
      const cursor = document.createElement("div");
      cursor.id = "demo-cursor";
      cursor.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M5 3L19 12L12 13L9 20L5 3Z" fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/>
      </svg>`;
      cursor.style.cssText = `
        position: fixed; z-index: 999999; pointer-events: none;
        width: 24px; height: 24px; transition: left 0.1s, top 0.1s;
        filter: drop-shadow(1px 1px 2px rgba(0,0,0,0.3));
      `;
      cursor.style.left = "0px";
      cursor.style.top = "0px";
      document.body.appendChild(cursor);
      document.addEventListener("mousemove", (e) => {
        cursor.style.left = e.clientX + "px";
        cursor.style.top = e.clientY + "px";
      });
    }
    if (!document.getElementById("demo-subtitle")) {
      const bar = document.createElement("div");
      bar.id = "demo-subtitle";
      bar.style.cssText = `
        position: fixed; bottom: 0; left: 0; right: 0; z-index: 999998;
        text-align: center; padding: 12px 24px;
        background: rgba(0,0,0,0.75); color: white;
        font-family: -apple-system, "Segoe UI", sans-serif;
        font-size: 16px; font-weight: 500; letter-spacing: 0.3px;
        transition: opacity 0.3s; pointer-events: none;
      `;
      bar.textContent = "";
      bar.style.opacity = "0";
      document.body.appendChild(bar);
    }
  }).catch(() => {});
}

function makeHelpers(page, baseURL) {
  const pause = (ms) => page.waitForTimeout(ms);

  async function showSubtitle(text) {
    await page.evaluate((t) => {
      const bar = document.getElementById("demo-subtitle");
      if (!bar) return;
      bar.textContent = t;
      bar.style.opacity = t ? "1" : "0";
    }, text).catch(() => {});
    if (text) await pause(800);
  }

  async function moveAndClick(locator, label, opts = {}) {
    const { postClickDelay = 800, ...clickOpts } = opts;
    const el = typeof locator === "string" ? page.locator(locator).first() : locator;
    try {
      await el.scrollIntoViewIfNeeded();
      await pause(300);
      const box = await el.boundingBox();
      if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 10 });
        await pause(400);
      }
      await el.click(clickOpts);
    } catch (e) {
      console.error(`WARNING: moveAndClick failed on "${label}": ${e.message}`);
      return false;
    }
    await pause(postClickDelay);
    return true;
  }

  async function typeSlowly(locator, text, label, charDelay = 35) {
    const el = typeof locator === "string" ? page.locator(locator).first() : locator;
    await moveAndClick(el, label);
    await el.fill("");
    await el.pressSequentially(text, { delay: charDelay });
    await pause(500);
    return true;
  }

  async function smoothScroll(top) {
    await page.evaluate((t) => window.scrollTo({ top: t, behavior: "smooth" }), top);
    await pause(1500);
  }

  return {
    page,
    baseURL,
    pause,
    showSubtitle,
    moveAndClick,
    typeSlowly,
    smoothScroll,
    injectOverlays: () => injectOverlays(page),
  };
}

// ── 主流程 ──────────────────────────────────────────────────────────────
const opts = parseArgs(process.argv.slice(2));

let Camoufox;
try {
  ({ Camoufox } = await import("camoufox-js"));
  await import("playwright-core");
} catch (e) {
  if (["ERR_MODULE_NOT_FOUND", "MODULE_NOT_FOUND"].includes(e.code)) {
    const skillDir = path.resolve(fileURLToPath(new URL("../", import.meta.url)));
    const quotedDir = "'" + skillDir.replaceAll("'", "'\\''") + "'";
    die(`ui-demo Node 依赖缺失（camoufox-js / playwright-core）。请重跑统一安装流程；单独修复可运行: npm install --prefix ${quotedDir} --omit=dev --no-audit --no-fund（${e.message}）`, 3);
  }
  die(`ui-demo Node 依赖加载失败: ${e.message}`, 3);
}

const outputAbs = path.resolve(opts.output);
fs.mkdirSync(path.dirname(outputAbs), { recursive: true });
const tmpVideoDir = fs.mkdtempSync(path.join(path.dirname(outputAbs), ".rec-"));

let stepsFn;
try {
  const mod = await import(pathToFileURL(path.resolve(opts.steps)).href);
  stepsFn = mod.default;
  if (typeof stepsFn !== "function") die("steps 文件必须默认导出一个 async 函数");
} catch (e) {
  die(`steps 文件加载失败: ${e.message}`);
}

let browser;
try {
  browser = await Camoufox({
    headless: !opts.headed,
    window: [opts.width, opts.height],
  });
} catch (e) {
  const msg = String(e.message || e);
  if (/not found|install/i.test(msg)) {
    die(`camoufox 浏览器未安装，请先运行: camoufox-cli install（${msg}）`, 3);
  }
  die(`浏览器启动失败: ${msg}`);
}

// camoufox 指纹会强制 outer window 尺寸（含模拟的浏览器 chrome 高度），
// context viewport 选项压不过它——先实测内容区，再按实测尺寸建录制画布，
// 否则成片底部会出现灰色填充带。
const probeCtx = await browser.newContext();
const probePage = await probeCtx.newPage();
const measured = await probePage.evaluate(() => ({ w: innerWidth, h: innerHeight }));
await probeCtx.close();
const recW = measured.w - (measured.w % 2);
const recH = measured.h - (measured.h % 2);

const context = await browser.newContext({
  viewport: { width: recW, height: recH },
  recordVideo: { dir: tmpVideoDir, size: { width: recW, height: recH } },
});

if (opts.cookies) {
  const raw = JSON.parse(fs.readFileSync(opts.cookies, "utf-8"));
  const cookies = Array.isArray(raw) ? raw : raw.cookies;
  if (Array.isArray(cookies) && cookies.length > 0) await context.addCookies(cookies);
}

const page = await context.newPage();
// 每次整页导航后自动重注入覆盖层（导航会销毁 DOM）
page.on("load", () => injectOverlays(page));

let stepError = null;
try {
  await injectOverlays(page);
  await stepsFn(makeHelpers(page, opts.baseURL));
  // 收尾停留，避免最后一个动作被掐掉
  await page.waitForTimeout(1500);
} catch (e) {
  stepError = String(e.message || e);
  console.error(`DEMO ERROR: ${stepError}`);
}

// 关 context 落视频，再拷到固定输出名
const video = page.video();
await context.close();
let saved = false;
if (video) {
  try {
    const src = await video.path();
    fs.copyFileSync(src, outputAbs);
    saved = true;
  } catch (e) {
    console.error(`WARNING: 视频保存失败: ${e.message}`);
  }
}
fs.rmSync(tmpVideoDir, { recursive: true, force: true });
await browser.close();

const report = {
  ok: !stepError && saved,
  output: saved ? outputAbs : null,
  size_bytes: saved ? fs.statSync(outputAbs).size : 0,
  headed: opts.headed,
  window: `${opts.width}x${opts.height}`,
  resolution: `${recW}x${recH}`,
};
if (stepError) report.error = `步骤执行出错（已录到的部分已保存）: ${stepError}`;
console.log(JSON.stringify(report, null, 2));
process.exit(report.ok ? 0 : 1);

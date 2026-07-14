/** Command implementations for the daemon. */

import type { Locator } from "playwright-core";
import { BrowserManager } from "./browser.js";
import { okResponse, errorResponse, type Response } from "./protocol.js";

type Handler = (manager: BrowserManager, cmdId: string, params: Record<string, unknown>) => Promise<Response>;

function resolveRef(manager: BrowserManager, refStr: string): Locator {
  const entry = manager.refs.resolve(refStr);
  if (!entry) {
    throw new Error(`Ref @${refStr.replace(/^@/, "")} not found. Run 'camoufox-cli snapshot' to refresh refs.`);
  }
  const page = manager.getPage();
  const locator = page.getByRole(entry.role as any, { name: entry.name, exact: true });
  return locator.nth(entry.nth);
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

const cmdOpen: Handler = async (manager, cmdId, params) => {
  const url = params.url as string;
  if (!url) return errorResponse(cmdId, "Missing 'url' parameter");

  if (!manager.isRunning) {
    await manager.launch(params.headless as boolean ?? true);
  }

  try {
    const page = manager.getPage();
    await page.goto(url, { waitUntil: "domcontentloaded" });
  } catch (e: any) {
    if (String(e).includes("has been closed")) {
      await manager.close();
      await manager.launch(params.headless as boolean ?? true);
      const page = manager.getPage();
      await page.goto(url, { waitUntil: "domcontentloaded" });
    } else {
      throw e;
    }
  }

  const page = manager.getPage();
  manager.pushHistory(page.url());
  return okResponse(cmdId, { url: page.url(), title: await page.title() });
};

const cmdBack: Handler = async (manager, cmdId) => {
  const url = await manager.goBack();
  if (url === null) return errorResponse(cmdId, "No previous page in history");
  const page = manager.getPage();
  return okResponse(cmdId, { url: page.url(), title: await page.title() });
};

const cmdForward: Handler = async (manager, cmdId) => {
  const url = await manager.goForward();
  if (url === null) return errorResponse(cmdId, "No next page in history");
  const page = manager.getPage();
  return okResponse(cmdId, { url: page.url(), title: await page.title() });
};

const cmdReload: Handler = async (manager, cmdId) => {
  const page = manager.getPage();
  await page.goto(page.url(), { waitUntil: "domcontentloaded" });
  return okResponse(cmdId);
};

const cmdUrl: Handler = async (manager, cmdId) => {
  return okResponse(cmdId, { url: manager.getPage().url() });
};

const cmdTitle: Handler = async (manager, cmdId) => {
  return okResponse(cmdId, { title: await manager.getPage().title() });
};

const cmdClose: Handler = async (manager, cmdId) => {
  await manager.close();
  return okResponse(cmdId, { closed: true });
};

// ---------------------------------------------------------------------------
// Snapshot
// ---------------------------------------------------------------------------

const cmdSnapshot: Handler = async (manager, cmdId, params) => {
  const page = manager.getPage();
  const interactive = params.interactive as boolean ?? false;
  const selector = params.selector as string | undefined;

  const target = selector ? page.locator(selector) : page.locator("body");
  const ariaText = await target.ariaSnapshot();
  const annotated = manager.refs.buildFromSnapshot(ariaText, interactive);
  return okResponse(cmdId, { snapshot: annotated });
};

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

const cmdClick: Handler = async (manager, cmdId, params) => {
  const refStr = params.ref as string;
  if (!refStr) return errorResponse(cmdId, "Missing 'ref' parameter");
  const locator = resolveRef(manager, refStr);
  const page = manager.getPage();
  const urlBefore = page.url();

  await locator.click();

  const urlAfter = page.url();
  if (urlAfter !== urlBefore) manager.pushHistory(urlAfter);
  return okResponse(cmdId);
};

const cmdFill: Handler = async (manager, cmdId, params) => {
  const refStr = params.ref as string;
  const text = params.text as string ?? "";
  if (!refStr) return errorResponse(cmdId, "Missing 'ref' parameter");
  await resolveRef(manager, refStr).fill(text);
  return okResponse(cmdId);
};

const cmdType: Handler = async (manager, cmdId, params) => {
  const refStr = params.ref as string;
  const text = params.text as string ?? "";
  if (!refStr) return errorResponse(cmdId, "Missing 'ref' parameter");
  await resolveRef(manager, refStr).pressSequentially(text);
  return okResponse(cmdId);
};

const cmdSelect: Handler = async (manager, cmdId, params) => {
  const refStr = params.ref as string;
  const value = params.value as string ?? "";
  if (!refStr) return errorResponse(cmdId, "Missing 'ref' parameter");
  await resolveRef(manager, refStr).selectOption({ label: value });
  return okResponse(cmdId);
};

const cmdCheck: Handler = async (manager, cmdId, params) => {
  const refStr = params.ref as string;
  if (!refStr) return errorResponse(cmdId, "Missing 'ref' parameter");
  const locator = resolveRef(manager, refStr);
  if (await locator.isChecked()) {
    await locator.uncheck({ force: true });
  } else {
    await locator.check({ force: true });
  }
  return okResponse(cmdId);
};

const cmdHover: Handler = async (manager, cmdId, params) => {
  const refStr = params.ref as string;
  if (!refStr) return errorResponse(cmdId, "Missing 'ref' parameter");
  await resolveRef(manager, refStr).hover({ force: true });
  return okResponse(cmdId);
};

const cmdPress: Handler = async (manager, cmdId, params) => {
  const key = params.key as string;
  if (!key) return errorResponse(cmdId, "Missing 'key' parameter");
  await manager.getPage().keyboard.press(key);
  return okResponse(cmdId);
};

// ---------------------------------------------------------------------------
// Data extraction
// ---------------------------------------------------------------------------

const cmdText: Handler = async (manager, cmdId, params) => {
  const target = params.target as string;
  if (!target) return errorResponse(cmdId, "Missing 'target' parameter");

  let text: string;
  if (target.startsWith("@")) {
    text = (await resolveRef(manager, target).textContent()) || "";
  } else {
    text = (await manager.getPage().locator(target).textContent()) || "";
  }
  return okResponse(cmdId, { text });
};

const cmdEval: Handler = async (manager, cmdId, params) => {
  const expression = params.expression as string;
  if (!expression) return errorResponse(cmdId, "Missing 'expression' parameter");
  const result = await manager.getPage().evaluate(expression);
  return okResponse(cmdId, { result });
};

const cmdScreenshot: Handler = async (manager, cmdId, params) => {
  const page = manager.getPage();
  const path = params.path as string | undefined;
  const fullPage = params.full_page as boolean ?? false;

  if (path) {
    await page.screenshot({ path, fullPage });
    return okResponse(cmdId, { path });
  } else {
    const buf = await page.screenshot({ fullPage });
    return okResponse(cmdId, { base64: buf.toString("base64") });
  }
};

const cmdPdf: Handler = async (manager, cmdId, params) => {
  const filePath = params.path as string;
  if (!filePath) return errorResponse(cmdId, "Missing 'path' parameter");

  const page = manager.getPage();
  const buf = await page.screenshot({ fullPage: true });

  const { PDFDocument } = await import("pdf-lib");
  const pdfDoc = await PDFDocument.create();
  const pngImage = await pdfDoc.embedPng(buf);
  const pdfPage = pdfDoc.addPage([pngImage.width, pngImage.height]);
  pdfPage.drawImage(pngImage, {
    x: 0,
    y: 0,
    width: pngImage.width,
    height: pngImage.height,
  });

  const pdfBytes = await pdfDoc.save();
  writeFileSync(filePath, Buffer.from(pdfBytes));

  return okResponse(cmdId, { path: filePath });
};

// ---------------------------------------------------------------------------
// File upload
// ---------------------------------------------------------------------------

const cmdUpload: Handler = async (manager, cmdId, params) => {
  const paths = (params.paths as string[] | undefined) ?? [];
  if (paths.length === 0) return errorResponse(cmdId, "Missing 'paths' parameter");

  // Fail fast with a clear message before touching the browser.
  for (const p of paths) {
    if (!existsSync(p)) return errorResponse(cmdId, `File not found: ${p}`);
  }

  const page = manager.getPage();
  let locator: Locator;
  if (typeof params.ref === "string") {
    locator = resolveRef(manager, params.ref);
  } else if (typeof params.selector === "string") {
    locator = page.locator(params.selector);
  } else {
    return errorResponse(cmdId, "Missing 'ref' or 'selector' parameter");
  }

  await locator.setInputFiles(paths);
  return okResponse(cmdId, { count: paths.length, paths });
};

// ---------------------------------------------------------------------------
// Scroll & Wait
// ---------------------------------------------------------------------------

const cmdScroll: Handler = async (manager, cmdId, params) => {
  const direction = params.direction as string ?? "down";
  let amount = Number(params.amount ?? 500);
  if (direction === "up") amount = -amount;
  await manager.getPage().evaluate(`window.scrollBy(0, ${amount})`);
  return okResponse(cmdId);
};

const cmdWait: Handler = async (manager, cmdId, params) => {
  const page = manager.getPage();

  if ("ms" in params) {
    await page.waitForTimeout(Number(params.ms));
  } else if ("ref" in params) {
    await resolveRef(manager, params.ref as string).waitFor();
  } else if ("selector" in params) {
    await page.waitForSelector(params.selector as string);
  } else if ("url" in params) {
    await page.waitForURL(params.url as string);
  } else {
    return errorResponse(cmdId, "wait requires ms, ref, selector, or url parameter");
  }
  return okResponse(cmdId);
};

// ---------------------------------------------------------------------------
// Tab management
// ---------------------------------------------------------------------------

const cmdTabs: Handler = async (manager, cmdId) => {
  const tabs = await manager.getTabsAsync();
  return okResponse(cmdId, { tabs: tabs as any });
};

const cmdSwitch: Handler = async (manager, cmdId, params) => {
  if (params.index === undefined) return errorResponse(cmdId, "Missing 'index' parameter");
  const page = await manager.switchToTab(Number(params.index));
  return okResponse(cmdId, { url: page.url(), title: await page.title() });
};

const cmdCloseTab: Handler = async (manager, cmdId) => {
  await manager.closeCurrentTab();
  const page = manager.getPage();
  return okResponse(cmdId, { url: page.url(), title: await page.title() });
};

// ---------------------------------------------------------------------------
// Cookies
// ---------------------------------------------------------------------------

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { readIdentitySummary } from "./identity.js";

const cmdCookies: Handler = async (manager, cmdId, params) => {
  const ctx = manager.getContext();
  const op = (params.op as string) || "list";

  if (op === "list") {
    const cookies = await ctx.cookies();
    return okResponse(cmdId, { cookies: cookies as any });
  } else if (op === "export") {
    const path = params.path as string;
    if (!path) return errorResponse(cmdId, "Missing 'path' parameter for export");
    const cookies = await ctx.cookies();
    writeFileSync(path, JSON.stringify(cookies, null, 2));
    return okResponse(cmdId, { path, count: cookies.length });
  } else if (op === "import") {
    const path = params.path as string;
    if (!path) return errorResponse(cmdId, "Missing 'path' parameter for import");
    const cookies = JSON.parse(readFileSync(path, "utf-8"));
    await ctx.addCookies(cookies);
    return okResponse(cmdId, { count: cookies.length });
  } else {
    return errorResponse(cmdId, `Unknown cookies op: ${op}`);
  }
};

// ---------------------------------------------------------------------------
// Identity export (UA + fingerprint summary; symmetric with `cookies export`)
// ---------------------------------------------------------------------------

const cmdIdentity: Handler = async (manager, cmdId, params) => {
  const op = (params.op as string) || "show";
  if (op !== "show" && op !== "export") {
    return errorResponse(cmdId, `Unknown identity op: ${op}`);
  }

  // navigator.* must be read from a live page; Camoufox spoofs UA from the
  // frozen fingerprint, so this is the effective UA sites see.
  const page = manager.getPage();
  const nav = await page.evaluate(() => ({
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    language: navigator.language,
    languages: navigator.languages,
    viewport: { width: window.innerWidth, height: window.innerHeight },
  }));

  const persistentDir = manager.persistentDir;
  const summary: Record<string, unknown> = {
    ...nav,
    persistent: persistentDir,
    identity: persistentDir ? readIdentitySummary(persistentDir) : null,
    exportedAt: new Date().toISOString(),
  };

  if (op === "export") {
    const path = params.path as string;
    if (!path) return errorResponse(cmdId, "Missing 'path' parameter for export");
    writeFileSync(path, JSON.stringify(summary, null, 2));
    return okResponse(cmdId, { path });
  }
  return okResponse(cmdId, summary);
};

// ---------------------------------------------------------------------------
// Handler dispatch table
// ---------------------------------------------------------------------------

const HANDLERS: Record<string, Handler> = {
  open: cmdOpen,
  back: cmdBack,
  forward: cmdForward,
  reload: cmdReload,
  url: cmdUrl,
  title: cmdTitle,
  close: cmdClose,
  snapshot: cmdSnapshot,
  click: cmdClick,
  fill: cmdFill,
  type: cmdType,
  select: cmdSelect,
  check: cmdCheck,
  hover: cmdHover,
  press: cmdPress,
  text: cmdText,
  eval: cmdEval,
  screenshot: cmdScreenshot,
  pdf: cmdPdf,
  scroll: cmdScroll,
  wait: cmdWait,
  tabs: cmdTabs,
  switch: cmdSwitch,
  "close-tab": cmdCloseTab,
  cookies: cmdCookies,
  upload: cmdUpload,
  identity: cmdIdentity,
};

export async function execute(manager: BrowserManager, command: Record<string, unknown>): Promise<Response> {
  const cmdId = (command.id as string) || "?";
  const action = (command.action as string) || "";
  const params = (command.params as Record<string, unknown>) || {};

  try {
    const handler = HANDLERS[action];
    if (!handler) return errorResponse(cmdId, `Unknown action: ${action}`);
    return await handler(manager, cmdId, params);
  } catch (e: any) {
    return errorResponse(cmdId, String(e.message || e));
  }
}

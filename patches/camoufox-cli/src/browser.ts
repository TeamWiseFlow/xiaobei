/** Browser manager: launches and manages Camoufox instance. */

import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { Camoufox, launchOptions } from "camoufox-js";
import { firefox, type Browser, type BrowserContext, type Page } from "playwright-core";
import { ensureMmdb } from "./install.js";
import { loadOrCreate, toLaunchOptions } from "./identity.js";
import { parseProxySettings } from "./proxy.js";
import { RefRegistry } from "./refs.js";

const MAX_HISTORY = 200;

function ensureBrowserInstalled(): void {
  try {
    execFileSync("npx", ["camoufox-js", "path"], { stdio: "pipe" });
  } catch {
    throw new Error(
      "Browser not found. Run `camoufox-cli install` to download it."
    );
  }
}

export class BrowserManager {
  refs = new RefRegistry();
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;
  private page: Page | null = null;
  private persistent: string | null;
  private proxy: string | null;
  private geoip: boolean;
  private locale: string | null;
  private history: string[] = [];
  private historyIndex = -1;

  constructor(persistent: string | null = null, proxy: string | null = null, geoip: boolean = true, locale: string | null = null) {
    this.persistent = persistent;
    this.proxy = proxy;
    this.geoip = geoip;
    this.locale = locale;
  }

  async launch(headless: boolean = true): Promise<void> {
    if (this.browser || this.context) return;

    ensureBrowserInstalled();

    if (this.proxy && this.geoip) {
      // Geoip resolution lazily downloads the GeoIP db via the rate-limited
      // GitHub API; fetch it through the resilient path first.
      await ensureMmdb();
    }

    const launchOpts: Record<string, unknown> = { headless };
    let proxySettings: { server: string; username?: string; password?: string } | null = null;
    if (this.proxy) {
      const settings = parseProxySettings(this.proxy);
      proxySettings = settings.proxy;
      launchOpts.proxy = settings.proxy;
      if (this.geoip) {
        launchOpts.geoip = true;
      }
    }

    if (this.persistent) {
      // Persistent identity: freeze fingerprint/OS on first launch; reload
      // it on subsequent launches. CLI-passed locale / proxy-derived geo
      // overwrite the stored values so the file tracks current intent.
      mkdirSync(this.persistent, { recursive: true });
      const identity = await loadOrCreate(
        this.persistent,
        this.locale,
        this.proxy,
        this.geoip,
      );
      Object.assign(launchOpts, toLaunchOptions(identity));
      const opts = await launchOptions(launchOpts);
      this.context = await firefox.launchPersistentContext(this.persistent, opts);
      const pages = this.context.pages();
      this.page = pages[0] || await this.context.newPage();
    } else {
      if (this.locale) {
        // Non-persistent path: locale is a one-shot override, no identity file.
        const locales = this.locale.split(",").map((s) => s.trim()).filter(Boolean);
        if (locales.length > 0) {
          launchOpts.locale = locales.length > 1 ? locales : locales[0];
        }
      }
      this.browser = await Camoufox(launchOpts) as Browser;
      this.page = await this.browser.newPage();
      this.context = this.page.context();
    }

    // Workaround: Playwright's Firefox (Juggler) fails proxy auth on HTTPS
    // CONNECT tunnels, raising NS_ERROR_PROXY_AUTHENTICATION_FAILED.
    // Inject Basic auth as an extra HTTP header like WebKit/Chromium do.
    if (proxySettings?.username) {
      const creds = `${proxySettings.username}:${proxySettings.password ?? ""}`;
      const token = Buffer.from(creds, "utf8").toString("base64");
      await this.context.setExtraHTTPHeaders({
        "Proxy-Authorization": `Basic ${token}`,
      });
    }
  }

  getPage(): Page {
    if (!this.page) throw new Error("Browser not launched. Send 'open' command first.");
    return this.page;
  }

  /** Persistent profile dir in use, or null for a non-persistent session. */
  get persistentDir(): string | null {
    return this.persistent;
  }

  getContext(): BrowserContext {
    if (!this.context) throw new Error("Browser not launched. Send 'open' command first.");
    return this.context;
  }

  async getTabsAsync(): Promise<{ index: number; url: string; title: string; active: boolean }[]> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    const tabs = [];
    for (let i = 0; i < pages.length; i++) {
      tabs.push({
        index: i,
        url: pages[i].url(),
        title: await pages[i].title(),
        active: pages[i] === this.page,
      });
    }
    return tabs;
  }

  async switchToTab(index: number): Promise<Page> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    if (index < 0 || index >= pages.length) {
      throw new RangeError(`Tab index ${index} out of range (0-${pages.length - 1})`);
    }
    this.page = pages[index];
    await this.page.bringToFront();
    return this.page;
  }

  async closeCurrentTab(): Promise<void> {
    const ctx = this.getContext();
    const pages = ctx.pages();
    if (pages.length <= 1) {
      throw new Error("Cannot close the last tab. Use 'close' to shut down the browser.");
    }
    const current = this.page!;
    const idx = pages.indexOf(current);
    const newIdx = idx > 0 ? idx - 1 : 1;
    this.page = pages[newIdx];
    await this.page.bringToFront();
    await current.close();
  }

  pushHistory(url: string): void {
    this.history = this.history.slice(0, this.historyIndex + 1);
    this.history.push(url);
    if (this.history.length > MAX_HISTORY) {
      this.history = this.history.slice(-MAX_HISTORY);
    }
    this.historyIndex = this.history.length - 1;
  }

  async goBack(): Promise<string | null> {
    if (this.historyIndex <= 0) return null;
    this.historyIndex--;
    const url = this.history[this.historyIndex];
    await this.getPage().goto(url, { waitUntil: "domcontentloaded" });
    return url;
  }

  async goForward(): Promise<string | null> {
    if (this.historyIndex >= this.history.length - 1) return null;
    this.historyIndex++;
    const url = this.history[this.historyIndex];
    await this.getPage().goto(url, { waitUntil: "domcontentloaded" });
    return url;
  }

  async close(): Promise<void> {
    if (this.browser) {
      try { await this.browser.close(); } catch {}
      this.browser = null;
    }
    if (this.context && !this.browser) {
      // persistent context: close context directly
      try { await this.context.close(); } catch {}
    }
    this.context = null;
    this.page = null;
    this.history = [];
    this.historyIndex = -1;
  }

  get isRunning(): boolean {
    return this.browser !== null || this.context !== null;
  }
}

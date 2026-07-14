/**
 * End-to-end tests exercising daemon server + socket protocol + real browser.
 */

import { describe, it, expect, beforeAll, afterAll } from "vitest";
import * as net from "node:net";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { DaemonServer } from "../src/server.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = path.resolve(__dirname, "fixture.html");
const FIXTURE_URL = `file://${FIXTURE_PATH}`;

const TEST_SESSION = `e2e-${process.pid}-${Date.now()}`;
const SOCK_PATH = `/tmp/camoufox-cli-${TEST_SESSION}.sock`;

function sendCommand(sockPath: string, cmd: Record<string, unknown>): Promise<Record<string, any>> {
  return new Promise((resolve, reject) => {
    const client = net.createConnection(sockPath, () => {
      client.end(JSON.stringify(cmd) + "\n");
    });
    let data = "";
    client.on("data", chunk => { data += chunk.toString(); });
    client.on("end", () => {
      try {
        resolve(JSON.parse(data.trim()));
      } catch (e) {
        reject(new Error(`Failed to parse response: ${data}`));
      }
    });
    client.on("error", reject);
  });
}

function cmd(sockPath: string, action: string, params: Record<string, unknown> = {}, id = "r1") {
  return sendCommand(sockPath, { id, action, params });
}

async function waitForSocket(sockPath: string, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fs.existsSync(sockPath)) return;
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error(`Socket ${sockPath} not found after ${timeoutMs}ms`);
}

function findRef(snapshot: string, role: string): string {
  for (const line of snapshot.split("\n")) {
    if (line.includes(`- ${role}`) && line.includes("[ref=")) {
      const start = line.indexOf("[ref=") + 5;
      const end = line.indexOf("]", start);
      return "@" + line.slice(start, end);
    }
  }
  throw new Error(`No ref found for role '${role}' in snapshot`);
}

describe("e2e", { timeout: 120_000 }, () => {
  let serverPromise: Promise<void>;

  beforeAll(async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      headless: true,
      timeout: 300,
    });
    serverPromise = server.start();
    await waitForSocket(SOCK_PATH);

    // Open fixture page
    const resp = await cmd(SOCK_PATH, "open", { url: FIXTURE_URL });
    expect(resp.success).toBe(true);
  });

  afterAll(async () => {
    try {
      await cmd(SOCK_PATH, "close");
    } catch {}
    await serverPromise;
  });

  it("open returns url and title", async () => {
    const urlResp = await cmd(SOCK_PATH, "url");
    expect(urlResp.success).toBe(true);
    expect(urlResp.data.url).toContain("fixture.html");

    const titleResp = await cmd(SOCK_PATH, "title");
    expect(titleResp.success).toBe(true);
    expect(titleResp.data.title).toBe("Test Fixture");
  });

  it("snapshot has refs", async () => {
    const resp = await cmd(SOCK_PATH, "snapshot");
    expect(resp.success).toBe(true);
    expect(resp.data.snapshot).toContain("[ref=");
  });

  it("fill textbox", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "textbox");

    const fillResp = await cmd(SOCK_PATH, "fill", { ref, text: "E2E-Alice" });
    expect(fillResp.success).toBe(true);

    const evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('name').value" });
    expect(evalResp.data.result).toBe("E2E-Alice");
  });

  it("click button", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "button");

    const clickResp = await cmd(SOCK_PATH, "click", { ref });
    expect(clickResp.success).toBe(true);

    const evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('output').textContent" });
    expect(evalResp.data.result).toBe("clicked");
  });

  it("select dropdown", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "combobox");

    const selResp = await cmd(SOCK_PATH, "select", { ref, value: "Green" });
    expect(selResp.success).toBe(true);

    const evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('color').value" });
    expect(evalResp.data.result).toBe("green");
  });

  it("check and uncheck", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "checkbox");

    // Check
    let resp = await cmd(SOCK_PATH, "check", { ref });
    expect(resp.success).toBe(true);
    let evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('agree').checked" });
    expect(evalResp.data.result).toBe(true);

    // Uncheck
    resp = await cmd(SOCK_PATH, "check", { ref });
    expect(resp.success).toBe(true);
    evalResp = await cmd(SOCK_PATH, "eval", { expression: "document.getElementById('agree').checked" });
    expect(evalResp.data.result).toBe(false);
  });

  it("scroll", async () => {
    const resp = await cmd(SOCK_PATH, "scroll", { direction: "down", amount: 100 });
    expect(resp.success).toBe(true);
  });

  it("wait ms", async () => {
    const resp = await cmd(SOCK_PATH, "wait", { ms: 50 });
    expect(resp.success).toBe(true);
  });

  it("press key", async () => {
    const snap = await cmd(SOCK_PATH, "snapshot");
    const ref = findRef(snap.data.snapshot, "textbox");
    await cmd(SOCK_PATH, "click", { ref });

    const resp = await cmd(SOCK_PATH, "press", { key: "Tab" });
    expect(resp.success).toBe(true);
  });

  it("back and forward", async () => {
    // Navigate to second page (use data: URI since about:blank may fail)
    const openResp = await cmd(SOCK_PATH, "open", { url: "data:text/html,<h1>Page2</h1>" });
    expect(openResp.success).toBe(true);

    // Go back to fixture
    const backResp = await cmd(SOCK_PATH, "back");
    expect(backResp.success).toBe(true);
    expect(backResp.data.url).toContain("fixture.html");

    // Go forward
    const fwdResp = await cmd(SOCK_PATH, "forward");
    expect(fwdResp.success).toBe(true);

    // Return to fixture for remaining tests
    await cmd(SOCK_PATH, "open", { url: FIXTURE_URL });
  });

  it("tabs", async () => {
    const resp = await cmd(SOCK_PATH, "tabs");
    expect(resp.success).toBe(true);
    expect(resp.data.tabs.length).toBeGreaterThanOrEqual(1);
    expect(resp.data.tabs.some((t: any) => t.active)).toBe(true);
  });

  it("cookies", async () => {
    const resp = await cmd(SOCK_PATH, "cookies", { op: "list" });
    expect(resp.success).toBe(true);
    expect(resp.data).toHaveProperty("cookies");
  });
});

describe("e2e close shuts down daemon", { timeout: 30_000 }, () => {
  it("close command stops daemon", async () => {
    const session = `e2e-close-${process.pid}-${Date.now()}`;
    const sockPath = `/tmp/camoufox-cli-${session}.sock`;
    const server = new DaemonServer({ session, headless: true, timeout: 60 });
    const promise = server.start();
    await waitForSocket(sockPath);

    const resp = await sendCommand(sockPath, { id: "r1", action: "close", params: {} });
    expect(resp.success).toBe(true);

    await promise;
    expect(fs.existsSync(sockPath)).toBe(false);
  });
});

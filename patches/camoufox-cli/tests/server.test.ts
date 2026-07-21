import { describe, it, expect, afterEach } from "vitest";
import * as net from "node:net";
import * as fs from "node:fs";
import { DaemonServer } from "../src/server.js";
import { getSocketPath, getPidPath } from "../src/cli.js";

const TEST_SESSION = `test-${process.pid}-${Date.now()}`;
const SOCK_PATH = getSocketPath(TEST_SESSION);
const PID_PATH = getPidPath(TEST_SESSION);

function cleanup() {
  for (const p of [SOCK_PATH, PID_PATH]) {
    try { fs.unlinkSync(p); } catch {}
  }
}

describe("DaemonServer", () => {
  afterEach(cleanup);

  it("constructs with defaults", () => {
    const server = new DaemonServer({});
    expect(server).toBeDefined();
  });

  it("constructs with custom options", () => {
    const server = new DaemonServer({
      session: "custom",
      headless: false,
      timeout: 60,
    });
    expect(server).toBeDefined();
  });

  it("clamps idle timeout to the 60s hard ceiling", () => {
    // A caller asking for 1800s (old default) must be clamped to 60 — this is
    // the backstop against browser accumulation. A caller asking for less is honored.
    const greedy = new DaemonServer({ session: "greedy", timeout: 1800 });
    expect((greedy as any).timeout).toBe(60);
    const modest = new DaemonServer({ session: "modest", timeout: 30 });
    expect((modest as any).timeout).toBe(30);
    const def = new DaemonServer({ session: "def" });
    expect((def as any).timeout).toBe(60);
  });

  it("starts and accepts connections", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    // Start server in background
    const serverPromise = server.start();

    // Wait for socket to appear
    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }
    expect(fs.existsSync(SOCK_PATH)).toBe(true);

    // Send close command to shut down
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const parsed = JSON.parse(response);
    expect(parsed.success).toBe(true);

    await serverPromise;
  });

  it("writes pid file", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(PID_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }
    expect(fs.existsSync(PID_PATH)).toBe(true);

    const pid = fs.readFileSync(PID_PATH, "utf-8").trim();
    expect(parseInt(pid, 10)).toBe(process.pid);

    // Clean shutdown
    const client = net.createConnection(SOCK_PATH, () => {
      client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;
  });

  it("handles unknown actions gracefully", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }

    // Send unknown action
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end(JSON.stringify({ id: "r1", action: "nonexistent", params: {} }) + "\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const parsed = JSON.parse(response);
    expect(parsed.success).toBe(false);
    expect(parsed.error).toContain("Unknown action");

    // Shut down
    const closeResp = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end(JSON.stringify({ id: "r2", action: "close", params: {} }) + "\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });
    expect(JSON.parse(closeResp).success).toBe(true);

    await serverPromise;
  });

  it("handles invalid JSON gracefully", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }

    // Send invalid JSON
    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end("not valid json\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const parsed = JSON.parse(response);
    expect(parsed.success).toBe(false);

    // Shut down
    const client = net.createConnection(SOCK_PATH, () => {
      client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;
  });

  it("cleans up socket and pid on shutdown", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }

    // Shut down
    const client = net.createConnection(SOCK_PATH, () => {
      client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;

    // Files should be cleaned up
    expect(fs.existsSync(SOCK_PATH)).toBe(false);
    expect(fs.existsSync(PID_PATH)).toBe(false);
  });

  it("reports session + headless mode via info action", async () => {
    const server = new DaemonServer({
      session: TEST_SESSION,
      headless: false,
      timeout: 5,
    });

    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise(r => setTimeout(r, 100));
    }

    const response = await new Promise<string>((resolve, reject) => {
      const client = net.createConnection(SOCK_PATH, () => {
        client.end(JSON.stringify({ id: "r1", action: "info", params: {} }) + "\n");
      });
      let data = "";
      client.on("data", chunk => { data += chunk.toString(); });
      client.on("end", () => resolve(data));
      client.on("error", reject);
    });

    const parsed = JSON.parse(response);
    expect(parsed.success).toBe(true);
    expect(parsed.data.session).toBe(TEST_SESSION);
    expect(parsed.data.headless).toBe(false);

    // Shut down
    const client = net.createConnection(SOCK_PATH, () => {
      client.end(JSON.stringify({ id: "r1", action: "close", params: {} }) + "\n");
    });
    client.on("data", () => {});
    await serverPromise;
  });
});

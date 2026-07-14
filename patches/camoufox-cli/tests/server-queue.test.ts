import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as net from "node:net";
import * as fs from "node:fs";

// Hoisted state shared with the mocked execute. The first command awaited
// here hangs on a gate we control, so a second command sent while it is
// in-flight deterministically observes the busy flag — no timers, no flakes.
const queueState = vi.hoisted(() => ({
  resolveFirst: (() => {}) as () => void,
  firstGate: Promise.resolve() as Promise<void>,
  calls: 0,
}));
queueState.firstGate = new Promise<void>((r) => { queueState.resolveFirst = r; });

vi.mock("../src/commands.js", () => ({
  execute: async (_mgr: unknown, command: { id?: string; action?: string }) => {
    queueState.calls++;
    if (queueState.calls === 1) await queueState.firstGate;
    return { id: (command as { id?: string }).id ?? "r1", success: true, data: { ok: true } };
  },
}));

// Imported after vi.mock so DaemonServer picks up the mocked execute.
import { DaemonServer } from "../src/server.js";

const TEST_SESSION = `queue-test-${process.pid}`;
const SOCK_PATH = `/tmp/camoufox-cli-${TEST_SESSION}.sock`;
const PID_PATH = `/tmp/camoufox-cli-${TEST_SESSION}.pid`;

function cleanup() {
  for (const p of [SOCK_PATH, PID_PATH]) {
    try { fs.unlinkSync(p); } catch {}
  }
}

function send(sockPath: string, command: Record<string, unknown>): Promise<string> {
  return new Promise((resolve, reject) => {
    const client = net.createConnection(sockPath, () => {
      client.end(JSON.stringify(command) + "\n");
    });
    let data = "";
    client.on("data", (chunk) => { data += chunk.toString(); });
    client.on("end", () => resolve(data));
    client.on("error", reject);
  });
}

describe("DaemonServer fail-first queue", () => {
  // Reset shared state between tests: `calls` is hoisted (module-scoped, never
  // reset by vi.clearAllMocks), and the first test resolves firstGate. Without
  // this reset the second test's command A would see calls>=2 and skip the
  // gate entirely, so close would run on an idle server and the bypass path
  // would never actually be exercised.
  beforeEach(() => {
    queueState.calls = 0;
    queueState.firstGate = new Promise<void>((r) => { queueState.resolveFirst = r; });
  });
  afterEach(cleanup);

  it("rejects a concurrent command with a busy message while one is in-flight", async () => {
    const server = new DaemonServer({ session: TEST_SESSION, timeout: 30 });
    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise((r) => setTimeout(r, 100));
    }
    expect(fs.existsSync(SOCK_PATH)).toBe(true);

    // Fire command A (hangs on the gate) and command B (concurrent) without
    // awaiting A first, so B arrives while A is mid-flight.
    const aPromise = send(SOCK_PATH, { id: "a", action: "snapshot", params: {} });
    // Let the connection for A be established and its data event land so that
    // execute() has been entered and busy is true.
    await new Promise((r) => setTimeout(r, 150));
    const bResponse = await send(SOCK_PATH, { id: "b", action: "snapshot", params: {} });
    const bParsed = JSON.parse(bResponse);
    expect(bParsed.success).toBe(false);
    expect(bParsed.error).toContain("正忙");
    expect(bParsed.error).toContain(TEST_SESSION);

    // Release A and confirm it completed normally.
    queueState.resolveFirst();
    const aResponse = await aPromise;
    const aParsed = JSON.parse(aResponse);
    expect(aParsed.success).toBe(true);

    // Tear down.
    await send(SOCK_PATH, { id: "c", action: "close", params: {} });
    await serverPromise;
  });

  it("allows close to bypass the queue (recovery escape hatch)", async () => {
    const server = new DaemonServer({ session: TEST_SESSION, timeout: 30 });
    const serverPromise = server.start();

    for (let i = 0; i < 50; i++) {
      if (fs.existsSync(SOCK_PATH)) break;
      await new Promise((r) => setTimeout(r, 100));
    }

    // A is in-flight (hung); close must still be accepted.
    const aPromise = send(SOCK_PATH, { id: "a", action: "snapshot", params: {} });
    await new Promise((r) => setTimeout(r, 150));

    const closeResponse = await send(SOCK_PATH, { id: "c", action: "close", params: {} });
    const closeParsed = JSON.parse(closeResponse);
    expect(closeParsed.success).toBe(true);

    // A never gets released; the server is tearing down regardless. Swallow
    // its rejection so the test doesn't fail on the hung connection closing.
    aPromise.catch(() => {});
    await serverPromise;
  });
});

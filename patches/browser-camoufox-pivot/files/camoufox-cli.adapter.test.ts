// Unit tests for the camoufox-cli adapter (Line 1 browser backend).
// Verifies each of the 17 browser-tool actions translates to the correct
// camoufox-cli daemon command + params, and that responses are shaped into the
// browser-tool result shape. The socket transport is injected — no real daemon.

import { describe, expect, it } from "vitest";
import {
  executeCamoufoxCliAction,
  shortenSession,
  socketPath,
  type CamoufoxCliSessionConfig,
  type Transport,
  type AdapterDeps,
} from "./camoufox-cli.adapter.js";

const CONFIG: CamoufoxCliSessionConfig = { session: "test", headless: true };

/** Recorded daemon call. */
interface Call { action: string; params: Record<string, unknown>; }

/**
 * Build a fake transport that records every command sent and returns canned
 * responses keyed by action. Tests assert on `calls` and the shaped result.
 */
function makeTransport(responses: Record<string, unknown> = {}): { transport: Transport; calls: Call[]; deps: AdapterDeps } {
  const calls: Call[] = [];
  const transport: Transport = async (_config, command) => {
    calls.push({ action: command.action, params: command.params ?? {} });
    const data = responses[command.action];
    if (data instanceof Error) return { id: command.id, success: false, error: data.message };
    return { id: command.id, success: true, data };
  };
  return { transport, calls, deps: { transport, isAlive: async () => true, ensureDaemon: async () => {} } };
}

function textOf(result: { content: Array<{ type: string; text?: string }> }): string {
  return result.content.map((c) => c.text ?? "").join("\n");
}

describe("camoufox-cli adapter — action translation", () => {
  it("doctor reports backend + liveness", async () => {
    const { deps } = makeTransport();
    const res = await executeCamoufoxCliAction({ action: "doctor" }, CONFIG, deps);
    expect(textOf(res)).toContain("camoufox-cli");
    expect(textOf(res)).toContain("daemonRunning");
  });

  it("status reports running state", async () => {
    const deps: AdapterDeps = { isAlive: async () => false, ensureDaemon: async () => {}, transport: async () => ({ success: true }) };
    const res = await executeCamoufoxCliAction({ action: "status" }, CONFIG, deps);
    expect(textOf(res)).toContain('"running": false');
  });

  it("start ensures the daemon", async () => {
    let ensured = false;
    const deps: AdapterDeps = { isAlive: async () => true, ensureDaemon: async () => { ensured = true; }, transport: async () => ({ success: true }) };
    const res = await executeCamoufoxCliAction({ action: "start" }, CONFIG, deps);
    expect(ensured).toBe(true);
    expect(textOf(res)).toContain('"started": true');
  });

  it("stop sends close", async () => {
    const { transport, calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "stop" }, CONFIG, deps);
    expect(calls.some((c) => c.action === "close")).toBe(true);
    void transport;
  });

  it("tabs wraps the daemon tabs response", async () => {
    const { calls, deps } = makeTransport({ tabs: { tabs: [{ url: "https://a", title: "A" }] } });
    const res = await executeCamoufoxCliAction({ action: "tabs" }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "tabs", params: {} });
    expect(textOf(res)).toContain("https://a");
    // tabs are untrusted page data → wrapped with the external-content notice
    expect((res.details as { externalContent?: { untrusted?: boolean } }).externalContent?.untrusted).toBe(true);
  });

  it("open sends open <url> and shapes url/title", async () => {
    const { calls, deps } = makeTransport({ open: { url: "https://x", title: "X" } });
    const res = await executeCamoufoxCliAction({ action: "open", targetUrl: "https://x" }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "open", params: { url: "https://x" } });
    expect(textOf(res)).toContain('"title": "X"');
  });

  it("navigate maps to open", async () => {
    const { calls, deps } = makeTransport({ open: { url: "https://n", title: "N" } });
    await executeCamoufoxCliAction({ action: "navigate", url: "https://n" }, CONFIG, deps);
    expect(calls[0].action).toBe("open");
    expect(calls[0].params).toEqual({ url: "https://n" });
  });

  it("focus resolves targetId → tab index → switch", async () => {
    const { calls, deps } = makeTransport({
      tabs: { tabs: [{ targetId: "t1" }, { targetId: "t2" }] },
      switch: { url: "https://t2", title: "T2" },
    });
    const res = await executeCamoufoxCliAction({ action: "focus", targetId: "t2" }, CONFIG, deps);
    expect(calls.map((c) => c.action)).toEqual(["tabs", "switch"]);
    expect(calls[1].params).toEqual({ index: 1 });
    expect(textOf(res)).toContain('"focused": "t2"');
  });

  it("focus on unknown targetId returns unsupported guidance", async () => {
    const { deps } = makeTransport({ tabs: { tabs: [{ targetId: "t1" }] } });
    const res = await executeCamoufoxCliAction({ action: "focus", targetId: "nope" }, CONFIG, { ...deps, transport: deps.transport });
    expect(textOf(res)).toContain("does not support");
  });

  it("close without targetId sends close-tab", async () => {
    const { calls, deps } = makeTransport({ "close-tab": { url: "about:blank", title: "" } });
    await executeCamoufoxCliAction({ action: "close" }, CONFIG, deps);
    expect(calls[0].action).toBe("close-tab");
  });

  it("close with targetId returns unsupported (cli closes current tab only)", async () => {
    const { deps } = makeTransport();
    const res = await executeCamoufoxCliAction({ action: "close", targetId: "t1" }, CONFIG, deps);
    expect(textOf(res)).toContain('does not support action="close"');
  });

  it("snapshot sends interactive + selector and wraps aria tree", async () => {
    const { calls, deps } = makeTransport({ snapshot: { snapshot: "- textbox [ref=e1]" } });
    const res = await executeCamoufoxCliAction({ action: "snapshot", interactive: true, selector: "#main" }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "snapshot", params: { interactive: true, selector: "#main" } });
    expect(textOf(res)).toContain("ref=e1");
    expect((res.details as { externalContent?: { untrusted?: boolean } }).externalContent?.untrusted).toBe(true);
  });

  it("screenshot writes to a temp path and returns it", async () => {
    const { calls, deps } = makeTransport({ screenshot: { path: "/tmp/x.png" } });
    const res = await executeCamoufoxCliAction({ action: "screenshot", fullPage: true }, CONFIG, deps);
    expect(calls[0].action).toBe("screenshot");
    expect(calls[0].params.full_page).toBe(true);
    expect(calls[0].params).toHaveProperty("path");
    expect(textOf(res)).toContain("file://");
  });

  it("console is unsupported with host fallback guidance", async () => {
    const { deps } = makeTransport();
    const res = await executeCamoufoxCliAction({ action: "console" }, CONFIG, deps);
    expect(textOf(res)).toContain('does not support action="console"');
    expect(textOf(res)).toContain('target="host"');
  });

  it("pdf writes to a temp file and returns FILE: pointer", async () => {
    const { calls, deps } = makeTransport({ pdf: { path: "/tmp/x.pdf" } });
    const res = await executeCamoufoxCliAction({ action: "pdf" }, CONFIG, deps);
    expect(calls[0].action).toBe("pdf");
    expect(calls[0].params).toHaveProperty("path");
    expect(textOf(res)).toMatch(/^FILE:.*\.pdf$/);
  });

  it("upload sends ref + paths", async () => {
    const { calls, deps } = makeTransport({ upload: { count: 2, paths: ["/a", "/b"] } });
    const res = await executeCamoufoxCliAction({ action: "upload", ref: "e1", paths: ["/a", "/b"] }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "upload", params: { paths: ["/a", "/b"], ref: "@e1" } });
    expect(textOf(res)).toContain('"count": 2');
  });

  it("upload accepts element as selector", async () => {
    const { calls, deps } = makeTransport({ upload: { count: 1 } });
    await executeCamoufoxCliAction({ action: "upload", element: "input[type=file]", paths: ["/a"] }, CONFIG, deps);
    expect(calls[0].params).toEqual({ paths: ["/a"], selector: "input[type=file]" });
  });

  it("upload requires paths", async () => {
    const { deps } = makeTransport();
    await expect(executeCamoufoxCliAction({ action: "upload", ref: "e1" }, CONFIG, deps)).rejects.toThrow("paths required");
  });

  it("dialog is unsupported with host fallback guidance", async () => {
    const { deps } = makeTransport();
    const res = await executeCamoufoxCliAction({ action: "dialog" }, CONFIG, deps);
    expect(textOf(res)).toContain('does not support action="dialog"');
  });
});

describe("camoufox-cli adapter — act kind translation", () => {
  it("act click → click @ref", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "click", ref: "e3" } }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "click", params: { ref: "@e3" } });
  });

  it("act type → type @ref text", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "type", ref: "e1", text: "hi" } }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "type", params: { ref: "@e1", text: "hi" } });
  });

  it("act fill with fields array → one fill per field", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "fill", fields: [{ ref: "e1", value: "a" }, { ref: "e2", value: "b" }] } }, CONFIG, deps);
    expect(calls).toEqual([
      { action: "fill", params: { ref: "@e1", text: "a" } },
      { action: "fill", params: { ref: "@e2", text: "b" } },
    ]);
  });

  it("act press → press key", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "press", key: "Enter" } }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "press", params: { key: "Enter" } });
  });

  it("act hover → hover @ref", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "hover", ref: "e1" } }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "hover", params: { ref: "@e1" } });
  });

  it("act select multi → one select per value", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "select", ref: "e1", values: ["red", "blue"] } }, CONFIG, deps);
    expect(calls).toEqual([
      { action: "select", params: { ref: "@e1", value: "red" } },
      { action: "select", params: { ref: "@e1", value: "blue" } },
    ]);
  });

  it("act wait timeMs → wait ms", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "wait", timeMs: 500 } }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "wait", params: { ms: 500 } });
  });

  it("act wait selector → wait selector", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "wait", selector: ".done" } }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "wait", params: { selector: ".done" } });
  });

  it("act wait url → wait url", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "wait", url: "https://x" } }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "wait", params: { url: "https://x" } });
  });

  it("act wait textGone → eval polling", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "wait", textGone: "Loading" } }, CONFIG, deps);
    expect(calls[0].action).toBe("eval");
    expect(calls[0].params.expression).toContain("Loading");
  });

  it("act evaluate → eval expression, returns result", async () => {
    const { calls, deps } = makeTransport({ eval: { result: 42 } });
    const res = await executeCamoufoxCliAction({ action: "act", request: { kind: "evaluate", fn: "1+1" } }, CONFIG, deps);
    expect(calls[0]).toEqual({ action: "eval", params: { expression: "1+1" } });
    expect(textOf(res)).toContain('"result": 42');
  });

  it("act close → close", async () => {
    const { calls, deps } = makeTransport();
    await executeCamoufoxCliAction({ action: "act", request: { kind: "close" } }, CONFIG, deps);
    expect(calls[0].action).toBe("close");
  });

  it("act clickCoords / drag / resize are unsupported", async () => {
    const { deps } = makeTransport();
    for (const kind of ["clickCoords", "drag", "resize"] as const) {
      const res = await executeCamoufoxCliAction({ action: "act", request: { kind } }, CONFIG, deps);
      expect(textOf(res)).toContain("does not support");
    }
  });

  it("propagates daemon errors as thrown Error", async () => {
    const { deps } = makeTransport({ click: new Error("element not found") });
    await expect(
      executeCamoufoxCliAction({ action: "act", request: { kind: "click", ref: "e1" } }, CONFIG, deps),
    ).rejects.toThrow("element not found");
  });
});

describe("shortenSession / socketPath — 108-char socket path limit", () => {
  // Regression for the cron long-session-ID bug: the daemon (patches/camoufox-cli)
  // hashes long session names to stay under Linux's 108-byte sockaddr_un limit.
  // The adapter MUST apply the identical shortening, else ensureDaemon waits on
  // a path the daemon never listens on and the browser never opens.
  const LONG_CRON_SESSION =
    "agent-main-cron-2b8125b0-082b-4c2b-bdc6-7fd2193bab9a-run-11c0d125-aeeb-4357-a6d7-11b0517c944a";

  it("short session is returned unchanged", () => {
    expect(shortenSession("default")).toBe("default");
    expect(shortenSession("my-session")).toBe("my-session");
  });

  it("84-char session is the unchanged boundary", () => {
    const s = "a".repeat(84);
    expect(shortenSession(s)).toBe(s);
  });

  it("85-char session is hashed to s-<16 hex>", () => {
    const result = shortenSession("a".repeat(85));
    expect(result).toMatch(/^s-[0-9a-f]{16}$/);
    expect(result.length).toBe(18);
  });

  it("long cron session ID is hashed", () => {
    const result = shortenSession(LONG_CRON_SESSION);
    expect(result).toMatch(/^s-[0-9a-f]{16}$/);
    expect(result.length).toBe(18);
  });

  it("shortenSession is deterministic", () => {
    expect(shortenSession(LONG_CRON_SESSION)).toBe(shortenSession(LONG_CRON_SESSION));
  });

  it("different long inputs produce different hashes", () => {
    const s1 = "agent-main-cron-aaa".padEnd(100, "a");
    const s2 = "agent-main-cron-bbb".padEnd(100, "b");
    expect(shortenSession(s1)).not.toBe(shortenSession(s2));
  });

  it("socketPath stays under 108 chars for any session", () => {
    expect(socketPath("default").length).toBeLessThanOrEqual(108);
    expect(socketPath(LONG_CRON_SESSION).length).toBeLessThanOrEqual(108);
    expect(socketPath("x".repeat(200)).length).toBeLessThanOrEqual(108);
  });

  it("socketPath for a long session is the hashed short form, not the raw name", () => {
    const raw = socketPath(LONG_CRON_SESSION);
    expect(raw).not.toContain(LONG_CRON_SESSION);
    expect(raw).toMatch(/^\/tmp\/camoufox-cli-s-[0-9a-f]{16}\.sock$/);
  });
});

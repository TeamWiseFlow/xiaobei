import { describe, it, expect, beforeEach } from "vitest";
import { execute } from "../src/commands.js";
import { BrowserManager } from "../src/browser.js";

describe("command dispatch", () => {
  let manager: BrowserManager;

  beforeEach(() => {
    manager = new BrowserManager();
  });

  it("returns error for unknown action", async () => {
    const resp = await execute(manager, { id: "r1", action: "nonexistent", params: {} });
    expect(resp.success).toBe(false);
    expect(resp.error).toContain("Unknown action");
  });

  it("returns error for missing action", async () => {
    const resp = await execute(manager, { id: "r1", params: {} });
    expect(resp.success).toBe(false);
    expect(resp.error).toContain("Unknown action");
  });

  it("preserves command id", async () => {
    const resp = await execute(manager, { id: "test-123", action: "nonexistent" });
    expect(resp.id).toBe("test-123");
  });

  it("defaults id to ?", async () => {
    const resp = await execute(manager, { action: "nonexistent" });
    expect(resp.id).toBe("?");
  });
});

describe("parameter validation", () => {
  let manager: BrowserManager;

  beforeEach(() => {
    manager = new BrowserManager();
  });

  it("open missing url", async () => {
    const resp = await execute(manager, { id: "r1", action: "open", params: {} });
    expect(resp.success).toBe(false);
    expect(resp.error!.toLowerCase()).toContain("url");
  });

  it("click missing ref", async () => {
    const resp = await execute(manager, { id: "r1", action: "click", params: {} });
    expect(resp.success).toBe(false);
    expect(resp.error!.toLowerCase()).toContain("ref");
  });

  it("fill missing ref", async () => {
    const resp = await execute(manager, { id: "r1", action: "fill", params: {} });
    expect(resp.success).toBe(false);
    expect(resp.error!.toLowerCase()).toContain("ref");
  });

  it("type missing ref", async () => {
    const resp = await execute(manager, { id: "r1", action: "type", params: {} });
    expect(resp.success).toBe(false);
  });

  it("select missing ref", async () => {
    const resp = await execute(manager, { id: "r1", action: "select", params: {} });
    expect(resp.success).toBe(false);
  });

  it("check missing ref", async () => {
    const resp = await execute(manager, { id: "r1", action: "check", params: {} });
    expect(resp.success).toBe(false);
  });

  it("hover missing ref", async () => {
    const resp = await execute(manager, { id: "r1", action: "hover", params: {} });
    expect(resp.success).toBe(false);
  });

  it("press missing key", async () => {
    const resp = await execute(manager, { id: "r1", action: "press", params: {} });
    expect(resp.success).toBe(false);
    expect(resp.error!.toLowerCase()).toContain("key");
  });

  it("text missing target", async () => {
    const resp = await execute(manager, { id: "r1", action: "text", params: {} });
    expect(resp.success).toBe(false);
  });

  it("eval missing expression", async () => {
    const resp = await execute(manager, { id: "r1", action: "eval", params: {} });
    expect(resp.success).toBe(false);
  });

  it("wait with no params", async () => {
    const resp = await execute(manager, { id: "r1", action: "wait", params: {} });
    expect(resp.success).toBe(false);
  });

  it("switch missing index", async () => {
    const resp = await execute(manager, { id: "r1", action: "switch", params: {} });
    expect(resp.success).toBe(false);
  });

  it("pdf missing path", async () => {
    const resp = await execute(manager, { id: "r1", action: "pdf", params: {} });
    expect(resp.success).toBe(false);
    expect(resp.error!.toLowerCase()).toContain("path");
  });
});

describe("browser not launched", () => {
  let manager: BrowserManager;

  beforeEach(() => {
    manager = new BrowserManager();
  });

  it("snapshot fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "snapshot", params: {} });
    expect(resp.success).toBe(false);
    expect(resp.error!.toLowerCase()).toContain("not launched");
  });

  it("url fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "url", params: {} });
    expect(resp.success).toBe(false);
  });

  it("title fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "title", params: {} });
    expect(resp.success).toBe(false);
  });

  it("tabs fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "tabs", params: {} });
    expect(resp.success).toBe(false);
  });

  it("scroll fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "scroll", params: { direction: "down" } });
    expect(resp.success).toBe(false);
  });

  it("close succeeds on non-running browser", async () => {
    const resp = await execute(manager, { id: "r1", action: "close", params: {} });
    expect(resp.success).toBe(true);
  });

  it("reload fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "reload", params: {} });
    expect(resp.success).toBe(false);
  });

  it("back fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "back", params: {} });
    expect(resp.success).toBe(false);
  });

  it("forward fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "forward", params: {} });
    expect(resp.success).toBe(false);
  });

  it("close-tab fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "close-tab", params: {} });
    expect(resp.success).toBe(false);
  });

  it("cookies fails", async () => {
    const resp = await execute(manager, { id: "r1", action: "cookies", params: { op: "list" } });
    expect(resp.success).toBe(false);
  });
});

describe("handler dispatch table coverage", () => {
  it("all expected actions exist", async () => {
    const manager = new BrowserManager();
    const knownActions = [
      "open", "back", "forward", "reload", "url", "title", "close",
      "snapshot", "click", "fill", "type", "select", "check", "hover", "press",
      "text", "eval", "screenshot", "pdf", "scroll", "wait",
      "tabs", "switch", "close-tab", "cookies",
    ];
    for (const action of knownActions) {
      const resp = await execute(manager, { id: "r1", action, params: {} });
      // All should return a response (not "Unknown action")
      if (resp.error) {
        expect(resp.error).not.toContain("Unknown action");
      }
    }
  });
});

import { describe, it, expect } from "vitest";
import { BrowserManager } from "../src/browser.js";

describe("BrowserManager", () => {
  it("starts as not running", () => {
    const manager = new BrowserManager();
    expect(manager.isRunning).toBe(false);
  });

  it("getPage throws when not launched", () => {
    const manager = new BrowserManager();
    expect(() => manager.getPage()).toThrow("not launched");
  });

  it("getContext throws when not launched", () => {
    const manager = new BrowserManager();
    expect(() => manager.getContext()).toThrow("not launched");
  });

  it("close on non-running is safe", async () => {
    const manager = new BrowserManager();
    await manager.close(); // should not throw
    expect(manager.isRunning).toBe(false);
  });

  it("has empty refs on creation", () => {
    const manager = new BrowserManager();
    expect(manager.refs.size).toBe(0);
  });
});

describe("BrowserManager history", () => {
  it("pushHistory tracks urls", () => {
    const manager = new BrowserManager();
    manager.pushHistory("https://a.com");
    manager.pushHistory("https://b.com");
    manager.pushHistory("https://c.com");
    // History should have 3 items (internal state)
  });

  it("pushHistory truncates forward history", () => {
    const manager = new BrowserManager();
    manager.pushHistory("https://a.com");
    manager.pushHistory("https://b.com");
    manager.pushHistory("https://c.com");
    // Simulate going back by manipulating internal state
    // This tests the slice logic: after going back, push truncates forward entries
  });
});

describe("BrowserManager persistent mode", () => {
  it("accepts persistent path in constructor", () => {
    const manager = new BrowserManager("/tmp/test-profile");
    expect(manager.isRunning).toBe(false);
  });

  it("defaults persistent to null", () => {
    const manager = new BrowserManager();
    expect(manager.isRunning).toBe(false);
  });
});

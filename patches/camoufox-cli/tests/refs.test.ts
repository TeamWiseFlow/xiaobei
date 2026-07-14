import { describe, it, expect } from "vitest";
import { RefRegistry } from "../src/refs.js";

describe("RefRegistry.buildFromSnapshot", () => {
  it("assigns refs to basic snapshot", () => {
    const registry = new RefRegistry();
    const result = registry.buildFromSnapshot('- link "About"\n- button "Submit"');
    expect(result).toContain("[ref=e1]");
    expect(result).toContain("[ref=e2]");
    expect(registry.size).toBe(2);
  });

  it("assigns roles and names", () => {
    const registry = new RefRegistry();
    registry.buildFromSnapshot('- link "Home"\n- button "OK"');
    const e1 = registry.resolve("e1");
    expect(e1).toBeDefined();
    expect(e1!.role).toBe("link");
    expect(e1!.name).toBe("Home");
    const e2 = registry.resolve("e2");
    expect(e2).toBeDefined();
    expect(e2!.role).toBe("button");
    expect(e2!.name).toBe("OK");
  });

  it("handles unnamed elements", () => {
    const registry = new RefRegistry();
    registry.buildFromSnapshot("- img\n- link");
    const e1 = registry.resolve("e1");
    expect(e1).toBeDefined();
    expect(e1!.role).toBe("img");
    expect(e1!.name).toBe("");
  });

  it("handles nested indentation", () => {
    const registry = new RefRegistry();
    const aria = '- list\n  - listitem\n    - link "Item 1"';
    const result = registry.buildFromSnapshot(aria);
    expect(result).toContain("[ref=e1]");
    expect(result).toContain("[ref=e2]");
    expect(result).toContain("[ref=e3]");
  });

  it("disambiguates duplicate role+name with nth", () => {
    const registry = new RefRegistry();
    registry.buildFromSnapshot('- link "Home"\n- link "Home"');
    const e1 = registry.resolve("e1");
    const e2 = registry.resolve("e2");
    expect(e1).toBeDefined();
    expect(e2).toBeDefined();
    expect(e1!.nth).toBe(0);
    expect(e2!.nth).toBe(1);
    expect(e1!.role).toBe("link");
    expect(e2!.role).toBe("link");
    expect(e1!.name).toBe("Home");
    expect(e2!.name).toBe("Home");
  });

  it("filters interactive-only", () => {
    const registry = new RefRegistry();
    const aria = '- heading "Title"\n- link "Click"\n- text: hello\n- button "OK"';
    const result = registry.buildFromSnapshot(aria, true);
    expect(result).not.toContain("Title");
    expect(result).not.toContain("hello");
    expect(result).toContain("Click");
    expect(result).toContain("OK");
    expect(registry.size).toBe(2);
  });

  it("clears previous entries", () => {
    const registry = new RefRegistry();
    registry.buildFromSnapshot('- link "A"');
    expect(registry.size).toBe(1);
    registry.buildFromSnapshot('- button "B"\n- button "C"');
    expect(registry.size).toBe(2);
    expect(registry.resolve("e1")!.role).toBe("button");
  });

  it("preserves non-matching lines", () => {
    const registry = new RefRegistry();
    const result = registry.buildFromSnapshot('plain text line\n- link "A"');
    expect(result).toContain("plain text line");
    expect(result).toContain("[ref=e1]");
  });

  it("handles empty snapshot", () => {
    const registry = new RefRegistry();
    const result = registry.buildFromSnapshot("");
    expect(registry.size).toBe(0);
  });

  it("handles all interactive roles", () => {
    const roles = [
      "link", "button", "combobox", "textbox", "textarea",
      "checkbox", "radio", "switch", "slider",
      "tab", "tabpanel", "menuitem", "option",
      "select", "listbox", "searchbox",
    ];
    const aria = roles.map(r => `- ${r} "test"`).join("\n");
    const registry = new RefRegistry();
    const result = registry.buildFromSnapshot(aria, true);
    expect(registry.size).toBe(roles.length);
  });

  it("filters non-interactive roles in interactive mode", () => {
    const nonInteractive = ["heading", "img", "list", "listitem", "paragraph", "region", "navigation"];
    const aria = nonInteractive.map(r => `- ${r} "test"`).join("\n");
    const registry = new RefRegistry();
    registry.buildFromSnapshot(aria, true);
    expect(registry.size).toBe(0);
  });
});

describe("RefRegistry.resolve", () => {
  it("resolves with @ prefix", () => {
    const registry = new RefRegistry();
    registry.buildFromSnapshot('- link "Test"');
    expect(registry.resolve("@e1")).toBeDefined();
  });

  it("resolves without @ prefix", () => {
    const registry = new RefRegistry();
    registry.buildFromSnapshot('- link "Test"');
    expect(registry.resolve("e1")).toBeDefined();
  });

  it("returns undefined for nonexistent ref", () => {
    const registry = new RefRegistry();
    registry.buildFromSnapshot('- link "Test"');
    expect(registry.resolve("e999")).toBeUndefined();
  });

  it("returns undefined on empty registry", () => {
    const registry = new RefRegistry();
    expect(registry.resolve("e1")).toBeUndefined();
  });
});

describe("RefRegistry.size", () => {
  it("returns 0 for empty registry", () => {
    const registry = new RefRegistry();
    expect(registry.size).toBe(0);
  });

  it("returns correct count", () => {
    const registry = new RefRegistry();
    registry.buildFromSnapshot('- link "A"\n- button "B"\n- textbox "C"');
    expect(registry.size).toBe(3);
  });
});

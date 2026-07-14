import { describe, it, expect } from "vitest";
import {
  parseCommand,
  serializeResponse,
  okResponse,
  errorResponse,
} from "../src/protocol.js";

describe("parseCommand", () => {
  it("parses basic command", () => {
    const result = parseCommand('{"action": "open", "params": {"url": "https://example.com"}}');
    expect(result).toEqual({ action: "open", params: { url: "https://example.com" } });
  });

  it("handles whitespace", () => {
    const result = parseCommand('  {"action": "close"}  \n');
    expect(result).toEqual({ action: "close" });
  });

  it("handles unicode", () => {
    const result = parseCommand('{"action": "fill", "params": {"text": "你好"}}');
    expect(result.params.text).toBe("你好");
  });

  it("throws on invalid JSON", () => {
    expect(() => parseCommand("not json")).toThrow();
  });

  it("handles command with id", () => {
    const result = parseCommand('{"id": "r1", "action": "open", "params": {}}');
    expect(result.id).toBe("r1");
    expect(result.action).toBe("open");
  });
});

describe("serializeResponse", () => {
  it("serializes basic response", () => {
    const resp = { id: "r1", success: true };
    const result = serializeResponse(resp);
    expect(JSON.parse(result.toString())).toEqual({ id: "r1", success: true });
  });

  it("handles unicode", () => {
    const resp = { id: "r1", success: true, data: { title: "腾讯网" } };
    const result = serializeResponse(resp);
    const str = result.toString("utf-8");
    expect(str).toContain("腾讯网");
  });

  it("ends with newline", () => {
    const result = serializeResponse({ id: "r1", success: true });
    expect(result.toString().endsWith("\n")).toBe(true);
  });

  it("returns Buffer", () => {
    const result = serializeResponse({ id: "r1", success: true });
    expect(Buffer.isBuffer(result)).toBe(true);
  });
});

describe("okResponse", () => {
  it("creates response without data", () => {
    const resp = okResponse("r1");
    expect(resp).toEqual({ id: "r1", success: true });
  });

  it("creates response with data", () => {
    const resp = okResponse("r1", { url: "https://example.com" });
    expect(resp).toEqual({ id: "r1", success: true, data: { url: "https://example.com" } });
  });

  it("omits data when undefined", () => {
    const resp = okResponse("r1", undefined);
    expect(resp).not.toHaveProperty("data");
  });

  it("preserves id", () => {
    const resp = okResponse("abc-123");
    expect(resp.id).toBe("abc-123");
  });
});

describe("errorResponse", () => {
  it("creates error response", () => {
    const resp = errorResponse("r1", "something went wrong");
    expect(resp).toEqual({ id: "r1", success: false, error: "something went wrong" });
  });

  it("preserves id", () => {
    const resp = errorResponse("abc123", "err");
    expect(resp.id).toBe("abc123");
  });

  it("sets success to false", () => {
    const resp = errorResponse("r1", "err");
    expect(resp.success).toBe(false);
  });
});

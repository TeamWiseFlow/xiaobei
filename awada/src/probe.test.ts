import { describe, expect, it } from "vitest";
import { validateAwadaRelayBaseUrl } from "./probe.js";

describe("validateAwadaRelayBaseUrl", () => {
  it("accepts http and https urls", () => {
    expect(validateAwadaRelayBaseUrl("http://127.0.0.1:8080")).toBeNull();
    expect(validateAwadaRelayBaseUrl("https://relay.example.com")).toBeNull();
    expect(validateAwadaRelayBaseUrl("https://relay.example.com:8443/path")).toBeNull();
  });

  it("rejects urls with unsupported protocol", () => {
    expect(validateAwadaRelayBaseUrl("redis://127.0.0.1:6379")).toBe(
      "invalid relayBaseUrl protocol (expected http:// or https://)",
    );
  });

  it("rejects malformed urls", () => {
    expect(validateAwadaRelayBaseUrl("not-a-url")).toBe("invalid relayBaseUrl format");
  });

  it("rejects empty input", () => {
    expect(validateAwadaRelayBaseUrl("  ")).toBe("missing relayBaseUrl");
  });
});

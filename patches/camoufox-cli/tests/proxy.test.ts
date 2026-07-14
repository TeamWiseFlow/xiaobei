import { describe, expect, it } from "vitest";
import { parseProxySettings } from "../src/proxy.js";

describe("parseProxySettings", () => {
  it("parses an HTTP proxy without credentials", () => {
    expect(parseProxySettings("http://host:8080")).toEqual({
      proxy: {
        server: "http://host:8080",
      },
    });
  });

  it("returns credentials for authenticated HTTP proxies", () => {
    expect(parseProxySettings("http://user:pass@host:8080")).toEqual({
      proxy: {
        server: "http://host:8080",
        username: "user",
        password: "pass",
      },
    });
  });

  it("decodes percent-encoded credentials", () => {
    expect(parseProxySettings("http://user%40x:pass%2Fword@host:8080")).toEqual({
      proxy: {
        server: "http://host:8080",
        username: "user@x",
        password: "pass/word",
      },
    });
  });

  it("supports https:// proxies", () => {
    // WHATWG URL strips default port 443 for https.
    expect(parseProxySettings("https://user:pass@host:443")).toEqual({
      proxy: {
        server: "https://host",
        username: "user",
        password: "pass",
      },
    });
  });

  it("preserves non-default https port", () => {
    expect(parseProxySettings("https://host:8443")).toEqual({
      proxy: { server: "https://host:8443" },
    });
  });

  it("rejects unsupported schemes like socks5://", () => {
    expect(() => parseProxySettings("socks5://host:1080")).toThrow(
      /Only http:\/\/ and https:\/\//
    );
  });
});

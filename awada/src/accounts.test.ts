import { describe, expect, it } from "vitest";
import {
  listAwadaAccountIds,
  resolveAwadaAccount,
  resolveDefaultAwadaAccountId,
} from "./accounts.js";
import type { ClawdbotConfig } from "openclaw/plugin-sdk";

function makeConfig(awada?: Record<string, unknown>): ClawdbotConfig {
  return { channels: awada !== undefined ? { awada } : undefined } as ClawdbotConfig;
}

describe("resolveAwadaAccount", () => {
  it("returns default values when no awada config is present", () => {
    const account = resolveAwadaAccount({ cfg: makeConfig() });
    expect(account.accountId).toBe("default");
    expect(account.enabled).toBe(true);
    expect(account.configured).toBe(false);
    expect(account.relayBaseUrl).toBeUndefined();
    expect(account.ofbKey).toBeUndefined();
    expect(account.lane).toBe("user");
  });

  it("resolves relayBaseUrl+ofbKey and marks configured=true", () => {
    const account = resolveAwadaAccount({
      cfg: makeConfig({ relayBaseUrl: "https://relay.example.com", ofbKey: "ofb_123" }),
    });
    expect(account.configured).toBe(true);
    expect(account.relayBaseUrl).toBe("https://relay.example.com");
    expect(account.ofbKey).toBe("ofb_123");
  });

  it("trims whitespace from relayBaseUrl/ofbKey", () => {
    const account = resolveAwadaAccount({
      cfg: makeConfig({ relayBaseUrl: "  https://relay.example.com  ", ofbKey: "  ofb_123  " }),
    });
    expect(account.relayBaseUrl).toBe("https://relay.example.com");
    expect(account.ofbKey).toBe("ofb_123");
  });

  it("marks configured=false when ofbKey missing", () => {
    const account = resolveAwadaAccount({
      cfg: makeConfig({ relayBaseUrl: "https://relay.example.com" }),
    });
    expect(account.configured).toBe(false);
  });

  it("marks configured=false when relayBaseUrl missing", () => {
    const account = resolveAwadaAccount({ cfg: makeConfig({ ofbKey: "ofb_123" }) });
    expect(account.configured).toBe(false);
  });

  it("respects enabled=false", () => {
    const account = resolveAwadaAccount({
      cfg: makeConfig({ enabled: false, relayBaseUrl: "https://relay.example.com", ofbKey: "k" }),
    });
    expect(account.enabled).toBe(false);
  });

  it("defaults enabled to true when not set", () => {
    const account = resolveAwadaAccount({
      cfg: makeConfig({ relayBaseUrl: "https://relay.example.com", ofbKey: "k" }),
    });
    expect(account.enabled).toBe(true);
  });

  it("uses custom lane when provided", () => {
    const account = resolveAwadaAccount({
      cfg: makeConfig({ lane: "cs" }),
    });
    expect(account.lane).toBe("cs");
  });

  it("uses provided accountId", () => {
    const account = resolveAwadaAccount({ cfg: makeConfig(), accountId: "custom-id" });
    expect(account.accountId).toBe("custom-id");
  });

  it("trims and falls back to default when accountId is blank", () => {
    const account = resolveAwadaAccount({ cfg: makeConfig(), accountId: "  " });
    expect(account.accountId).toBe("default");
  });
});

describe("listAwadaAccountIds", () => {
  it("always returns [default]", () => {
    expect(listAwadaAccountIds({} as ClawdbotConfig)).toEqual(["default"]);
  });
});

describe("resolveDefaultAwadaAccountId", () => {
  it("always returns default", () => {
    expect(resolveDefaultAwadaAccountId({} as ClawdbotConfig)).toBe("default");
  });
});

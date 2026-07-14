import { describe, expect, it } from "vitest";
import {
  buildOutboundMeta,
  buildOutboundTarget,
  decodeAwadaTo,
  encodeAwadaTo,
} from "./send.js";
import type { OutboundTarget } from "./redis-types.js";

const makeTarget = (overrides: Partial<OutboundTarget> = {}): OutboundTarget => ({
  platform: "wx",
  tenant_id: "t1",
  lane: "user",
  user_id_external: "u1",
  channel_id: "c1",
  ...overrides,
});

describe("encodeAwadaTo / decodeAwadaTo", () => {
  it("round-trips a minimal target", () => {
    const target = makeTarget();
    const encoded = encodeAwadaTo(target);
    expect(encoded).toMatch(/^awada:/);
    const decoded = decodeAwadaTo(encoded);
    expect(decoded).toEqual(target);
  });

  it("round-trips a target with optional conversation_id", () => {
    const target = makeTarget({ conversation_id: "conv_abc" });
    const decoded = decodeAwadaTo(encodeAwadaTo(target));
    expect(decoded?.conversation_id).toBe("conv_abc");
  });

  it("round-trips a target with reply_token", () => {
    const target = makeTarget({ reply_token: "tok_xyz" });
    const decoded = decodeAwadaTo(encodeAwadaTo(target));
    expect(decoded?.reply_token).toBe("tok_xyz");
  });

  it("returns null for string without awada: prefix", () => {
    expect(decodeAwadaTo("feishu:somevalue")).toBeNull();
  });

  it("returns null for invalid base64 JSON", () => {
    expect(decodeAwadaTo("awada:!!!not_base64!!!")).toBeNull();
  });

  it("returns null for valid base64 but non-JSON content", () => {
    const bad = "awada:" + Buffer.from("not json").toString("base64");
    expect(decodeAwadaTo(bad)).toBeNull();
  });

  it("preserves unicode in user_id_external", () => {
    const target = makeTarget({ user_id_external: "用户_123" });
    const decoded = decodeAwadaTo(encodeAwadaTo(target));
    expect(decoded?.user_id_external).toBe("用户_123");
  });
});

describe("buildOutboundTarget", () => {
  it("builds target with all required fields", () => {
    const target = buildOutboundTarget({
      lane: "user",
      tenant_id: "tenant_1",
      channel_id: "ch_1",
      user_id_external: "ext_user",
      platform: "wechat",
    });

    expect(target).toEqual({
      platform: "wechat",
      tenant_id: "tenant_1",
      lane: "user",
      user_id_external: "ext_user",
      channel_id: "ch_1",
    });
    expect(target.conversation_id).toBeUndefined();
  });

  it("includes conversation_id when provided", () => {
    const target = buildOutboundTarget({
      lane: "user",
      tenant_id: "t1",
      channel_id: "c1",
      user_id_external: "u1",
      platform: "wx",
      conversation_id: "conv_99",
    });

    expect(target.conversation_id).toBe("conv_99");
  });

  it("omits conversation_id when not provided", () => {
    const target = buildOutboundTarget({
      lane: "user",
      tenant_id: "t1",
      channel_id: "c1",
      user_id_external: "u1",
      platform: "wx",
    });

    expect(Object.keys(target)).not.toContain("conversation_id");
  });
});

describe("buildOutboundMeta", () => {
  it("carries the routing fields required by POST /outbound", () => {
    const meta = buildOutboundMeta(makeTarget(), "evt_inbound_1");
    expect(meta.platform).toBe("wx");
    expect(meta.channel_id).toBe("c1");
    expect(meta.user_id_external).toBe("u1");
    expect(meta.tenant_id).toBe("t1");
    expect(meta.source_event_id).toBe("evt_inbound_1");
  });

  it("omits source_event_id when not provided", () => {
    const meta = buildOutboundMeta(makeTarget());
    expect(meta.source_event_id).toBeUndefined();
  });
});

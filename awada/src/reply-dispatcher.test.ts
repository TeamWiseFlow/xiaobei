import { describe, expect, it } from "vitest";
import { formatAwadaReplyRecipient } from "./reply-dispatcher.js";
import type { OutboundTarget } from "./redis-types.js";

function makeTarget(overrides: Partial<OutboundTarget> = {}): OutboundTarget {
  return {
    platform: "worktool:bot",
    tenant_id: "tenant",
    lane: "station",
    user_id_external: "user_001",
    channel_id: "group_100",
    ...overrides,
  };
}

describe("formatAwadaReplyRecipient", () => {
  it("formats as user_external_id[channel_id] when both values exist", () => {
    const formatted = formatAwadaReplyRecipient(
      makeTarget({ user_id_external: "user_a", channel_id: "group_x" }),
    );
    expect(formatted).toBe("user_a[group_x]");
  });

  it("formats as [channel_id] when user_external_id is missing", () => {
    const formatted = formatAwadaReplyRecipient(
      makeTarget({ user_id_external: "   ", channel_id: "group_x" }),
    );
    expect(formatted).toBe("[group_x]");
  });

  it("keeps user id when channel_id is missing", () => {
    const formatted = formatAwadaReplyRecipient(
      makeTarget({ user_id_external: "user_a", channel_id: " " }),
    );
    expect(formatted).toBe("user_a");
  });
});

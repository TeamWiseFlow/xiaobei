import type { ChannelSetupWizard, DmPolicy, OpenClawConfig } from "openclaw/plugin-sdk/setup";
import { createTopLevelChannelDmPolicy, DEFAULT_ACCOUNT_ID } from "openclaw/plugin-sdk/setup";
import { probeAwada } from "./probe.js";
import type { AwadaConfig } from "./types.js";

const channel = "awada" as const;

function getAwadaCfg(cfg: OpenClawConfig): AwadaConfig | undefined {
  return cfg.channels?.awada as AwadaConfig | undefined;
}

function isAwadaConfigured(cfg: OpenClawConfig): boolean {
  const c = getAwadaCfg(cfg);
  return Boolean(c?.relayBaseUrl?.trim() && c?.ofbKey?.trim());
}

function setAwadaAllowFrom(cfg: OpenClawConfig, allowFrom: string[]): OpenClawConfig {
  return {
    ...cfg,
    channels: {
      ...cfg.channels,
      awada: {
        ...getAwadaCfg(cfg),
        allowFrom,
      },
    },
  };
}

const awadaDmPolicy = createTopLevelChannelDmPolicy({
  label: "Awada",
  channel,
  policyKey: "channels.awada.dmPolicy",
  allowFromKey: "channels.awada.allowFrom",
  getCurrent: (cfg) => (getAwadaCfg(cfg)?.dmPolicy ?? "open") as DmPolicy,
  getAllowFrom: (cfg) => getAwadaCfg(cfg)?.allowFrom,
  promptAllowFrom: async ({ cfg, prompter }) => {
    const existing = getAwadaCfg(cfg)?.allowFrom ?? [];
    const entry = await prompter.text({
      message: "Awada allowFrom (user_id_external values, comma-separated)",
      placeholder: "user_123, user_456",
      initialValue: existing.join(", "),
      validate: (value) => (String(value ?? "").trim() ? undefined : "Required"),
    });
    const parts = String(entry)
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const unique = [...new Set([...existing, ...parts])];
    return setAwadaAllowFrom(cfg, unique);
  },
});

export const awadaSetupWizard: ChannelSetupWizard = {
  channel,
  resolveAccountIdForConfigure: () => DEFAULT_ACCOUNT_ID,
  resolveShouldPromptAccountIds: () => false,
  status: {
    configuredLabel: "configured",
    unconfiguredLabel: "needs relay endpoint + OFB_KEY",
    configuredHint: "configured",
    unconfiguredHint: "needs relay endpoint + OFB_KEY",
    configuredScore: 2,
    unconfiguredScore: 0,
    resolveConfigured: ({ cfg }) => isAwadaConfigured(cfg),
    resolveStatusLines: async ({ cfg, configured }) => {
      const awadaCfg = getAwadaCfg(cfg);
      const relayBaseUrl = awadaCfg?.relayBaseUrl?.trim();
      let probeResult = null;
      if (configured && relayBaseUrl) {
        try {
          probeResult = await probeAwada({ relayBaseUrl });
        } catch {
          // ignore probe errors
        }
      }
      if (!configured) {
        return ["Awada: needs relayBaseUrl + ofbKey"];
      }
      if (probeResult?.ok) {
        return ["Awada: relay reachable"];
      }
      return ["Awada: configured (relay not verified)"];
    },
    resolveSelectionHint: ({ cfg }) =>
      isAwadaConfigured(cfg) ? "configured" : "needs relay endpoint + OFB_KEY",
    resolveQuickstartScore: ({ cfg }) => (isAwadaConfigured(cfg) ? 2 : 0),
  },
  credentials: [],
  finalize: async ({ cfg, prompter }) => {
    const awadaCfg = getAwadaCfg(cfg);
    const currentUrl = awadaCfg?.relayBaseUrl?.trim() ?? "";
    const currentKey = awadaCfg?.ofbKey?.trim() ?? "";

    await prompter.note(
      [
        "Configure awada channel to receive WeChat messages via the relay gateway.",
        "You need:",
        "  1. A running relay with awada-server gateway (exposes /api/v1/awada)",
        "  2. relayBaseUrl (e.g. https://relay.example.com)",
        "  3. OFB_KEY issued by relay admin (carries awada:lane:<lane> scope)",
        "  4. Lane to subscribe to (default: user)",
        "  5. Platform identifier for proactive sends (e.g. worktool:mybot)",
      ].join("\n"),
      "Awada setup",
    );

    const relayBaseUrl = String(
      await prompter.text({
        message: "Relay base URL",
        placeholder: "https://relay.example.com",
        initialValue: currentUrl,
        validate: (value) => (String(value ?? "").trim() ? undefined : "Required"),
      }),
    ).trim();

    const ofbKey = String(
      await prompter.text({
        message: "OFB_KEY",
        placeholder: "ofb_...",
        initialValue: currentKey,
        validate: (value) => (String(value ?? "").trim() ? undefined : "Required"),
      }),
    ).trim();

    let next: OpenClawConfig = {
      ...cfg,
      channels: {
        ...cfg.channels,
        awada: {
          ...awadaCfg,
          enabled: true,
          relayBaseUrl,
          ofbKey,
        },
      },
    };

    // Test connection
    try {
      const probe = await probeAwada({ relayBaseUrl });
      if (probe.ok) {
        await prompter.note("Relay reachable!", "Awada connection test");
      } else {
        await prompter.note(
          `Connection failed: ${probe.error ?? "unknown error"}`,
          "Awada connection test",
        );
      }
    } catch (err) {
      await prompter.note(`Connection test failed: ${String(err)}`, "Awada connection test");
    }

    // Lane configuration
    const currentLane = awadaCfg?.lane?.trim() ?? "user";
    const laneInput = String(
      await prompter.text({
        message: "Lane to subscribe to",
        placeholder: "user",
        initialValue: currentLane,
      }),
    ).trim();
    const resolvedLane = laneInput || "user";
    next = {
      ...next,
      channels: {
        ...next.channels,
        awada: {
          ...(next.channels?.awada as AwadaConfig),
          lane: resolvedLane,
        },
      },
    };

    // Platform configuration (used for proactive sends)
    const currentPlatform = awadaCfg?.platform?.trim() ?? "";
    const platformInput = String(
      await prompter.text({
        message: "Platform identifier for proactive sends (e.g. worktool:mybot)",
        placeholder: "worktool:mybot",
        initialValue: currentPlatform,
      }),
    ).trim();
    if (platformInput) {
      next = {
        ...next,
        channels: {
          ...next.channels,
          awada: {
            ...(next.channels?.awada as AwadaConfig),
            platform: platformInput,
          },
        },
      };
    }

    return { cfg: next };
  },
  dmPolicy: awadaDmPolicy,
  disable: (cfg) => ({
    ...cfg,
    channels: {
      ...cfg.channels,
      awada: { ...getAwadaCfg(cfg), enabled: false },
    },
  }),
};

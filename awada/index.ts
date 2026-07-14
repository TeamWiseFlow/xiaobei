import type { OpenClawPluginApi } from "openclaw/plugin-sdk/feishu";
import { awadaPlugin } from "./src/channel.js";
import { setAwadaRuntime } from "./src/runtime.js";
import { registerCustomerDb, type CustomerDbConfig } from "./src/customerdb.js";

export { monitorAwadaProvider } from "./src/monitor.js";
export { probeAwada } from "./src/probe.js";
export { sendTextToAwada, encodeAwadaTo, decodeAwadaTo } from "./src/send.js";
export { publishTextToAwada } from "./src/publisher.js";
export { awadaPlugin } from "./src/channel.js";

type AwadaPluginConfig = {
  /**
   * When set, activates the built-in CustomerDB feature:
   * injects customer context into LLM prompts and registers silent sales
   * commands (payment_success, club_join).
   *
   * Example openclaw.json:
   *   "plugins": {
   *     "entries": {
   *       "awada": {
   *         "config": {
   *           "customerdb": {
   *             "agentId": "sales-cs",
   *             "workspaceDir": "/home/user/.openclaw/workspace-sales-cs"
   *           }
   *         }
   *       }
   *     }
   *   }
   */
  customerdb?: CustomerDbConfig & { enabled?: boolean };
};

// Custom config schema that allows the `customerdb` field.
// Using emptyPluginConfigSchema() would reject any config key (additionalProperties: false).
const awadaConfigSchema = {
  safeParse(
    value: unknown,
  ): { success: true; data: unknown } | { success: false; error: string } {
    if (value === undefined) return { success: true, data: undefined };
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return { success: false, error: "expected config object" };
    }
    const obj = value as Record<string, unknown>;
    const allowed = new Set(["customerdb"]);
    const extra = Object.keys(obj).filter((k) => !allowed.has(k));
    if (extra.length > 0) {
      return { success: false, error: `unknown config keys: ${extra.join(", ")}` };
    }
    return { success: true, data: obj };
  },
  jsonSchema: {
    type: "object",
    additionalProperties: false,
    properties: {
      customerdb: {
        type: "object",
        additionalProperties: false,
        properties: {
          enabled: { type: "boolean" },
          agentId: { type: "string" },
          workspaceDir: { type: "string" },
        },
      },
    },
  },
};

const plugin = {
  id: "awada",
  name: "Awada",
  description: "Awada channel plugin — WeChat via Redis bridge",
  configSchema: awadaConfigSchema,
  register(api: OpenClawPluginApi) {
    setAwadaRuntime(api.runtime);
    api.registerChannel({ plugin: awadaPlugin });

    const pluginCfg = (api.pluginConfig ?? {}) as AwadaPluginConfig;
    const cdbCfg = pluginCfg.customerdb;
    if (cdbCfg && cdbCfg.enabled !== false && cdbCfg.agentId) {
      registerCustomerDb(api, cdbCfg);
    }
  },
};

export default plugin;

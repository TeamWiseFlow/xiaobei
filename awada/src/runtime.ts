import type { PluginRuntime } from "openclaw/plugin-sdk/core";

let runtime: PluginRuntime | null = null;

export function setAwadaRuntime(next: PluginRuntime) {
  runtime = next;
}

export function getAwadaRuntime(): PluginRuntime {
  if (!runtime) {
    throw new Error("Awada runtime not initialized");
  }
  return runtime;
}

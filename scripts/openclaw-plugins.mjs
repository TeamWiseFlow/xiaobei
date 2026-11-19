import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const engine = path.join(root, "openclaw");
const profilePath = path.join(root, "config-templates/openclaw-plugins.json");

function readPluginProfile(profileFile) {
  const { plugins, buildSupport, buildPrerequisites } = JSON.parse(fs.readFileSync(profileFile, "utf8"));
  if (!Array.isArray(plugins) || !plugins.length ||
      !Array.isArray(buildSupport) || !Array.isArray(buildPrerequisites)) {
    throw new Error("Invalid OpenClaw plugin profile");
  }
  const workspaceDirectories = [...plugins, ...buildSupport, ...buildPrerequisites];
  if (new Set(workspaceDirectories).size !== workspaceDirectories.length ||
      workspaceDirectories.some(id => typeof id !== "string" || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id))) {
    throw new Error("Invalid or duplicate OpenClaw plugin directory");
  }
  return { plugins, selected: new Set([...plugins, ...buildSupport]), buildPrerequisites };
}

export function applyBundledPluginDefaults(config, template) {
  let changed = false;
  for (const id of readPluginProfile(profilePath).plugins) {
    const defaults = template.plugins?.entries?.[id];
    if (!defaults) continue;
    const entry = config.plugins?.entries?.[id] ?? {};
    let entryChanged = false;
    if (typeof defaults.enabled === "boolean" && entry.enabled === undefined) {
      entry.enabled = defaults.enabled;
      entryChanged = true;
    }
    for (const [key, value] of Object.entries(defaults.config ?? {})) {
      if (entry.config?.[key] !== undefined) continue;
      entry.config ??= {};
      entry.config[key] = structuredClone(value);
      entryChanged = true;
    }
    if (!entryChanged) continue;
    config.plugins ??= {};
    config.plugins.entries ??= {};
    config.plugins.entries[id] = entry;
    changed = true;
  }
  return changed;
}

function prepareWorkspace(engineDir, profile) {
  const workspaceFile = path.join(engineDir, "pnpm-workspace.yaml");
  const workspace = fs.readFileSync(workspaceFile, "utf8");
  const extensions = /^  - extensions\/[^\r\n]+(?:\r?\n  - extensions\/[^\r\n]+)*/m;
  if (!extensions.test(workspace)) {
    throw new Error("OpenClaw workspace no longer declares extensions in its package list");
  }
  const workspacePackages = [];
  for (const id of [...profile.selected, ...profile.buildPrerequisites].sort()) {
    const directory = path.join(engineDir, "extensions", id);
    const hasPackage = fs.existsSync(path.join(directory, "package.json"));
    const hasManifest = fs.existsSync(path.join(directory, "openclaw.plugin.json"));
    const isPlugin = profile.plugins.includes(id);
    const isSupport = profile.selected.has(id) && !isPlugin;
    if ((isPlugin && !hasManifest) || (!isPlugin && !hasPackage) || (isSupport && hasManifest)) {
      throw new Error(`OpenClaw plugin profile entry has moved or changed: ${id}`);
    }
    if (hasPackage) workspacePackages.push(`  - extensions/${id}`);
  }
  fs.writeFileSync(workspaceFile, workspace.replace(extensions, workspacePackages.join("\n")));
  fs.copyFileSync(profilePath, path.join(engineDir, ".xiaobei-plugins.json"));
}

function excludedExtensionDirectories(directory, selected) {
  return fs.readdirSync(directory, { withFileTypes: true })
    .filter(entry => entry.isDirectory() && entry.name !== "node_modules" && !selected.has(entry.name))
    .map(entry => entry.name);
}

function assertRequiredExtensions(directory, { plugins, selected }) {
  const pluginIds = new Set(plugins);
  const missing = [...selected].filter(id => !fs.existsSync(path.join(
    directory, id, pluginIds.has(id) ? "openclaw.plugin.json" : "package.json",
  )));
  if (missing.length) throw new Error(`OpenClaw plugin build is missing: ${missing.join(", ")}`);
}

function trimDistribution(engineDir, profile) {
  assertRequiredExtensions(path.join(engineDir, "dist/extensions"), profile);
  for (const subdirectory of ["extensions", "dist/extensions", "dist-runtime/extensions"]) {
    const directory = path.join(engineDir, subdirectory);
    if (!fs.existsSync(directory)) continue;
    const physicalPath = path.join(fs.realpathSync(engineDir), subdirectory);
    if (fs.realpathSync(directory) !== physicalPath) {
      throw new Error(`Cannot trim a redirected OpenClaw plugin directory: ${directory}`);
    }
    for (const id of excludedExtensionDirectories(directory, profile.selected)) {
      fs.rmSync(path.join(directory, id), { force: true, recursive: true });
    }
  }
}

if (import.meta.main) {
  const [command, engineDir = engine] = process.argv.slice(2);
  const profile = readPluginProfile(profilePath);
  switch (command) {
    case "prepare":
      prepareWorkspace(engineDir, profile);
      break;
    case "verify": {
      const directory = path.join(engineDir, "dist/extensions");
      assertRequiredExtensions(directory, profile);
      const unexpected = excludedExtensionDirectories(directory, profile.selected);
      if (unexpected.length) throw new Error(`Unexpected OpenClaw plugin build output: ${unexpected.join(", ")}`);
      break;
    }
    case "rsync-excludes":
      for (const id of excludedExtensionDirectories(path.join(engineDir, "extensions"), profile.selected)) {
        console.log(`/extensions/${id}`);
      }
      break;
    case "trim-distribution":
      trimDistribution(engineDir, profile);
      break;
    default:
      throw new Error("Usage: node scripts/openclaw-plugins.mjs <prepare|verify|rsync-excludes|trim-distribution> [engine-dir]");
  }
}

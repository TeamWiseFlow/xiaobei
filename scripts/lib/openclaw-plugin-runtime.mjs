// Restore plugin-owned dependency links after a portable production install.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

function sameLinks(left, right) {
  const actual = fs.lstatSync(right, { throwIfNoEntry: false });
  if (!actual) return false;
  const expected = fs.lstatSync(left);
  if (expected.isSymbolicLink())
    return actual.isSymbolicLink() && fs.readlinkSync(left) === fs.readlinkSync(right);
  if (!expected.isDirectory() || !actual.isDirectory() || actual.isSymbolicLink()) return false;
  const names = fs.readdirSync(left).sort();
  const other = fs.readdirSync(right).sort();
  return names.length === other.length && names.every((name, index) =>
    name === other[index] && sameLinks(path.join(left, name), path.join(right, name)));
}

function dependencyRoot(directory, name) {
  for (let current = directory; ; current = path.dirname(current)) {
    const candidate = path.join(current, "node_modules", name);
    if (fs.existsSync(path.join(candidate, "package.json"))) return fs.realpathSync(candidate);
    if (path.dirname(current) === current) return undefined;
  }
}

export function restoreOpenClawPluginRuntime(root) {
  const engine = path.join(path.resolve(root), "openclaw");
  const extensions = path.join(engine, "dist/extensions");
  if (!fs.existsSync(extensions)) return [];
  const plugins = fs.readdirSync(extensions, { withFileTypes: true }).filter(entry =>
    entry.isDirectory() && entry.name !== "node_modules" &&
    fs.existsSync(path.join(engine, "extensions", entry.name, "package.json")));
  if (!plugins.length) return [];
  const { linkSourcePluginDependencies } = createRequire(import.meta.url)(
    path.join(engine, "scripts/lib/bundled-plugin-dependency-links.mjs"));
  const changed = [];
  for (const entry of plugins) {
    const source = path.join(engine, "extensions", entry.name);
    const destination = path.join(extensions, entry.name);
    const manifest = JSON.parse(fs.readFileSync(path.join(source, "package.json"), "utf8"));
    const required = Object.keys(manifest.dependencies ?? {}).filter(name =>
      !Object.hasOwn(manifest.optionalDependencies ?? {}, name));
    for (const name of required) {
      if (!dependencyRoot(source, name))
        throw new Error(`Plugin ${entry.name} dependency ${name} is missing; rerun the pinned production dependency installation.`);
    }
    const target = path.join(destination, "node_modules");
    const staged = fs.mkdtempSync(path.join(destination, ".xiaobei-plugin-deps-"));
    const backup = staged + ".previous";
    let saved = false;
    let published = false;
    try {
      linkSourcePluginDependencies(source, staged);
      if (sameLinks(staged, target)) continue;
      if (fs.lstatSync(target, { throwIfNoEntry: false })) {
        fs.renameSync(target, backup);
        saved = true;
      }
      fs.renameSync(staged, target);
      published = true;
      for (const name of required) {
        if (dependencyRoot(destination, name) !== dependencyRoot(source, name))
          throw new Error(`Plugin ${entry.name} dependency ${name} is not reachable from its compiled runtime.`);
      }
      changed.push(entry.name);
    } catch (error) {
      try {
        if (published) fs.rmSync(target, { recursive: true, force: true });
        if (saved) fs.renameSync(backup, target);
      } catch (restoreError) {
        throw new AggregateError([error, restoreError], `Plugin dependency rollback failed; previous links retained at ${backup}`);
      }
      throw error;
    } finally {
      fs.rmSync(staged, { recursive: true, force: true });
    }
    if (saved) fs.rmSync(backup, { recursive: true, force: true });
  }
  return changed;
}

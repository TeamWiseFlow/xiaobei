#!/usr/bin/env node
// Shared by source/Docker and tarball installers; dependencies stay in each skill.
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";

function main(argv) {
  const opts = { registry: process.env.npm_config_registry || "https://registry.npmmirror.com" };
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (!["--root", "--state-dir", "--npm-cli", "--registry"].includes(key) || !argv[i + 1]) {
      throw new Error("Usage: install-skill-deps.mjs --root <project> --state-dir <runtime> [--npm-cli <npm-cli.js>] [--registry <url>]");
    }
    opts[key.slice(2)] = argv[++i];
  }
  if (!opts.root || !opts["state-dir"]) throw new Error("--root and --state-dir are required");
  const root = path.resolve(opts.root);
  if (!fs.statSync(root).isDirectory()) throw new Error(`Project directory not found: ${root}`);
  const dirs = [];
  function scan(dir) {
    if (!fs.existsSync(dir)) return;
    if (fs.existsSync(path.join(dir, "SKILL.md")) && fs.existsSync(path.join(dir, "package.json"))) dirs.push(dir);
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory() && !["node_modules", ".git"].includes(entry.name)) scan(path.join(dir, entry.name));
    }
  }
  scan(path.join(root, "skills"));
  const crews = path.join(root, "crews");
  if (fs.existsSync(crews)) {
    for (const entry of fs.readdirSync(crews, { withFileTypes: true })) {
      if (entry.isDirectory()) scan(path.join(crews, entry.name, "skills"));
    }
  }
  dirs.sort();
  if (!dirs.length) {
    console.log("No skill package.json found");
    return;
  }

  const digest = createHash("sha256");
  const skills = dirs.map(dir => {
    const raw = fs.readFileSync(path.join(dir, "package.json"));
    digest.update(path.relative(root, dir).split(path.sep).join("/") + "\0").update(raw).update("\0");
    const pkg = JSON.parse(raw);
    const installer = pkg.xiaobei?.dependencyInstaller;
    let script;
    if (installer) {
      if (typeof installer.script !== "string" || !Array.isArray(installer.inputs)) throw new Error(`Invalid dependencyInstaller: ${dir}`);
      for (const input of [installer.script, ...installer.inputs]) {
        if (typeof input !== "string" || path.isAbsolute(input)) throw new Error(`Invalid installer input: ${dir}`);
        const target = path.resolve(dir, input);
        if (!target.startsWith(dir + path.sep)) throw new Error(`Installer input outside skill: ${target}`);
        digest.update(input + "\0").update(fs.readFileSync(target)).update("\0");
      }
      script = path.resolve(dir, installer.script);
    }
    return { dir, script, dependencies: Object.keys(pkg.dependencies || {}) };
  }).filter(skill => skill.script || skill.dependencies.length > 0);
  const currentHash = digest.digest("hex");
  const stamp = path.join(path.resolve(opts["state-dir"]), ".skill-pkg-hash");
  const storedHash = fs.existsSync(stamp) ? fs.readFileSync(stamp, "utf8").trim() : "";
  const missing = skill => {
    if (skill.dependencies.some(
      name => !fs.existsSync(path.join(skill.dir, "node_modules", name, "package.json"))
    )) return true;
    if (!skill.script) return false;
    const result = spawnSync(process.execPath, [skill.script, "--check"], { cwd: skill.dir, stdio: "ignore" });
    return !!result.error || result.status !== 0;
  };
  const pending = skills.filter(skill => currentHash !== storedHash || missing(skill));
  if (!pending.length) {
    console.log(`Skill dependencies up to date (hash: ${currentHash.slice(0, 8)})`);
    return;
  }

  const failures = [];
  for (const skill of pending) {
    console.log(`Installing skill dependencies: ${path.relative(root, skill.dir)}`);
    const args = ["install", "--omit=dev", "--no-audit", "--no-fund", "--loglevel=warn", `--registry=${opts.registry}`];
    const npmCli = opts["npm-cli"];
    const command = skill.script ? process.execPath : npmCli ? process.execPath : "npm";
    const commandArgs = skill.script ? [skill.script, "--registry", opts.registry, ...(npmCli ? ["--npm-cli", path.resolve(npmCli)] : [])] : npmCli ? [path.resolve(npmCli), ...args] : args;
    const result = spawnSync(command, commandArgs, {
      cwd: skill.dir,
      stdio: "inherit",
    });
    if (result.error || result.status !== 0 || missing(skill)) {
      failures.push(skill.dir);
      console.error(`Skill dependency install failed: ${skill.dir}${result.error ? ` (${result.error.message})` : ""}`);
    }
  }
  if (failures.length) throw new Error(`Dependencies incomplete in ${failures.length} skill(s); fix npm errors and rerun installation. Success hash was not updated.`);
  fs.mkdirSync(path.dirname(stamp), { recursive: true });
  fs.writeFileSync(stamp, currentHash + "\n");
  console.log(`Skill dependencies installed (hash: ${currentHash.slice(0, 8)})`);
}

try {
  main(process.argv.slice(2));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}

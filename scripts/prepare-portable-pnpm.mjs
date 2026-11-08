#!/usr/bin/env node
// pnpm 12 ships a Node launcher plus a platform-specific native executable.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const manifestPath = fileURLToPath(new URL("../package.json", import.meta.url));
const targets = {
  "linux-x64": { os: "linux", cpu: "x64", package: "@pnpm/exe.linux-x64" },
  "mac-arm64": { os: "darwin", cpu: "arm64", package: "@pnpm/exe.darwin-arm64" },
  "mac-x64": { os: "darwin", cpu: "x64", package: "@pnpm/exe.darwin-x64" },
  "win-x64": { os: "win32", cpu: "x64", package: "@pnpm/exe.win32-x64" },
};

export async function fetchBytes(url, { idleTimeoutMs = 120_000 } = {}) {
  const controller = new AbortController();
  let timer;
  const progress = () => {
    clearTimeout(timer);
    timer = setTimeout(() => controller.abort(new Error("No portable pnpm download progress")), idleTimeoutMs);
    timer.unref();
  };
  progress();
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);
    if (!response.body) throw new Error(`Empty pnpm response: ${url}`);
    const chunks = [];
    let bytes = 0, reported = Date.now();
    for await (const chunk of response.body) {
      progress(); chunks.push(chunk); bytes += chunk.length;
      if (Date.now() - reported >= 30_000) {
        process.stderr.write(`Downloading portable pnpm: ${(bytes / 1048576).toFixed(1)} MiB\n`);
        reported = Date.now();
      }
    }
    return Buffer.concat(chunks);
  } finally {
    clearTimeout(timer);
    controller.abort();
  }
}

async function extractPackage(name, version, registry, destination, expectedHash) {
  const metadata = JSON.parse(await fetchBytes(`${registry}/${encodeURIComponent(name)}/${version}`));
  if (metadata.name !== name || metadata.version !== version) {
    throw new Error(`Unexpected package metadata for ${name}@${version}`);
  }
  const integrity = metadata.dist?.integrity?.split(/\s+/).find(value => value.startsWith("sha512-"));
  if (!integrity || !metadata.dist?.tarball) throw new Error(`Missing tarball/SHA-512 for ${name}@${version}`);
  const archive = await fetchBytes(metadata.dist.tarball);
  const digest = createHash("sha512").update(archive).digest();
  if (`sha512-${digest.toString("base64")}` !== integrity ||
      (expectedHash && digest.toString("hex") !== expectedHash)) {
    throw new Error(`SHA-512 mismatch for ${name}@${version}`);
  }
  fs.mkdirSync(destination, { recursive: true });
  const archivePath = `${destination}.tgz`;
  fs.writeFileSync(archivePath, archive);
  try {
    execFileSync("tar", ["-xzf", archivePath, "-C", destination, "--strip-components=1"], { stdio: "pipe" });
  } finally {
    fs.rmSync(archivePath, { force: true });
  }
  const pkg = JSON.parse(fs.readFileSync(path.join(destination, "package.json"), "utf8"));
  if (pkg.name !== name || pkg.version !== version) throw new Error(`Unexpected package contents for ${name}@${version}`);
  return pkg;
}

export async function preparePortablePnpm({ output, platform = "all", registry = "https://registry.npmjs.org", manifest = manifestPath }) {
  if (!output) throw new Error("--output is required");
  const host = Object.keys(targets).find(key => targets[key].os === process.platform && targets[key].cpu === process.arch);
  const selected = platform === "all" ? Object.keys(targets) : [platform === "host" ? host : platform];
  if (selected.some(key => !Object.hasOwn(targets, key))) throw new Error(`Unsupported pnpm platform: ${platform}`);
  const { packageManager } = JSON.parse(fs.readFileSync(manifest, "utf8"));
  const pin = /^pnpm@(\d+\.\d+\.\d+)\+sha512\.([a-f0-9]{128})$/.exec(packageManager);
  if (!pin) throw new Error("package.json must pin pnpm with an exact version and SHA-512");
  const [, version, expectedHash] = pin;
  const outputRoot = path.resolve(output);
  for (const key of selected) {
    if (fs.existsSync(path.join(outputRoot, key))) throw new Error(`Output already exists: ${path.join(outputRoot, key)}`);
  }
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "xiaobei-portable-pnpm-"));
  try {
    const wrapper = path.join(temporary, "wrapper");
    const pkg = await extractPackage("pnpm", version, registry.replace(/\/$/, ""), wrapper, expectedHash);
    if (!fs.statSync(path.join(wrapper, "bin/pnpm.mjs")).isFile()) throw new Error("pnpm launcher is missing");
    for (const key of selected) {
      const target = targets[key];
      if (pkg.optionalDependencies?.[target.package] !== version) {
        throw new Error(`pnpm ${version} does not declare ${target.package}@${version}`);
      }
      const staged = path.join(temporary, key);
      fs.cpSync(wrapper, staged, { recursive: true });
      const nativeDirectory = path.join(temporary, `native-${key}`);
      const native = await extractPackage(target.package, version, registry.replace(/\/$/, ""), nativeDirectory);
      if (!native.os?.includes(target.os) || !native.cpu?.includes(target.cpu)) {
        throw new Error(`Wrong native platform in ${target.package}`);
      }
      const binary = path.join(nativeDirectory, target.os === "win32" ? "pnpm.exe" : "pnpm");
      if (!fs.statSync(binary).isFile()) throw new Error(`Missing native pnpm binary for ${key}`);
      // bin/pnpm.mjs recognizes this pre-downloaded path. Keep the executable
      // beside dist/: pnpm locates its bundled node-gyp relative to itself.
      const bundledBinary = path.join(staged, target.os === "win32" ? "pnpm-native.exe" : "pnpm-native");
      fs.copyFileSync(binary, bundledBinary);
      fs.chmodSync(bundledBinary, 0o755);
      for (const notice of ["LICENSE", "THIRD-PARTY-NOTICES.md"]) {
        if (fs.existsSync(path.join(nativeDirectory, notice))) {
          fs.copyFileSync(path.join(nativeDirectory, notice), path.join(staged, notice));
        }
      }
      if (key === host) {
        const env = {
          ...process.env,
          PATH: `${path.dirname(process.execPath)}${path.delimiter}${process.env.PATH || ""}`,
          COREPACK_ENABLE_NETWORK: "0",
        };
        const actual = execFileSync(process.execPath, [path.join(staged, "bin/pnpm.mjs"), "--version"], {
          cwd: temporary,
          env,
          encoding: "utf8",
          timeout: 30_000,
        }).trim();
        if (actual !== version) throw new Error(`Bundled pnpm reports ${actual}; expected ${version}`);
        const smoke = path.join(temporary, "lifecycle-smoke");
        fs.mkdirSync(smoke);
        fs.writeFileSync(path.join(smoke, "package.json"), JSON.stringify({
          private: true,
          scripts: { "check-node-gyp": "node-gyp --version" },
        }));
        execFileSync(process.execPath, [path.join(staged, "bin/pnpm.mjs"), "--dir", smoke,
          "--offline", "--config.update-notifier=false", "run", "check-node-gyp"], {
          cwd: temporary, env, encoding: "utf8", timeout: 30_000,
        });
        if (process.platform !== "win32") {
          // Exercise the shipped installers' actual arguments before the engine
          // build, using an isolated project with a real node-gyp lifecycle.
          const project = path.join(smoke, "openclaw");
          fs.mkdirSync(project);
          fs.writeFileSync(path.join(project, "package.json"), JSON.stringify({
            private: true, scripts: { install: "node-gyp --version" },
          }));
          const installerEnv = { ...env, WISEFLOW_INSTALL_SH_NO_RUN: "1", WISEFLOW_ROOT: smoke,
            PNPM_CONFIG_OFFLINE: "true", PNPM_CONFIG_UPDATE_NOTIFIER: "false",
            PNPM_CONFIG_STORE_DIR: path.join(smoke, "store"),
          };
          execFileSync(process.execPath, [path.join(staged, "bin/pnpm.mjs"), "--dir", project,
            "install", "--lockfile-only", "--ignore-scripts"], {
            cwd: temporary, env: installerEnv, encoding: "utf8", timeout: 30_000,
          });
          fs.mkdirSync(path.join(smoke, "tools/node/bin"), { recursive: true });
          fs.symlinkSync(process.execPath, path.join(smoke, "tools/node/bin/node"));
          fs.symlinkSync(staged, path.join(smoke, "tools/pnpm"), "dir");
          for (const installer of ["install.sh", "install-atomgit.sh"]) {
            execFileSync("bash", ["-c", 'source "$1"\nVERBOSE=1\npnpm_install_prod',
              "portable-pnpm-installer-check", fileURLToPath(new URL(installer, import.meta.url))], {
              cwd: temporary, env: installerEnv, encoding: "utf8", timeout: 30_000,
            });
          }
        }
      }
      fs.mkdirSync(outputRoot, { recursive: true });
      fs.cpSync(staged, path.join(outputRoot, key), { recursive: true });
      console.log(`Prepared pnpm ${version} for ${key}${key === host ? " (offline launch, node-gyp and installer arguments verified)" : ""}`);
    }
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const options = {};
    for (let i = 2; i < process.argv.length; i++) {
      const flag = process.argv[i];
      if (!["--output", "--platform", "--registry"].includes(flag) || !process.argv[i + 1]) {
        throw new Error("Usage: prepare-portable-pnpm.mjs --output <directory> [--platform all|host|linux-x64|mac-arm64|mac-x64|win-x64] [--registry <url>]");
      }
      options[flag.slice(2)] = process.argv[++i];
    }
    await preparePortablePnpm(options);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

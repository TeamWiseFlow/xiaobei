#!/usr/bin/env node
// One owned CPython + venv per installation. Never discovers or modifies host Python.
import fs from 'node:fs';
import path from 'node:path';
import { homedir } from 'node:os';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { downloadAsset, verify } from '../browser/scripts/download-asset.mjs';
import { configureInstallationNetwork, githubDownloadUrl } from '../browser/scripts/download-network.mjs';

export function runtimePaths(root, platform = process.platform) {
  const venv = path.join(path.resolve(root), 'tools', 'python');
  const bin = path.join(venv, platform === 'win32' ? 'Scripts' : 'bin');
  return { venv, bin, python: path.join(bin, platform === 'win32' ? 'python.exe' : 'python3') };
}

export function runtimeEnvironment(root) {
  const { venv, bin } = runtimePaths(root);
  const env = { ...process.env };
  for (const key of Object.keys(env)) {
    if (['PATH', 'PYTHONHOME', 'PYTHONPATH', 'PIP_USER', 'PIP_TARGET', 'PIP_PREFIX', 'PIP_BREAK_SYSTEM_PACKAGES'].includes(key.toUpperCase())) delete env[key];
  }
  env.PATH = bin + path.delimiter + (process.env.PATH || process.env.Path || '');
  return { ...env, VIRTUAL_ENV: venv, PYTHONNOUSERSITE: '1', PIP_REQUIRE_VIRTUALENV: 'true' };
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: 'inherit', ...options });
  if (result.error || result.status !== 0) throw new Error(`Python runtime command failed: ${command} (${result.error?.message || result.status})`);
  return result.stdout?.toString().trim();
}

function readJSON(file) {
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : null;
}

function writeJSON(file, data) {
  const temp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(data, null, 2) + '\n', { mode: 0o600 });
  fs.renameSync(temp, file);
}

export function assetPin(root, platform) {
  const pin = readJSON(path.join(root, 'scripts', 'python-runtime.lock.json'));
  if (!pin) throw new Error('Python runtime lock is missing; install a complete xiaobei release.');
  platform ||= `${{ linux: 'linux', darwin: 'mac', win32: 'win' }[process.platform]}-${process.arch}`;
  const asset = pin.assets[platform];
  if (!asset || !/^3\.12\.\d+$/.test(pin.version) || !/^\d{8}$/.test(pin.build) || !/^[a-f0-9]{64}$/.test(asset.sha256)) throw new Error(`Unsupported or invalid Python runtime pin: ${platform}`);
  const name = `cpython-${pin.version}+${pin.build}-${asset.target}-install_only_stripped.tar.gz`;
  return { ...pin, ...asset, platform, name, key: `${pin.version}-${pin.build}-${platform}`, url: `${pin.source}/releases/download/${pin.build}/${encodeURIComponent(name)}` };
}

async function archive(root, pin) {
  const shipped = path.join(root, 'tools', 'python-assets', pin.name);
  const cache = path.resolve(process.env.XIAOBEI_CACHE_DIR || path.join(homedir(), '.xiaobei', 'cache'));
  const cached = path.join(cache, pin.name);
  for (const candidate of [shipped, cached]) {
    if (fs.existsSync(candidate)) { await verify(candidate, pin.sha256); return candidate; }
  }
  fs.mkdirSync(cache, { recursive: true });
  await downloadAsset(githubDownloadUrl(pin.url), `${cached}.part`, pin.sha256);
  fs.renameSync(`${cached}.part`, cached);
  return cached;
}

export async function bundlePython(root, output, platform) {
  const pin = assetPin(root, platform);
  const source = await archive(root, pin);
  fs.mkdirSync(output, { recursive: true });
  const target = path.join(output, pin.name);
  if (path.resolve(source) !== path.resolve(target)) fs.copyFileSync(source, target);
  return target;
}

export function collectRequirements(root) {
  const lines = new Set();
  function add(file) {
    for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      // All dependencies are repository declarations, not per-invocation pip options/files.
      if (trimmed.startsWith('-')) throw new Error(`Unsupported requirements directive in ${file}: ${trimmed}`);
      lines.add(trimmed);
    }
  }
  function scan(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') scan(path.join(dir, entry.name));
      else if (entry.isFile() && entry.name === 'requirements.txt') add(path.join(dir, entry.name));
    }
  }
  const rootReq = path.join(root, 'requirements.txt');
  if (fs.existsSync(rootReq)) add(rootReq);
  scan(path.join(root, 'skills'));
  const crews = path.join(root, 'crews');
  if (fs.existsSync(crews)) for (const entry of fs.readdirSync(crews, { withFileTypes: true })) {
    if (entry.isDirectory()) scan(path.join(crews, entry.name, 'skills'));
  }
  return [...lines].sort().join('\n') + '\n';
}

function inspectPython(python, env) {
  return JSON.parse(run(python, ['-c', 'import json,sys; print(json.dumps(dict(version=".".join(map(str,sys.version_info[:3])),prefix=sys.prefix,base=sys.base_prefix)))'], { env, stdio: ['ignore', 'pipe', 'pipe'] }));
}

function samePath(left, right) {
  const normalize = value => {
    const result = fs.realpathSync(value);
    return process.platform === 'win32' ? result.toLowerCase() : result;
  };
  return normalize(left) === normalize(right);
}

async function installUnlocked(root) {
  const pin = assetPin(root);
  const { venv, bin, python } = runtimePaths(root);
  const base = path.join(root, 'tools', 'python-base', pin.key);
  const basePython = process.platform === 'win32' ? path.join(base, 'python.exe') : path.join(base, 'bin', 'python3');
  const env = runtimeEnvironment(root);
  const requirements = collectRequirements(root);
  const hash = createHash('sha256').update(pin.sha256).update(requirements).digest('hex');
  if (fs.existsSync(base)) {
    if (readJSON(path.join(base, '.xiaobei-python.json'))?.sha256 !== pin.sha256) throw new Error(`Unrecognised Python base directory; preserved: ${base}`);
  } else {
    const asset = await archive(root, pin);
    fs.mkdirSync(path.dirname(base), { recursive: true });
    const stage = fs.mkdtempSync(path.join(path.dirname(base), '.extract-'));
    try {
      run('tar', ['-xzf', asset, '-C', stage]);
      const extracted = path.join(stage, 'python');
      writeJSON(path.join(extracted, '.xiaobei-python.json'), { key: pin.key, sha256: pin.sha256 });
      fs.renameSync(extracted, base);
    } finally { fs.rmSync(stage, { recursive: true, force: true }); }
  }
  if (inspectPython(basePython, env).version !== pin.version) throw new Error('Bundled Python version does not match the release pin.');
  if (fs.existsSync(venv) && !fs.existsSync(path.join(venv, 'pyvenv.cfg'))) throw new Error(`Python runtime directory is not a venv; preserved: ${venv}`);
  let reusable = false;
  if (fs.existsSync(python)) {
    try {
      const info = inspectPython(python, env);
      reusable = info.version === pin.version && samePath(info.prefix, venv) && samePath(info.base, base);
      if (reusable) {
        const stamp = readJSON(path.join(venv, '.xiaobei-dependencies.json'));
        const installed = run(python, ['-m', 'pip', 'list', '--format=json', '--disable-pip-version-check'], { env, stdio: ['ignore', 'pipe', 'pipe'] });
        reusable = stamp?.hash === hash && stamp?.installed === installed;
      }
    } catch { /* A broken or old owned venv is backed up and rebuilt below. */ }
  }
  let backup;
  try {
    if (!reusable) {
      if (fs.existsSync(venv)) {
        backup = `${venv}.backup-${Date.now()}`;
        fs.renameSync(venv, backup);
      }
      console.log(`Creating xiaobei Python ${pin.version} environment: ${venv}`);
      run(basePython, ['-m', 'venv', venv], { env });
    }
    if (process.platform === 'win32') {
      // Native PowerShell and Git Bash must agree on both standard command names.
      for (const name of ['python3.exe', 'python3.12.exe']) {
        const target = path.join(bin, name);
        if (!fs.existsSync(target)) fs.copyFileSync(python, target);
      }
    }
    const info = inspectPython(python, env);
    if (!samePath(info.prefix, venv) || !samePath(info.base, base)) throw new Error('Python did not select the managed venv.');
    run(python, ['-m', 'pip', '--version'], { env, stdio: 'ignore' });
    const stampFile = path.join(venv, '.xiaobei-dependencies.json');
    const stamp = readJSON(stampFile);
    const installed = () => run(python, ['-m', 'pip', 'list', '--format=json', '--disable-pip-version-check'], { env, stdio: ['ignore', 'pipe', 'inherit'] });
    if (stamp?.hash !== hash || stamp?.installed !== installed()) {
      const reqFile = path.join(venv, '.xiaobei-requirements.txt');
      fs.writeFileSync(reqFile, requirements);
      if (requirements.trim()) run(python, ['-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location', '--index-url', process.env.XIAOBEI_PYPI_INDEX_URL || process.env.PIP_INDEX_URL || 'https://mirrors.aliyun.com/pypi/simple/', '-r', reqFile], { env });
      run(python, ['-m', 'pip', 'check'], { env });
      writeJSON(stampFile, { hash, installed: installed(), key: pin.key });
    } else {
      run(python, ['-m', 'pip', 'check'], { env, stdio: 'ignore' });
      console.log('Python skill dependencies already installed in managed venv');
    }
    writeJSON(path.join(venv, '.xiaobei-runtime.json'), { key: pin.key, sha256: pin.sha256, base });
  } catch (error) {
    if (backup) {
      fs.rmSync(venv, { recursive: true, force: true });
      fs.renameSync(backup, venv);
    } else if (!reusable) {
      // First migration has no previous owned venv; discard our incomplete new one.
      fs.rmSync(venv, { recursive: true, force: true });
    }
    throw error;
  }
  if (backup) console.log(`Previous Python environment preserved: ${backup}`);
  console.log(`Managed Python ready: ${python}`);
  return runtimePaths(root);
}

export async function installPython(root) {
  root = path.resolve(root);
  fs.mkdirSync(path.join(root, 'tools'), { recursive: true });
  const lock = path.join(root, 'tools', '.python-install.lock');
  let fd;
  try { fd = fs.openSync(lock, 'wx', 0o600); }
  catch (error) { if (error.code === 'EEXIST') throw new Error(`Another Python installation is active, or a previous install was interrupted. Inspect ${lock} before retrying.`); throw error; }
  fs.writeSync(fd, JSON.stringify({ pid: process.pid }));
  try { return await installUnlocked(root); }
  finally { fs.closeSync(fd); fs.rmSync(lock); }
}

export function configurePython(root, configFile) {
  const { bin } = runtimePaths(root);
  const before = fs.readFileSync(configFile, 'utf8');
  const config = JSON.parse(before);
  function prepend(exec) {
    if (exec.pathPrepend !== undefined && (!Array.isArray(exec.pathPrepend) || exec.pathPrepend.some(p => typeof p !== 'string'))) throw new Error('Invalid tools.exec.pathPrepend; existing config preserved.');
    exec.pathPrepend = [bin, ...(exec.pathPrepend || []).filter(p => p !== bin)];
  }
  config.tools ??= {};
  config.tools.exec ??= {};
  prepend(config.tools.exec);
  // An agent array overrides the global value; retain custom entries after our runtime.
  for (const agent of Object.values(config.agents?.entries || {})) {
    if (agent?.tools?.exec?.pathPrepend !== undefined) prepend(agent.tools.exec);
  }
  const after = JSON.stringify(config, null, 2) + '\n';
  if (after !== before) {
    if (fs.readFileSync(configFile, 'utf8') !== before) throw new Error('Configuration changed while preparing Python paths; retry.');
    writeJSON(configFile, config);
  }
}

export function configurePythonServiceEnv(root, file) {
  if (!fs.existsSync(file)) return;
  const before = fs.readFileSync(file, 'utf8');
  const newline = before.includes('\r\n') ? '\r\n' : '\n';
  const lines = before.split(/\r?\n/);
  const entries = lines.filter(line => /^(?:export )?PATH=/.test(line));
  const old = entries.at(-1) || '';
  const exported = old.startsWith('export ') || (!old && lines.some(line => line.startsWith('export ')));
  let value = old.replace(/^(?:export )?PATH=/, '');
  const bin = runtimePaths(root).bin;
  const quote = text => "'" + text.replaceAll("'", "'\\''") + "'";
  let line;
  if (exported) {
    // Preserve the existing shell expression without evaluating it.
    const prefix = `export PATH=${quote(bin)}:`;
    line = old.startsWith(prefix) ? old : prefix + (value || quote(process.env.PATH || '/usr/bin:/bin'));
  } else {
    if (/^(["']).*\1$/.test(value)) value = value.slice(1, -1);
    const parts = (value || process.env.PATH || '/usr/bin:/bin').split(path.delimiter).filter(p => p !== bin);
    line = `PATH=${bin}${path.delimiter}${parts.join(path.delimiter)}`;
  }
  const variables = {
    VIRTUAL_ENV: runtimePaths(root).venv,
    PYTHON: runtimePaths(root).python,
    PYTHONNOUSERSITE: '1',
    PYTHONHOME: '',
    PYTHONPATH: '',
  };
  const owned = /^(?:export )?(?:PATH|VIRTUAL_ENV|PYTHON|PYTHONNOUSERSITE|PYTHONHOME|PYTHONPATH)=/;
  const retained = lines.filter(item => !owned.test(item));
  while (retained.at(-1) === '') retained.pop();
  const additions = Object.entries(variables).map(([key, value]) => exported ? `export ${key}=${quote(value)}` : `${key}=${value}`);
  const after = [...retained, line, ...additions].join(newline) + newline;
  if (after !== before) fs.writeFileSync(file, after);
}

export function syncPythonGuidance(root, configFile) {
  const config = readJSON(configFile);
  const seen = new Set();
  for (const agent of Object.values(config?.agents?.entries || {})) {
    if (typeof agent?.workspace !== 'string') continue;
    const workspace = path.resolve(agent.workspace.startsWith('~/') ? path.join(homedir(), agent.workspace.slice(2)) : agent.workspace);
    if (seen.has(workspace)) continue;
    seen.add(workspace);
    const soul = path.join(workspace, 'SOUL.md');
    const agents = path.join(workspace, 'AGENTS.md');
    if (!fs.existsSync(soul) || !fs.existsSync(agents)) continue;
    const type = /^crew-type:[ \t]*(\S+)/im.exec(fs.readFileSync(soul, 'utf8'))?.[1].toLowerCase();
    if (type !== 'internal') continue;
    const args = ['python-runtime', agents, runtimePaths(root).venv];
    run(runtimePaths(root).python, [path.join(root, 'scripts/lib/workspace-guides.py'), ...args], {env: runtimeEnvironment(root)});
  }
}

async function main(argv) {
  const [action, ...args] = argv;
  const opts = {};
  for (let i = 0; i < args.length; i += 2) {
    if (!['--root', '--output', '--platform', '--config', '--env-file'].includes(args[i]) || !args[i + 1]) throw new Error('Usage: python-runtime.mjs install|bundle|configure|service-env --root ROOT [--output DIR --platform PLATFORM | --config FILE | --env-file FILE]');
    opts[args[i].slice(2)] = args[i + 1];
  }
  const root = path.resolve(opts.root || fileURLToPath(new URL('../', import.meta.url)));
  configureInstallationNetwork();
  if (action === 'install') await installPython(root);
  else if (action === 'bundle' && opts.output && opts.platform) console.log(await bundlePython(root, path.resolve(opts.output), opts.platform));
  else if (action === 'configure' && opts.config) {
    const configFile = path.resolve(opts.config);
    configurePython(root, configFile);
    syncPythonGuidance(root, configFile);
  }
  else if (action === 'service-env' && opts['env-file']) configurePythonServiceEnv(root, path.resolve(opts['env-file']));
  else throw new Error('Expected install, bundle or configure action.');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1; });
}

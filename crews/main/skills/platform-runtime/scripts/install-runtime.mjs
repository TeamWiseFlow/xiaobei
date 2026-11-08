#!/usr/bin/env node
import fs from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve, basename, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const hash = (data, algorithm = 'sha256', encoding = 'hex') => createHash(algorithm).update(data).digest(encoding);
const readJson = async path => JSON.parse(await fs.readFile(path, 'utf8'));
const profile = await readJson(join(root, 'runtime-profile.json'));
const sourcePackage = await readJson(join(root, 'package.json'));
const fingerprint = hash(Buffer.concat(await Promise.all(['package.json', 'runtime-profile.json', 'scripts/install-runtime.mjs'].map(path => fs.readFile(join(root, path))))));
const cache = join(root, '.runtime');
const modules = join(root, 'node_modules');

// The fixed npm release contains ordinary files/directories only. Reject other
// archive types or paths rather than extracting a different layout silently.
export async function extractArchive(archive, destination) {
  const tar = gunzipSync(archive, { maxOutputLength: 64 * 1024 * 1024 });
  const string = (header, start, length) => header.subarray(start, start + length).toString().split('\0')[0];
  const seen = new Set();
  for (let offset = 0; offset + 512 <= tar.length;) {
    const header = tar.subarray(offset, offset + 512);
    if (header.every(byte => byte === 0)) break;
    const number = (start, length) => parseInt(string(header, start, length).trim() || '0', 8);
    const size = number(124, 12), checksum = number(148, 8);
    const actual = header.reduce((sum, byte, index) => sum + (index >= 148 && index < 156 ? 32 : byte), 0);
    if (!Number.isSafeInteger(size) || size < 0 || checksum !== actual || offset + 512 + size > tar.length) throw new Error('Invalid package archive');
    const prefix = string(header, 345, 155);
    const name = (prefix ? prefix + '/' : '') + string(header, 0, 100);
    if (!name.startsWith('package/') || name.includes('\\') || name.split('/').some(part => part === '..') || seen.has(name)) throw new Error('Unexpected package archive path');
    seen.add(name);
    const target = resolve(destination, name);
    if (!target.startsWith(resolve(destination) + sep)) throw new Error('Package archive path outside staging directory');
    const type = string(header, 156, 1);
    if (type === '5') await fs.mkdir(target, { recursive: true });
    else if (type === '0' || !type) {
      await fs.mkdir(dirname(target), { recursive: true });
      await fs.writeFile(target, tar.subarray(offset + 512, offset + 512 + size));
    } else throw new Error('Unsupported package archive entry type');
    offset += 512 + Math.ceil(size / 512) * 512;
  }
  await fs.access(join(destination, 'package/package.json'));
}

export async function prunePackage(directory) {
  const pkg = await readJson(join(directory, 'package.json'));
  if (pkg.name !== profile.package || pkg.version !== profile.version) throw new Error('Unexpected platform package version');
  if (JSON.stringify(pkg.dependencies) !== JSON.stringify(profile.dependencies)) throw new Error('Platform dependency layout changed; review the profile before upgrading');
  const registryPath = join(directory, 'dist/platforms/index.js');
  const registry = await fs.readFile(registryPath, 'utf8');
  if (hash(registry) !== profile.registrySha256) throw new Error('Platform registry changed; review the profile before upgrading');
  const platformDirs = await fs.readdir(join(directory, 'dist/platforms'), { withFileTypes: true });
  const actual = platformDirs.filter(entry => entry.isDirectory() && !entry.name.startsWith('_')).map(entry => entry.name).sort();
  if (JSON.stringify(actual) !== JSON.stringify([...profile.platforms].sort())) throw new Error('Unexpected platform package scope');
  for (const platform of profile.platforms) await fs.access(join(directory, 'dist/platforms', platform, 'index.js'));
  for (const entry of await fs.readdir(join(directory, 'static'), { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.name.startsWith('_') && !profile.platforms.includes(entry.name)) throw new Error('Unexpected platform assets');
  }
  if (!profile.businessAssets || Object.keys(profile.businessAssets).length !== 4) throw new Error('Missing business asset profile');
  for (const [name, digest] of Object.entries(profile.businessAssets)) {
    if (!/^static\/(?:x|tiktok|kuaishou)\/[\w/.-]+\.json$/.test(name) || name.split('/').includes('..') || !/^[a-f0-9]{64}$/.test(digest)) throw new Error('Invalid business asset profile');
    if (hash(await fs.readFile(join(directory, name))) !== digest) throw new Error('Business asset changed: ' + name);
  }
  const contract = await readJson(join(directory, 'runtime-contract.json'));
  if (contract.version !== 1 || contract.signingMode !== 'relay' || !/^[A-Z][A-Z0-9_]{1,63}$/.test(contract.stateEnvironment || '')
      || !/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(contract.errorExport || '')
      || !/^[A-Za-z0-9_.-]{1,128}$/.test(contract.rawSymbol || '')) throw new Error('Invalid runtime adapter contract');
}

export async function preparedArchive() {
  const filename = profile.artifact?.filename;
  if (!filename || filename !== basename(filename)) throw new Error('Invalid prepared artifact name');
  const candidates = [process.env.XIAOBEI_PLATFORM_RUNTIME_ARCHIVE,
    join(process.env.XIAOBEI_CACHE_DIR || join(homedir(), '.xiaobei/cache'), filename), join(cache, filename)].filter(Boolean);
  let archive;
  for (const file of candidates) {
    try { archive = await fs.readFile(file); break; }
    catch (error) { if (error.code !== 'ENOENT' || file === process.env.XIAOBEI_PLATFORM_RUNTIME_ARCHIVE) throw error; }
  }
  if (!archive) {
    const url = new URL(profile.artifact.url);
    if (url.protocol !== 'https:' || url.hostname !== 'github.com'
        || !url.pathname.startsWith('/TeamWiseFlow/xiaobei/releases/download/')) throw new Error('Invalid prepared artifact location');
    const response = await fetch(url, { signal: AbortSignal.timeout(120000) });
    if (!response.ok) throw new Error('Prepared platform artifact is unavailable; preload the fixed package into the install cache');
    const chunks = [];
    let size = 0;
    for await (const chunk of response.body) {
      size += chunk.length;
      if (size > 64 * 1024 * 1024) throw new Error('Prepared platform artifact is too large');
      chunks.push(chunk);
    }
    archive = Buffer.concat(chunks);
  }
  if ('sha512-' + hash(archive, 'sha512', 'base64') !== profile.integrity) throw new Error('Platform package integrity mismatch; installation stopped');
  return archive;
}

async function fileHashes(directory) {
  const files = {};
  async function visit(current) {
    const entries = await fs.readdir(current, { withFileTypes: true });
    for (const entry of entries.sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)) {
      const path = join(current, entry.name);
      if (entry.isDirectory()) await visit(path);
      else if (entry.isFile()) files[relative(directory, path).split(sep).join('/')] = hash(await fs.readFile(path));
      else throw new Error('Unexpected link in platform package');
    }
  }
  await visit(directory);
  return files;
}

async function validate(directory, marker, archivePath) {
  if (marker.fingerprint !== fingerprint) throw new Error('Runtime installation profile changed');
  if (hash(await fs.readFile(archivePath)) !== marker.archiveSha256) throw new Error('Prepared runtime archive missing or changed');
  const pkgRoot = join(directory, profile.package);
  const pkg = await readJson(join(pkgRoot, 'package.json'));
  if (pkg.version !== profile.version || JSON.stringify(pkg.dependencies) !== JSON.stringify(profile.dependencies)) throw new Error('Runtime package does not match the platform profile');
  if (JSON.stringify(await fileHashes(pkgRoot)) !== JSON.stringify(marker.files)) throw new Error('Runtime package files are incomplete or changed');
  for (const excluded of profile.excludeDependencies) {
    try { await fs.access(join(directory, excluded)); } catch (error) { if (error.code === 'ENOENT') continue; throw error; }
    throw new Error('Excluded platform dependency is installed: ' + excluded);
  }
  const require = createRequire(join(pkgRoot, 'package.json'));
  for (const [name, version] of Object.entries(profile.dependencies)) {
    let dependency;
    for (const search of require.resolve.paths(name + '/package.json') || []) {
      try { dependency = await readJson(join(search, name, 'package.json')); break; } catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    if (dependency?.version !== version) throw new Error('Runtime dependency missing or has an unexpected version: ' + name);
  }
  probeRuntime(directory);
}

function probeRuntime(directory) {
  // Also catches missing transitive/native modules when a matching installer
  // hash would otherwise skip a damaged installation. This makes no requests.
  const probe = profile.platforms.map(id => `await import(${JSON.stringify(join(directory, profile.package, 'dist/platforms', id, 'web/commands.js'))});`).join('\n') + `\nconst require = (await import('node:module')).createRequire(${JSON.stringify(join(directory, profile.package, 'package.json'))}); if(!(await require('qrcode').toDataURL('runtime-install-check')).startsWith('data:image/png;')) throw new Error('QR encoder unavailable'); const {createTransport}=await import(require.resolve('wreq-js')); const transport=await createTransport({browser:'chrome_131'}); await transport.close();`;
  const contract = JSON.parse(readFileSync(join(directory, profile.package, 'runtime-contract.json'), 'utf8'));
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', probe], { cwd: dirname(directory), env: { ...process.env, [contract.stateEnvironment]: join(dirname(directory), '.runtime/probe-state') }, encoding: 'utf8', timeout: 60000 });
  if (result.error || result.status !== 0) throw new Error('Prepared platform runtime cannot load on this machine: ' + (result.error?.message || result.stderr));
}

function npm(options, cwd, args, capture = false) {
  const result = spawnSync(options.npmCli ? process.execPath : 'npm', options.npmCli ? [options.npmCli, ...args] : args, { cwd, stdio: capture ? 'pipe' : 'inherit', encoding: 'utf8', timeout: 600000 });
  if (result.error || result.status !== 0) throw new Error('Platform runtime npm step failed' + (result.error ? ': ' + result.error.message : '') + (capture ? '\n' + result.stderr : ''));
  return capture ? JSON.parse(result.stdout) : undefined;
}

async function install(options) {
  const lock = join(root, '.runtime-install-lock');
  try { await fs.mkdir(lock); } catch (error) { if (error.code !== 'EEXIST') throw error; throw new Error('Another platform runtime installation is running'); }
  let stage, preserveStage = false;
  try {
    stage = await fs.mkdtemp(join(root, '.runtime-install-'));
    const archive = await preparedArchive();
    await extractArchive(archive, stage);
    const packageDir = join(stage, 'package');
    await prunePackage(packageDir);
    const expectedFiles = await fileHashes(packageDir);
    await fs.mkdir(join(stage, '.runtime'));
    await fs.writeFile(join(stage, '.runtime/platform-backend.tgz'), archive);
    await fs.writeFile(join(stage, '.runtime', profile.artifact.filename), archive);
    await fs.writeFile(join(stage, 'package.json'), JSON.stringify(sourcePackage, null, 2) + '\n');
    npm(options, stage, ['install', '--omit=dev', '--no-audit', '--no-fund', '--loglevel=warn', `--registry=${options.registry}`]);
    const archivePath = join(stage, '.runtime/platform-backend.tgz');
    const marker = { fingerprint, version: profile.version, platforms: profile.platforms, archiveSha256: hash(await fs.readFile(archivePath)), files: expectedFiles };
    await validate(join(stage, 'node_modules'), marker, archivePath);
    await fs.writeFile(join(stage, '.runtime/install.json'), JSON.stringify(marker, null, 2) + '\n');
    const targets = ['node_modules', '.runtime', 'package-lock.json'];
    const replaced = [], backups = [];
    try {
      for (const name of targets) {
        try { await fs.rename(join(root, name), join(stage, 'previous-' + name)); backups.push(name); } catch (error) { if (error.code !== 'ENOENT') throw error; }
        await fs.rename(join(stage, name), join(root, name));
        replaced.push(name);
      }
    } catch (error) {
      try {
        for (const name of replaced.reverse()) await fs.rm(join(root, name), { recursive: true, force: true });
        for (const name of backups.reverse()) await fs.rename(join(stage, 'previous-' + name), join(root, name));
      } catch (restoreError) {
        preserveStage = true;
        throw new Error(`Runtime replacement and rollback failed; old files retained in ${stage}: ${restoreError.message}`);
      }
      throw error;
    }
    console.log('Platform runtime installed and verified: ' + profile.platforms.join(', '));
  } finally {
    if (stage && !preserveStage) await fs.rm(stage, { recursive: true, force: true });
    await fs.rm(lock, { recursive: true, force: true });
  }
}

async function main(args) {
  if (args.length === 1 && args[0] === '--check') return validate(modules, await readJson(join(cache, 'install.json')), join(cache, 'platform-backend.tgz'));
  const options = { registry: process.env.npm_config_registry || 'https://registry.npmmirror.com' };
  for (let index = 0; index < args.length; index += 2) {
    if (!['--registry', '--npm-cli'].includes(args[index]) || !args[index + 1]) throw new Error('Use the project skill dependency installer');
    options[args[index] === '--npm-cli' ? 'npmCli' : 'registry'] = args[index + 1];
  }
  await install(options);
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main(process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1; });

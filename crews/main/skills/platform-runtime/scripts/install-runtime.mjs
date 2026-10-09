#!/usr/bin/env node
import fs from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve, basename, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

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
  const retained = Object.keys(pkg.dependencies).filter(name => !profile.excludeDependencies.includes(name)).sort();
  if (JSON.stringify(retained) !== JSON.stringify(Object.keys(profile.dependencies).sort()) || profile.excludeDependencies.some(name => !pkg.dependencies[name])) throw new Error('Platform dependency layout changed; review the profile before upgrading');
  const registryPath = join(directory, 'dist/platforms/index.js');
  const registry = await fs.readFile(registryPath, 'utf8');
  if (hash(registry) !== profile.registrySha256) throw new Error('Platform registry changed; review the profile before upgrading');
  const platformDirs = await fs.readdir(join(directory, 'dist/platforms'), { withFileTypes: true });
  const excluded = platformDirs.filter(entry => entry.isDirectory() && !entry.name.startsWith('_') && !profile.platforms.includes(entry.name)).map(entry => entry.name);
  for (const platform of profile.platforms) await fs.access(join(directory, 'dist/platforms', platform, 'index.js'));
  let pruned = registry;
  for (const platform of excluded) {
    const line = `import ${platform} from './${platform}/index.js';\n`;
    if (!pruned.includes(line)) throw new Error('Unexpected platform import: ' + platform);
    pruned = pruned.replace(line, '');
    await fs.rm(join(directory, 'dist/platforms', platform), { recursive: true });
  }
  const declaration = /export const PLATFORMS = \[([^\]]+)\];/;
  const original = pruned.match(declaration);
  if (!original) throw new Error('Unexpected platform registration');
  const selected = original[1].split(',').map(id => id.trim()).filter(id => profile.platforms.includes(id));
  if (selected.length !== profile.platforms.length) throw new Error('Incomplete platform registration');
  pruned = pruned.replace(declaration, `export const PLATFORMS = [${selected.join(', ')}];`);
  await fs.writeFile(registryPath, pruned);
  for (const entry of await fs.readdir(join(directory, 'static'), { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.name.startsWith('_') && !profile.platforms.includes(entry.name)) await fs.rm(join(directory, 'static', entry.name), { recursive: true });
  }
  // Only dependency/registration metadata changes. Retained business modules
  // and shared modules are copied verbatim from the integrity-checked release.
  pkg.dependencies = profile.dependencies;
  await fs.writeFile(join(directory, 'package.json'), JSON.stringify(pkg, null, 2) + '\n');
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
  if (pkg.version !== profile.version || JSON.stringify(pkg.dependencies) !== JSON.stringify(profile.dependencies)) throw new Error('Runtime package does not match the four-platform profile');
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
  const probe = profile.platforms.map(id => `await import(${JSON.stringify(join(directory, profile.package, 'dist/platforms', id, 'web/commands.js'))});`).join('\n') + `\nconst require = (await import('node:module')).createRequire(${JSON.stringify(join(directory, profile.package, 'package.json'))}); const {createCanvas}=require('@napi-rs/canvas'); if(!createCanvas(2,2).toBuffer('image/png').length) throw new Error('Canvas unavailable'); const cv=await require('@techstark/opencv-js'); const mat=new cv.Mat(); mat.delete(); const {createTransport}=await import(require.resolve('wreq-js')); const transport=await createTransport({browser:'chrome_131'}); await transport.close();`;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', probe], { cwd: dirname(directory), env: { ...process.env, CATBUS_HOME: join(dirname(directory), '.runtime/probe-state') }, encoding: 'utf8', timeout: 60000 });
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
    const packed = npm(options, stage, ['pack', `${profile.package}@${profile.version}`, '--json', '--ignore-scripts', '--workspaces=false', `--registry=${options.registry}`], true)[0];
    if (packed.filename !== basename(packed.filename)) throw new Error('Unexpected package archive filename');
    const archive = await fs.readFile(join(stage, packed.filename));
    if ('sha512-' + hash(archive, 'sha512', 'base64') !== profile.integrity) throw new Error('Platform package integrity mismatch; installation stopped');
    await extractArchive(archive, stage);
    const packageDir = join(stage, 'package');
    await prunePackage(packageDir);
    const expectedFiles = await fileHashes(packageDir);
    await fs.mkdir(join(stage, '.runtime'));
    const slim = npm(options, stage, ['pack', packageDir, '--json', '--ignore-scripts', '--workspaces=false', '--pack-destination', join(stage, '.runtime')], true)[0];
    await fs.rename(join(stage, '.runtime', slim.filename), join(stage, '.runtime/catbus-cli.tgz'));
    await fs.writeFile(join(stage, 'package.json'), JSON.stringify(sourcePackage, null, 2) + '\n');
    npm(options, stage, ['install', '--omit=dev', '--no-audit', '--no-fund', '--loglevel=warn', `--registry=${options.registry}`]);
    const archivePath = join(stage, '.runtime/catbus-cli.tgz');
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
    console.log('Four-platform runtime installed and verified: ' + profile.platforms.join(', '));
  } finally {
    if (stage && !preserveStage) await fs.rm(stage, { recursive: true, force: true });
    await fs.rm(lock, { recursive: true, force: true });
  }
}

async function main(args) {
  if (args.length === 1 && args[0] === '--check') return validate(modules, await readJson(join(cache, 'install.json')), join(cache, 'catbus-cli.tgz'));
  const options = { registry: process.env.npm_config_registry || 'https://registry.npmmirror.com' };
  for (let index = 0; index < args.length; index += 2) {
    if (!['--registry', '--npm-cli'].includes(args[index]) || !args[index + 1]) throw new Error('Use the project skill dependency installer');
    options[args[index] === '--npm-cli' ? 'npmCli' : 'registry'] = args[index + 1];
  }
  await install(options);
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main(process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1; });

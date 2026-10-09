import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { packageRoot, PlatformError, platforms } from './backend.mjs';

const cache = new Map();
async function platformMetadata(platform) {
  if (!cache.has(platform)) {
    const root = packageRoot();
    const { default: entry } = await import(pathToFileURL(join(root, 'dist/platforms', platform, 'index.js')));
    const options = await import(pathToFileURL(join(root, 'dist/core/options.js')));
    const argv = await import(pathToFileURL(join(root, 'dist/cli/argv.js')));
    const { z } = await import(pathToFileURL(join(root, 'node_modules/zod/index.js'))).catch(async () => {
      // npm hoists zod beside catbus-cli.
      const { createRequire } = await import('node:module');
      return import(pathToFileURL(createRequire(join(root, 'package.json')).resolve('zod')));
    });
    cache.set(platform, { entry, ...options, ...argv, z });
  }
  return cache.get(platform);
}
export async function schemaFor(platform, key) {
  const { entry, describeOption, flagName } = await platformMetadata(platform);
  const command = entry.endpoints.web.commands.get(key);
  if (!command || command.status !== 'implemented') throw new PlatformError('UNSUPPORTED', '该接口没有实现', 4);
  return {
    command: key, args: command.args, note: command.note,
    ...(key === 'item publish' && platforms[platform]?.video_publish ? { constraints: { video: platforms[platform].video_publish } } : {}),
    options: Object.fromEntries(Object.entries(command.options).filter(([name]) => name !== 'all').map(([name, schema]) => ['--' + flagName(name), describeOption(schema)])),
  };
}
export async function xTextPreview(text, thread = []) {
  // 与保留的发布路由共用计数函数，不重写计数或修改上游业务模块。
  const { tweetWeight, TWEET_WEIGHT_LIMIT } = await import(pathToFileURL(join(packageRoot(), 'dist/platforms/x/web/api.js')));
  const posts = [text, ...thread].map((content, index) => {
    const weightedLength = tweetWeight(content);
    return { position: index + 1, weighted_length: weightedLength, mode: weightedLength > TWEET_WEIGHT_LIMIT ? 'long' : 'standard' };
  });
  const longPosts = posts.filter(post => post.mode === 'long');
  return {
    text_check: { normal_weight_limit: TWEET_WEIGHT_LIMIT, posts, requires_premium: longPosts.length > 0, premium_status: 'not_checked' },
    warnings: longPosts.map(post => `第 ${post.position} 条正文权重 ${post.weighted_length}，超过 ${TWEET_WEIGHT_LIMIT}，将自动走长推，需要账号具备 X Premium 长推权限；当前未验证订阅。未订阅或权限未确认时，先精简该条正文再预览，不要直接提交`),
  };
}
export async function validateArgs(platform, key, args) {
  const { entry, parseArgv, collectOptionKinds, z } = await platformMetadata(platform);
  const command = entry.endpoints.web.commands.get(key);
  if (!command || command.status !== 'implemented') throw new PlatformError('UNSUPPORTED', '该接口没有实现', 4);
  let parsed;
  try { parsed = parseArgv(args, collectOptionKinds([entry])); }
  catch (error) { throw new PlatformError('USAGE', error.message); }
  if (parsed.global.endpoint || parsed.global.output || parsed.global.yes || parsed.options.all) throw new PlatformError('USAGE', '不能覆盖端、输出格式或无限翻页');
  for (const option of Object.keys(parsed.options)) {
    if (!(option in command.options)) throw new PlatformError('USAGE', '此命令不支持选项 ' + option);
  }
  const minimum = command.args.filter(arg => !arg.optional).length;
  if (parsed.positionals.length < minimum || parsed.positionals.length > command.args.length) throw new PlatformError('USAGE', '参数数量不符；必需参数：' + command.args.filter(arg => !arg.optional).map(arg => arg.name).join(', '));
  const checked = z.object(command.options).safeParse(parsed.options);
  if (!checked.success) throw new PlatformError('USAGE', '选项取值不符合本平台接口，请通过 methods 查看 schema');
  const positional = Object.fromEntries(command.args.map((arg, index) => [arg.name, parsed.positionals[index] ?? arg.default]));
  const problem = command.check?.(positional, checked.data);
  if (problem) throw new PlatformError('USAGE', problem);
  return { args: positional, options: checked.data, global: parsed.global };
}

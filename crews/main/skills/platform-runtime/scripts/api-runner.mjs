// 固定版本平台传输的进程入口。浏览器导入会话沿用实际 UA，不重写依赖文件。
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { packageRoot, runtimeContract, credential, backendAccount, platforms } from './backend.mjs';
import { instrumentRequests } from './diagnostics.mjs';
import { isVideoPublish, videoTransportPolicy, videoRequestPolicy } from './weibo-video.mjs';
import { publicationObserver, publicationResult } from './publication.mjs';
import { qrObserver } from './kuaishou-qr.mjs';
import { processIdentity } from './login-job.mjs';
import { xPublicationObserver } from './x-publication.mjs';
import { checkXResponse, xArticleRequest } from './x-response.mjs';
import { checkYoutubeMediaResponse } from './youtube-response.mjs';

const [platform, ...args] = process.argv.slice(2);
const root = packageRoot();
const contract = runtimeContract(root);
const stateHome = process.env.PLATFORM_RUNTIME_STATE_HOME || process.env[contract.stateEnvironment];
if (platform === 'kuaishou' && process.env.PLATFORM_API_LOGIN_JOB) {
  const ownerPid = Number(process.env.PLATFORM_API_LOGIN_OWNER_PID);
  const ownerIdentity = processIdentity(ownerPid);
  if (!ownerIdentity) process.exit(2);
  // Also stop if exec is killed without delivering a catchable signal to its
  // owner. The backend must never finish a login as an orphan.
  setInterval(() => { if (processIdentity(ownerPid) !== ownerIdentity) process.exit(2); }, 500).unref();
}
let identity;
let user;
let saved;
try {
  saved = await credential(platform, backendAccount(args), stateHome);
  user = saved.user;
} catch { /* 未登录时身份可为空 */ }
try {
  identity = process.env.PLATFORM_API_IDENTITY_FILE
    ? JSON.parse(await readFile(process.env.PLATFORM_API_IDENTITY_FILE, 'utf8'))
    : saved?.device?.browser_identity;
} catch { /* auth login/status 在没有本地会话时仍须运行 */ }

process.env.NO_PROXY = process.env.no_proxy = '*,0.0.0.0/0,::/0';
const { HttpClient, closeTransports, parseJson } = await import(pathToFileURL(join(root, 'dist/core/http.js')));
if (identity?.userAgent) {
  if (platform === 'x') {
    const { PROFILE } = await import(pathToFileURL(join(root, 'dist/platforms/x/web/profile.js')));
    PROFILE.ua = identity.userAgent;
    PROFILE.acceptLanguage = identity.languages?.join(',') || identity.language || PROFILE.acceptLanguage;
  }
}
const { Output } = await import(pathToFileURL(join(root, 'dist/cli/output.js')));
const RuntimeError = (await import(pathToFileURL(join(root, 'dist/core/errors.js'))))[contract.errorExport];
let requestPolicy;
if (platform === 'weibo' && isVideoPublish(args)) {
  const policy = videoTransportPolicy(platforms.weibo.video_transport);
  if (!policy.valid) {
    process.stdout.write(JSON.stringify({ ok: false, error: { code: 'USAGE', message: policy.message } }) + '\n');
    process.exit(2);
  }
  requestPolicy = (input, client) => videoRequestPolicy(input, client, policy, RuntimeError);
}
const publishing = args[0] === 'item' && args[1] === 'publish' && ['weibo', 'kuaishou'].includes(platform);
const observer = publishing ? publicationObserver(platform, parseJson) : undefined;
const xPublication = platform === 'x' && ['item', 'article'].includes(args[0]) && args[1] === 'publish'
  ? xPublicationObserver() : undefined;
const qr = platform === 'kuaishou' && process.env.PLATFORM_API_LOGIN_JOB && args[0] === 'auth' && args[1] === 'login'
  ? qrObserver(stateHome, parseJson, RuntimeError) : undefined;
const converters = platform === 'weibo' && publishing ? await import(pathToFileURL(join(root, 'dist/platforms/weibo/web/sign.js'))) : {};
const requests = instrumentRequests(HttpClient, { platform, identity: platform === 'youtube' ? undefined : identity,
  requestPolicy: platform === 'x' ? xArticleRequest : qr?.policy || requestPolicy,
  observeRequest: xPublication?.request,
  observeResponse: platform === 'x' ? (input, response) => checkXResponse(input, response, RuntimeError)
    : platform === 'youtube' ? (input, response) => checkYoutubeMediaResponse(input, response, RuntimeError) : qr?.response || observer?.response });
const outputResult = Output.prototype.result;
Output.prototype.result = function (data, options) {
  if (observer?.state.accepted) data = publicationResult(platform, data, { state: observer.state, raw: data?.[Symbol.for(contract.rawSymbol)], user, ...converters });
  return outputResult.call(this, data, options);
};
let acceptedUnparsed = false;
const fail = Output.prototype.fail;
Output.prototype.fail = function (error) {
  if (observer?.state.accepted) {
    // 平台明确接受后，解析失败不会把已经发生的提交变成未知，更不能触发重发。
    acceptedUnparsed = true;
    return this.result(null);
  }
  const request = requests.last();
  if (!request && !xPublication) return fail.call(this, error);
  const detail = error.detail && typeof error.detail === 'object' && !Array.isArray(error.detail) ? error.detail : {};
  return fail.call(this, new RuntimeError(error.code, error.message, { hint: error.hint,
    detail: { ...detail, ...(request ? { request } : {}), ...(xPublication ? { publication: { ...xPublication.state } } : {}) } }));
};
const { run } = await import(pathToFileURL(join(root, 'dist/cli/dispatch.js')));
const code = await run([platform, ...args]);
await closeTransports();
await new Promise(done => process.stdout.write('', done));
await new Promise(done => process.stderr.write('', done));
process.exit(acceptedUnparsed ? 0 : code);

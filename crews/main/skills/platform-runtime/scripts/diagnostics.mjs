// 错误诊断只保留定位所需字段；不转发请求体、响应正文、请求头或 stderr。
import { isVideoSubmit } from './weibo-video.mjs';
const ERROR_CODES = new Set(['ERROR', 'USAGE', 'UNSUPPORTED', 'CONFIRM_REQUIRED', 'AUTH_REQUIRED', 'AUTH_EXPIRED', 'NOT_IMPLEMENTED', 'RISK_CONTROL', 'NETWORK', 'UPSTREAM']);
const SENSITIVE = /cookie|token|authorization|password|secret|ticket|private.?key|api_[sp][ht]|web_[sp][ht]|kw[fwcs]|ts.?sign/i;
const PAIR = /\b(authorization|[\w.-]*token|[\w.-]*secret|password|ticket[\w.-]*|private[_-]?key|[\w.-]*api_[sp][ht]|[\w.-]*web_[sp][ht]|kwscode|kwssectoken|kwfv1|kwfcv1|kww|__NS_[\w]+)(["']?\s*[:=]\s*)((?:bearer|basic)\s+)?("[^"]*"|'[^']*'|[^\s,;&]+)/gi;
const STAGES = {
  '/rest/v2/creator/pc/authority/account/current': 'publish_authority',
  '/rest/cp/works/v2/video/pc/upload/pre': 'upload_pre',
  '/api/upload/resume': 'upload_resume',
  '/api/upload/fragment': 'upload_fragment',
  '/api/upload/complete': 'upload_complete',
  '/rest/cp/works/v2/video/pc/upload/finish': 'upload_finish',
  '/rest/cp/works/v2/common/pc/report': 'cover_report',
  '/rest/cp/works/v2/video/pc/submit': 'video_submit',
  '/rest/cp/works/atlas/pc/publish/submit': 'atlas_submit',
};

function credentialSecrets(saved) {
  const values = new Set();
  const add = value => { if (typeof value === 'string' && value.length >= 4) values.add(value); };
  const walk = (value, depth = 0) => {
    if (depth > 6) return;
    if (typeof value === 'string') add(value);
    else if (value && typeof value === 'object') Object.values(value).forEach(child => walk(child, depth + 1));
  };
  for (const scope of Object.values(saved?.scopes || {})) {
    for (const cookie of Array.isArray(scope?.cookies) ? scope.cookies : []) add(cookie?.value);
    walk(scope?.tokens);
  }
  for (const [key, value] of Object.entries(saved?.device || {})) if (SENSITIVE.test(key)) walk(value);
  return [...values].sort((a, b) => b.length - a.length);
}

export function safeDiagnostic(error, { redact, saved } = {}) {
  const secrets = credentialSecrets(saved);
  const text = value => {
    if (typeof value !== 'string') return undefined;
    // 固定依赖的脱敏规则不可用时，仅返回错误码，关闭文本透传。
    if (!redact) return undefined;
    let clean = String(redact(value)).replace(PAIR, '$1$2***')
      .replace(/\b(?:set-)?cookie["']?\s*[:=]\s*[^\n]*/gi, 'cookie: ***')
      .replace(/--(?:cookie|token|password|secret|ticket|proxy)\s+(?:"[^"]*"|'[^']*'|\S+)/gi, '--credential ***')
      .replace(/https?:\/\/[^\s<>"']+/gi, value => {
        try { const url = new URL(value); return url.origin + url.pathname; } catch { return '[URL]'; }
      });
    for (const secret of secrets) clean = clean.split(secret).join('***');
    return clean.replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '').slice(0, 1200);
  };
  const scalar = value => typeof value === 'number' && Number.isFinite(value) || typeof value === 'boolean' ? value : text(value);
  const diagnostic = { code: ERROR_CODES.has(error?.code) ? error.code : 'UPSTREAM' };
  for (const key of ['message', 'hint']) {
    const value = text(error?.[key]);
    if (value) diagnostic[key] = value;
  }
  if (error?.detail && typeof error.detail === 'object' && !Array.isArray(error.detail)) {
    const detail = {};
    for (const key of ['status', 'result', 'code', 'kind', 'path', 'message', 'reason', 'error_msg']) {
      const value = scalar(error.detail[key]);
      if (value !== undefined) detail[key] = value;
    }
    const request = error.detail.request;
    if (request && typeof request === 'object') {
      const safe = {};
      for (const key of ['stage', 'method', 'host', 'path', 'status', 'content_type', 'transport_error']) {
        const value = scalar(request[key]);
        if (value !== undefined) safe[key] = value;
      }
      if (typeof request.timeout_seconds === 'number' && Number.isFinite(request.timeout_seconds) && request.timeout_seconds > 0) safe.timeout_seconds = request.timeout_seconds;
      if (typeof request.csrf_header_present === 'boolean') safe.csrf_header_present = request.csrf_header_present;
      if (request.video_contract && typeof request.video_contract === 'object') {
        const contract = {};
        for (const key of ['caption_empty', 'photo_status', 'publish_time', 'body_keys', 'kww_length', 'kwfv1_length', 'kwssectoken_length', 'kwscode_length', 'kww_differs_from_kwfv1', 'has_connection', 'has_content_length', 'has_host']) {
          const value = request.video_contract[key];
          if (typeof value === 'boolean' || typeof value === 'number' && Number.isFinite(value)) contract[key] = value;
        }
        if (Object.keys(contract).length) safe.video_contract = contract;
      }
      if (Object.keys(safe).length) detail.request = safe;
    }
    if (Object.keys(detail).length) diagnostic.detail = detail;
  }
  return diagnostic;
}

function describeRequest(platform, input, client) {
  let url;
  try { url = new URL(input.url); } catch { return undefined; }
  const diagnostic = { method: (input.method || 'GET').toUpperCase(), host: url.hostname, path: url.pathname.replace(/[A-Za-z0-9_-]{64,}/g, '***').slice(0, 256) };
  if (platform === 'kuaishou') diagnostic.stage = STAGES[url.pathname] || 'platform_request';
  if (platform === 'weibo') {
    const stage = {
      'fileplatform.api.weibo.com/2/fileplatform/init.json': 'video_init',
      'up.video.weibocdn.com/2/fileplatform/upload.json': 'video_upload',
      'fileplatform.api.weibo.com/2/fileplatform/check.json': 'video_check',
      'weibo.com/ajax/multimedia/output': 'video_transcode',
    }[url.hostname + url.pathname];
    diagnostic.stage = stage || (isVideoSubmit(input) ? 'video_submit' : 'platform_request');
    const seconds = input.timeout ?? client?.options?.timeout ?? 30;
    if (typeof seconds === 'number' && Number.isFinite(seconds) && seconds > 0) diagnostic.timeout_seconds = seconds;
    if (diagnostic.stage === 'video_submit') {
      const headers = Array.isArray(input.headers) ? input.headers : Object.entries(input.headers || {});
      diagnostic.csrf_header_present = headers.some(([name, value]) => name.toLowerCase() === 'x-xsrf-token' && Boolean(value));
    }
  }
  if (platform === 'kuaishou' && url.hostname === 'cp.kuaishou.com' && diagnostic.stage === 'video_submit') {
    const headers = new Map((Array.isArray(input.headers) ? input.headers : Object.entries(input.headers || {})).map(([key, value]) => [key.toLowerCase(), value]));
    const cookies = new Map(String(headers.get('cookie') || '').split(';').map(pair => { const index = pair.indexOf('='); return [pair.slice(0, index).trim(), pair.slice(index + 1).trim()]; }));
    let body;
    try { body = JSON.parse(input.body); } catch { /* 不记录无法解析的正文 */ }
    const kww = String(headers.get('kww') || '');
    const kwfv1 = cookies.get('kwfv1') || '';
    diagnostic.video_contract = {
      ...(body && typeof body === 'object' ? { caption_empty: body.caption === '', photo_status: body.photoStatus, publish_time: body.publishTime, body_keys: Object.keys(body).length } : {}),
      kww_length: kww.length, kwfv1_length: kwfv1.length,
      kwssectoken_length: (cookies.get('kwssectoken') || '').length, kwscode_length: (cookies.get('kwscode') || '').length,
      kww_differs_from_kwfv1: Boolean(kww && kwfv1 && kww !== kwfv1),
      has_connection: headers.has('connection'), has_content_length: headers.has('content-length'), has_host: headers.has('host'),
    };
  }
  return diagnostic;
}

export function instrumentRequests(HttpClient, { platform, identity, requestPolicy, observeResponse } = {}) {
  const original = HttpClient.prototype.request;
  let last;
  HttpClient.prototype.request = async function (input) {
    if (identity?.userAgent) {
      const pairs = Array.isArray(input.headers) ? input.headers : Object.entries(input.headers || {});
      const headers = pairs.filter(([key]) => !/^user-agent$|^sec-ch-ua/i.test(key));
      headers.push(['user-agent', identity.userAgent]);
      input = { ...input, headers };
    }
    const current = describeRequest(platform, input, this);
    last = current;
    let attempted = false;
    try {
      if (requestPolicy) {
        input = requestPolicy(input, this);
        const revised = describeRequest(platform, input, this);
        if (current && revised) Object.assign(current, revised);
      }
      attempted = true;
      const response = await original.call(this, input);
      if (observeResponse) await observeResponse(input, response);
      if (current) {
        current.status = response.status;
        const type = response.headers?.get('content-type')?.split(';')[0].trim();
        if (type && /^[a-z0-9.+-]+\/[a-z0-9.+-]+$/i.test(type)) current.content_type = type;
      }
      return response;
    } catch (error) {
      if (current && attempted) current.transport_error = true;
      throw error;
    }
  };
  return { last: () => last, restore: () => { HttpClient.prototype.request = original; } };
}

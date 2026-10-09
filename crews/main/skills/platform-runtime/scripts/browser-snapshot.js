// 只读当前平台会话；运行库将结果写入私有临时目录，不向终端输出。
(async () => {
  const storage = area => Object.fromEntries(Array.from({ length: area.length }, (_, index) => area.key(index)).filter(Boolean).map(key => [key, area.getItem(key)]));
  const local = storage(localStorage), session = storage(sessionStorage);
  const result = {
    origin: location.origin, user_agent: navigator.userAgent, document_cookie: document.cookie,
    local_storage: local, session_storage: session,
    browser_metrics: { screen_width: screen.width, screen_height: screen.height, inner_width: innerWidth, inner_height: innerHeight, outer_width: outerWidth, outer_height: outerHeight, language: navigator.language, languages: navigator.languages, platform: navigator.platform, hardware_concurrency: navigator.hardwareConcurrency },
  };
  const aliases = {
    ticketguardprivatekey: 'ticket_guard_private_key',
    ticketguardencryptticket: 'ticket_guard_encrypt_ticket',
    ticketguardtssign: 'ticket_guard_ts_sign',
    ticketguardversion: 'ticket_guard_version', ticketguarditerationversion: 'ticket_guard_iteration_version',
    ticketguardpublickey: 'ticket_guard_public_key', ticketguardwebversion: 'ticket_guard_web_version',
    deviceid: 'device_id', odinid: 'odin_id',
  };
  const guardedAliases = { privatekey: 'ticket_guard_private_key', encryptticket: 'ticket_guard_encrypt_ticket', tssign: 'ticket_guard_ts_sign' };
  const pending = [];
  function visit(value, key = '', depth = 0, inGuard = false) {
    if (depth > 8 || value == null) return;
    inGuard ||= /ticket.*guard/i.test(key);
    const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, '');
    const name = aliases[normalized] || (inGuard ? guardedAliases[normalized] : undefined);
    if (typeof CryptoKey !== 'undefined' && value instanceof CryptoKey) {
      if (value.type === 'private' && value.extractable && name === 'ticket_guard_private_key') pending.push(crypto.subtle.exportKey('pkcs8', value).then(buffer => {
        const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
        result.ticket_guard_private_key = '-----BEGIN PRIVATE KEY-----\n' + base64.match(/.{1,64}/g).join('\n') + '\n-----END PRIVATE KEY-----\n';
      }).catch(() => {}));
      return;
    }
    if (typeof value === 'string') {
      if (name && value && !result[name]) result[name] = value;
      try { visit(JSON.parse(value), key, depth + 1, inGuard); } catch { /* 普通字符串 */ }
    } else if (typeof value === 'object') for (const [childKey, child] of Object.entries(value)) visit(child, childKey, depth + 1, inGuard);
  }
  visit(local); visit(session);
  try {
    const hydration = JSON.parse(document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__')?.textContent || '{}');
    const context = hydration.__DEFAULT_SCOPE__?.['webapp.app-context'] || {};
    if (context.wid) result.device_id = String(context.wid);
    if (context.odinId) result.odin_id = String(context.odinId);
  } catch { /* 页面不提供 hydration */ }
  // security-sdk 可能使用 IndexedDB；只检查名称匹配的库，不读取其他平台数据。
  try {
    if (location.hostname.endsWith('tiktok.com') && indexedDB.databases) {
      const databases = (await indexedDB.databases()).filter(entry => /ticket|guard|security|passport/i.test(entry.name || ''));
      for (const entry of databases.slice(0, 8)) {
        const database = await new Promise((done, reject) => {
          const request = indexedDB.open(entry.name);
          request.onsuccess = () => done(request.result); request.onerror = () => reject(request.error);
        });
        try {
          for (const name of Array.from(database.objectStoreNames).slice(0, 16)) {
            const records = await new Promise((done, reject) => {
              const request = database.transaction(name).objectStore(name).getAll(undefined, 100);
              request.onsuccess = () => done(request.result); request.onerror = () => reject(request.error);
            });
            visit(records, entry.name + ':' + name);
          }
        } finally { database.close(); }
      }
    }
  } catch { /* 不可导出的私钥不补造 */ }
  await Promise.all(pending);
  return result;
})()

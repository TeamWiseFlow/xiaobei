// 发布确认与公开链接分开处理；只从本次提交或精确关联的本人作品取 ID。
export function fullId(value) {
  if (typeof value === 'number') return Number.isSafeInteger(value) && value > 0 ? String(value) : null;
  return typeof value === 'string' && /^[A-Za-z0-9:_-]+$/.test(value) && value !== '0' ? value : null;
}
const decimalId = value => {
  const id = fullId(value);
  return id && /^[1-9]\d*$/.test(id) ? id : null;
};
const videoMediaId = value => decimalId(value) || (typeof value === 'string' && /^1034:[1-9]\d*$/.test(value) ? value.slice(5) : null);
const plainObject = value => value && typeof value === 'object' && !Array.isArray(value);

export function publicationObserver(platform, parseJson) {
  const state = { accepted: false };
  return {
    state,
    async response(input, response) {
      if ((input.method || 'GET').toUpperCase() !== 'POST' || response.status !== 200) return;
      const url = new URL(input.url);
      const weibo = platform === 'weibo' && url.origin === 'https://weibo.com' && url.pathname === '/ajax/statuses/update';
      const kuaishou = platform === 'kuaishou' && url.origin === 'https://cp.kuaishou.com' && ['/rest/cp/works/v2/video/pc/submit', '/rest/cp/works/atlas/pc/publish/submit'].includes(url.pathname);
      if (!weibo && !kuaishou) return;
      let body;
      try { body = await parseJson(response.clone()); } catch { return; }
      if (weibo ? body?.ok !== 1 : body?.result !== 1) return;
      state.accepted = true;
      if (weibo) {
        const form = Array.isArray(input.form) ? Object.fromEntries(input.form) : input.form;
        try { state.media_id = videoMediaId(JSON.parse(form?.media)?.media_id); } catch { /* 图文没有视频关联 ID */ }
        // 不保存响应正文；这些字段只用于识别本次提交对应的微博。
        const object = plainObject(body.data?.mblog) ? body.data.mblog : plainObject(body.data) ? body.data : {};
        state.id = decimalId(object.idstr) || decimalId(object.mid) || decimalId(object.id);
        const bid = object.mblogid ?? object.bid;
        if (typeof bid === 'string' && /^[A-Za-z0-9]{1,12}$/.test(bid)) state.bid = bid;
      }
    },
  };
}

export function publicationResult(platform, data, { state, raw, user, midToBid, bidToMid } = {}) {
  if (!state?.accepted || !['weibo', 'kuaishou'].includes(platform)) return data;
  const result = plainObject(data) ? { ...data } : {};
  const publication = { accepted: true };
  if (platform === 'weibo') {
    let id = decimalId(result.id) || state.id;
    if (!id && state.bid && bidToMid && midToBid) {
      const mid = decimalId(bidToMid(state.bid));
      if (mid && midToBid(mid) === state.bid) id = mid;
    }
    const uid = decimalId(result.author?.id) || decimalId(user?.id);
    if (id) {
      result.id = id;
      result.url = uid ? `https://weibo.com/${uid}/${midToBid(id)}` : `https://m.weibo.cn/detail/${id}`;
      publication.id_kind = 'weibo_mid';
    } else {
      result.id = null;
      result.url = null;
    }
    if (state.media_id) {
      publication.media_id = state.media_id;
      result.kind = 'video';
    }
  } else {
    const id = fullId(result.id);
    const publishId = decimalId(raw?.publishId);
    const workId = fullId(raw?.workId) || fullId(raw?.photoId) || fullId(raw?.photoIdStr);
    const publicId = id && /^3[A-Za-z0-9]+$/.test(id) && /[A-Za-z]/.test(id);
    if (id && (id === workId || id === publishId || publicId)) {
      result.id = id;
      publication.id_kind = id === workId ? 'creator_work' : id === publishId ? 'creator_publish' : 'public_work';
      // 数字创作者 ID 不是公开 short-video ID；不能用它拼造分享链接。
      if (!publicId || result.status === 'private') result.url = null;
    } else {
      if (id) publication.upload_id = id;
      result.id = null;
      result.url = null;
    }
  }
  publication.id_pending = !result.id;
  return { ...result, publication };
}

export function completePublication(platform, item, user, converters = {}) {
  if (!plainObject(item)) return null;
  const result = { ...item, id: fullId(item.id) };
  if (!result.id) return null;
  if (platform === 'weibo') {
    const id = decimalId(result.id);
    if (!id) return null;
    const author = decimalId(result.author?.id);
    const own = decimalId(user?.id);
    if (author && own && author !== own) return null;
    result.url = (author || own) ? `https://weibo.com/${author || own}/${converters.midToBid(id)}` : `https://m.weibo.cn/detail/${id}`;
  }
  if (platform === 'kuaishou' && !result.url) {
    const confirmed = item.publication?.accepted === true && ['creator_publish', 'creator_work'].includes(item.publication?.id_kind);
    if (!confirmed) return null;
    result.url = null;
    result.publication = { ...item.publication, id_pending: false, public_url_available: false };
    return result;
  }
  return typeof result.url === 'string' && result.url ? result : null;
}

export function matchWeiboVideo(items, mediaId, userId, submittedAt) {
  const since = Date.parse(submittedAt);
  if (!decimalId(mediaId) || !decimalId(userId) || !Number.isFinite(since)) return null;
  const matches = items.filter(item => item.kind === 'video' && fullId(item.author?.id) === String(userId)
    && item.media?.some(media => media.type === 'video' && videoMediaId(media.id) === String(mediaId))
    && decimalId(item.id) && Number.isFinite(Date.parse(item.created_at)) && Date.parse(item.created_at) >= since - 60000);
  return matches.length === 1 ? matches[0] : null;
}

export function creatorRecordId(row) {
  try {
    const reference = JSON.parse(row.notes)?.platform_runtime;
    return ['creator_publish', 'creator_work'].includes(reference?.id_kind) ? decimalId(reference.id) : null;
  } catch { return null; }
}

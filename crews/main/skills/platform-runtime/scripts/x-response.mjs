// REST 写接口也可能用 HTTP 200 + errors 表达失败，不能把响应当作成功。
export function xArticleRequest(input) {
  const url = new URL(input.url);
  if (url.origin !== 'https://x.com' || !url.pathname.endsWith('/ArticleEntityUpdateContent')) return input;
  const state = input.json?.variables?.content_state;
  if (!Array.isArray(state?.blocks) || !Array.isArray(state.entity_map)) return input;
  const entities = [...state.entity_map];
  let next = Math.max(-1, ...entities.map(entity => Number(entity.key))) + 1;
  if (!Number.isSafeInteger(next)) return input;
  let changed = false;
  const blocks = state.blocks.map(block => {
    if (block.type !== 'unstyled' || block.entity_ranges?.length || block.inline_style_ranges?.length) return block;
    const tweet = /^<?https?:\/\/(?:www\.|mobile\.)?(?:x|twitter)\.com\/[^/\s]+\/status\/(\d+)[^\s>]*>?$/.exec(block.text || '');
    if (!tweet) return block;
    const key = next++;
    entities.push({ key: String(key), value: { type: 'TWEET', mutability: 'Immutable', data: { tweet_id: tweet[1] } } });
    changed = true;
    return { ...block, text: ' ', type: 'atomic', inline_style_ranges: [], entity_ranges: [{ key, offset: 0, length: 1 }] };
  });
  return changed ? { ...input, json: { ...input.json, variables: { ...input.json.variables, content_state: { ...state, blocks, entity_map: entities } } } } : input;
}

export async function checkXResponse(input, response, RuntimeError) {
  const url = new URL(input.url);
  if (url.origin !== 'https://x.com' || !url.pathname.startsWith('/i/api/1.1/')
      || (input.method || 'GET').toUpperCase() !== 'POST' || !response.ok) return;
  let body;
  try { body = await response.clone().json(); } catch { return; }
  if (!Array.isArray(body?.errors) || !body.errors.length) return;
  const code = Number(body.errors[0]?.code);
  const error = [32, 89, 215, 353].includes(code) ? 'AUTH_EXPIRED'
    : [88, 226, 344].includes(code) ? 'RISK_CONTROL' : 'UPSTREAM';
  throw new RuntimeError(error, 'X 拒绝此写操作', { detail: { code, status: response.status, path: url.pathname } });
}

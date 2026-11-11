import axios from 'axios';
import https from 'node:https';

// Keep the existing ccMixter-only TLS compatibility setting.
const api = axios.create({httpsAgent: new https.Agent({rejectUnauthorized: false}), timeout: 15000});
const API_BASE = 'https://ccmixter.org/api/query';

export function termsFor(value) {
  const terms = [...new Set(String(value).toLowerCase().split(/[\s,+]+/u)
    .map(t => t.replace(/[^\p{L}\p{N}_-]/gu, '')).filter(Boolean))];
  if (!terms.length) throw new Error('Provide non-empty music tags (English tags or --preset recommended).');
  return terms;
}

export function rankTracks(tracks, terms) {
  const score = track => {
    const tags = new Set(String(track.upload_extra?.usertags || '').toLowerCase().split(','));
    const title = String(track.upload_name || '').toLowerCase();
    return terms.reduce((sum, t) => sum + (tags.has(t) ? 2 : title.includes(t) ? 1 : 0), 0);
  };
  // Stable sort preserves the requested upstream ordering for equally relevant candidates.
  return tracks.map(track => ({track, score: score(track)})).filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score).map(item => item.track);
}

function retryable(err) {
  return ['ECONNRESET', 'ECONNABORTED', 'ETIMEDOUT', 'EAI_AGAIN', 'HPE_HEADER_OVERFLOW'].includes(err.code)
    || /header overflow/i.test(err.message || '')
    || err.response?.status === 429 || err.response?.status >= 500;
}

export async function queryApi(params, {get = url => api.get(url),
  wait = ms => new Promise(resolve => setTimeout(resolve, ms)),
  warn = message => console.error(message)} = {}) {
  const url = `${API_BASE}?${new URLSearchParams({f: 'json', ...params})}`;
  for (let attempt = 0; ; attempt++) {
    let response;
    try {
      response = await get(url);
    } catch (err) {
      if (attempt >= 2 || !retryable(err)) throw err;
      warn(`ccMixter query retry ${attempt + 1}/2: ${err.code || err.message}`);
      await wait(1000 * (attempt + 1));
      continue;
    }
    if (!Array.isArray(response.data)) throw new Error('Unexpected API response format');
    return response.data;
  }
}

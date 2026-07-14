/**
 * Safety-net stripping of reasoning/thinking tags from outbound text.
 *
 * Some domestic LLM providers embed <think>…</think> inline in the response
 * text instead of returning a separate reasoning block.  This must never reach
 * the customer on external channels like Awada.
 *
 * The implementation mirrors upstream `stripAssistantInternalScaffolding` (from
 * `openclaw/src/shared/text/assistant-visible-text.ts`) but is self-contained
 * so it can live in the plugin without importing private upstream modules.
 */

// ---- quick-exit guards ----
const QUICK_TAG_RE = /<\s*\/?\s*(?:think(?:ing)?|thought|antthinking|final)\b/i;
const MEMORY_TAG_QUICK_RE = /<\s*\/?\s*relevant[-_]memories\b/i;

// ---- tag patterns ----
const FINAL_TAG_RE = /<\s*\/?\s*final\b[^<>]*>/gi;
const THINKING_TAG_RE = /<\s*(\/?)\s*(?:think(?:ing)?|thought|antthinking)\b[^<>]*>/gi;
const MEMORY_TAG_RE = /<\s*(\/?)\s*relevant[-_]memories\b[^<>]*>/gi;

// ---- code region detection (simplified) ----
type Region = [start: number, end: number];

function findCodeRegions(text: string): Region[] {
  const regions: Region[] = [];
  const fenceRe = /^(`{3,}|~{3,})/gm;
  let openIndex: number | undefined;
  for (const m of text.matchAll(fenceRe)) {
    const idx = m.index ?? 0;
    if (openIndex === undefined) {
      openIndex = idx;
    } else {
      regions.push([openIndex, idx + m[0].length]);
      openIndex = undefined;
    }
  }
  // Unclosed fence → treat rest of text as code
  if (openIndex !== undefined) {
    regions.push([openIndex, text.length]);
  }
  return regions;
}

function isInsideCode(pos: number, regions: Region[]): boolean {
  return regions.some(([s, e]) => pos >= s && pos < e);
}

// ---- strip paired tags + content (thinking) ----
function stripPairedTags(
  text: string,
  tagRe: RegExp,
  codeRegions: Region[],
): string {
  tagRe.lastIndex = 0;
  let result = "";
  let lastIndex = 0;
  let depth = false;

  for (const match of text.matchAll(tagRe)) {
    const idx = match.index ?? 0;
    const isClose = match[1] === "/";

    if (isInsideCode(idx, codeRegions)) {
      continue;
    }

    if (!depth) {
      result += text.slice(lastIndex, idx);
      if (!isClose) {
        depth = true;
      }
    } else if (isClose) {
      depth = false;
    }

    lastIndex = idx + match[0].length;
  }

  // Preserve trailing text (mode "preserve")
  result += text.slice(lastIndex);
  return result;
}

// ---- strip self-closing tags only, keep content (<final>) ----
function stripSelfClosingTags(
  text: string,
  tagRe: RegExp,
  codeRegions: Region[],
): string {
  tagRe.lastIndex = 0;
  const matches: Array<{ start: number; length: number }> = [];
  for (const m of text.matchAll(tagRe)) {
    const start = m.index ?? 0;
    if (!isInsideCode(start, codeRegions)) {
      matches.push({ start, length: m[0].length });
    }
  }
  let result = text;
  for (let i = matches.length - 1; i >= 0; i--) {
    const { start, length } = matches[i];
    result = result.slice(0, start) + result.slice(start + length);
  }
  return result;
}

/**
 * Strip reasoning / thinking tags and internal scaffolding from text.
 *
 * Safe to call on any text — returns the input unchanged when no tags are found.
 */
export function stripThinkingFromText(text: string): string {
  if (!text) {
    return text;
  }

  let cleaned = text;

  // 1. Strip thinking / reasoning tags + content
  if (QUICK_TAG_RE.test(cleaned)) {
    const codeRegions = findCodeRegions(cleaned);
    // <final>…</final> → keep content, remove tags only
    if (FINAL_TAG_RE.test(cleaned)) {
      cleaned = stripSelfClosingTags(cleaned, FINAL_TAG_RE, codeRegions);
    }
    // <think>…</think> etc. → remove tags + content
    const codeRegions2 = findCodeRegions(cleaned);
    cleaned = stripPairedTags(cleaned, THINKING_TAG_RE, codeRegions2);
  }

  // 2. Strip <relevant-memories>…</relevant-memories>
  if (MEMORY_TAG_QUICK_RE.test(cleaned)) {
    const codeRegions = findCodeRegions(cleaned);
    cleaned = stripPairedTags(cleaned, MEMORY_TAG_RE, codeRegions);
  }

  return cleaned.trimStart();
}

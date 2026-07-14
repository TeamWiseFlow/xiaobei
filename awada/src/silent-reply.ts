/**
 * Returns true when the text should be suppressed (not delivered to the channel).
 * Rules:
 * 1. Text is exactly "NO_REPLY" (ignoring surrounding whitespace) — silent sentinel
 * 2. Text contains "⚠️ ✉️ Message failed" — delivery failure notice from upstream
 */
export function isNoReplyText(text: string | undefined | null): boolean {
  if (!text) return false;
  if (/^\s*NO_REPLY\s*$/i.test(text)) return true;
  if (text.includes('⚠️ ✉️ Message failed')) return true;
  return false;
}

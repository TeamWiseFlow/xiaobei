// Read-only readiness polling: preserve the platform's minimum wait and the original deadline.
export function pollDelay(attempt, baseMs, remainingMs, afterMs = 0) {
  const base = Number.isFinite(baseMs) && baseMs > 0 ? baseMs : 1000;
  const advised = Number.isFinite(afterMs) && afterMs > 0 ? afterMs : 0;
  const adaptive = Math.max(base, Math.min(8000, base * 2 ** Math.min(Math.max(0, attempt), 3)));
  return Math.max(0, Math.min(remainingMs, Math.max(advised, adaptive)));
}

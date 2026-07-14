/**
 * CustomerDB feature — injects customer context into LLM prompts and handles
 * silent sales commands (payment_success, club_join) without invoking an LLM.
 *
 * Originally a standalone plugin (customerdb-hook); merged into awada-extension
 * so that a single plugin entry in openclaw.json covers both channel and CRM.
 *
 * Activated when `pluginConfig.customerdb.agentId` is set in openclaw.json:
 *
 *   "plugins": [{
 *     "path": "awada",
 *     "config": {
 *       "customerdb": {
 *         "agentId": "sales-cs",
 *         "workspaceDir": "/home/.../.openclaw/workspace-sales-cs"
 *       }
 *     }
 *   }]
 */

import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

// ── Config ───────────────────────────────────────────────────────────────────

export interface CustomerDbConfig {
  /** Agent ID to attach context to. Default: "sales-cs" */
  agentId?: string;
  /** Workspace directory containing db/customer.db. Default: ~/.openclaw/workspace-sales-cs */
  workspaceDir?: string;
}

// ── Types ────────────────────────────────────────────────────────────────────

type CustomerRow = {
  peer: string;
  business_status: string;
  purpose: string;
  prompt_source: string;
  club_in: string;
  created_at: string;
  updated_at: string;
};

type SentFollowUp = {
  id: number;
  sent_text: string;
};

// ── Schema DDL ───────────────────────────────────────────────────────────────

const CS_RECORD_DDL = `
CREATE TABLE IF NOT EXISTS cs_record (
  peer            TEXT PRIMARY KEY,
  business_status TEXT DEFAULT 'free',
  purpose         TEXT DEFAULT '',
  prompt_source   TEXT DEFAULT '',
  club_in         TEXT,
  created_at      TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
  updated_at      TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
);
`.trim();

const FOLLOW_UP_DDL = `
CREATE TABLE IF NOT EXISTS follow_up (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  peer              TEXT NOT NULL,
  user_id_external  TEXT NOT NULL,
  follow_up_at      TEXT NOT NULL,
  reason            TEXT NOT NULL,
  context_summary   TEXT,
  status            TEXT DEFAULT 'pending',
  sent_text         TEXT,
  retry_count       INTEGER DEFAULT 0,
  created_at        TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
  completed_at      TEXT,
  FOREIGN KEY (peer) REFERENCES cs_record(peer)
);
`.trim();

// ── Peer normalization ────────────────────────────────────────────────────────

/**
 * Normalize a raw peer string to a canonical, DB-safe form.
 *
 * Rules (applied in order):
 *   1. trim leading/trailing whitespace
 *   2. lowercase  (openclaw already lowercases peerId when building sessionKey,
 *                  so this makes the command path consistent with the hook path)
 *   3. strip ASCII control characters U+0000–U+001F and U+007F
 *      (\t \n \r \0 etc. — \t breaks tab-separated sqlite3 output parsing;
 *       \n/\r break line-based output; \0 is a null-byte hazard in SQLite C layer)
 */
function normalizePeer(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[\x00-\x1f\x7f]/g, "");
}

function resolvePeerFromSessionKey(sessionKey?: string): string | null {
  if (!sessionKey) return null;
  const preferred = sessionKey.match(/^agent:[^:]+:awada:direct:(.+)$/);
  if (preferred?.[1]) return normalizePeer(preferred[1]);
  const tolerant = sessionKey.match(/^agent:.*:awada:direct:(.+)$/);
  if (tolerant?.[1]) return normalizePeer(tolerant[1]);
  return null;
}

function resolvePeerForCommand(ctx: {
  channel: string;
  senderId?: string;
}): string | null {
  if (ctx.channel !== "awada") return null;
  if (!ctx.senderId) return null;
  return normalizePeer(ctx.senderId);
}

// ── SQLite helpers ────────────────────────────────────────────────────────────

function sqliteExec(dbFile: string, args: string[], options?: { input?: string }) {
  const res = spawnSync("sqlite3", [dbFile, ...args], {
    encoding: "utf8",
    input: options?.input,
  });
  if (res.status !== 0) {
    throw new Error(res.stderr || res.stdout || "sqlite3 command failed");
  }
  return (res.stdout || "").trim();
}

function sqlQuote(input: string): string {
  return `'${input.replace(/'/g, "''")}'`;
}

// ── DB initialization ─────────────────────────────────────────────────────────

function ensureDatabaseReady(params: { dbFile: string; schemaFile: string }) {
  const { dbFile, schemaFile } = params;

  const tableName = sqliteExec(dbFile, [
    "SELECT name FROM sqlite_master WHERE type='table' AND name='cs_record';",
  ]);
  if (tableName !== "cs_record") {
    try {
      const schemaSql = readFileSync(schemaFile, "utf8");
      sqliteExec(dbFile, [], { input: schemaSql });
    } catch {
      sqliteExec(dbFile, [], { input: CS_RECORD_DDL });
    }
  }

  // Idempotent: always ensure follow_up table
  sqliteExec(dbFile, [], { input: FOLLOW_UP_DDL });

  // Migration: rename awada_customer_id → user_id_external if legacy column exists
  try {
    const cols = sqliteExec(dbFile, ["PRAGMA table_info(follow_up);"]);
    if (cols.includes("awada_customer_id")) {
      sqliteExec(dbFile, [
        "ALTER TABLE follow_up RENAME COLUMN awada_customer_id TO user_id_external;",
      ]);
    }
  } catch {
    // SQLite < 3.25 doesn't support RENAME COLUMN — skip migration
  }
}

// ── cs_record operations ──────────────────────────────────────────────────────

function ensurePeerRow(dbFile: string, peer: string) {
  sqliteExec(dbFile, [
    `INSERT INTO cs_record (peer, business_status, purpose, prompt_source) VALUES (${sqlQuote(peer)}, 'free', '', '') ON CONFLICT(peer) DO UPDATE SET updated_at = strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime');`,
  ]);
}

function updateForPaymentSuccess(dbFile: string, peer: string) {
  sqliteExec(dbFile, [
    `UPDATE cs_record SET business_status='subs', club_in=strftime('%Y-%m-%d', 'now', 'localtime') WHERE peer=${sqlQuote(peer)};`,
  ]);
}

function updateForClubJoin(dbFile: string, peer: string) {
  sqliteExec(dbFile, [
    `UPDATE cs_record SET business_status='club', club_in=strftime('%Y-%m-%d', 'now', 'localtime') WHERE peer=${sqlQuote(peer)};`,
  ]);
}

function selectCustomerRow(dbFile: string, peer: string): CustomerRow | null {
  const out = sqliteExec(dbFile, [
    "-separator",
    "\t",
    `SELECT peer, business_status, purpose, prompt_source, club_in, created_at, updated_at FROM cs_record WHERE peer=${sqlQuote(peer)} LIMIT 1;`,
  ]);
  if (!out) return null;
  const [p, business_status, purpose, prompt_source, club_in, created_at, updated_at] =
    out.split("\t");
  return {
    peer: p ?? peer,
    business_status: business_status ?? "free",
    purpose: purpose ?? "",
    prompt_source: prompt_source ?? "",
    club_in: club_in ?? "",
    created_at: created_at ?? "",
    updated_at: updated_at ?? "",
  };
}

// ── follow_up operations ──────────────────────────────────────────────────────

function selectSentOnceFollowUp(dbFile: string, peer: string): SentFollowUp | null {
  const out = sqliteExec(dbFile, [
    "-separator",
    "\t",
    `SELECT id, sent_text FROM follow_up WHERE peer=${sqlQuote(peer)} AND status='sent_once' ORDER BY created_at DESC LIMIT 1;`,
  ]);
  if (!out) return null;
  const [id, sent_text] = out.split("\t");
  if (!id || !sent_text) return null;
  return { id: parseInt(id, 10), sent_text };
}

function completePendingFollowUps(dbFile: string, peer: string): void {
  sqliteExec(dbFile, [
    `UPDATE follow_up SET status='completed', completed_at=strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime') WHERE peer=${sqlQuote(peer)} AND status IN ('pending', 'sent_once');`,
  ]);
}

// ── Prompt context builders ───────────────────────────────────────────────────

const STATIC_RULES = [
  "CustomerDB 规则（每轮适用）：",
  "- [CustomerDB].peer 是当前客户在数据库中的主键，用于所有 SQL 查询和写库操作。",
  "- Sender 块中的 id（即 user_id_external）是 awada 原始用户标识，用于需要与 awada 交互的技能（如 exp_invite）。",
  "- 仅在信息更明确时更新 business_status/purpose/prompt_source。",
  "- 字段为空时不要臆测。",
].join("\n");

function buildDynamicContext(row: CustomerRow): string {
  return [
    "[CustomerDB]",
    `peer: ${row.peer}`,
    `business_status: ${row.business_status}`,
    `club_in: ${row.club_in || ""}`,
    `purpose: ${row.purpose || ""}`,
    `prompt_source: ${row.prompt_source || ""}`,
    `updated_at: ${row.updated_at || ""}`,
    "[/CustomerDB]",
  ].join("\n");
}

function buildFollowUpContext(followUp: SentFollowUp): string {
  return [
    "[FollowUp]",
    `你之前主动跟进过该客户，发送内容：「${followUp.sent_text}」`,
    "客户本次是主动回复，跟进任务已自动完成。",
    "[/FollowUp]",
  ].join("\n");
}

// ── Public registration function ─────────────��────────────────────────────────

/**
 * Register CustomerDB hooks and commands into the given plugin API.
 * Called from awada-extension's register() when pluginConfig.customerdb is set.
 */
export function registerCustomerDb(api: OpenClawPluginApi, cfg: CustomerDbConfig): void {
  const agentId = cfg.agentId ?? "sales-cs";
  const workspaceDir = cfg.workspaceDir ?? `${process.env.HOME ?? "/root"}/.openclaw/workspace-sales-cs`;
  const dbFile = join(workspaceDir, "db", "customer.db");
  const schemaFile = join(workspaceDir, "db", "schema.sql");

  try {
    ensureDatabaseReady({ dbFile, schemaFile });
  } catch (err) {
    api.logger.warn?.(
      `customerdb: DB init failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  const preparePeer = (peer: string) => ensurePeerRow(dbFile, peer);

  api.registerCommand({
    name: "payment_success",
    description: "Mark customer as subscription-success (silent)",
    acceptsArgs: false,
    requireAuth: false,
    handler: async (ctx) => {
      try {
        const peer = resolvePeerForCommand({ channel: ctx.channel, senderId: ctx.senderId });
        if (!peer) {
          api.logger.warn?.(
            `payment_success: peer unresolved (channel=${ctx.channel}, senderId=${ctx.senderId ?? ""})`,
          );
          return { text: "NO_REPLY" };
        }
        preparePeer(peer);
        updateForPaymentSuccess(dbFile, peer);
        return { text: "NO_REPLY" };
      } catch (err) {
        api.logger.warn?.(
          `payment_success failed: ${err instanceof Error ? err.message : String(err)}`,
        );
        return { text: "NO_REPLY" };
      }
    },
  });

  api.registerCommand({
    name: "club_join",
    description: "Mark customer as club member and stamp join date (silent)",
    acceptsArgs: false,
    requireAuth: false,
    handler: async (ctx) => {
      try {
        const peer = resolvePeerForCommand({ channel: ctx.channel, senderId: ctx.senderId });
        if (!peer) {
          api.logger.warn?.(
            `club_join: peer unresolved (channel=${ctx.channel}, senderId=${ctx.senderId ?? ""})`,
          );
          return { text: "NO_REPLY" };
        }
        preparePeer(peer);
        updateForClubJoin(dbFile, peer);
        return { text: "NO_REPLY" };
      } catch (err) {
        api.logger.warn?.(
          `club_join failed: ${err instanceof Error ? err.message : String(err)}`,
        );
        return { text: "NO_REPLY" };
      }
    },
  });

  api.on("before_prompt_build", (_event, ctx) => {
    try {
      if (ctx.agentId !== agentId) return;
      const peer = resolvePeerFromSessionKey(ctx.sessionKey);
      if (!peer) return;

      preparePeer(peer);
      const row = selectCustomerRow(dbFile, peer);
      if (!row) return;

      const sentFollowUp = selectSentOnceFollowUp(dbFile, peer);
      completePendingFollowUps(dbFile, peer);

      let appendCtx = buildDynamicContext(row);
      if (sentFollowUp) {
        appendCtx += "\n\n" + buildFollowUpContext(sentFollowUp);
      }

      return {
        prependSystemContext: STATIC_RULES,
        appendSystemContext: appendCtx,
      };
    } catch (err) {
      api.logger.warn?.(
        `customerdb before_prompt_build failed: ${err instanceof Error ? err.message : String(err)}`,
      );
      return;
    }
  });
}

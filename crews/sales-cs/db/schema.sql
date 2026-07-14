-- sales-cs CustomerDB schema
-- 此文件是规范定义；实际初始化由 customerdb-hook 内联 DDL 完成（幂等，支持迁移）

CREATE TABLE IF NOT EXISTS cs_record (
  peer            TEXT PRIMARY KEY,
  business_status TEXT DEFAULT 'free',
  purpose         TEXT DEFAULT '',
  prompt_source   TEXT DEFAULT '',
  club_in         TEXT,
  created_at      TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
  updated_at      TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
);

-- 主动跟进任务表
-- status: pending → sent_once → completed
--   pending:   已创建，尚未发送
--   sent_once: 已发送第一次，等待客户回复或第二次 heartbeat
--   completed: 已完成（客户主动回复 或 发送第二次后）
CREATE TABLE IF NOT EXISTS follow_up (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  peer              TEXT NOT NULL,
  user_id_external  TEXT NOT NULL,          -- Sender 块的 id 字段（awada 原始用户标识）
  follow_up_at      TEXT NOT NULL,          -- 计划跟进时间 YYYY-MM-DD HH:MM
  reason            TEXT NOT NULL,          -- 跟进原因（供 agent 和 heartbeat 参考）
  context_summary   TEXT,                   -- 对话摘要 + 推荐跟进话术方向
  status            TEXT DEFAULT 'pending',
  sent_text         TEXT,                   -- 实际发送的跟进消息内容
  retry_count       INTEGER DEFAULT 0,
  created_at        TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
  completed_at      TEXT,
  FOREIGN KEY (peer) REFERENCES cs_record(peer)
);

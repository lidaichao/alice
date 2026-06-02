/**
 * Conversations — 多会话管理（SQLite 持久化 + JSON 平滑迁移）
 * 替代原 JSON 全量读写方案，迁移至 better-sqlite3。
 */
const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

class ConversationStore {
  constructor(userDataPath) {
    this.userDataPath = userDataPath;
    const dbPath = path.join(userDataPath, 'conversations.db');

    fs.mkdirSync(userDataPath, { recursive: true });

    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('foreign_keys = ON');

    this._initSchema();

    // 预编译常用语句（必须在 _migrateFromJSON 之前）
    this._stmts = {
      listConvs: this.db.prepare(`
        SELECT c.id, c.title, c.createdAt, c.updatedAt, c.isActive,
               (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id) AS messageCount
        FROM conversations c ORDER BY c.updatedAt DESC
      `),
      getActiveId: this.db.prepare('SELECT id FROM conversations WHERE isActive = 1 LIMIT 1'),
      getConv: this.db.prepare('SELECT * FROM conversations WHERE id = ?'),
      getMessages: this.db.prepare('SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC'),
      insertConv: this.db.prepare(
        'INSERT INTO conversations (id, title, createdAt, updatedAt, isActive) VALUES (?, ?, ?, ?, ?)'
      ),
      updateTitle: this.db.prepare('UPDATE conversations SET title = ?, updatedAt = ? WHERE id = ?'),
      clearActive: this.db.prepare('UPDATE conversations SET isActive = 0'),
      setActive: this.db.prepare('UPDATE conversations SET isActive = 1 WHERE id = ?'),
      touchConv: this.db.prepare('UPDATE conversations SET updatedAt = ? WHERE id = ?'),
      deleteConv: this.db.prepare('DELETE FROM conversations WHERE id = ?'),
      insertMsg: this.db.prepare(
        'INSERT INTO messages (conversation_id, role, content, timestamp, raw_json) VALUES (?, ?, ?, ?, ?)'
      ),
      deleteMsgs: this.db.prepare('DELETE FROM messages WHERE conversation_id = ?'),
      msgCount: this.db.prepare('SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?'),
    };

    this._migrateFromJSON();
  }

  // ──────────── 初始化表结构 ────────────
  _initSchema() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS conversations (
        id         TEXT PRIMARY KEY,
        title      TEXT NOT NULL DEFAULT '新会话',
        createdAt  TEXT NOT NULL,
        updatedAt  TEXT NOT NULL,
        isActive   INTEGER NOT NULL DEFAULT 0
      );

      CREATE TABLE IF NOT EXISTS messages (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id  TEXT NOT NULL,
        role             TEXT NOT NULL,
        content          TEXT NOT NULL,
        timestamp        TEXT NOT NULL,
        raw_json         TEXT,
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
      );

      CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
    `);
  }

  // ──────────── JSON → SQLite 平滑迁移 ────────────
  _migrateFromJSON() {
    const jsonPath = path.join(this.userDataPath, 'conversations.json');
    if (!fs.existsSync(jsonPath)) return;

    const count = this.db.prepare('SELECT COUNT(*) AS cnt FROM conversations').get();
    if (count.cnt > 0) return; // 已有数据，跳过迁移

    try {
      const raw = fs.readFileSync(jsonPath, 'utf8');
      const data = JSON.parse(raw);
      const convs = data.conversations || [];
      const activeId = data.activeId;

      if (convs.length === 0) {
        fs.renameSync(jsonPath, jsonPath + '.bak');
        return;
      }

      const tx = this.db.transaction(() => {
        for (const c of convs) {
          this._stmts.insertConv.run(
            c.id,
            c.title || '新会话',
            c.createdAt || this._now(),
            c.updatedAt || this._now(),
            c.id === activeId ? 1 : 0
          );
          for (const m of (c.messages || [])) {
            const ts = m.timestamp || this._now();
            this._stmts.insertMsg.run(
              c.id,
              m.role || 'user',
              m.content || '',
              ts,
              JSON.stringify({ ...m, timestamp: ts })
            );
          }
        }
      });

      tx();

      fs.renameSync(jsonPath, jsonPath + '.bak');
      console.log(`[ConversationStore] 迁移完成：${convs.length} 个会话 → SQLite，旧文件已备份为 .bak`);
    } catch (err) {
      console.error('[ConversationStore] JSON 迁移失败，旧文件保留:', err.message);
    }
  }

  // ──────────── 辅助 ────────────
  _now() {
    return new Date().toISOString();
  }

  _convRow(row) {
    return {
      id: row.id,
      title: row.title,
      createdAt: row.createdAt,
      updatedAt: row.updatedAt,
    };
  }

  _msgRow(row) {
    if (row.raw_json) {
      try { return JSON.parse(row.raw_json); } catch { /* fall through */ }
    }
    return { role: row.role, content: row.content, timestamp: row.timestamp };
  }

  // ──────────── 公开 API（签名与原版完全兼容）────────────

  async list() {
    const convs = this._stmts.listConvs.all();
    const active = this._stmts.getActiveId.get();
    return {
      conversations: convs.map(r => ({
        id: r.id,
        title: r.title,
        createdAt: r.createdAt,
        updatedAt: r.updatedAt,
        messageCount: r.messageCount,
      })),
      activeId: active ? active.id : null,
    };
  }

  async create(title) {
    const now = this._now();
    const id = `conv-${crypto.randomUUID().slice(0, 8)}`;
    const convTitle = title || '新会话';

    this._stmts.clearActive.run();
    this._stmts.insertConv.run(id, convTitle, now, now, 1);

    return { id, title: convTitle, createdAt: now, updatedAt: now, messages: [] };
  }

  async get(id) {
    const conv = this._stmts.getConv.get(id);
    if (!conv) return null;

    const msgs = this._stmts.getMessages.all(id);
    return {
      ...this._convRow(conv),
      messages: msgs.map(m => this._msgRow(m)),
    };
  }

  async delete(id) {
    this._stmts.deleteConv.run(id);

    // 若删除的是当前活跃会话，自动切换到第一个
    const active = this._stmts.getActiveId.get();
    if (!active) {
      const first = this.db.prepare('SELECT id FROM conversations ORDER BY updatedAt DESC LIMIT 1').get();
      if (first) this._stmts.setActive.run(first.id);
    }
  }

  async rename(id, title) {
    this._stmts.updateTitle.run(title, this._now(), id);
  }

  async setActive(id) {
    const conv = this._stmts.getConv.get(id);
    if (!conv) return;

    this._stmts.clearActive.run();
    this._stmts.setActive.run(id);
    this._stmts.touchConv.run(this._now(), id);
  }

  async appendMessage(id, msg) {
    const conv = this._stmts.getConv.get(id);
    if (!conv) return;

    const ts = this._now();
    const msgData = { ...msg, timestamp: ts };

    this._stmts.insertMsg.run(id, msg.role || 'user', msg.content || '', ts, JSON.stringify(msgData));
    this._stmts.touchConv.run(ts, id);

    // 首条用户消息自动命名
    if (conv.title === '新会话' && msg.role === 'user') {
      const autoTitle = (msg.content || '').slice(0, 30) || '新会话';
      this._stmts.updateTitle.run(autoTitle, ts, id);
    }
  }

  async clearMessages(id) {
    this._stmts.deleteMsgs.run(id);
    this._stmts.touchConv.run(this._now(), id);
  }

  async truncateMessagesFrom(conversationId, messageId) {
    this.db.prepare(
      'DELETE FROM messages WHERE conversation_id = ? AND id >= ?'
    ).run(conversationId, messageId);
  }
}

module.exports = { ConversationStore };

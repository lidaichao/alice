/**
 * Conversations — 多会话管理（借鉴白泽 conversation-store.cjs）
 * 本地 JSON 存储，支持创建/切换/删除/重命名会话
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

class ConversationStore {
  constructor(userDataPath) {
    this.filePath = path.join(userDataPath, 'conversations.json');
    this.store = null;
  }

  async _read() {
    if (this.store) return this.store;
    try {
      const raw = await fs.promises.readFile(this.filePath, 'utf8');
      this.store = JSON.parse(raw);
    } catch {
      this.store = { conversations: [], activeId: null };
    }
    return this.store;
  }

  async _write() {
    await fs.promises.mkdir(path.dirname(this.filePath), { recursive: true });
    await fs.promises.writeFile(this.filePath, JSON.stringify(this.store, null, 2), 'utf8');
  }

  _now() { return new Date().toISOString(); }

  async list() {
    const s = await this._read();
    return {
      conversations: s.conversations.map(c => ({
        id: c.id, title: c.title, createdAt: c.createdAt,
        updatedAt: c.updatedAt, messageCount: (c.messages || []).length
      })),
      activeId: s.activeId
    };
  }

  async create(title) {
    const s = await this._read();
    const now = this._now();
    const conv = {
      id: `conv-${crypto.randomUUID().slice(0, 8)}`,
      title: title || '新会话',
      createdAt: now,
      updatedAt: now,
      messages: []
    };
    s.conversations.unshift(conv);
    s.activeId = conv.id;
    await this._write();
    return conv;
  }

  async get(id) {
    const s = await this._read();
    return s.conversations.find(c => c.id === id) || null;
  }

  async delete(id) {
    const s = await this._read();
    s.conversations = s.conversations.filter(c => c.id !== id);
    if (s.activeId === id) s.activeId = s.conversations[0]?.id || null;
    await this._write();
  }

  async rename(id, title) {
    const s = await this._read();
    const conv = s.conversations.find(c => c.id === id);
    if (conv) { conv.title = title; conv.updatedAt = this._now(); }
    s.activeId = id;
    await this._write();
  }

  async setActive(id) {
    const s = await this._read();
    s.activeId = id;
    const conv = s.conversations.find(c => c.id === id);
    if (conv) conv.updatedAt = this._now();
    await this._write();
  }

  async appendMessage(id, msg) {
    const s = await this._read();
    const conv = s.conversations.find(c => c.id === id);
    if (!conv) return;
    conv.messages.push({ ...msg, timestamp: this._now() });
    conv.updatedAt = this._now();
    // 用第一条用户消息自动命名
    if (conv.title === '新会话' && msg.role === 'user') {
      conv.title = (msg.content || '').slice(0, 30) || '新会话';
    }
    await this._write();
  }

  async clearMessages(id) {
    const s = await this._read();
    const conv = s.conversations.find(c => c.id === id);
    if (conv) { conv.messages = []; conv.updatedAt = this._now(); }
    await this._write();
  }
}

module.exports = { ConversationStore };

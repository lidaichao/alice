import { useState, useEffect, useCallback } from 'react';
import { useXConversations } from '@ant-design/x-sdk';

/**
 * useAliceConversations — 封装 useXConversations 桥接 window.baize IPC
 *
 * @param {Object}  [options]
 * @param {string}  [options.activeKey]  当前激活的 conversation key
 * @param {Function}[options.onChange]   切换对话回调 (key)
 * @returns {Object} useXConversations 返回值 + activeKey
 */
export function useAliceConversations({ activeKey, onChange } = {}) {
  const [ready, setReady] = useState(false);

  const {
    conversations,
    addConversation,
    removeConversation,
    setConversations
  } = useXConversations({
    defaultConversations: [],
    defaultActiveConversationKey: activeKey
  });

  // 首次加载：从 IPC 拉取对话列表
  useEffect(() => {
    if (typeof window.baize?.listConversations !== 'function') return;

    window.baize.listConversations()
      .then((list) => {
        if (Array.isArray(list) && list.length > 0) {
          setConversations(list.map(c => ({
            key: c.id || c.conversationId || `conv-${Date.now()}`,
            label: c.name || c.title || '未命名对话'
          })));
        }
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);

  // 新建对话
  const handleCreate = useCallback(async () => {
    if (typeof window.baize?.createConversation !== 'function') return;
    try {
      const created = await window.baize.createConversation({ name: '新对话' });
      const key = created?.id || created?.conversationId || `conv-${Date.now()}`;
      addConversation({ key, label: '新对话' });
      if (onChange) onChange(key);
    } catch {}
  }, [addConversation, onChange]);

  // 删除对话
  const handleRemove = useCallback(async (key) => {
    if (typeof window.baize?.deleteConversation !== 'function') return;
    try {
      await window.baize.deleteConversation(key);
      removeConversation(key);
    } catch {}
  }, [removeConversation]);

  return {
    conversations,
    addConversation: handleCreate,
    removeConversation: handleRemove,
    onChange,
    ready
  };
}

import { useXChat } from '@ant-design/x-sdk';

/**
 * AliceV2 Hub 自定义 ChatProvider
 *
 * 桥接 Electron IPC (window.baize.chatStream) → useXChat 数据流。
 * 不创建新的 HTTP fetch 通道，复用现有 preload.cjs IPC。
 */
class AliceChatProvider {
  async request({ messages, ...params }, { onUpdate, onSuccess, onError, signal }) {
    const input = {
      text: params.text || '',
      conversationId: params.conversationId || '',
      clientId: params.clientId || ''
    };

    // Abort 监听
    if (signal) {
      signal.addEventListener('abort', () => {
        try { window.baize.cancelChatStream(); } catch {}
      });
    }

    let fullReply = '';

    try {
      await window.baize.chatStream(input, (event) => {
        if (!event) return;

        // 文本增量（SSE delta）
        if (event.delta) {
          fullReply += event.delta;
          onUpdate({ content: event.delta, role: 'assistant', status: 'updating' });
          return;
        }

        // 完整回复
        if (event.reply) {
          fullReply = event.reply;
          onUpdate({ content: event.reply, role: 'assistant', status: 'updating' });
          return;
        }

        // Jira 卡片等结构化事件 — 保留原文供上层 parser 使用
        if (event.type && event.type !== 'delta' && event.type !== 'reply') {
          onUpdate({ content: JSON.stringify(event), role: 'assistant', status: 'updating', eventType: event.type });
        }
      });

      onSuccess({ content: fullReply, role: 'assistant', status: 'success' });
    } catch (error) {
      onError(error);
    }
  }
}

/**
 * useAliceChat — 封装 useXChat 对接 AliceV2 Hub SSE 管道
 *
 * @param {Object}  [options]
 * @param {string}  [options.conversationId] 会话 ID
 * @param {string}  [options.clientId]       客户端 ID
 * @returns {Object} useXChat 返回值
 */
export function useAliceChat(options = {}) {
  return useXChat({
    provider: new AliceChatProvider(),
    conversationKey: options.conversationId || `alice-${Date.now()}`,
    requestPlaceholder: {
      role: 'assistant',
      content: 'Alice 正在思考…'
    }
  });
}

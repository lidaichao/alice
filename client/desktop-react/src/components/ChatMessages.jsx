import { useRef, useEffect } from 'react';
import { Bubble } from '@ant-design/x';
import { XMarkdown } from '@ant-design/x-markdown';
import JiraOperationCard from './cards/JiraOperationCard.jsx';

const ROLE = {
  user: { placement: 'end' },
  ai: { placement: 'start' }
};

/** 解析 Jira 事件类型，返回 operation 数据 */
function parseJiraEvent(msg) {
  if (!msg?.message?.eventType) return null;
  const et = msg.message.eventType;
  if (et !== 'jira_operation_required' && et !== 'jira_operation_recovery_required') return null;
  try {
    const event = JSON.parse(msg.message.content);
    return event;
  } catch {
    return null;
  }
}

function ChatMessages({ messages, isRequesting, conversationId, clientId }) {
  const listRef = useRef(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  const items = messages.map((msg) => {
    const msgRole = msg.message?.role || 'user';
    const msgContent = msg.message?.content || '';
    const msgStatus = msg.message?.status;
    const msgEventType = msg.message?.eventType;

    const bubbleRole = msgRole === 'assistant' ? 'ai' : 'user';
    const isStreaming = msgRole === 'assistant' && msgStatus === 'updating';

    // Jira 卡片：解析结构化事件，渲染卡片组件
    const jiraEvent = parseJiraEvent(msg);
    if (jiraEvent && jiraEvent.operation) {
      return {
        key: msg.id,
        role: 'ai',
        content: (
          <JiraOperationCard
            operation={jiraEvent.operation}
            conversationId={conversationId}
            clientId={clientId}
          />
        ),
        footer: `[${msgEventType}]`
      };
    }

    return {
      key: msg.id,
      role: bubbleRole,
      content: bubbleRole === 'ai'
        ? (
          <XMarkdown
            content={msgContent}
            streaming={{
              hasNextChunk: isStreaming,
              enableAnimation: true,
              tail: isStreaming
            }}
          />
        )
        : msgContent,
      footer: msgEventType
        ? `[${msgEventType}]`
        : undefined
    };
  });

  return (
    <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: '12px 0' }}>
      <Bubble.List items={items} role={ROLE} />
    </div>
  );
}

export default ChatMessages;

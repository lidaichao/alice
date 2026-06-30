import { useRef, useEffect } from 'react';
import { Bubble } from '@ant-design/x';
import { XMarkdown } from '@ant-design/x-markdown';

const ROLE = {
  user: { placement: 'end' },
  ai: { placement: 'start' }
};

function ChatMessages({ messages, isRequesting }) {
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

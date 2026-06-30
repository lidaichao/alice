import { useState, useCallback } from 'react';
import { ConfigProvider, theme } from 'antd';
import { useAliceChat } from './hooks/useAliceChat.js';
import { useAliceConversations } from './hooks/useAliceConversations.js';
import ChatMessages from './components/ChatMessages.jsx';
import ChatSender from './components/ChatSender.jsx';
import ChatSidebar from './components/ChatSidebar.jsx';
import ChatWelcome from './components/ChatWelcome.jsx';

function ChatApp() {
  const [convKey, setConvKey] = useState('');
  const { onRequest, messages, abort, isRequesting } = useAliceChat({ conversationId: convKey });

  const {
    conversations,
    addConversation,
    removeConversation,
    ready
  } = useAliceConversations({
    activeKey: convKey,
    onChange: (key) => setConvKey(key)
  });

  const handleSend = useCallback((value) => {
    if (!value || !value.text) return;
    onRequest(value);
  }, [onRequest]);

  const handleSelectConv = useCallback((key) => {
    setConvKey(key);
  }, []);

  const hasMessages = messages.length > 0;

  if (!ready) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <span>加载中…</span>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <ChatSidebar
        conversations={conversations}
        activeKey={convKey}
        onAdd={addConversation}
        onRemove={removeConversation}
        onSelect={handleSelectConv}
      />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '0 16px' }}>
        {hasMessages ? (
          <ChatMessages messages={messages} isRequesting={isRequesting} />
        ) : (
          <ChatWelcome />
        )}

        <ChatSender
          isRequesting={isRequesting}
          onRequest={handleSend}
          onCancel={abort}
        />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: { colorPrimary: '#1677ff' }
      }}
    >
      <ChatApp />
    </ConfigProvider>
  );
}

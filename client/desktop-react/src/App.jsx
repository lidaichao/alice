import React from 'react';
import { useState, useCallback, useEffect } from 'react';
import { ConfigProvider, theme, Button, Space } from 'antd';
import { LogoutOutlined, SettingOutlined, UserOutlined } from '@ant-design/icons';
import { useAliceChat } from './hooks/useAliceChat.js';
import { useAliceConversations } from './hooks/useAliceConversations.js';
import ChatMessages from './components/ChatMessages.jsx';
import ChatSender from './components/ChatSender.jsx';
import ChatSidebar from './components/ChatSidebar.jsx';
import ChatWelcome from './components/ChatWelcome.jsx';
import LoginPage from './components/LoginPage.jsx';
import SettingsPage from './components/SettingsPage.jsx';

function ChatApp({ user, onLogout }) {
  const [convKey, setConvKey] = useState('');
  const [showSettings, setShowSettings] = useState(false);
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

  const [clientId, setClientId] = useState('');

  useEffect(() => {
    if (typeof window.baize?.getClientId === 'function') {
      window.baize.getClientId().then(setClientId).catch(() => setClientId(''));
    }
  }, []);

  const handleSend = useCallback((value) => {
    if (!value || !value.text) return;
    onRequest(value);
  }, [onRequest]);

  const handleLogout = async () => {
    try { await window.baize.logout(); } catch {}
    onLogout();
  };

  if (showSettings) {
    return (
      <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm, token: { colorPrimary: '#1677ff' } }}>
        <SettingsPage onBack={() => setShowSettings(false)} />
      </ConfigProvider>
    );
  }

  if (!ready) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <span>加载中…</span>
      </div>
    );
  }

  const displayName = user?.displayName || user?.username || '用户';
  const hasMessages = messages.length > 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* 顶栏 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '6px 16px', borderBottom: '1px solid #f0f0f0', background: '#fafafa'
      }}>
        <span style={{ fontWeight: 600, fontSize: 15 }}>Alice</span>
        <Space>
          <Button size="small" icon={<SettingOutlined />} onClick={() => setShowSettings(true)}>设置</Button>
          <Button size="small" icon={<LogoutOutlined />} onClick={handleLogout}>
            {displayName}
          </Button>
        </Space>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <ChatSidebar
          conversations={conversations}
          activeKey={convKey}
          onAdd={addConversation}
          onRemove={removeConversation}
          onSelect={(key) => setConvKey(key)}
        />

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '0 16px' }}>
          {hasMessages ? (
            <ChatMessages
              messages={messages}
              isRequesting={isRequesting}
              conversationId={convKey}
              clientId={clientId}
            />
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
    </div>
  );
}

export default function App() {
  const [authUser, setAuthUser] = useState(null);

  // 启动时检查已有登录态
  useEffect(() => {
    if (typeof window.baize?.getAuth === 'function') {
      window.baize.getAuth()
        .then((result) => {
          if (result?.user) setAuthUser(result.user);
        })
        .catch(() => {});
    }
  }, []);

  const handleLoginSuccess = (user) => setAuthUser(user);
  const handleLogout = () => setAuthUser(null);

  if (!authUser) {
    return (
      <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm, token: { colorPrimary: '#1677ff' } }}>
        <LoginPage onLoginSuccess={handleLoginSuccess} />
      </ConfigProvider>
    );
  }

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm, token: { colorPrimary: '#1677ff' } }}>
      <ChatApp user={authUser} onLogout={handleLogout} />
    </ConfigProvider>
  );
}

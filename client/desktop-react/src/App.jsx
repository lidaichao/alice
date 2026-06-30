import { useState, useRef, useCallback } from 'react';
import { ConfigProvider, Button, Input, Card, Typography, Spin, Space, theme } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import { useAliceChat } from './hooks/useAliceChat.js';

const { Text, Paragraph } = Typography;

function ChatTest() {
  const [text, setText] = useState('');
  const messagesEndRef = useRef(null);
  const { onRequest, messages, abort, isRequesting } = useAliceChat();

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isRequesting) return;
    setText('');
    onRequest({
      text: trimmed,
      conversationId: ''
    });
  }, [text, isRequesting, onRequest]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', padding: 24, display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Typography.Title level={4} style={{ textAlign: 'center' }}>
        Alice Desktop — React 外壳
      </Typography.Title>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0' }}>
        {messages.length === 0 && (
          <Card style={{ textAlign: 'center', marginTop: 60 }}>
            <Text type="secondary">发送「你好」开始测试 Alice 对话</Text>
          </Card>
        )}

        {messages.map((msg, idx) => (
          <Card
            key={msg.id || idx}
            size="small"
            style={{
              marginBottom: 8,
              backgroundColor: msg.message?.role === 'user' ? '#e6f7ff' : '#f6ffed'
            }}
          >
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text strong type={msg.message?.role === 'user' ? undefined : 'success'}>
                {msg.message?.role === 'user' ? '你' : 'Alice'}
              </Text>
              <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                {msg.message?.content || ''}
                {msg.message?.status === 'updating' && msg.message?.role === 'assistant' && (
                  <Spin size="small" style={{ marginLeft: 8 }} />
                )}
              </Paragraph>
              {msg.message?.eventType && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  [{msg.message.eventType}]
                </Text>
              )}
            </Space>
          </Card>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div style={{ padding: '12px 0', borderTop: '1px solid #f0f0f0' }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息…"
            disabled={isRequesting}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={isRequesting}
            disabled={!text.trim()}
          >
            发送
          </Button>
          {isRequesting && (
            <Button onClick={abort}>停止</Button>
          )}
        </Space.Compact>
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
      <ChatTest />
    </ConfigProvider>
  );
}

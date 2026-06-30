import { Sender } from '@ant-design/x';

function ChatSender({ isRequesting, onRequest, onCancel }) {
  const handleSubmit = (value) => {
    if (!value || !value.trim()) return;
    onRequest({ text: value.trim(), conversationId: '' });
  };

  return (
    <div style={{ padding: '12px 0', borderTop: '1px solid #f0f0f0' }}>
      <Sender
        loading={isRequesting}
        onSubmit={handleSubmit}
        onCancel={onCancel}
        placeholder="输入消息…"
      />
    </div>
  );
}

export default ChatSender;

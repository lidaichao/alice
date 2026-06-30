import { Welcome } from '@ant-design/x';
import { SmileOutlined } from '@ant-design/icons';

function ChatWelcome() {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Welcome
        icon={<SmileOutlined style={{ fontSize: 48, color: '#1677ff' }} />}
        title="Alice"
        description="AI 工程助手 · 发送消息开始对话"
      />
    </div>
  );
}

export default ChatWelcome;

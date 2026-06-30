import { Conversations } from '@ant-design/x';
import { Button } from 'antd';
import { PlusOutlined } from '@ant-design/icons';

function ChatSidebar({ conversations, activeKey, onAdd, onRemove, onSelect }) {
  const items = conversations.map(c => ({
    key: c.key,
    label: c.label || '未命名对话'
  }));

  return (
    <div style={{
      width: 260,
      minWidth: 260,
      borderRight: '1px solid #f0f0f0',
      display: 'flex',
      flexDirection: 'column',
      height: '100vh'
    }}>
      <div style={{ padding: 12 }}>
        <Button
          type="dashed"
          block
          icon={<PlusOutlined />}
          onClick={onAdd}
        >
          新建对话
        </Button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        <Conversations
          items={items}
          activeKey={activeKey}
          onActiveChange={onSelect}
          onDelete={onRemove}
        />
      </div>
    </div>
  );
}

export default ChatSidebar;

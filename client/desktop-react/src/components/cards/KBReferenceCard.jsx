import { Table } from 'antd';
import { LinkOutlined } from '@ant-design/icons';

export default function KBReferenceCard({ sourceResults }) {
  if (!sourceResults || sourceResults.length === 0) return null;

  const columns = [
    {
      title: '来源',
      dataIndex: 'title',
      key: 'title',
      width: 200,
      ellipsis: true,
      render: (text, record) => {
        const url = record.url || record.relativePath;
        if (url) {
          return (
            <a href={url} target="_blank" rel="noopener noreferrer">
              <LinkOutlined style={{ marginRight: 4 }} />
              {text || '未命名'}
            </a>
          );
        }
        return text || '未命名';
      }
    },
    {
      title: '路径',
      dataIndex: 'relativePath',
      key: 'path',
      width: 180,
      ellipsis: true,
      render: (text, record) => text || record.source || 'local'
    },
    {
      title: '摘要',
      dataIndex: 'snippet',
      key: 'snippet',
      ellipsis: true,
      render: (text) => text ? (
        <span style={{ fontSize: 12, color: '#666' }}>{text.length > 100 ? text.slice(0, 100) + '…' : text}</span>
      ) : '-'
    }
  ];

  const dataSource = sourceResults.map((r, i) => ({ ...r, key: r.id || i }));

  return (
    <div style={{ padding: 12, border: '1px solid #e8e8e8', borderRadius: 8, margin: '8px 0' }}>
      <div style={{ fontSize: 13, color: '#666', marginBottom: 8 }}>
        知识库引用 · {sourceResults.length} 条结果
      </div>
      <Table
        columns={columns}
        dataSource={dataSource}
        pagination={false}
        size="small"
        locale={{ emptyText: '无引用结果' }}
      />
    </div>
  );
}

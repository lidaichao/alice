import { useState } from 'react';
import { Button, Space, Tag } from 'antd';
import { PaperClipOutlined, CheckCircleOutlined, StopOutlined } from '@ant-design/icons';

export default function AttachmentCard({ attachment }) {
  const [status, setStatus] = useState(
    attachment.memory?.status === 'remembered' ? 'remembered' : 'pending'
  );
  const [statusMsg, setStatusMsg] = useState('');
  const [loading, setLoading] = useState(false);

  const isImage = attachment.type === 'image'
    || /^image\//i.test(attachment.mimeType || '')
    || /\.(png|jpe?g|gif|webp|svg)$/i.test(attachment.fileName || '');

  const isPendingImageAnalysis = isImage && (!attachment.analysis || attachment.analysis.provider === 'local_claude_code_pending');

  const summaryText = isPendingImageAnalysis
    ? '图片已上传。'
    : attachment.analysis?.summary || 'Alice 已收到文件。';

  const reasonText = isPendingImageAnalysis
    ? '记忆建议：点击加入记忆区后，将由客户端本机 Claude Code 进行视觉分析。'
    : attachment.analysis?.reason
      ? `记忆建议：${attachment.analysis.reason}`
      : '记忆建议：等待确认。';

  const isDone = status === 'remembered' || status === 'skipped';

  const handleRemember = async () => {
    setLoading(true);
    setStatusMsg(isImage ? '正在进行图片视觉分析并加入记忆区…' : '正在加入记忆区…');
    try {
      await window.baize.rememberAttachment(attachment.id, {
        category: attachment.memory?.category || 'project',
        type: attachment.type,
        fileName: attachment.fileName,
        mimeType: attachment.mimeType,
        size: attachment.size,
        localPath: attachment.localPath,
        clientAnalysis: isImage ? undefined : attachment.analysis
      });
      setStatus('remembered');
      setStatusMsg('');
    } catch (error) {
      setStatusMsg(`错误：${error?.message || error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = () => {
    setStatus('skipped');
    setStatusMsg('已跳过，不加入记忆区。');
  };

  return (
    <div style={{ padding: 16, border: '1px solid #e8e8e8', borderRadius: 8, margin: '8px 0' }}>
      <div style={{ marginBottom: 8 }}>
        <Space>
          <PaperClipOutlined />
          <strong>上传文件：{attachment.fileName || '未命名文件'}</strong>
          {isImage && <Tag color="blue">图片</Tag>}
        </Space>
      </div>

      <div style={{ fontSize: 13, color: '#666', marginBottom: 8 }}>
        {summaryText}
      </div>

      <div style={{ fontSize: 12, color: '#888', marginBottom: 12, padding: '8px 12px', background: '#fafafa', borderRadius: 4 }}>
        {reasonText}
      </div>

      {statusMsg ? (
        <div style={{ marginBottom: 8, padding: '8px 12px', borderRadius: 4, fontSize: 13,
          background: status === 'remembered' ? '#f6ffed' : status === 'skipped' ? '#fffbe6' : '#f5f5f5',
          color: status === 'remembered' ? '#52c41a' : status === 'skipped' ? '#fa8c16' : '#666'
        }}>
          {status === 'remembered' && <CheckCircleOutlined style={{ marginRight: 6 }} />}
          {status === 'skipped' && <StopOutlined style={{ marginRight: 6 }} />}
          {status === 'remembered' ? `已加入记忆区：${attachment.memory?.category || 'project'}` : statusMsg}
        </div>
      ) : (
        <div style={{ marginBottom: 8, fontSize: 13, color: '#666' }}>
          {status === 'remembered' ? '已加入记忆区。' : '请确认是否加入 Alice 记忆区。'}
        </div>
      )}

      <Space>
        <Button
          type="primary"
          icon={<CheckCircleOutlined />}
          loading={loading}
          disabled={isDone}
          onClick={handleRemember}
        >
          加入记忆区
        </Button>
        <Button
          icon={<StopOutlined />}
          disabled={isDone}
          onClick={handleSkip}
        >
          暂不加入
        </Button>
      </Space>
    </div>
  );
}

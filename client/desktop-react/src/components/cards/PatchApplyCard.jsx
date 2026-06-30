import { useState, useEffect } from 'react';
import { Button, Space, Spin, Tag } from 'antd';
import { CodeOutlined, FolderOpenOutlined, EyeOutlined, ThunderboltOutlined } from '@ant-design/icons';

export default function PatchApplyCard({ operation }) {
  const [workspacePath, setWorkspacePath] = useState('加载中…');
  const [statusMsg, setStatusMsg] = useState('');
  const [statusType, setStatusType] = useState(''); // 'ok' | 'error'
  const [loading, setLoading] = useState(false);

  const proposal = operation.proposal || {};
  const files = proposal.files || [];
  const summary = proposal.summary || '补丁草案已生成。';
  const patchBody = proposal.patch;

  useEffect(() => {
    window.baize.listWorkspaces()
      .then(res => {
        const active = (res.workspaces || []).find(w => w.id === res.activeWorkspaceId);
        setWorkspacePath(active ? active.rootPath : '未选择本地工作区');
      })
      .catch(() => setWorkspacePath('未选择本地工作区'));
  }, []);

  const handleChooseWorkspace = async () => {
    setLoading(true);
    try {
      const selected = await window.baize.authorizeWorkspace();
      setWorkspacePath(selected?.rootPath || '未选择本地工作区');
    } catch (error) {
      setStatusMsg(`错误：${error?.message || error}`);
      setStatusType('error');
    } finally {
      setLoading(false);
    }
  };

  const handlePreview = async () => {
    setLoading(true);
    setStatusMsg('正在预览补丁…');
    try {
      const result = await window.baize.previewPatch({ patch: patchBody });
      setStatusMsg(`预览通过：${result.files?.length || 0} 个文件可应用。`);
      setStatusType('ok');
    } catch (error) {
      setStatusMsg(`预览失败：${error?.message || error}`);
      setStatusType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async () => {
    if (!window.confirm('确认要把这个补丁应用到当前本地工作区吗？')) return;
    setLoading(true);
    setStatusMsg('正在应用补丁…');
    try {
      const result = await window.baize.applyPatch({ patch: patchBody });
      await window.baize.reportClaudeCodeApplicationResult(operation.id, {
        conversationId: operation.conversationId,
        clientId: operation.clientId,
        status: 'applied',
        appliedFiles: result.appliedFiles
      }).catch(() => null);
      setStatusMsg(`已应用：${(result.appliedFiles || []).join('、')}`);
      setStatusType('ok');
    } catch (error) {
      await window.baize.reportClaudeCodeApplicationResult(operation.id, {
        conversationId: operation.conversationId,
        clientId: operation.clientId,
        status: 'apply_failed',
        error: error?.message || String(error)
      }).catch(() => null);
      setStatusMsg(`应用失败：${error?.message || error}`);
      setStatusType('error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 16, border: '1px solid #e8e8e8', borderRadius: 8, margin: '8px 0' }}>
      <div style={{ marginBottom: 8 }}>
        <Space>
          <CodeOutlined />
          <strong>Claude Code 补丁草案</strong>
          {operation.permission?.mode && <Tag>{operation.permission.mode}</Tag>}
        </Space>
      </div>

      <div style={{ fontSize: 13, color: '#666', marginBottom: 8 }}>{summary}</div>

      {files.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>涉及文件</div>
          <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, color: '#666' }}>
            {files.map((f, i) => (
              <li key={i}>{f.path}（+{f.additions || 0} / -{f.deletions || 0}）</li>
            ))}
          </ul>
        </div>
      )}

      <div style={{ fontSize: 13, color: '#888', marginBottom: 12 }}>本地工作区：{workspacePath}</div>

      {statusMsg && (
        <div style={{
          marginBottom: 12, padding: '8px 12px', borderRadius: 4, fontSize: 13,
          background: statusType === 'ok' ? '#f6ffed' : statusType === 'error' ? '#fff2f0' : '#f5f5f5',
          border: `1px solid ${statusType === 'ok' ? '#b7eb8f' : statusType === 'error' ? '#ffccc7' : '#e8e8e8'}`
        }}>
          {loading && <Spin size="small" style={{ marginRight: 8 }} />}
          {statusMsg}
        </div>
      )}

      <Space>
        <Button icon={<FolderOpenOutlined />} loading={loading} onClick={handleChooseWorkspace}>
          选择本地工作区
        </Button>
        <Button icon={<EyeOutlined />} loading={loading} onClick={handlePreview}>
          预览补丁
        </Button>
        <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={handleApply}>
          应用到本地工作区
        </Button>
      </Space>
    </div>
  );
}

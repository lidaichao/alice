import { useState, useEffect, useRef } from 'react';
import { Button, Progress, Tag, Spin, Space } from 'antd';
import { CheckCircleOutlined, ExclamationCircleOutlined, BugOutlined, ReloadOutlined, CaretRightOutlined } from '@ant-design/icons';

function isActiveRun(run) {
  return run && !['completed', 'cancelled', 'timed_out', 'superseded'].includes(run.status);
}

export default function BugAnalysisCard({ run: initialRun, clientId }) {
  const [run, setRun] = useState(initialRun);
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const intervalRef = useRef(null);

  const total = run.total || 0;
  const completed = run.completed || 0;
  const failed = run.failed || 0;
  const percent = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;

  useEffect(() => {
    // Poll every 5s
    intervalRef.current = setInterval(async () => {
      try {
        const response = await window.baize.getBugAnalysisRun(initialRun.id);
        const updated = response.run || response;
        if (updated) {
          setRun(updated);
          if (!isActiveRun(updated) && intervalRef.current) {
            clearInterval(intervalRef.current);
          }
        }
      } catch {
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    }, 5000);

    // Initial fetch
    window.baize.getBugAnalysisRun(initialRun.id)
      .then(response => { const u = response.run || response; if (u) setRun(u); })
      .catch(() => {});

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [initialRun.id]);

  const handleConfirmComment = async (item) => {
    setLoading(true);
    setStatusMsg(`正在写入 ${item.issueKey} 评论…`);
    try {
      const response = await window.baize.confirmBugAnalysisComment(run.id, item.id, { clientId });
      const updated = response.run || response;
      if (updated) setRun(prev => ({ ...prev, ...updated }));
      setStatusMsg('');
    } catch (error) {
      setStatusMsg(`写入失败：${error?.message || error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRecoverItem = async (item) => {
    setLoading(true);
    setStatusMsg(`正在重试 ${item.issueKey}…`);
    try {
      const response = await window.baize.applyBugAnalysisRecovery(run.id, item.id, { actionId: 'retry_analysis', clientId });
      const updated = response.run || response;
      if (updated) setRun(prev => ({ ...prev, ...updated }));
      setStatusMsg('');
    } catch (error) {
      setStatusMsg(`重试失败：${error?.message || error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async () => {
    setLoading(true);
    setStatusMsg('正在恢复分析…');
    try {
      const response = await window.baize.resumeBugAnalysisRun(run.id, { clientId });
      const updated = response.run || response;
      if (updated) setRun(prev => ({ ...prev, ...updated }));
      setStatusMsg('');
    } catch (error) {
      setStatusMsg(`恢复失败：${error?.message || error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    try {
      const response = await window.baize.getBugAnalysisRun(run.id);
      const updated = response.run || response;
      if (updated) setRun(prev => ({ ...prev, ...updated }));
    } catch {}
  };

  const items = run.items || [];
  const awaitingCount = items.filter(i => i.status === 'awaiting_comment_confirmation').length;
  const analyzingCount = items.filter(i => i.status === 'analyzing').length;

  return (
    <div style={{ padding: 16, border: '1px solid #e8e8e8', borderRadius: 8, margin: '8px 0' }}>
      <div style={{ marginBottom: 12 }}>
        <Space>
          <BugOutlined />
          <strong>Jira BUG 工程分析</strong>
          <Tag>{run.status || 'unknown'}</Tag>
        </Space>
      </div>

      <div style={{ marginBottom: 12, fontSize: 13, color: '#666' }}>
        总数 {total} · 完成 {completed} · 失败 {failed}
        {awaitingCount > 0 && <span style={{ color: '#fa8c16' }}> · 待确认 {awaitingCount}</span>}
        {analyzingCount > 0 && <span style={{ color: '#1677ff' }}> · 分析中 {analyzingCount}</span>}
      </div>

      <Progress percent={percent} size="small" status={failed > 0 && completed + failed >= total ? 'exception' : undefined} />

      {statusMsg && (
        <div style={{ margin: '8px 0', color: '#888', fontSize: 13 }}>
          <Spin size="small" style={{ marginRight: 8 }} />
          {statusMsg}
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        {items.map((item) => (
          <div key={item.id} style={{
            padding: '8px 12px', marginBottom: 8,
            border: '1px solid #f0f0f0', borderRadius: 4,
            background: item.status === 'recovery_required' ? '#fff2f0' :
                       item.status === 'awaiting_comment_confirmation' ? '#fffbe6' :
                       item.status === 'completed' ? '#f6ffed' : '#fafafa'
          }}>
            <div style={{ marginBottom: 4 }}>
              <Space>
                <strong style={{ fontSize: 13 }}>{item.issueKey || item.id}</strong>
                <Tag color={
                  item.status === 'completed' ? 'green' :
                  item.status === 'failed' || item.status === 'recovery_required' ? 'red' :
                  item.status === 'awaiting_comment_confirmation' ? 'orange' :
                  item.status === 'analyzing' ? 'blue' : 'default'
                }>{item.status}</Tag>
              </Space>
            </div>

            {item.error && (
              <div style={{ fontSize: 12, color: '#ff4d4f', marginBottom: 4 }}>
                <ExclamationCircleOutlined style={{ marginRight: 4 }} />
                {item.error}
              </div>
            )}

            {item.commentDraft && item.status === 'awaiting_comment_confirmation' && !['cancelled', 'timed_out', 'superseded'].includes(run.status) && (
              <div style={{ marginBottom: 8 }}>
                <pre style={{
                  background: '#f5f5f5', padding: 8, borderRadius: 4,
                  fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  maxHeight: 120, overflowY: 'auto', margin: '4px 0'
                }}>
                  {item.commentDraft}
                </pre>
              </div>
            )}

            {item.status === 'awaiting_comment_confirmation' && item.commentDraft && !['cancelled', 'timed_out', 'superseded'].includes(run.status) && (
              <Button
                type="primary"
                size="small"
                icon={<CheckCircleOutlined />}
                loading={loading}
                onClick={() => handleConfirmComment(item)}
              >
                写入 Jira 评论
              </Button>
            )}

            {item.status === 'recovery_required' && (
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={loading}
                onClick={() => handleRecoverItem(item)}
              >
                重试分析
              </Button>
            )}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 8 }}>
        <Space>
          <Button size="small" icon={<ReloadOutlined />} onClick={handleRefresh}>刷新</Button>
          {isActiveRun(run) && (
            <Button size="small" icon={<CaretRightOutlined />} onClick={handleResume} loading={loading}>
              继续/恢复
            </Button>
          )}
        </Space>
      </div>
    </div>
  );
}

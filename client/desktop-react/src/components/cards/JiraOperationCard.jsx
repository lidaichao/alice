import { useState, useCallback, useEffect, useRef } from 'react';
import { Button, List, Tag, Space, Alert, Typography, Spin, Input, Select, Divider } from 'antd';
import {
  CheckOutlined, CloseOutlined, LoadingOutlined,
  CheckCircleFilled, ExclamationCircleFilled, ReloadOutlined, LinkOutlined
} from '@ant-design/icons';

const { Text, Title } = Typography;

/* ------------------------------------------------------------------ */
/* 子组件：草稿确认面板                                                   */
/* ------------------------------------------------------------------ */
function ConfirmPanel({ operation, disabled, onConfirm, onReject }) {
  const draftImport = operation?.draftImport || {};
  const drafts = draftImport.drafts || [];
  const count = draftImport.count || drafts.length;
  const warnings = draftImport.warnings || [];
  const isConfirming = disabled;

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      <Title level={5} style={{ margin: 0 }}>Jira 批量创建确认</Title>

      <Text type="secondary">
        已解析 {count} 个 Jira 需求单草稿，确认后会写入 Jira。
      </Text>

      {warnings.length > 0 && (
        <Alert type="warning" message={warnings.join('；')} showIcon style={{ padding: '4px 12px' }} />
      )}

      {drafts.length > 0 && (
        <List size="small" bordered dataSource={drafts.slice(0, 20)}
          renderItem={(draft) => (
            <List.Item style={{ padding: '4px 12px', fontSize: 13 }}>
              <Space size={4} wrap>
                <Text>{draft.summary}</Text>
                {draft.projectKey && <Tag color="blue" style={{ fontSize: 11, lineHeight: '18px' }}>{draft.projectKey}</Tag>}
                {draft.issueType && <Tag style={{ fontSize: 11, lineHeight: '18px' }}>{draft.issueType}</Tag>}
                {draft.assignee && <Text type="secondary" style={{ fontSize: 12 }}>负责人：{draft.assignee}</Text>}
              </Space>
            </List.Item>
          )}
        />
      )}
      {drafts.length > 20 && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          仅展示前 20 条，确认创建时仍按全部 {drafts.length} 条执行。
        </Text>
      )}

      <Space>
        <Button type="primary" icon={isConfirming ? <LoadingOutlined /> : <CheckOutlined />}
          loading={isConfirming} disabled={disabled}
          onClick={onConfirm}>
          确认创建 Jira 单
        </Button>
        <Button danger icon={<CloseOutlined />} disabled={disabled} onClick={onReject}>
          取消
        </Button>
      </Space>
    </Space>
  );
}

/* ------------------------------------------------------------------ */
/* 子组件：进度面板                                                       */
/* ------------------------------------------------------------------ */
function ProgressPanel({ message, createdCount, totalCount }) {
  const pct = totalCount > 0 ? Math.min(99, Math.round((createdCount / totalCount) * 100)) : 0;
  return (
    <div style={{ textAlign: 'center', padding: '12px 0' }}>
      <Spin indicator={<LoadingOutlined style={{ fontSize: 32 }} spin />} />
      <Title level={5} style={{ marginTop: 12 }}>Jira 正在创建</Title>
      <Text type="secondary">{message}</Text>
      {totalCount > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 28, fontWeight: 700, color: '#1677ff' }}>{createdCount} / {totalCount}</div>
          <Text type="secondary" style={{ fontSize: 12 }}>已创建 Jira 单</Text>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 子组件：成功面板                                                       */
/* ------------------------------------------------------------------ */
function SuccessPanel({ operation }) {
  const createdIssues = (operation?.createdIssues || []).filter(Boolean);
  const keyList = createdIssues.map((i) => i.key).filter(Boolean);

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      <Space>
        <CheckCircleFilled style={{ color: '#52c41a', fontSize: 20 }} />
        <Title level={5} style={{ margin: 0, color: '#52c41a' }}>Jira 创建成功</Title>
      </Space>
      {keyList.length > 0 ? (
        <>
          <Text>已创建 {keyList.length} 个 Jira 单：</Text>
          <Space wrap>
            {keyList.map((key) => (
              <Tag key={key} color="green" style={{ cursor: 'pointer', fontSize: 13 }}
                onClick={() => window.open(`https://jira.lidong.xin/browse/${key}`, '_blank')}>
                <LinkOutlined style={{ marginRight: 4 }} />{key}
              </Tag>
            ))}
          </Space>
        </>
      ) : (
        <Text>Jira 单创建成功。</Text>
      )}
    </Space>
  );
}

/* ------------------------------------------------------------------ */
/* 子组件：恢复面板                                                       */
/* ------------------------------------------------------------------ */
function RecoveryPanel({ operation, conversationId, clientId }) {
  const recovery = operation?.recovery || {};
  const [sending, setSending] = useState(false);
  const [statusMsg, setStatusMsg] = useState('请选择下一步操作。');
  const [iv, setIv] = useState({});
  const [disabled, setDisabled] = useState(false);

  const supplement = recovery.supplement;
  const actions = recovery.actions || [];
  const createdCount = (operation?.createdIssues || []).filter(Boolean).length;

  const handleAction = useCallback(async (action) => {
    if (action.requiresConfirmation && !window.confirm(action.description || '确认执行？')) return;
    setSending(true); setDisabled(true); setStatusMsg('正在执行恢复操作。');
    try {
      const res = await window.baize.recoverJiraOperation(operation.id, {
        conversationId, clientId, actionId: action.id, inputs: iv
      });
      const u = res?.operation || res;
      if (u?.status === 'created') setStatusMsg('恢复成功，刷新查看结果。');
      else if (u?.status === 'recovery_required') {
        setStatusMsg('恢复操作未完成。'); setSending(false); setDisabled(false);
      } else if (u?.status === 'rejected') setStatusMsg('已取消 Jira 创建。');
      else { setStatusMsg(u?.error || '恢复操作未完成。'); setSending(false); setDisabled(false); }
    } catch {
      setStatusMsg('恢复失败。'); setSending(false); setDisabled(false);
    }
  }, [operation, conversationId, clientId, iv]);

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      <Space>
        <ExclamationCircleFilled style={{ color: '#faad14', fontSize: 20 }} />
        <Title level={5} style={{ margin: 0, color: '#faad14' }}>Jira 创建失败，可尝试恢复</Title>
      </Space>
      <Text type="secondary">{recovery.summary || 'Alice 已分析失败原因。'}</Text>
      {operation?.error && <Alert type="error" message={`错误：${operation.error}`} showIcon style={{ padding: '4px 12px' }} />}
      {recovery.reason && <Alert type="warning" message={`原因：${recovery.reason}`} showIcon style={{ padding: '4px 12px' }} />}
      {createdCount > 0 && <Text type="secondary" style={{ fontSize: 12 }}>已创建 {createdCount} 个，恢复只处理剩余草稿。</Text>}

      {supplement?.inputs?.length > 0 && (
        <>
          <Divider style={{ margin: '4px 0' }} />
          <Text>{supplement.prompt || '请补充信息。'}</Text>
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            {supplement.inputs.map((item) => (
              <div key={item.id}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>{item.label || item.id}</Text>
                {item.type === 'select' ? (
                  <Select style={{ width: '100%' }} placeholder="请选择" disabled={disabled}
                    onChange={(v) => setIv(p => ({ ...p, [item.id]: v }))}
                    options={(item.options || []).map(v => ({ value: v, label: v }))} />
                ) : (
                  <Input placeholder={item.label || item.id} disabled={disabled}
                    onChange={(e) => setIv(p => ({ ...p, [item.id]: e.target.value }))} />
                )}
              </div>
            ))}
          </Space>
        </>
      )}

      {actions.length > 0 && (
        <>
          <Divider style={{ margin: '4px 0' }} />
          <Space wrap>
            {actions.map((a) => (
              <Button key={a.id} type={a.style === 'primary' ? 'primary' : 'default'}
                danger={a.style === 'danger'} icon={<ReloadOutlined />}
                loading={sending} disabled={disabled}
                onClick={() => handleAction(a)}>
                {a.label || a.id}
              </Button>
            ))}
          </Space>
        </>
      )}

      <Text type={statusMsg.includes('成功') ? 'success' : statusMsg.includes('失败') ? 'danger' : 'secondary'}
        style={{ fontSize: 12 }}>{statusMsg}</Text>
    </Space>
  );
}

/* ================================================================== */
/* 主组件：JiraOperationCard 状态机编排                                   */
/* ================================================================== */
const POLL_INTERVAL = 2000;

function JiraOperationCard({ operation, conversationId, clientId }) {
  const [cardState, setCardState] = useState('confirm'); // confirm | progress | success | recovery
  const [progressMsg, setProgressMsg] = useState('Claude Code 正在调用 Jira 插件执行已确认的创建操作。');
  const [currentOp, setCurrentOp] = useState(operation);
  const [createdCount, setCreatedCount] = useState(0);
  const timerRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }, []);

  // 根据 initial operation status 决定初始面板
  useEffect(() => {
    if (operation?.status === 'created') {
      setCardState('success');
      setCreatedCount((operation.createdIssues || []).length);
    } else if (operation?.status === 'recovery_required') {
      setCardState('recovery');
    } else if (operation?.status === 'confirmed_running') {
      setCardState('progress');
      setCreatedCount((operation.createdIssues || []).length);
    }
  }, [operation]);

  // ---- 轮询进度 ----
  useEffect(() => {
    if (cardState !== 'progress') return;

    const poll = async () => {
      if (!window.baize?.getJiraOperation) return;
      try {
        const updated = await window.baize.getJiraOperation(operation.id);
        if (!updated) return;
        setCurrentOp(updated);
        const issues = updated.createdIssues || [];
        setCreatedCount(issues.length);

        if (updated.status === 'created') {
          setCardState('success');
          stopPolling();
        } else if (updated.status === 'recovery_required') {
          setCardState('recovery');
          stopPolling();
        } else {
          setProgressMsg(issues.length > 0
            ? `Claude Code 已创建 ${issues.length} 个 Jira 单，正在继续处理剩余草稿。`
            : '正在等待本机 Claude Code 返回下一步 Jira 工具调用。');
        }
      } catch { /* ignore poll errors */ }
    };

    poll();
    timerRef.current = setInterval(poll, POLL_INTERVAL);
    return stopPolling;
  }, [cardState, operation.id, stopPolling]);

  // ---- 确认创建 ----
  const handleConfirm = useCallback(async () => {
    if (!window.baize?.confirmJiraOperation) return;
    setCardState('progress');
    setProgressMsg('正在交给本机 Claude Code 调用 Jira 插件创建。');
    try {
      await window.baize.confirmJiraOperation(
        operation.id,
        { conversationId, clientId },
        (event) => { if (event?.message) setProgressMsg(event.message); }
      );
    } catch {
      setCardState('recovery');
    }
  }, [operation, conversationId, clientId]);

  // ---- 取消 ----
  const handleReject = useCallback(async () => {
    if (!window.baize?.rejectJiraOperation) return;
    try { await window.baize.rejectJiraOperation(operation.id, { clientId }); } catch {}
    setCardState('confirm'); // stay with disabled message
  }, [operation, clientId]);

  const totalCount = operation?.draftImport?.count || operation?.draftImport?.drafts?.length || 0;

  return (
    <div style={{ padding: 4 }}>
      {cardState === 'confirm' && (
        <ConfirmPanel operation={currentOp} disabled={false} onConfirm={handleConfirm} onReject={handleReject} />
      )}
      {cardState === 'progress' && (
        <ProgressPanel message={progressMsg} createdCount={createdCount} totalCount={totalCount} />
      )}
      {cardState === 'success' && (
        <SuccessPanel operation={currentOp} />
      )}
      {cardState === 'recovery' && (
        <RecoveryPanel operation={currentOp} conversationId={conversationId} clientId={clientId} />
      )}
    </div>
  );
}

export default JiraOperationCard;

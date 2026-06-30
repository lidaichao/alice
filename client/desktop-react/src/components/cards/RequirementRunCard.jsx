import { useState, useEffect, useRef } from 'react';
import { Button, Spin, Collapse, Tag, Space } from 'antd';
import { CheckCircleOutlined, ExclamationCircleOutlined, LoadingOutlined, FileTextOutlined, PlayCircleOutlined } from '@ant-design/icons';

const STATUS_LABELS = {
  awaiting_plan: '待生成计划',
  planning: '生成计划中',
  plan_failed: '计划失败',
  awaiting_execution_confirmation: '待确认执行',
  queued_for_execution: '待执行',
  executing: '执行中',
  execution_failed: '执行失败',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  timed_out: '已超时'
};

const STATUS_COLORS = {
  completed: 'green',
  failed: 'red',
  plan_failed: 'red',
  execution_failed: 'red',
  cancelled: 'default',
  timed_out: 'orange',
  executing: 'blue',
  planning: 'blue'
};

export default function RequirementRunCard({ run: initialRun, conversationId, clientId }) {
  const [run, setRun] = useState(initialRun);
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const [operations, setOperations] = useState([]);
  const intervalRef = useRef(null);

  useEffect(() => {
    // Poll for status updates every 2s
    intervalRef.current = setInterval(async () => {
      try {
        const response = await window.baize.getRequirementCompletionRun(initialRun.id);
        const updated = response.run || response;
        if (updated) setRun(prev => ({ ...prev, ...updated }));
      } catch {}
    }, 2000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [initialRun.id]);

  const status = run.status || 'awaiting_plan';
  const statusLabel = STATUS_LABELS[status] || status;

  const handleConfirmPlan = async () => {
    setLoading(true);
    setStatusMsg('正在生成工程执行计划…');
    try {
      const response = await window.baize.confirmRequirementCompletionRun(
        run, { phase: 'plan', clientId },
        (event) => {
          const msg = event?.message || event?.text || event?.reply || '需求计划生成中…';
          setOperations(prev => [...prev, msg]);
        }
      );
      const updated = response.run || response;
      if (updated) setRun(prev => ({ ...prev, ...updated }));
      setStatusMsg('');
    } catch (error) {
      setStatusMsg(`错误：${error?.message || error}`);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmExecute = async () => {
    setLoading(true);
    setStatusMsg('正在按确认计划执行工程修改…');
    try {
      const response = await window.baize.confirmRequirementCompletionRun(
        run, { phase: 'execute', clientId },
        (event) => {
          const msg = event?.message || event?.text || event?.reply || '需求工程执行中…';
          setOperations(prev => [...prev, msg]);
        }
      );
      const updated = response.run || response;
      if (updated) setRun(prev => ({ ...prev, ...updated }));
      setStatusMsg('');
    } catch (error) {
      setStatusMsg(`错误：${error?.message || error}`);
    } finally {
      setLoading(false);
    }
  };

  const showPlanBtn = status === 'awaiting_plan' || status === 'plan_failed';
  const showExecuteBtn = status === 'awaiting_execution_confirmation';
  const isTerminal = ['completed', 'failed', 'cancelled', 'timed_out'].includes(status);

  return (
    <div style={{ padding: 16, border: '1px solid #e8e8e8', borderRadius: 8, margin: '8px 0' }}>
      <div style={{ marginBottom: 12 }}>
        <Space>
          <FileTextOutlined />
          <strong>工程需求完成：{run.title || run.id}</strong>
          <Tag color={STATUS_COLORS[status] || 'default'}>{statusLabel}</Tag>
        </Space>
      </div>

      {(run.requirementText || run.originalText) && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>需求描述</div>
          <pre style={{
            background: '#f5f5f5', padding: 12, borderRadius: 4,
            fontSize: 13, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            maxHeight: 200, overflowY: 'auto', margin: 0
          }}>
            {run.requirementText || run.originalText}
          </pre>
        </div>
      )}

      {run.plan?.text && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>执行计划</div>
          <pre style={{
            background: '#f0f5ff', padding: 12, borderRadius: 4,
            fontSize: 13, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            maxHeight: 200, overflowY: 'auto', margin: 0, border: '1px solid #d6e4ff'
          }}>
            {run.plan.text}
          </pre>
        </div>
      )}

      {run.stoppedReason || run.error ? (
        <div style={{ marginBottom: 12, padding: '8px 12px', background: '#fff2f0', border: '1px solid #ffccc7', borderRadius: 4 }}>
          <ExclamationCircleOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
          {run.stoppedReason || run.error}
        </div>
      ) : isTerminal && status === 'completed' ? (
        <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 4 }}>
          <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 8 }} />
          需求工程执行已完成。
        </div>
      ) : null}

      {operations.length > 0 && (
        <Collapse
          ghost
          size="small"
          items={[{
            key: 'ops',
            label: `操作日志（${operations.length} 条）`,
            children: (
              <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                {operations.map((op, i) => (
                  <div key={i} style={{ fontSize: 12, color: '#666', padding: '4px 0', borderBottom: '1px solid #f0f0f0' }}>
                    {op}
                  </div>
                ))}
              </div>
            )
          }]}
        />
      )}

      {statusMsg && (
        <div style={{ margin: '8px 0', color: '#888', fontSize: 13 }}>
          <Spin size="small" style={{ marginRight: 8 }} />
          {statusMsg}
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        <Space>
          {showPlanBtn && (
            <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={handleConfirmPlan}>
              生成执行计划
            </Button>
          )}
          {showExecuteBtn && (
            <Button type="primary" icon={<CheckCircleOutlined />} loading={loading} onClick={handleConfirmExecute}>
              确认并开始执行
            </Button>
          )}
        </Space>
      </div>
    </div>
  );
}

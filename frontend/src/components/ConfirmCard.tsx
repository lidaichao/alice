import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { ShieldAlert, CheckCircle, XCircle, RotateCcw } from 'lucide-react';
import IssueDraftList from '@/components/IssueDraftList';
import type { ConfirmCard as ConfirmCardType, RecoveryAction } from '@/store/slices/chatSlice';

interface Props {
  card: ConfirmCardType;
  progressMessage?: string;
  onConfirm: (
    opId: string,
    opts?: { recoveryAction?: string; supplement?: Record<string, string> },
  ) => Promise<void>;
  onReject: (opId: string) => Promise<void>;
  resolved?: boolean;
  resolvedText?: string;
}

function actionNeedsForm(action: RecoveryAction): boolean {
  return (
    action.id === 'submit_supplement' ||
    (Array.isArray(action.inputs) && action.inputs.length > 0)
  );
}

export default function ConfirmCard({ card, progressMessage, onConfirm, onReject, resolved, resolvedText }: Props) {
  const [loading, setLoading] = useState<'confirm' | 'reject' | string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});

  if (resolved) {
    return (
      <div className="mt-3 border border-border rounded-lg p-3 text-sm bg-muted/30">
        {resolvedText || '✅ 已处理'}
      </div>
    );
  }

  const isRecovery = card.operation_status === 'recovery_required' || !!card.recovery?.actions?.length;

  const supplementAction = useMemo(
    () => (card.recovery?.actions || []).find((a) => a.id === 'submit_supplement'),
    [card.recovery?.actions],
  );

  const runConfirm = async (
    recoveryAction?: string,
    supplement?: Record<string, string>,
  ) => {
    if (loading) return;
    setLoading(recoveryAction || 'confirm');
    try {
      await onConfirm(card.op_id, recoveryAction ? { recoveryAction, supplement } : undefined);
    } finally {
      setLoading(null);
    }
  };

  const handleSupplementSubmit = async () => {
    const inputs = supplementAction?.inputs || [{ id: 'projectKey', required: true }];
    const supplement: Record<string, string> = {};
    for (const inp of inputs) {
      const val = (formValues[inp.id] || '').trim();
      if (inp.required && !val) {
        return;
      }
      if (val) supplement[inp.id] = val;
    }
    await runConfirm('submit_supplement', supplement);
  };

  const handleReject = async () => {
    if (loading) return;
    setLoading('reject');
    try {
      await onReject(card.op_id);
    } finally {
      setLoading(null);
    }
  };

  const op = card.operation || {};
  const typeLabel = (op.type === 'add_jira_comment' || op.type === 'add_comment') ? '添加评论'
    : (op.type === 'create_issue' || op.type === 'bulk_create') ? '创建 Issue'
    : op.type === 'update_issue' ? '更新 Issue'
    : op.type === 'transition_issue' ? '状态流转'
    : op.type || '未知操作';

  const recoveryActions = (card.recovery?.actions || []).filter(
    (a) => a.id !== 'cancel' && !actionNeedsForm(a),
  );

  return (
    <div className="mt-3 border border-orange-400/50 bg-orange-50/30 dark:bg-orange-900/40 rounded-lg p-4 animate-in fade-in">
      <div className="flex items-start gap-3 mb-3">
        <ShieldAlert className="w-5 h-5 text-orange-500 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-orange-700 dark:text-orange-300">
            {isRecovery ? '⚠️ 需要恢复 — ' : '🛡️ Jira 操作确认 — '}
            {typeLabel}
          </div>
          {isRecovery && card.recovery?.summary && (
            <div className="text-xs text-amber-800 dark:text-amber-200 mt-1">
              {card.recovery.summary}
            </div>
          )}
          {isRecovery && card.recovery?.reason && (
            <div className="text-xs text-muted-foreground mt-0.5">
              {card.recovery.reason}
            </div>
          )}
          {op.issue_key && (
            <div className="text-xs text-muted-foreground mt-1">
              目标: <span className="font-mono font-medium">{op.issue_key}</span>
            </div>
          )}
          {op.summary && (
            <div className="text-xs text-muted-foreground mt-0.5 truncate">
              {op.summary}
            </div>
          )}
          {op.description && (
            <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
              {op.description}
            </div>
          )}
          {(op.drafts_count ?? 0) > 1 && (
            <div className="text-xs text-muted-foreground mt-1">
              共 {op.drafts_count} 条待创建
            </div>
          )}
        </div>
      </div>

      {op.drafts && op.drafts.length > 0 && (
        <div className="mb-3">
          <IssueDraftList items={op.drafts} />
        </div>
      )}
      {op.warnings && op.warnings.length > 0 && (
        <ul className="mb-3 text-xs text-amber-700 dark:text-amber-300 list-disc pl-4">
          {op.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}

      {supplementAction && (
        <div className="mb-3 p-3 rounded-md border border-amber-300/50 bg-background/80 space-y-2">
          <div className="text-xs font-medium text-amber-900 dark:text-amber-100">
            {supplementAction.label || '补充必填字段'}
          </div>
          {(supplementAction.inputs || [{ id: 'projectKey', label: '项目 Key', required: true }]).map(
            (inp) => (
              <label key={inp.id} className="block text-xs">
                <span className="text-muted-foreground">{inp.label || inp.id}</span>
                <input
                  className="mt-1 w-full rounded border border-border px-2 py-1 text-sm bg-background"
                  value={formValues[inp.id] || ''}
                  onChange={(e) =>
                    setFormValues((v) => ({ ...v, [inp.id]: e.target.value }))
                  }
                  placeholder={inp.id === 'projectKey' ? '例如 CT' : ''}
                />
              </label>
            ),
          )}
          <Button
            size="sm"
            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white"
            disabled={loading !== null}
            onClick={() => void handleSupplementSubmit()}
          >
            {loading === 'submit_supplement' ? '提交并继续创建…' : '补充并继续创建'}
          </Button>
        </div>
      )}

      {progressMessage && (
        <div className="mb-3 text-xs text-muted-foreground animate-pulse">
          {progressMessage}
        </div>
      )}

      <div className="flex flex-wrap gap-2 justify-end">
        <Button
          variant="destructive"
          size="sm"
          onClick={handleReject}
          disabled={loading !== null}
          className="gap-1.5"
        >
          <XCircle size={14} />
          {loading === 'reject' ? '拒绝中...' : '拒绝拦截'}
        </Button>
        {isRecovery && recoveryActions.length > 0 ? (
          recoveryActions.map((action) => (
            <Button
              key={action.id}
              variant="default"
              size="sm"
              onClick={() => runConfirm(action.id)}
              disabled={loading !== null}
              className="gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              <RotateCcw size={14} />
              {loading === action.id ? '执行中...' : action.label}
            </Button>
          ))
        ) : !supplementAction ? (
          <Button
            variant="default"
            size="sm"
            onClick={() => runConfirm()}
            disabled={loading !== null}
            className="gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            <CheckCircle size={14} />
            {loading === 'confirm' ? '放行中...' : '授权放行'}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

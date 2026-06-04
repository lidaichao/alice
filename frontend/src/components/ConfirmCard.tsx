import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { ShieldAlert, CheckCircle, XCircle, RotateCcw } from 'lucide-react';
import IssueDraftList from '@/components/IssueDraftList';
import type { ConfirmCard as ConfirmCardType } from '@/store/slices/chatSlice';

interface Props {
  card: ConfirmCardType;
  progressMessage?: string;
  onConfirm: (opId: string, opts?: { recoveryAction?: string }) => Promise<void>;
  onReject: (opId: string) => Promise<void>;
}

export default function ConfirmCard({ card, progressMessage, onConfirm, onReject }: Props) {
  const [loading, setLoading] = useState<'confirm' | 'reject' | string | null>(null);

  const isRecovery = card.operation_status === 'recovery_required' || !!card.recovery?.actions?.length;

  const runConfirm = async (recoveryAction?: string) => {
    if (loading) return;
    setLoading(recoveryAction || 'confirm');
    try {
      await onConfirm(card.op_id, recoveryAction ? { recoveryAction } : undefined);
    } finally {
      setLoading(null);
    }
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

  const recoveryActions = (card.recovery?.actions || []).filter((a) => a.id !== 'cancel');

  return (
    <div className="mt-3 border border-orange-400/50 bg-orange-50/30 dark:bg-orange-950/20 rounded-lg p-4 animate-in fade-in">
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
        ) : (
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
        )}
      </div>
    </div>
  );
}

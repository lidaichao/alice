import { useCallback, useRef, useState } from 'react';
import { buildAliceUserHeaders, buildJiraWriteRequestBody } from '@/lib/runtimeConfig';
import { confirmOperationWithProgress } from '@/lib/operationConfirmStream';

export type OperationActionResult = {
  ok: boolean;
  message?: string;
  error?: string;
  error_code?: string;
  operation?: { created_issues?: { key?: string }[]; recovery?: unknown };
};

export type BatchItemResult = {
  opId: string;
  ok: boolean;
  error?: string;
};

export type BatchProgress = {
  current: number;
  total: number;
  action: 'confirm' | 'reject';
};

export type UseOperationActionsOptions = {
  /** Chat path: append assistant message after confirm/reject. Console omits this. */
  onConfirmSuccess?: (result: OperationActionResult) => void | Promise<void>;
  onRejectSuccess?: () => void | Promise<void>;
  onBatchComplete?: (results: BatchItemResult[]) => void | Promise<void>;
};

export function useOperationActions(opts: UseOperationActionsOptions = {}) {
  const [progressByOpId, setProgressByOpId] = useState<Record<string, string>>({});
  const [busyOpId, setBusyOpId] = useState<string | null>(null);
  const [lastError, setLastError] = useState<Record<string, string>>({});
  const [batchProgress, setBatchProgress] = useState<BatchProgress | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);
  const batchGuard = useRef(false);

  const confirm = useCallback(
    async (
      opId: string,
      actionOpts?: { recoveryAction?: string; supplement?: Record<string, string> },
    ): Promise<OperationActionResult> => {
      const extra: Record<string, unknown> = {};
      if (actionOpts?.recoveryAction) extra.recovery_action = actionOpts.recoveryAction;
      if (actionOpts?.supplement) extra.supplement = actionOpts.supplement;
      const body = buildJiraWriteRequestBody(extra);
      setBusyOpId(opId);
      setLastError((e) => {
        const next = { ...e };
        delete next[opId];
        return next;
      });
      setProgressByOpId((p) => ({ ...p, [opId]: '开始执行…' }));
      try {
        const data = await confirmOperationWithProgress(opId, body, (ev) => {
          setProgressByOpId((p) => ({ ...p, [opId]: ev.message || ev.phase }));
        });
        setProgressByOpId((p) => {
          const next = { ...p };
          delete next[opId];
          return next;
        });
        const result: OperationActionResult = {
          ok: data.ok !== false,
          message: data.message,
          error: data.error,
          error_code: data.error_code,
          operation: data.operation,
        };
        if (data.ok === false) {
          setLastError((e) => ({ ...e, [opId]: data.error || '操作失败' }));
          const err = new Error(data.error || '操作失败') as Error & { error_code?: string };
          err.error_code = data.error_code;
          throw err;
        }
        await opts.onConfirmSuccess?.(result);
        return result;
      } finally {
        setBusyOpId((id) => (id === opId ? null : id));
      }
    },
    [opts],
  );

  const reject = useCallback(
    async (opId: string): Promise<void> => {
      setBusyOpId(opId);
      setLastError((e) => {
        const next = { ...e };
        delete next[opId];
        return next;
      });
      try {
        const res = await fetch(`/operations/${opId}/reject`, {
          method: 'POST',
          headers: buildAliceUserHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(buildJiraWriteRequestBody()),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.ok === false) {
          const err = (data as { error?: string }).error || '拒绝失败';
          setLastError((e) => ({ ...e, [opId]: err }));
          throw new Error(err);
        }
        await opts.onRejectSuccess?.();
      } finally {
        setBusyOpId((id) => (id === opId ? null : id));
      }
    },
    [opts],
  );

  const runBatch = useCallback(
    async (
      opIds: string[],
      action: 'confirm' | 'reject',
    ): Promise<BatchItemResult[]> => {
      if (batchGuard.current || opIds.length === 0) return [];
      batchGuard.current = true;
      setBatchBusy(true);
      const results: BatchItemResult[] = [];
      try {
        for (let i = 0; i < opIds.length; i++) {
          const opId = opIds[i];
          setBatchProgress({ current: i + 1, total: opIds.length, action });
          try {
            if (action === 'confirm') {
              await confirm(opId);
            } else {
              await reject(opId);
            }
            results.push({ opId, ok: true });
          } catch (e) {
            const err = e instanceof Error ? e.message : String(e);
            results.push({ opId, ok: false, error: err });
          }
        }
        await opts.onBatchComplete?.(results);
        return results;
      } finally {
        setBatchProgress(null);
        setBatchBusy(false);
        batchGuard.current = false;
      }
    },
    [confirm, reject, opts],
  );

  const confirmBatch = useCallback(
    (opIds: string[]) => runBatch(opIds, 'confirm'),
    [runBatch],
  );

  const rejectBatch = useCallback(
    (opIds: string[]) => runBatch(opIds, 'reject'),
    [runBatch],
  );

  const clearError = useCallback((opId: string) => {
    setLastError((e) => {
      const next = { ...e };
      delete next[opId];
      return next;
    });
  }, []);

  return {
    confirm,
    reject,
    confirmBatch,
    rejectBatch,
    progressByOpId,
    busyOpId,
    lastError,
    batchProgress,
    batchBusy,
    clearError,
  };
}

import React, { useEffect, useState, useCallback } from 'react';
import { Bell, ArrowRight, X } from 'lucide-react';

interface ApprovalBannerProps {
  userId: string;
  onOpenApproval: () => void;
  pollIntervalMs?: number;
}

const ApprovalBanner: React.FC<ApprovalBannerProps> = ({
  userId,
  onOpenApproval,
  pollIntervalMs = 10_000,
}) => {
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const fetchPending = useCallback(async () => {
    try {
      const params = new URLSearchParams({ status: 'pending' });
      if (userId) params.set('user_id', userId);
      const r = await fetch(`/operations?${params.toString()}`, {
        signal: AbortSignal.timeout(5000),
      });
      if (!r.ok) { setError(`HTTP ${r.status}`); return; }
      const d = await r.json();
      if (d.ok) {
        setPendingCount((d.operations || []).length);
        setError(null);
      } else {
        setError(d.error || 'unknown');
      }
    } catch {
      setError('网络错误');
    }
  }, [userId]);

  useEffect(() => {
    fetchPending();
    const id = setInterval(fetchPending, pollIntervalMs);
    return () => clearInterval(id);
  }, [fetchPending, pollIntervalMs]);

  // 每次有新的 pending 数据时取消 dismiss
  useEffect(() => {
    if (pendingCount > 0) setDismissed(false);
  }, [pendingCount]);

  if (pendingCount === 0 || dismissed) return null;

  return (
    <div className="sticky top-0 z-20 flex items-center justify-between px-4 py-2.5 bg-amber-50 border-b border-amber-400 text-amber-900 text-sm">
      <button
        onClick={onOpenApproval}
        className="flex items-center gap-2 flex-1 min-w-0 hover:opacity-80 transition-opacity"
      >
        <Bell size={15} className="shrink-0 text-amber-600" />
        <span className="truncate">
          🔔 有 <strong>{pendingCount}</strong> 项待审批操作 — 查看审批中心
        </span>
        <ArrowRight size={14} className="shrink-0 text-amber-500" />
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); setDismissed(true); }}
        className="shrink-0 p-1 rounded hover:bg-amber-100 transition-colors ml-2"
        title="暂时关闭"
      >
        <X size={14} className="text-amber-500" />
      </button>
      {error && (
        <span className="text-[10px] text-amber-500 ml-2 shrink-0 hidden sm:inline">
          ({error})
        </span>
      )}
    </div>
  );
};

export default ApprovalBanner;

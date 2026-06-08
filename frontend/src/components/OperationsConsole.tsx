import React, { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { RefreshCw, ArrowLeft, Activity } from 'lucide-react';

type OpRow = {
  id: string;
  status: string;
  kind?: string;
  conversation_id?: string;
  created_at?: string;
  updated_at?: string;
  warnings?: string[];
  error?: string | null;
  operation?: { issue_key?: string; type?: string };
};

type HealthPayload = {
  status?: string;
  hub_only_jira?: boolean;
  integrations?: Record<string, { status?: string; detail?: string }>;
};

export const OperationsConsole: React.FC<{ onBack: () => void }> = ({ onBack }) => {
  const [ops, setOps] = useState<OpRow[]>([]);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const [hRes, oRes] = await Promise.all([
        fetch('/health'),
        fetch('/operations?limit=80'),
      ]);
      if (hRes.ok) setHealth(await hRes.json());
      if (!oRes.ok) throw new Error(`operations HTTP ${oRes.status}`);
      const data = await oRes.json();
      setOps(data.operations || []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const pending = ops.filter((o) =>
    ['awaiting_confirmation', 'recovery_required'].includes(o.status),
  );
  const active = ops.filter((o) => o.status === 'running');
  const failed = ops.filter((o) => o.status === 'failed');

  return (
    <div className="flex flex-col h-full min-w-0 bg-background">
      <header className="flex items-center gap-3 px-4 py-3 border-b border-border shrink-0">
        <Button variant="ghost" size="icon" onClick={onBack} title="返回聊天">
          <ArrowLeft size={18} />
        </Button>
        <div className="flex-1">
          <h1 className="text-sm font-semibold">审批管控台</h1>
          <p className="text-[11px] text-muted-foreground">待确认 · 进行中 · 失败 · 链路健康</p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          <span className="ml-1">刷新</span>
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {err && (
          <div className="text-sm text-red-500 border border-red-200 rounded-lg p-3">{err}</div>
        )}

        <section className="rounded-lg border border-border p-3">
          <div className="flex items-center gap-2 text-xs font-semibold mb-2">
            <Activity size={14} />
            链路健康
          </div>
          {health ? (
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>Hub: <span className="font-mono">{health.status}</span></div>
              <div>Hub-only Jira: <span className="font-mono">{String(health.hub_only_jira)}</span></div>
              {Object.entries(health.integrations || {}).map(([k, v]) => (
                <div key={k}>
                  {k}: <span className="font-mono">{v.status}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">加载中…</p>
          )}
        </section>

        <OpSection title={`待审批 (${pending.length})`} rows={pending} empty="暂无待确认操作" />
        <OpSection title={`进行中 (${active.length})`} rows={active} empty="暂无进行中操作" />
        <OpSection title={`失败 (${failed.length})`} rows={failed} empty="暂无失败记录" />
      </div>
    </div>
  );
};

function OpSection({
  title,
  rows,
  empty,
}: {
  title: string;
  rows: OpRow[];
  empty: string;
}) {
  return (
    <section className="rounded-lg border border-border">
      <div className="px-3 py-2 border-b border-border text-xs font-semibold">{title}</div>
      {rows.length === 0 ? (
        <p className="px-3 py-4 text-xs text-muted-foreground">{empty}</p>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((o) => (
            <li key={o.id} className="px-3 py-2 text-[11px] space-y-0.5">
              <div className="flex justify-between gap-2">
                <span className="font-mono truncate">{o.id}</span>
                <span className="shrink-0 text-muted-foreground">{o.status}</span>
              </div>
              <div className="text-muted-foreground truncate">
                {o.kind}
                {o.operation?.issue_key ? ` · ${o.operation.issue_key}` : ''}
                {o.conversation_id ? ` · ${o.conversation_id.slice(0, 8)}…` : ''}
              </div>
              {o.error && <div className="text-red-500 truncate">{o.error}</div>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

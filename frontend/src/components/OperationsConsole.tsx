import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { RefreshCw, ArrowLeft, Activity, CheckCircle, XCircle, Link2 } from 'lucide-react';
import { useOperationActions } from '@/hooks/useOperationActions';
import { useToast } from '@/components/Toast';
import {
  buildAliceUserHeaders,
  getAliceUserId,
  loadRuntimeConfig,
  saveRuntimeConfig,
} from '@/lib/runtimeConfig';
import { useChatStore } from '@/store/useChatStore';
import type { RecoveryAction, RecoveryInfo } from '@/store/slices/chatSlice';

type OpRow = {
  id: string;
  status: string;
  kind?: string;
  conversation_id?: string;
  created_at?: string;
  updated_at?: string;
  drafts_count?: number;
  warnings?: string[];
  error?: string | null;
  recovery?: RecoveryInfo;
  operation?: { issue_key?: string; type?: string; summary?: string };
  user_id?: string;
  rejected_by?: string;
  rejected_at?: string;
  confirmed_by?: string;
  confirmed_at?: string;
};

type HealthPayload = {
  status?: string;
  hub_only_jira?: boolean;
  integrations?: Record<string, { status?: string; detail?: string }>;
};

function actionNeedsForm(action: RecoveryAction): boolean {
  return (
    action.id === 'submit_supplement' ||
    (Array.isArray(action.inputs) && action.inputs.length > 0)
  );
}

export const OperationsConsole: React.FC<{ onBack: () => void; embedded?: boolean }> = ({ onBack, embedded }) => {
  const [ops, setOps] = useState<OpRow[]>([]);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchSummary, setBatchSummary] = useState('');
  const [userId, setUserId] = useState(() => getAliceUserId());
  const [filterMode, setFilterMode] = useState<'mine' | 'all'>('mine');
  const [activeTab, setActiveTab] = useState<string>('pending');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const setActiveSession = useChatStore((s) => s.setActiveSession);
  const setMainView = useChatStore((s) => s.setMainView);
  const approvalDataVersion = useChatStore((s) => s.approvalDataVersion);
  const { toast } = useToast();

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const headers = buildAliceUserHeaders();
      const [hRes, oRes] = await Promise.all([
        fetch('/health', { headers }),
        fetch(filterMode === 'mine'
          ? `/operations?limit=80&user_id=${encodeURIComponent(userId)}`
          : '/operations?limit=80',
          { headers }),
      ]);
      if (hRes.ok) setHealth(await hRes.json());
      if (!oRes.ok) throw new Error(`operations HTTP ${oRes.status}`);
      const data = await oRes.json();
      setOps(data.operations || []);
      setSelectedIds(new Set());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      toast('连接断开，正在重连...', { type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [filterMode, userId]);

  const {
    confirm,
    reject,
    confirmBatch,
    rejectBatch,
    progressByOpId,
    busyOpId,
    lastError,
    batchProgress,
    batchBusy,
  } = useOperationActions({
    onConfirmSuccess: () => refresh(),
    onRejectSuccess: () => refresh(),
    onBatchComplete: (results) => {
      const ok = results.filter((r) => r.ok).length;
      const fail = results.length - ok;
      setBatchSummary(
        fail > 0
          ? `批量完成：成功 ${ok} 条，失败 ${fail} 条`
          : `批量完成：全部 ${ok} 条成功`,
      );
      if (fail > 0) {
        toast(`成功 ${ok} 个，失败 ${fail} 个`, { type: 'error' });
      } else {
        toast('全部已处理', { type: 'success' });
      }
      refresh();
    },
  });

  useEffect(() => {
    refresh();
  }, [refresh]);

  // AL-114: 审批面板打开时每 30s 自动刷新
  useEffect(() => {
    const id = setInterval(refresh, 30_000);
    return () => clearInterval(id);
  }, [refresh]);

  // AL-154: 写入操作完成后触发审批数据重新拉取
  const approvalVersionRef = useRef(approvalDataVersion);
  useEffect(() => {
    if (approvalVersionRef.current !== approvalDataVersion) {
      approvalVersionRef.current = approvalDataVersion;
      refresh();
    }
  }, [approvalDataVersion, refresh]);

  const pending = ops.filter((o) =>
    ['awaiting_confirmation', 'recovery_required'].includes(o.status),
  );
  const batchEligible = useMemo(
    () => pending.filter((o) => o.status === 'awaiting_confirmation'),
    [pending],
  );
  const active = ops.filter((o) => o.status === 'running');
  const failed = ops.filter((o) => o.status === 'failed');

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllBatch = () => {
    setSelectedIds(new Set(batchEligible.map((o) => o.id)));
  };

  const invertSelection = () => {
    setSelectedIds((prev) => {
      const next = new Set<string>();
      for (const o of batchEligible) {
        if (!prev.has(o.id)) next.add(o.id);
      }
      return next;
    });
  };

  const selectedList = useMemo(
    () => batchEligible.filter((o) => selectedIds.has(o.id)).map((o) => o.id),
    [batchEligible, selectedIds],
  );

  const handleBatchConfirm = async () => {
    if (selectedList.length === 0 || batchBusy) return;
    setBatchSummary('');
    toast('批量放行中...', { type: 'info' });
    await confirmBatch(selectedList);
  };

  const handleBatchReject = async () => {
    if (selectedList.length === 0 || batchBusy) return;
    setBatchSummary('');
    toast('批量拒绝中...', { type: 'info' });
    await rejectBatch(selectedList);
  };

  const handleConfirm = async (opId: string, recoveryAction?: string) => {
    console.log('[OpsConsole] handleConfirm', opId, recoveryAction);
    try {
      await confirm(opId, recoveryAction ? { recoveryAction } : undefined);
    } catch (e) {
      console.error('[OpsConsole] confirm failed', e);
      toast(`操作失败：${e instanceof Error ? e.message : String(e)}`, { type: 'error' });
    }
  };

  const handleReject = async (opId: string) => {
    console.log('[OpsConsole] handleReject', opId);
    try {
      await reject(opId);
    } catch (e) {
      console.error('[OpsConsole] reject failed', e);
      toast(`操作失败：${e instanceof Error ? e.message : String(e)}`, { type: 'error' });
    }
  };

  const jumpToConversation = (conversationId?: string) => {
    console.log('[OpsConsole] jumpToConversation', conversationId);
    if (!conversationId) return;
    setActiveSession(conversationId);
    setMainView('chat');
    onBack();
  };

  const anyBusy = batchBusy || busyOpId !== null;

  return (
    <div className="flex flex-col h-full min-w-0 bg-background">
      <header className="flex items-center gap-3 px-4 py-3 border-b border-border shrink-0">
        {!embedded && (
          <Button variant="ghost" size="icon" onClick={onBack} title="返回聊天">
            <ArrowLeft size={18} />
          </Button>
        )}
        <div className="flex-1 flex items-center gap-3 min-w-0">
          <h1 className="text-sm font-semibold whitespace-nowrap">审批管控台</h1>
          <p className="text-[11px] text-muted-foreground whitespace-nowrap">待确认 · 进行中 · 失败 · 链路健康</p>
        </div>
        <div className="flex items-center gap-1 ml-3">
          <Button variant={filterMode === 'mine' ? 'secondary' : 'ghost'} size="sm" className="h-7 text-[11px]"
            onClick={() => { setFilterMode('mine'); }}>
            我的
          </Button>
          <Button variant={filterMode === 'all' ? 'secondary' : 'ghost'} size="sm" className="h-7 text-[11px]"
            onClick={() => { setFilterMode('all'); }}>
            全部
          </Button>
        </div>
        <label className="flex items-center gap-1 text-[11px] text-muted-foreground">
          <span>用户 ID</span>
          <input
            className="h-7 w-28 rounded border border-border bg-background px-2 text-xs font-mono"
            value={userId}
            placeholder="rabbit"
            onChange={(e) => {
              const v = e.target.value;
              setUserId(v);
              saveRuntimeConfig({ user_id: v });
            }}
            onBlur={() => {
              const rc = loadRuntimeConfig();
              setUserId(rc.user_id || '');
            }}
            title="M4.1 审批身份（写入 X-Alice-User-Id）"
          />
        </label>
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading || anyBusy}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          <span className="ml-1">刷新</span>
        </Button>
      </header>

      {/* Tab 栏 */}
      <div className="flex border-b border-border px-4 pt-3">
        {[
          { id: 'pending', label: '待审批', count: pending.length },
          { id: 'active',  label: '进行中', count: active.length },
          { id: 'failed',  label: '失败',   count: failed.length },
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 transition-colors -mb-[1px] ${
              activeTab === tab.id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className={`rounded-full min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-bold px-1 ${
                tab.id === 'pending' ? 'bg-red-500 text-white' :
                tab.id === 'failed' ? 'bg-amber-500 text-white' : 'bg-muted text-muted-foreground'
              }`}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {err && (
          <div className="text-sm text-destructive border border-destructive/30 bg-destructive/10 rounded-lg p-3">{err}</div>
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

        {batchEligible.length > 0 && (
          <section className="rounded-lg border border-border px-3 py-2 flex flex-wrap items-center gap-2 text-[11px]">
            <span className="font-semibold">批量操作</span>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="checkbox"
                className="rounded"
                checked={selectedList.length === batchEligible.length && batchEligible.length > 0}
                onChange={(e) => (e.target.checked ? selectAllBatch() : setSelectedIds(new Set()))}
                disabled={anyBusy}
              />
              全选
            </label>
            <Button variant="ghost" size="sm" className="h-7 text-[11px]" onClick={invertSelection} disabled={anyBusy}>
              反选
            </Button>
            <span className="text-muted-foreground">已选 {selectedList.length} 条</span>
            {batchProgress && (
              <span className="text-blue-600">
                {batchProgress.action === 'confirm' ? '批量放行' : '批量拒绝'}{' '}
                {batchProgress.current}/{batchProgress.total}
              </span>
            )}
            <Button
              variant="default"
              size="sm"
              className="h-7 text-[11px]"
              disabled={selectedList.length === 0 || anyBusy}
              onClick={handleBatchConfirm}
            >
              批量放行
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-[11px] text-destructive"
              disabled={selectedList.length === 0 || anyBusy}
              onClick={handleBatchReject}
            >
              批量拒绝
            </Button>
            {batchSummary && <span className="text-muted-foreground">{batchSummary}</span>}
          </section>
        )}

        {activeTab === 'pending' && (
        <OpSection
          title={`待审批 (${pending.length})`}
          rows={pending}
          empty="暂无待确认操作"
          actionable
          batchEligibleIds={new Set(batchEligible.map((o) => o.id))}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          busyOpId={busyOpId}
          batchBusy={batchBusy}
          progressByOpId={progressByOpId}
          lastError={lastError}
          onConfirm={handleConfirm}
          onReject={handleReject}
          onJumpToSession={jumpToConversation}
          activeTab={activeTab}
          expandedId={expandedId}
          onToggleExpand={(id: string) => setExpandedId(expandedId === id ? null : id)}
        />
        )}
        {activeTab === 'active' && (
        <OpSection title={`进行中 (${active.length})`} rows={active} empty="暂无进行中操作" onJumpToSession={jumpToConversation}
          activeTab={activeTab}
          expandedId={expandedId}
          onToggleExpand={(id: string) => setExpandedId(expandedId === id ? null : id)}
        />
        )}
        {activeTab === 'failed' && (
        <OpSection title={`失败 (${failed.length})`} rows={failed} empty="暂无失败记录" onJumpToSession={jumpToConversation}
          activeTab={activeTab}
          expandedId={expandedId}
          onToggleExpand={(id: string) => setExpandedId(expandedId === id ? null : id)}
        />
        )}
      </div>
    </div>
  );
};

function AuditTrail({ row }: { row: OpRow }) {
  const hasCreator = !!row.user_id;
  const hasApprover = !!(row.confirmed_by || row.rejected_by);
  if (!hasCreator && !hasApprover) return null;
  return (
    <div className="text-[11px] text-muted-foreground space-y-0.5 pt-0.5">
      {hasCreator && (
        <div>
          创建者 <span className="font-mono text-foreground">{row.user_id}</span>
        </div>
      )}
      {row.confirmed_by && (
        <div>
          审批放行{' '}
          <span className="font-mono text-green-700">{row.confirmed_by}</span>
          {row.confirmed_at ? ` · ${row.confirmed_at}` : ''}
        </div>
      )}
      {row.rejected_by && (
        <div>
          审批拒绝{' '}
          <span className="font-mono text-destructive">{row.rejected_by}</span>
          {row.rejected_at ? ` · ${row.rejected_at}` : ''}
        </div>
      )}
    </div>
  );
}

function OpSection({
  title,
  rows,
  empty,
  actionable,
  batchEligibleIds,
  selectedIds,
  onToggleSelect,
  busyOpId,
  batchBusy,
  progressByOpId,
  lastError,
  onConfirm,
  onReject,
  onJumpToSession,
  activeTab,
  expandedId,
  onToggleExpand,
}: {
  title: string;
  rows: OpRow[];
  empty: string;
  actionable?: boolean;
  batchEligibleIds?: Set<string>;
  selectedIds?: Set<string>;
  onToggleSelect?: (id: string) => void;
  busyOpId?: string | null;
  batchBusy?: boolean;
  progressByOpId?: Record<string, string>;
  lastError?: Record<string, string>;
  onConfirm?: (opId: string, recoveryAction?: string) => void;
  onReject?: (opId: string) => void;
  onJumpToSession?: (conversationId?: string) => void;
  activeTab?: string;
  expandedId?: string | null;
  onToggleExpand?: (id: string) => void;
}) {
  return (
    <section className="rounded-lg border border-border">
      <div className="px-3 py-2 border-b border-border text-xs font-semibold">{title}</div>
      {rows.length === 0 ? (
        <p className="px-3 py-4 text-xs text-muted-foreground">{empty}</p>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((o) => (
            <li key={o.id} className="px-3 py-2 text-[11px] space-y-1">
              <div className="flex items-start gap-2">
                {actionable && batchEligibleIds?.has(o.id) && onToggleSelect && (
                  <input
                    type="checkbox"
                    className="mt-0.5 rounded shrink-0"
                    checked={selectedIds?.has(o.id) ?? false}
                    onChange={() => onToggleSelect(o.id)}
                    disabled={batchBusy || busyOpId === o.id}
                  />
                )}
                <div className="flex-1 min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-xs">
                      {o.kind === 'jira_bulk_create' ? '创建 Jira 子任务'
                       : o.kind === 'add_jira_comment' ? '添加 Jira 评论'
                       : o.kind || '操作'}
                    </span>
                    {o.operation?.issue_key && (
                      <span className="font-mono text-[11px] text-blue-600 bg-blue-50 dark:bg-blue-950/30 px-1 rounded">{o.operation.issue_key}</span>
                    )}
                    {o.drafts_count != null && o.drafts_count > 0 && (
                      <span className="text-[11px] text-muted-foreground">{o.drafts_count} 条</span>
                    )}
                    <span className="text-[11px] text-muted-foreground ml-auto">{o.status}</span>
                  </div>
                  {o.operation?.summary && (
                    <div className="text-[11px] text-muted-foreground truncate">{o.operation.summary}</div>
                  )}
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span>提交: {o.created_at?.slice(0, 16) || '—'}</span>
                    {o.user_id && <span>发起人: {o.user_id}</span>}
                  </div>
                  <AuditTrail row={o} />
                </div>
              </div>
              {o.drafts_count != null && o.drafts_count > 0 && (
                <div className="text-muted-foreground">草稿 {o.drafts_count} 条</div>
              )}
              {(o.warnings || []).map((w, i) => (
                <div key={i} className="text-amber-600 truncate">{w}</div>
              ))}
              {o.error && <div className="text-destructive truncate">{o.error}</div>}
              {o.recovery?.summary && (
                <div className="text-amber-700">{o.recovery.summary}</div>
              )}
              {o.conversation_id && onJumpToSession && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-[11px] gap-1 px-2"
                  onClick={() => onJumpToSession(o.conversation_id)}
                >
                  <Link2 size={12} />
                  查看原会话
                </Button>
              )}
              {actionable && onConfirm && onReject && (
                <PendingActions
                  row={o}
                  busy={busyOpId === o.id || !!batchBusy}
                  progress={progressByOpId?.[o.id]}
                  error={lastError?.[o.id]}
                  onConfirm={onConfirm}
                  onReject={onReject}
                />
              )}
              {/* 展开详情 */}
              {activeTab && ['pending', 'failed'].includes(activeTab) && onToggleExpand && (
                <button
                  onClick={() => onToggleExpand(o.id)}
                  className="text-[11px] text-primary hover:underline mt-1"
                >
                  {expandedId === o.id ? '收起详情' : '展开详情'}
                </button>
              )}
              {activeTab && expandedId === o.id && (
                <div className="mt-2 p-2 rounded bg-muted/30 text-[11px] space-y-1 border border-border/50">
                  {o.operation?.summary && (
                    <div className="text-muted-foreground">操作: {o.operation.summary}</div>
                  )}
                  {o.operation?.issue_key && (
                    <div className="font-mono text-muted-foreground">
                      Issue: <a href={`http://ctjira1.lmdgame.com:8080/browse/${o.operation.issue_key}`} target="_blank" rel="noreferrer" className="text-primary hover:underline flex items-center gap-1 inline-flex">
                        {o.operation.issue_key} <Link2 size={10} />
                      </a>
                    </div>
                  )}
                  {o.drafts_count != null && o.drafts_count > 0 && (
                    <div className="text-muted-foreground">子任务: {o.drafts_count} 条</div>
                  )}
                  {o.error && (
                    <div className="text-destructive">错误: {o.error}</div>
                  )}
                  <div className="text-muted-foreground">
                    创建: {o.created_at || '—'} · 更新: {o.updated_at || '—'}
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PendingActions({
  row,
  busy,
  progress,
  error,
  onConfirm,
  onReject,
}: {
  row: OpRow;
  busy: boolean;
  progress?: string;
  error?: string;
  onConfirm: (opId: string, recoveryAction?: string) => void;
  onReject: (opId: string) => void;
}) {
  const recoveryActions = (row.recovery?.actions || []).filter(
    (a) => a.id !== 'cancel' && !actionNeedsForm(a),
  );
  const hasFormAction = (row.recovery?.actions || []).some(actionNeedsForm);

  return (
    <div className="pt-1 space-y-1.5">
      {progress && (
        <div className="text-[11px] text-blue-600">{progress}</div>
      )}
      {error && (
        <div className="text-[11px] text-destructive">{error}</div>
      )}
      {hasFormAction && (
        <p className="text-[11px] text-muted-foreground">
          需补充信息的操作请在聊天会话中使用确认卡处理。
        </p>
      )}
      <div className="flex flex-wrap gap-1.5">
        {recoveryActions.map((a) => (
          <Button
            key={a.id}
            variant="outline"
            size="sm"
            className="h-7 text-[11px]"
            disabled={busy}
            onClick={() => onConfirm(row.id, a.id)}
          >
            {a.label || a.id}
          </Button>
        ))}
        <Button
          variant="default"
          size="sm"
          className="h-7 text-[11px] gap-1"
          disabled={busy}
          onClick={() => onConfirm(row.id)}
        >
          <CheckCircle size={12} />
          授权放行
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-[11px] gap-1 text-destructive hover:text-destructive/70"
          disabled={busy}
          onClick={() => onReject(row.id)}
        >
          <XCircle size={12} />
          拒绝拦截
        </Button>
      </div>
    </div>
  );
}

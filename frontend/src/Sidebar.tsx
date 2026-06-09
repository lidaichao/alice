import React, { useState, useEffect, useRef } from 'react';
import { useChatStore } from '@/store/useChatStore';
import { Button } from '@/components/ui/button';
import { useTheme } from 'next-themes';
import { Sun, Moon, Monitor, Plus, Trash2, Edit2, Wifi, Bug, ClipboardList, Workflow, Zap, Bell, Settings, Search, X, MessageSquare, Activity } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { TeamMemoryPanel } from '@/components/TeamMemoryPanel';
import { useToast } from '@/components/Toast';

export const Sidebar: React.FC = () => {
  const sessions = useChatStore((s) => s.sessions);
  const activeId = useChatStore((s) => s.activeSessionId);
  const createSession = useChatStore((s) => s.addSession);
  const switchSession = useChatStore((s) => s.setActiveSession);
  const deleteSession = useChatStore((s) => s.deleteSession);
  const renameSession = useChatStore((s) => s.renameSession);
  const pendingConfirmations = useChatStore((s) => s.pendingConfirmations);
  const pendingDraftCards = useChatStore((s) => s.pendingDraftCards);
  const pendingCount = pendingConfirmations.filter(c => c.status !== 'confirmed' && c.status !== 'rejected').length;
  const approvalPanelOpen = useChatStore((s) => s.approvalPanelOpen);
  const setApprovalPanelOpen = useChatStore((s) => s.setApprovalPanelOpen);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const { theme, setTheme } = useTheme();
  const { toast } = useToast();

  const pendingTotal = pendingConfirmations.length + pendingDraftCards.length;

  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [wfTemplates, setWfTemplates] = useState<Array<{id: string; name: string; description: string}>>([]);
  const [wfOpen, setWfOpen] = useState(false);
  const [wfLoading, setWfLoading] = useState(false);
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('alice_pinned_sessions') || '[]'); }
    catch { return []; }
  });

  // M5.4 — 加载工作流模板列表
  const loadWorkflowTemplates = async () => {
    setWfLoading(true);
    try {
      const res = await fetch('/v1/workflow/templates');
      if (res.ok) {
        const data = await res.json();
        setWfTemplates(data?.templates || []);
      }
    } catch {
      // 端点可能未就绪，静默降级
    } finally {
      setWfLoading(false);
    }
  };

  const triggerWorkflow = (templateId: string) => {
    const msg = `[WORKFLOW:${templateId}]`;
    sendMessage(msg);
    setWfOpen(false);
  };

  const handleRename = (id: string, title: string) => {
    setEditingId(id);
    setEditTitle(title);
  };

  const commitRename = async (id: string) => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== sessions.find((s) => s.id === id)?.title) {
      await renameSession(id, trimmed);
    }
    setEditingId(null);
    setEditTitle('');
  };

  // Sort: pinned first, then by updatedAt desc; filter by search
  const sorted = [...sessions]
    .filter((s) => !searchQuery || s.title.toLowerCase().includes(searchQuery.toLowerCase()))
    .sort((a, b) => {
      const aPinned = pinnedIds.includes(a.id) ? 0 : 1;
      const bPinned = pinnedIds.includes(b.id) ? 0 : 1;
      if (aPinned !== bPinned) return aPinned - bPinned;
      return b.updatedAt - a.updatedAt;
    });
  const pinSession = (id: string) => {
    setPinnedIds(prev => {
      const next = prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id];
      localStorage.setItem('alice_pinned_sessions', JSON.stringify(next));
      return next;
    });
  };
  const handleDelete = async (id: string) => {
    const session = sessions.find(s => s.id === id);
    const title = session?.title || '会话';
    toast(`已删除 "${title}"`, {
      type: 'info',
      action: {
        label: '撤销',
        onClick: () => { /* restore: create a new session - simplified */ },
      },
      duration: 3000,
    });
    await deleteSession(id);
  };

  return (
    <aside className="w-64 h-full border-r border-border/40 bg-background/85 backdrop-blur-md flex flex-col overflow-hidden">
      {/* Header + New Session */}
      <div className="p-3 border-b border-border flex items-center justify-between shrink-0">
        <span className="text-sm font-semibold text-foreground">会话列表</span>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => createSession()} title="新建会话">
          <Plus size={16} />
        </Button>
      </div>

      <div className="px-2 pt-2 space-y-1.5">
        {/* M5.4 — 工作流启动器 */}
        <Popover open={wfOpen} onOpenChange={(open) => { setWfOpen(open); if (open) loadWorkflowTemplates(); }}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              className="w-full justify-start gap-2 text-xs"
            >
              <Workflow size={14} />
              工作流
              {wfTemplates.length > 0 && (
                <span className="ml-auto rounded-full bg-blue-500/20 px-1.5 text-[11px]">{wfTemplates.length}</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-60 p-2" align="start" side="right">
            <div className="text-xs font-semibold text-muted-foreground mb-1.5">可用工作流模板</div>
            {wfLoading && (
              <div className="text-[11px] text-muted-foreground py-2">加载中...</div>
            )}
            {!wfLoading && wfTemplates.length === 0 && (
              <div className="text-[11px] text-muted-foreground py-2">
                暂无可用模板（Hub 端点 /v1/workflow/templates 未就绪）
              </div>
            )}
            {wfTemplates.map((tpl) => (
              <button
                key={tpl.id}
                onClick={() => triggerWorkflow(tpl.id)}
                className="w-full text-left px-2 py-2 rounded hover:bg-muted text-xs flex items-start gap-2 group"
              >
                <Zap size={12} className="mt-0.5 shrink-0 text-blue-500" />
                <div className="min-w-0">
                  <div className="font-medium text-foreground truncate">{tpl.name}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{tpl.description}</div>
                </div>
              </button>
            ))}
            {wfTemplates.length > 0 && (
              <div className="mt-2 border-t border-border pt-1.5">
                <div className="text-[11px] text-muted-foreground mb-1">或手动输入：</div>
                <code className="text-[11px] bg-muted px-1.5 py-0.5 rounded block text-center font-mono">
                  [WORKFLOW:template-id]
                </code>
              </div>
            )}
          </PopoverContent>
        </Popover>
      </div>

      {pendingTotal > 0 && !approvalPanelOpen && (
        <div className="mx-2 mt-2 mb-1 p-2 rounded-lg border border-amber-400/40 bg-amber-50/50 dark:bg-amber-950/30">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-800 dark:text-amber-200 mb-1.5">
            <ClipboardList size={14} />
            待处理 ({pendingTotal})
          </div>
          <ul className="space-y-1 max-h-28 overflow-y-auto">
            {pendingDraftCards.map((d) => (
              <li key={d.draft_id} className="text-[11px] text-muted-foreground truncate">
                草稿 · {d.items.length} 条
              </li>
            ))}
            {pendingConfirmations.map((c) => (
              <li key={c.op_id} className="text-[11px] text-muted-foreground truncate">
                {c.operation_status === 'recovery_required' ? '恢复' : '确认'} · {c.operation.type}
                {c.operation.issue_key ? ` ${c.operation.issue_key}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Session list */}
      <div className="px-3 pb-2">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border/50 bg-muted/30 text-sm">
          <Search size={14} className="text-muted-foreground shrink-0" />
          <input
            placeholder="搜索会话..."
            className="bg-transparent border-none outline-none flex-1 text-[12px] text-foreground placeholder:text-muted-foreground"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')} className="text-muted-foreground hover:text-foreground">
              <X size={14} />
            </button>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {sorted.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-muted-foreground">
            点击 <Plus size={10} className="inline" /> 新建会话
          </div>
        ) : (
          sorted.map((session) => {
            const isActive = session.id === activeId;
            const isEditing = editingId === session.id;
            return (
              <div
                key={session.id}
                onClick={() => { console.log('[Sidebar] Switching to:', session.id); switchSession(session.id); }}
                className={`group mx-2 my-0.5 px-3 py-2 rounded-lg cursor-pointer transition-colors text-sm z-0 ${
                  isActive
                    ? 'bg-primary/10 text-primary font-medium border border-primary/20'
                    : 'hover:bg-muted/60 text-foreground/80'
                }`}
              >
                {isEditing ? (
                  <input
                    autoFocus
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={() => commitRename(session.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitRename(session.id);
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="w-full bg-background border border-border rounded px-2 py-0.5 text-sm outline-none focus:ring-1 focus:ring-primary"
                  />
                ) : (
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate flex-1 min-w-0">
                      <div className="truncate text-[13px]">
                        <span
                          className="cursor-default"
                          onDoubleClick={(e) => { e.stopPropagation(); handleRename(session.id, session.title); }}
                          title="双击重命名"
                        >
                          {session.title || '新会话'}
                          {pinnedIds.includes(session.id) && <span className="ml-1 text-[11px]">📌</span>}
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-0.5">
                        {new Date(session.updatedAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        {session.messages.length > 0 && ` · ${session.messages.length}条`}
                      </div>
                    </div>
                    <Popover>
                      <PopoverTrigger asChild>
                        <button
                          onClick={(e) => e.stopPropagation()}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-muted transition-opacity shrink-0"
                        >
                          <Edit2 size={12} className="text-muted-foreground" />
                        </button>
                      </PopoverTrigger>
                      <PopoverContent className="w-32 p-1" align="start" side="right">
                        <button
                          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2"
                          onClick={(e) => { e.stopPropagation(); pinSession(session.id); }}
                        >
                          <Edit2 size={12} /> {pinnedIds.includes(session.id) ? '取消置顶' : '📌 置顶'}
                        </button>
                        <button
                          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2"
                          onClick={(e) => { e.stopPropagation(); handleRename(session.id, session.title); }}
                        >
                          <Edit2 size={12} /> 重命名
                        </button>
                        <button
                          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-red-50 text-red-600 flex items-center gap-2"
                          onClick={(e) => { e.stopPropagation(); void handleDelete(session.id); }}
                        >
                          <Trash2 size={12} /> 删除
                        </button>
                      </PopoverContent>
                    </Popover>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* 审批中心入口 */}
      <div className="px-3 py-1">
        <Button
          variant="ghost"
          className="w-full justify-start gap-2 h-9 text-sm"
          onClick={() => setApprovalPanelOpen(true)}
        >
          <Bell size={16} />
          <span className="flex-1 text-left">审批中心</span>
          {pendingCount > 0 && (
            <span className="bg-red-500 text-white text-[11px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
              {pendingCount}
            </span>
          )}
        </Button>
      </div>

      <TeamMemoryPanel />

      {/* Footer */}
      <div className="p-3 border-t border-border shrink-0 flex flex-col gap-2 bg-background/50">
        <div className="text-[11px] font-medium text-muted-foreground flex items-center gap-1.5 px-1">
          <Settings size={12} />
          <span>设置</span>
        </div>
        <div className="flex items-center justify-center">
          <div className="flex items-center gap-1 bg-muted rounded-full p-1 border border-border/50 shadow-inner">
            <button onClick={() => setTheme('light')} className={`p-1.5 rounded-full transition-all ${theme === 'light' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="浅色"><Sun size={14} /></button>
            <button onClick={() => setTheme('system')} className={`p-1.5 rounded-full transition-all ${theme === 'system' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="系统"><Monitor size={14} /></button>
            <button onClick={() => setTheme('dark')} className={`p-1.5 rounded-full transition-all ${theme === 'dark' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="深色"><Moon size={14} /></button>
          </div>
        </div>
        <TestConnectionWidget />
        <FeedbackButton />
        <DiagnosticsButton />
      </div>
    </aside>
  );
};

// ── 自助排障探测器 ─────────────────────────────
function TestConnectionWidget() {
  const [status, setStatus] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle');
  const [msg, setMsg] = useState('');

  const test = async () => {
    setStatus('testing');
    setMsg('');
    try {
      const res = await fetch('/api/system/status');
      if (!res.ok) throw new Error('down');
      const data = await res.json();
      setStatus('ok');
      setMsg(data.service || data.status || '在线');
    } catch {
      setStatus('fail');
      setMsg('后端不可达');
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <button onClick={test} disabled={status === 'testing'}
        className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors disabled:opacity-50">
        <Wifi size={12} className={status === 'ok' ? 'text-green-500' : status === 'fail' ? 'text-red-500' : 'text-muted-foreground'} />
        {status === 'testing' ? '检测中...' : 'Test Connection'}
      </button>
      {status !== 'idle' && (
        <span className={`text-[11px] font-semibold truncate max-w-[140px] ${status === 'ok' ? 'text-green-600' : 'text-red-500'}`}>
          {status === 'ok' ? '✅ 在线' : '❌ 不可达'}
        </span>
      )}
    </div>
  );
}

// ── 灰度测试反馈黑匣子 ───────────────────────────
// ── 轻量反馈 ────────────────────────────
function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [sent, setSent] = useState(false);
  const submit = () => {
    const reports = JSON.parse(localStorage.getItem('alice_feedback') || '[]');
    reports.push({ text, time: Date.now() });
    localStorage.setItem('alice_feedback', JSON.stringify(reports));
    setSent(true);
    setTimeout(() => { setOpen(false); setSent(false); setText(''); }, 1500);
  };
  return (
    <>
      <button onClick={() => setOpen(true)}
        className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors">
        <MessageSquare size={12} className="text-muted-foreground" /> 反馈
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setOpen(false)}>
          <div className="bg-background border border-border rounded-xl shadow-2xl p-5 w-[400px] max-w-[92vw]" onClick={e => e.stopPropagation()}>
            <div className="font-semibold mb-3">告诉我们你的想法</div>
            <textarea className="w-full h-20 text-sm border border-border rounded-lg p-3 resize-none bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 mb-3"
              placeholder="哪里让你觉得好用或不好用..." value={text} onChange={e => setText(e.target.value)} />
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <input type="checkbox" className="rounded" /> 附带诊断信息
              </label>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>取消</Button>
                <Button size="sm" onClick={submit} disabled={!text.trim()}>
                  {sent ? '已发送' : '发送'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ── 诊断工具 ───────────────────────────
function DiagnosticsButton() {
  const [open, setOpen] = useState(false);
  const [desc, setDesc] = useState('');
  const [sent, setSent] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [fullReport, setFullReport] = useState('');

  const clientInfo = [
    `OS: ${navigator.platform || 'unknown'}`,
    `UA: ${navigator.userAgent.substring(0, 80)}`,
    `Screen: ${window.screen.width}x${window.screen.height}`,
    `Lang: ${navigator.language}`,
    `Time: ${new Date().toISOString()}`,
  ].join('\n');

  const handleGenerate = async () => {
    setLogsLoading(true);
    let backendLogs = '';
    try {
      const res = await fetch('/api/diagnostics/logs');
      const data = await res.json();
      backendLogs = data.ok && data.lines?.length ? data.lines.join('\n') : (data.error || '(日志接口不可达)');
    } catch { backendLogs = '(后端不可达)'; }
    const report = [
      `=== Alice 灰度测试反馈报告 ===`,
      `时间: ${new Date().toISOString()}`,
      '', `## 用户描述`, desc || '(未填写)', '',
      `## 客户端环境`, clientInfo, '',
      `## 后端日志 (最近200行)`, backendLogs,
    ].join('\n');
    setFullReport(report);
    setLogsLoading(false);
    localStorage.setItem('alice_bug_reports', JSON.stringify(
      [...(JSON.parse(localStorage.getItem('alice_bug_reports') || '[]')), { desc, clientInfo, backendLogs, time: Date.now() }]
    ));
    setSent(true);
  };

  return (
    <>
      <button onClick={() => { setOpen(true); setSent(false); setFullReport(''); }}
        className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors" title="诊断工具">
        <Activity size={12} className="text-blue-500" /> 🔧 诊断工具
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setOpen(false)}>
          <div className="bg-background border border-border rounded-xl shadow-2xl p-5 w-[460px] max-w-[92vw] max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-4"><Bug className="w-5 h-5 text-amber-500" /><span className="font-semibold text-lg">🐞 灰度测试反馈</span></div>
            <div className="text-xs text-muted-foreground mb-3 p-2 bg-muted/30 rounded-md font-mono whitespace-pre-wrap">{clientInfo}</div>
            <textarea className="w-full h-20 text-sm border border-border rounded-lg p-3 resize-none bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 mb-3" placeholder="描述你遇到的问题..." value={desc} onChange={e => setDesc(e.target.value)} />
            {!sent && <Button size="sm" onClick={handleGenerate} disabled={logsLoading || !desc.trim()} className="w-full mb-2">{logsLoading ? '⏳ 抓取后端日志中...' : '生成诊断报告'}</Button>}
            {sent && fullReport && (
              <>
                <div className="text-xs text-muted-foreground mb-1">诊断报告已生成 ({fullReport.length} 字符)</div>
                <pre className="text-[11px] bg-muted/50 rounded-lg p-3 max-h-48 overflow-y-auto mb-3 whitespace-pre-wrap font-mono border border-border/30">{fullReport.substring(0, 800)}...</pre>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => navigator.clipboard.writeText(fullReport)} className="flex-1">📋 复制到剪贴板</Button>
                  <Button variant="outline" size="sm" onClick={() => { const b = new Blob([fullReport], { type: 'text/plain;charset=utf-8' }); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `alice_bug_report_${Date.now()}.txt`; a.click(); URL.revokeObjectURL(u); }} className="flex-1">💾 下载 .txt</Button>
                </div>
              </>
            )}
            <div className="flex justify-end mt-3"><Button variant="ghost" size="sm" onClick={() => setOpen(false)}>关闭</Button></div>
          </div>
        </div>
      )}
    </>
  );
}

import React, { useState } from 'react';
import { useSessionStore } from '@/store/useSessionStore';
import { Button } from '@/components/ui/button';
import { useTheme } from 'next-themes';
import { Sun, Moon, Monitor, Plus, Trash2, Edit2, Wifi, Bug, ExternalLink } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export const Sidebar: React.FC = () => {
  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeId);
  const createSession = useSessionStore((s) => s.createSession);
  const switchSession = useSessionStore((s) => s.switchSession);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const renameSession = useSessionStore((s) => s.renameSession);
  const { theme, setTheme } = useTheme();

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const handleRename = (id: string, title: string) => {
    setEditingId(id);
    setEditTitle(title);
  };

  const commitRename = (id: string) => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== sessions.find((s) => s.id === id)?.title) {
      renameSession(id, trimmed);
    }
    setEditingId(null);
    setEditTitle('');
  };

  // Sort by updatedAt desc
  const sorted = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <aside className="w-64 bg-background border-r border-border flex flex-col shrink-0 h-full">
      {/* Header + New Session */}
      <div className="p-3 border-b border-border flex items-center justify-between shrink-0">
        <span className="text-sm font-semibold text-foreground">会话列表</span>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={createSession} title="新建会话">
          <Plus size={16} />
        </Button>
      </div>

      {/* Session list */}
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
                      <div className="truncate text-[13px]">{session.title || '新会话'}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
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
                          onClick={(e) => { e.stopPropagation(); handleRename(session.id, session.title); }}
                        >
                          <Edit2 size={12} /> 重命名
                        </button>
                        <button
                          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-red-50 text-red-600 flex items-center gap-2"
                          onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
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

      {/* Footer */}
      <div className="p-3 border-t border-border shrink-0 flex flex-col gap-2 bg-background/50">
        <div className="text-xs text-muted-foreground font-medium px-2">设置</div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 bg-muted rounded-full p-1 border border-border/50 shadow-inner">
            <button onClick={() => setTheme('light')} className={`p-1.5 rounded-full transition-all ${theme === 'light' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="浅色"><Sun size={14} /></button>
            <button onClick={() => setTheme('system')} className={`p-1.5 rounded-full transition-all ${theme === 'system' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="系统"><Monitor size={14} /></button>
            <button onClick={() => setTheme('dark')} className={`p-1.5 rounded-full transition-all ${theme === 'dark' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="深色"><Moon size={14} /></button>
          </div>
        </div>
        <TestConnectionWidget />
        <button
          onClick={() => window.open('http://127.0.0.1:9099/admin.html', '_blank')}
          className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors"
          title="后端管理后台"
        >
          <ExternalLink size={12} className="text-muted-foreground" />
          管理后台
        </button>
        <BugReportButton />
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
        <span className={`text-[10px] truncate max-w-[140px] ${status === 'ok' ? 'text-green-600' : 'text-red-500'}`}>{msg}</span>
      )}
    </div>
  );
}

// ── 灰度测试反馈黑匣子 ───────────────────────────
function BugReportButton() {
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
        className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors" title="反馈 Bug">
        <Bug size={12} className="text-amber-500" /> 反馈
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

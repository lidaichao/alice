import React, { useState } from 'react';
import { useChatStore, AGENTS } from '@/store/useChatStore';
import { Button } from '@/components/ui/button';
import { useTheme } from 'next-themes';
import SettingsPanel, { SettingsSidebar } from '@/components/SettingsPanel';
import { Sun, Moon, Monitor, Plus, MoreVertical, Pin, Trash2, Edit2, Wifi, Bug, Settings } from 'lucide-react';
import { AgentMarket } from '@/components/AgentMarket';
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export const Sidebar: React.FC = () => {
  const isSidebarOpen = useChatStore((state) => state.isSidebarOpen);
  const sessions = useChatStore((state) => state.sessions);
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const setActiveSession = useChatStore((state) => state.setActiveSession);
  const addSession = useChatStore((state) => state.addSession);
  const renameSession = useChatStore((state) => state.renameSession);
  const togglePinSession = useChatStore((state) => state.togglePinSession);
  const deleteSession = useChatStore((state) => state.deleteSession);
  const { theme, setTheme } = useTheme();

  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editTitle, setEditTitle] = React.useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsMenu, setSettingsMenu] = useState('settings');

  const handleRename = (id: string, title: string) => {
    setEditingId(id);
    setEditTitle(title);
  };

  const commitRename = (id: string) => {
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== sessions.find(s => s.id === id)?.title) {
      renameSession(id, trimmed);
    }
    setEditingId(null);
    setEditTitle('');
  };

  const cancelRename = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const sortedSessions = [...sessions].sort((a, b) => {
    if (a.isPinned && !b.isPinned) return -1;
    if (!a.isPinned && b.isPinned) return 1;
    return b.updatedAt - a.updatedAt;
  });

  const handleDelete = (id: string) => {
    if (window.confirm('确定要删除这个会话吗？此操作不可撤销。')) {
      deleteSession(id);
    }
  };

  if (!isSidebarOpen) return null;

  return (
    <>
      <aside className="w-64 border-r border-border bg-muted/20 flex flex-col transition-all duration-300 shrink-0">
      <div className="p-4 border-b border-border flex flex-col gap-3 shrink-0">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-foreground flex items-center gap-2">
            <span className="text-xl">⚛️</span> Alice
          </span>
          <Button variant="ghost" size="icon" onClick={() => addSession()} title="新建对话">
            <Plus size={18} />
          </Button>
        </div>
        <AgentMarket />
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {sortedSessions.map((session) => {
          const agent = AGENTS.find(a => a.id === session.agentId) || AGENTS[0];
          const isActive = activeSessionId === session.id;
          
          return (
            <div 
              key={session.id} 
              className={`group relative rounded-md cursor-pointer text-sm transition-all flex items-center justify-between pr-2 border ${
                isActive 
                  ? 'bg-background border-border shadow-sm text-primary font-medium' 
                  : 'border-transparent text-muted-foreground hover:bg-muted/50 hover:text-foreground'
              }`}
            >
              <div 
                onClick={() => setActiveSession(session.id)}
                className="flex-1 px-3 py-2.5 flex items-center gap-2 min-w-0"
              >
                <span className="opacity-80 shrink-0">{agent.avatar}</span>
                {editingId === session.id ? (
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') commitRename(session.id); if (e.key === 'Escape') cancelRename(); }}
                    onBlur={() => commitRename(session.id)}
                    className="flex-1 min-w-0 bg-transparent border-b border-primary text-xs px-1 py-0 outline-none"
                    autoFocus
                  />
                ) : (
                  <span className="truncate flex-1">{session.title}</span>
                )}
                {session.isPinned && <Pin size={12} className="text-orange-500 rotate-45 shrink-0" />}
              </div>

              <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                <Popover>
                  <PopoverTrigger asChild>
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="h-7 w-7 rounded text-muted-foreground hover:text-foreground"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreVertical size={14} />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent side="bottom" align="end" sideOffset={4} className="w-36 p-1">
                    <div className="flex flex-col gap-0.5">
                      <Button variant="ghost" size="sm" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setTimeout(() => togglePinSession(session.id), 50); }} className="justify-start gap-2 h-8 text-xs w-full">
                        <Pin size={14} className={session.isPinned ? "text-orange-500" : ""} />
                        {session.isPinned ? '取消置顶' : '置顶会话'}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setTimeout(() => handleRename(session.id, session.title), 50); }} className="justify-start gap-2 h-8 text-xs w-full">
                        <Edit2 size={14} />
                        重命名
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setTimeout(() => handleDelete(session.id), 50); }} className="justify-start gap-2 h-8 text-xs w-full text-destructive hover:text-destructive">
                        <Trash2 size={14} />
                        删除会话
                      </Button>
                    </div>
                  </PopoverContent>
                </Popover>
              </div>
            </div>
          );
        })}
      </div>

      <div className="p-3 border-t border-border shrink-0 flex flex-col gap-2 bg-background/50">
        <div className="text-xs text-muted-foreground font-medium px-2">设置</div>

        <button
          onClick={() => setSettingsOpen(true)}
          className="flex items-center gap-1.5 px-2 py-1.5 text-[11px] rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors"
        >
          <Settings size={12} />
          系统配置
        </button>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1 bg-muted rounded-full p-1 border border-border/50 shadow-inner">
            <button onClick={() => setTheme('light')} className={`p-1.5 rounded-full transition-all ${theme === 'light' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="浅色"><Sun size={14} /></button>
            <button onClick={() => setTheme('system')} className={`p-1.5 rounded-full transition-all ${theme === 'system' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="系统"><Monitor size={14} /></button>
            <button onClick={() => setTheme('dark')} className={`p-1.5 rounded-full transition-all ${theme === 'dark' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="深色"><Moon size={14} /></button>
          </div>
        </div>
        <TestConnectionWidget />
        <BugReportButton />
      </div>
    </aside>

    {/* ⚙️ 系统配置全屏 Modal */}
    {settingsOpen && (
      <div className="fixed inset-0 z-[9999] flex bg-white">
        <div className="flex w-full h-full">
          <SettingsPanel fullPage onClose={() => setSettingsOpen(false)} />
        </div>
      </div>
    )}
    </>
  );
};

// ── 自助排障探测器 ─────────────────────────────
function TestConnectionWidget() {
  const [status, setStatus] = useState<'idle' | 'testing' | 'ok' | 'fail'>('idle');
  const [msg, setMsg] = useState('');

  const test = async () => {
    setStatus('testing');
    try {
      const res = await fetch('/api/test_connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jira_url: localStorage.getItem('jiraUrl') || '',
          jira_pat: localStorage.getItem('jiraPat') || ''
        })
      });
      const data = await res.json();
      if (data.ok) {
        setStatus('ok');
        setMsg(`已连接: ${data.user}`);
      } else {
        setStatus('fail');
        setMsg(data.error || '未知错误');
      }
    } catch {
      setStatus('fail');
      setMsg('网络错误或后端未启动');
    }
  };

  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={test}
        disabled={status === 'testing'}
        className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors disabled:opacity-50"
      >
        <Wifi size={12} className={status === 'ok' ? 'text-green-500' : status === 'fail' ? 'text-red-500' : 'text-muted-foreground'} />
        {status === 'testing' ? '检测中...' : 'Test Connection'}
      </button>
      {status !== 'idle' && (
        <span className={`text-[10px] truncate max-w-[120px] ${status === 'ok' ? 'text-green-600' : 'text-red-500'}`}>
          {msg}
        </span>
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

  const clientInfo = (() => {
    const ua = navigator.userAgent;
    const appMatch = ua.match(/Alice\/(\S+)/);
    return [
      `OS: ${navigator.platform || 'unknown'}`,
      `UA: ${ua.substring(0, 80)}`,
      `Version: ${appMatch ? appMatch[1] : 'dev'}`,
      `Screen: ${window.screen.width}x${window.screen.height}`,
      `Lang: ${navigator.language}`,
      `Time: ${new Date().toISOString()}`,
    ].join('\n');
  })();

  const handleGenerate = async () => {
    setLogsLoading(true);
    let backendLogs = '';

    try {
      const res = await fetch('/api/diagnostics/logs');
      const data = await res.json();
      if (data.ok && data.lines?.length > 0) {
        backendLogs = data.lines.join('\n');
      } else {
        backendLogs = data.error || '(日志接口不可达)';
      }
    } catch {
      backendLogs = '(后端不可达，无法抓取日志)';
    }

    const report = [
      `=== Alice 灰度测试反馈报告 ===`,
      `时间: ${new Date().toISOString()}`,
      ``,
      `## 用户描述`,
      desc || '(未填写)',
      ``,
      `## 客户端环境`,
      clientInfo,
      ``,
      `## 后端日志 (最近200行)`,
      backendLogs,
    ].join('\n');

    setFullReport(report);
    setLogsLoading(false);

    // 同时存 localStorage
    const reports = JSON.parse(localStorage.getItem('alice_bug_reports') || '[]');
    reports.push({ desc, clientInfo, backendLogs, time: Date.now() });
    localStorage.setItem('alice_bug_reports', JSON.stringify(reports));
    setSent(true);
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(fullReport);
  };

  const handleDownload = () => {
    const blob = new Blob([fullReport], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `alice_bug_report_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <button
        onClick={() => { setOpen(true); setSent(false); setFullReport(''); }}
        className="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors"
        title="反馈 Bug"
      >
        <Bug size={12} className="text-amber-500" />
        反馈
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setOpen(false)}>
          <div
            className="bg-background border border-border rounded-xl shadow-2xl p-5 w-[460px] max-w-[92vw] max-h-[85vh] overflow-y-auto animate-in zoom-in-95"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-4">
              <Bug className="w-5 h-5 text-amber-500" />
              <span className="font-semibold text-lg">🐞 灰度测试反馈</span>
            </div>

            <div className="text-xs text-muted-foreground mb-3 p-2 bg-muted/30 rounded-md font-mono whitespace-pre-wrap">
              {clientInfo}
            </div>

            <textarea
              className="w-full h-20 text-sm border border-border rounded-lg p-3 resize-none bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 mb-3"
              placeholder="描述你遇到的问题..."
              value={desc}
              onChange={e => setDesc(e.target.value)}
            />

            {!sent && (
              <Button size="sm" onClick={handleGenerate} disabled={logsLoading || !desc.trim()} className="w-full mb-2">
                {logsLoading ? '⏳ 抓取后端日志中...' : '生成诊断报告'}
              </Button>
            )}

            {sent && fullReport && (
              <>
                <div className="text-xs text-muted-foreground mb-1">诊断报告已生成 ({fullReport.length} 字符)</div>
                <pre className="text-[11px] bg-muted/50 rounded-lg p-3 max-h-48 overflow-y-auto mb-3 whitespace-pre-wrap font-mono border border-border/30">
                  {fullReport.substring(0, 800)}...
                </pre>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={handleCopy} className="flex-1">📋 复制到剪贴板</Button>
                  <Button variant="outline" size="sm" onClick={handleDownload} className="flex-1">💾 下载 .txt</Button>
                </div>
              </>
            )}

            <div className="flex justify-end mt-3">
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>关闭</Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

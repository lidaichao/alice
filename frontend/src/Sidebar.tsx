import React, { useState } from 'react';
import { useChatStore } from '@/store/useChatStore';
import { Button } from '@/components/ui/button';
import { useTheme } from 'next-themes';
import { Sun, Moon, Monitor, Plus, Trash2, Edit2, ClipboardList, Bell, Settings, Search, X } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
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
  const { theme, setTheme } = useTheme();
  const { toast } = useToast();

  const pendingTotal = pendingConfirmations.length + pendingDraftCards.length;

  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('alice_pinned_sessions') || '[]'); }
    catch { return []; }
  });

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
        onClick: () => { createSession(); },
      },
      duration: 3000,
    });
    await deleteSession(id);
  };

  return (
    <aside className="w-64 h-full shadow-sm bg-background/85 backdrop-blur-md flex flex-col overflow-hidden">
      {/* Header + New Session */}
      <div className="p-3 border-b border-border flex items-center justify-between shrink-0">
        <span className="text-sm font-semibold text-foreground">会话列表</span>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => createSession()} title="新建会话">
          <Plus size={16} />
        </Button>
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
                          className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-muted transition-opacity shrink-0 text-muted-foreground/60 hover:text-muted-foreground"
                          title="会话操作"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                      </PopoverTrigger>
                      <PopoverContent className="w-32 p-1" align="start" side="right">
                        <button
                          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2 text-muted-foreground/60 hover:text-muted-foreground"
                          onClick={(e) => { e.stopPropagation(); pinSession(session.id); }}
                        >
                          <Edit2 className="w-3.5 h-3.5" /> {pinnedIds.includes(session.id) ? '取消置顶' : '📌 置顶'}
                        </button>
                        <button
                          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2 text-muted-foreground/60 hover:text-muted-foreground"
                          onClick={(e) => { e.stopPropagation(); handleRename(session.id, session.title); }}
                        >
                          <Edit2 className="w-3.5 h-3.5" /> 重命名
                        </button>
                        <button
                          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-red-50 text-muted-foreground/60 hover:text-red-500 flex items-center gap-2"
                          onClick={(e) => { e.stopPropagation(); void handleDelete(session.id); }}
                        >
                          <Trash2 className="w-3.5 h-3.5" /> 删除
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

      {/* Footer */}
      <div className="p-3 border-t border-border shrink-0 flex flex-col gap-2 bg-background/50">
        <button
          onClick={() => useChatStore.getState().setMainView('settings')}
          className="flex items-center gap-1.5 px-1 py-1 text-[11px] font-medium text-muted-foreground hover:text-foreground rounded hover:bg-muted transition-colors"
          title="设置中心"
        >
          <Settings size={12} />
          <span>设置</span>
        </button>
        <div className="flex items-center justify-center">
          <div className="flex items-center gap-1 bg-muted rounded-full p-1 border border-border/50 shadow-inner">
            <button onClick={() => setTheme('light')} className={`p-1.5 rounded-full transition-all ${theme === 'light' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="浅色"><Sun size={14} /></button>
            <button onClick={() => setTheme('system')} className={`p-1.5 rounded-full transition-all ${theme === 'system' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="系统"><Monitor size={14} /></button>
            <button onClick={() => setTheme('dark')} className={`p-1.5 rounded-full transition-all ${theme === 'dark' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="深色"><Moon size={14} /></button>
          </div>
        </div>
      </div>
    </aside>
  );
};

import React from 'react';
import { useChatStore, AGENTS } from '@/store/useChatStore';
import { Button } from '@/components/ui/button';
import { useTheme } from 'next-themes';
import { Sun, Moon, Monitor, Plus, MoreVertical, Pin, Trash2, Edit2 } from 'lucide-react';
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

      <div className="p-3 border-t border-border shrink-0 flex items-center justify-between bg-background/50">
        <div className="text-xs text-muted-foreground font-medium px-2">设置</div>
        <div className="flex items-center gap-1 bg-muted rounded-full p-1 border border-border/50 shadow-inner">
          <button onClick={() => setTheme('light')} className={`p-1.5 rounded-full transition-all ${theme === 'light' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="浅色"><Sun size={14} /></button>
          <button onClick={() => setTheme('system')} className={`p-1.5 rounded-full transition-all ${theme === 'system' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="系统"><Monitor size={14} /></button>
          <button onClick={() => setTheme('dark')} className={`p-1.5 rounded-full transition-all ${theme === 'dark' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'}`} title="深色"><Moon size={14} /></button>
        </div>
      </div>
    </aside>
  );
};

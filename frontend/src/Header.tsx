import React from 'react';
import { useChatStore, AGENTS } from '@/store/useChatStore';
import { Button } from '@/components/ui/button';
import { PanelRight } from 'lucide-react';

export const Header: React.FC = () => {
  const isSidebarOpen = useChatStore((state) => state.isSidebarOpen);
  const toggleSidebar = useChatStore((state) => state.toggleSidebar);
  const isRightPanelOpen = useChatStore((state) => state.isRightPanelOpen);
  const toggleRightPanel = useChatStore((state) => state.toggleRightPanel);
  
  const sessions = useChatStore((state) => state.sessions);
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const activeSession = sessions.find(s => s.id === activeSessionId);
  
  const currentAgent = AGENTS.find(a => a.id === activeSession?.agentId) || AGENTS[0];

  return (
    <header className="h-16 bg-background flex items-center justify-between px-4 border-b border-border shrink-0">
      <div className="flex items-center gap-2">
        {!isSidebarOpen && (
          <Button variant="ghost" size="icon" onClick={toggleSidebar} title="展开侧边栏">
            <svg className="w-5 h-5 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16"></path></svg>
          </Button>
        )}
        
        {activeSession ? (
          <div className="flex items-center gap-2">
            <div className="text-xl">{currentAgent.avatar}</div>
            <div>
              <h2 className="text-sm font-semibold text-foreground tracking-tight leading-tight">
                {activeSession.title}
              </h2>
              <div className="text-[11px] text-muted-foreground flex items-center gap-1">
                由 {currentAgent.name} 提供支持
              </div>
            </div>
          </div>
        ) : (
          <h2 className="text-sm font-semibold text-muted-foreground tracking-tight">未选择会话</h2>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button variant={isRightPanelOpen ? "secondary" : "ghost"} size="sm" onClick={toggleRightPanel}>
          <PanelRight size={16} className="mr-2" />
          上下文
        </Button>
      </div>
    </header>
  );
};

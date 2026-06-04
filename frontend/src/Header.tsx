import React from 'react';
import { useSessionStore } from '@/store/useSessionStore';
import { useChatStore } from '@/store/useChatStore';
import { Button } from '@/components/ui/button';
import { PanelRight } from 'lucide-react';

export const Header: React.FC = () => {
  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeId);
  const toggleRightPanel = useChatStore((s) => s.toggleRightPanel);
  const activeSession = sessions.find((s) => s.id === activeId);

  return (
    <header className="h-16 bg-background flex items-center justify-between px-4 border-b border-border shrink-0">
      <div className="flex items-center gap-2">
        {activeSession ? (
          <div className="flex items-center gap-2">
            <div className="text-xl">⚛️</div>
            <div>
              <h2 className="text-sm font-semibold text-foreground tracking-tight leading-tight">
                {activeSession.title}
              </h2>
              <div className="text-[11px] text-muted-foreground">
                {activeSession.messages.length} 条消息
              </div>
            </div>
          </div>
        ) : (
          <h2 className="text-sm font-semibold text-muted-foreground tracking-tight">爱丽丝研发中枢</h2>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => { console.log('点击了上下文按钮'); toggleRightPanel(); }}>
          <PanelRight size={16} className="mr-2" />
          上下文
        </Button>
      </div>
    </header>
  );
};

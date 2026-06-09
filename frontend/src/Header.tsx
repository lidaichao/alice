import React from 'react';
import { useChatStore } from '@/store/useChatStore';

export const Header: React.FC = () => {
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const activeSession = sessions.find((s) => s.id === activeSessionId);

  return (
    <header className="h-16 bg-background flex items-center justify-between px-4 border-b border-border shrink-0">
      <div className="flex items-center gap-2">
        {activeSession ? (
          <div className="flex items-center gap-2">
            <div className="text-xl text-primary">⚛️</div>
            <div>
              <h2 className="text-sm font-semibold text-foreground font-medium tracking-tight leading-tight">
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
    </header>
  );
};

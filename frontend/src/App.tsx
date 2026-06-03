import React, { useEffect, useState, useRef } from 'react';
import { COMMANDS, type Command } from '@/store/useChatStore';
import { useSessionStore, type ChatMessage } from '@/store/useSessionStore';
import { Header } from '@/Header';
import { Sidebar } from '@/Sidebar';
import { RightPanel } from '@/RightPanel';
import { Button } from '@/components/ui/button';
import { CommandPanel } from '@/components/CommandPanel';
import ConfirmCard from '@/components/ConfirmCard';
import { useChat } from '@ai-sdk/react';
import { ChatList } from '@lobehub/ui/chat';
import { ThemeProvider } from '@lobehub/ui';
import { Square } from 'lucide-react';

export const App: React.FC = () => {
  // ═══ 所有 Hook 必须在最顶层，无条件调用 ═══
  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeId);
  const createSession = useSessionStore((s) => s.createSession);
  const updateMessages = useSessionStore((s) => s.updateMessages);

  const activeSession = sessions?.find((s) => s.id === activeId);

  const { messages, input, setInput, append, isLoading, error, stop } = useChat({
    api: '/v1/chat/completions',
    id: activeId || 'default',
    initialMessages: activeSession?.messages || [],
  } as any);

  const isGenerating = isLoading;
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [selectedCmdIndex, setSelectedCmdIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);

  // 持续同步 messages 到 IndexedDB
  useEffect(() => {
    if (activeId && messages.length > 0) {
      const t = setTimeout(() => {
        updateMessages(activeId, messages.map(m => ({ id: m.id, role: m.role as ChatMessage['role'], content: m.content })));
      }, 1000);
      return () => clearTimeout(t);
    }
  }, [messages, activeId]);

  useEffect(() => {
    if (isGenerating && userScrolledUp) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating, userScrolledUp]);

  const handleChatScroll = () => {
    if (!chatContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
    setUserScrolledUp((scrollHeight - scrollTop - clientHeight > 80) && isGenerating);
  };

  // ── 绝对防弹发送逻辑 ──
  const doSendMessage = () => {
    if (!input || input.trim() === '' || isLoading) return;
    const text = input;
    setInput('');
    append({ role: 'user', content: text } as any);
  };

  const filteredCmds = COMMANDS.filter(c =>
    c.key.toLowerCase().includes(commandFilter.toLowerCase()) ||
    c.label.toLowerCase().includes(commandFilter.toLowerCase())
  );

  const handleSelectCommand = (cmd: Command) => {
    setInput(cmd.template);
    setShowCommands(false);
    setSelectedCmdIndex(0);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target?.value ?? (e as any);
    setInput(typeof val === 'string' ? val : String(val || ''));
    // auto-resize
    const el = e.target as HTMLTextAreaElement;
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 200) + 'px'; }
    // slash command
    const v = typeof val === 'string' ? val : '';
    if (v.endsWith('/')) { setShowCommands(true); setCommandFilter(''); setSelectedCmdIndex(0); }
    else if (showCommands) {
      const idx = v.lastIndexOf('/');
      if (idx !== -1) {
        const txt = v.slice(idx + 1);
        txt.includes(' ') ? setShowCommands(false) : (setCommandFilter(txt), setSelectedCmdIndex(0));
      } else setShowCommands(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showCommands && filteredCmds.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedCmdIndex(p => (p + 1) % filteredCmds.length); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedCmdIndex(p => (p - 1 + filteredCmds.length) % filteredCmds.length); return; }
      if (e.key === 'Enter') { e.preventDefault(); handleSelectCommand(filteredCmds[selectedCmdIndex]); return; }
      if (e.key === 'Escape') { e.preventDefault(); setShowCommands(false); return; }
    }
    if (e.key === 'Enter' && !e.shiftKey && !showCommands) {
      e.preventDefault();
      doSendMessage();
    }
  };

  // ═══ 渲染: 所有 Hook 之后才做条件判断 ═══
  if (!sessions || !activeId) {
    return (
      <ThemeProvider>
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
          <Sidebar />
          <main className="flex-1 flex flex-col items-center justify-center text-muted-foreground">
            加载会话中...
          </main>
        </div>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0 bg-muted/10 relative border-r border-border">
          <Header />
          <div ref={chatContainerRef} onScroll={handleChatScroll} className="flex-1 overflow-y-auto p-4 md:p-6">
            <ChatList
              data={messages.map(m => ({
                id: m.id,
                role: m.role as any,
                content: m.content,
                extra: (m as any).pendingCard ? (
                  <ConfirmCard
                    card={(m as any).pendingCard}
                    onConfirm={async (opId: string) => { await fetch(`/operations/${opId}/confirm`, { method: 'POST' }); }}
                    onReject={async (opId: string) => { await fetch(`/operations/${opId}/reject`, { method: 'POST' }); }}
                  />
                ) : undefined,
              })) as any}
            />
            {isGenerating && <span className="blinking-cursor" />}
            <div ref={messagesEndRef} className="h-1" />
          </div>

          <div className="p-4 bg-background border-t border-border flex-shrink-0 flex flex-col gap-2 relative">
            {/* 错误守卫 — 暴露网络死因 */}
            {error && <div className="text-red-500 text-xs mb-1 px-1">后端通信异常: {error.message}</div>}

            <div className="flex justify-center gap-2 mb-2">
              {isGenerating && (
                <Button variant="ghost" size="sm" onClick={stop} className="text-red-500 hover:text-red-700 text-xs gap-1">
                  <Square size={12} /> ⏹ 停止生成
                </Button>
              )}
            </div>

            <div className="flex items-end gap-3 max-w-4xl mx-auto w-full relative">
              {showCommands && <CommandPanel filterText={commandFilter} selectedIndex={selectedCmdIndex} onSelect={handleSelectCommand} />}
              <textarea
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="输入分析指令，或键入 / 呼出模板..." rows={1}
                className="flex-1 max-h-48 min-h-[56px] resize-none rounded-xl border border-input bg-background px-4 py-4 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-sm"
              />
              <Button onClick={doSendMessage}
                disabled={isLoading || !input || input.trim() === ''} className="h-12 w-12 shrink-0 rounded-xl shadow-md">
                <svg className="w-5 h-5 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
                </svg>
              </Button>
            </div>
          </div>
        </main>
        <RightPanel />
      </div>
    </ThemeProvider>
  );
};

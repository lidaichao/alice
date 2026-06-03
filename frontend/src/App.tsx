import React, { useEffect, useState, useRef } from 'react';
import { useChatStore, COMMANDS, type Command } from '@/store/useChatStore';
import { Header } from '@/Header';
import { Sidebar } from '@/Sidebar';
import { RightPanel } from '@/RightPanel';
import { Button } from '@/components/ui/button';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { CommandPanel } from '@/components/CommandPanel';
import ConfirmCard from '@/components/ConfirmCard';
import { useChat } from '@ai-sdk/react';
import { CopyButton } from '@lobehub/ui';
import { Loader2, Blocks, Square, RefreshCw } from 'lucide-react';

export const App: React.FC = () => {
  const initDB = useChatStore((state) => state.initDB);
  const isDbLoaded = useChatStore((state) => state.isDbLoaded);
  const sessions = useChatStore((state) => state.sessions);
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const loadMemories = useChatStore((state) => state.loadMemories);

  // ── Vercel AI SDK stream engine ──
  const { messages, input, handleInputChange: aiHandleInput, handleSubmit: aiHandleSubmit, stop, setMessages, isLoading } = useChat({
    api: '/v1/chat/completions',
  });

  const isGenerating = isLoading;
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [selectedCmdIndex, setSelectedCmdIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const activeSession = sessions.find(s => s.id === activeSessionId);

  useEffect(() => { initDB(); loadMemories(); }, [initDB, loadMemories]);

  useEffect(() => {
    if (isGenerating && userScrolledUp) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating, userScrolledUp]);

  const handleChatScroll = () => {
    if (!chatContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
    setUserScrolledUp((scrollHeight - scrollTop - clientHeight > 80) && isGenerating);
  };

  const filteredCmds = COMMANDS.filter(c =>
    c.key.toLowerCase().includes(commandFilter.toLowerCase()) ||
    c.label.toLowerCase().includes(commandFilter.toLowerCase())
  );

  const handleSelectCommand = (cmd: Command) => {
    const ev = { target: { value: cmd.template, style: { height: 'auto' } } } as unknown as React.ChangeEvent<HTMLTextAreaElement>;
    aiHandleInput(ev);
    setShowCommands(false);
    setSelectedCmdIndex(0);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    aiHandleInput(e);
    const val = e.target.value;
    if (val.endsWith('/')) { setShowCommands(true); setCommandFilter(''); setSelectedCmdIndex(0); }
    else if (showCommands) {
      const idx = val.lastIndexOf('/');
      if (idx !== -1) {
        const txt = val.slice(idx + 1);
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
      aiHandleSubmit(e as unknown as React.FormEvent);
    }
  };

  if (!isDbLoaded) return <div className="h-screen w-screen flex items-center justify-center text-muted-foreground">加载会话中...</div>;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 bg-muted/10 relative border-r border-border">
        <Header />
        <div ref={chatContainerRef} onScroll={handleChatScroll} className="flex-1 overflow-y-auto p-4 md:p-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-70">
              <span className="text-4xl mb-4">⚛️</span>
              <p className="font-medium">爱丽丝研发中枢</p>
              <p className="text-xs text-muted-foreground mt-1">输入 / 呼出指令模板，或直接提问开始分析</p>
            </div>
          ) : (
            messages.map((msg, idx) => {
              const isLast = idx === messages.length - 1;
              const hasPlugin = (msg as any).plugin;
              return (
                <div key={msg.id || `msg-${idx}`} className={`flex w-full group ${msg.role === 'user' ? 'justify-end' : 'justify-start'} mb-6`}>
                  <div className={`max-w-[80%] rounded-2xl px-5 py-3 relative ${
                    msg.role === 'user'
                      ? 'bg-primary text-primary-foreground rounded-tr-sm shadow-md'
                      : 'bg-background border border-border text-foreground rounded-tl-sm shadow-sm'
                  }`}>
                    {hasPlugin && (
                      <div className="mb-3 flex items-center gap-3 p-2.5 rounded-lg border border-border bg-muted/30 text-sm w-fit">
                        {hasPlugin.status === 'running' && isGenerating ? (
                          <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                        ) : (<Blocks size={16} className="text-green-500" />)}
                        <span className="font-medium text-foreground">{hasPlugin.status === 'running' && isGenerating ? '正在检索数据...' : '插件执行完毕'}</span>
                      </div>
                    )}
                    {(msg as any).error ? (
                      <div style={{ color: 'red', fontWeight: 500 }}>⚠️ 后端服务连接中断或响应异常</div>
                    ) : !msg.content && isLast && isGenerating ? (
                      <span className="flex items-center gap-1 text-muted-foreground text-sm">
                        <span className="animate-bounce">●</span><span className="animate-bounce delay-75">●</span><span className="animate-bounce delay-150">●</span>
                        <span className="ml-1">爱丽丝识别中...</span>
                      </span>
                    ) : !msg.content && !isGenerating ? (
                      <div className="text-gray-400 text-sm italic">[已停止生成]</div>
                    ) : msg.role === 'user' ? (
                      <div className="text-[15px] break-words whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                    ) : (
                      <MarkdownRenderer content={msg.content} citations={(msg as any).citations} />
                    )}
                    {(msg as any).pendingCard && (msg as any).pendingCard.event === 'confirm_card' && (
                      <ConfirmCard
                        card={(msg as any).pendingCard}
                        onConfirm={async (opId) => {
                          await fetch(`/operations/${opId}/confirm`, { method: 'POST' });
                          const { sessions: s, activeSessionId: sid } = useChatStore.getState();
                          useChatStore.setState({ sessions: s.map(ss => ss.id === sid ? { ...ss, messages: ss.messages.map(m => m.id === msg.id ? { ...m, pendingCard: null } : m) } : ss) });
                        }}
                        onReject={async (opId) => {
                          await fetch(`/operations/${opId}/reject`, { method: 'POST' });
                          const { sessions: s, activeSessionId: sid } = useChatStore.getState();
                          useChatStore.setState({ sessions: s.map(ss => ss.id === sid ? { ...ss, messages: ss.messages.map(m => m.id === msg.id ? { ...m, pendingCard: null } : m) } : ss) });
                        }}
                      />
                    )}
                    {/* LobeHub CopyButton */}
                    <div className={`absolute -top-3 opacity-0 group-hover:opacity-100 transition-opacity ${msg.role === 'user' ? '-left-4' : '-right-4'}`}>
                      {msg.content && <CopyButton content={msg.content} size="small" />}
                    </div>
                  </div>
                </div>
              );
            })
          )}
          {isGenerating && <span className="blinking-cursor" />}
          <div ref={messagesEndRef} className="h-1" />
        </div>

        <div className="p-4 bg-background border-t border-border flex-shrink-0 flex flex-col gap-2 relative">
          <div className="flex justify-center gap-2 mb-2">
            {isGenerating && (
              <Button variant="ghost" size="sm" onClick={stop} className="text-red-500 hover:text-red-700 text-xs gap-1">
                <Square size={12} /> ⏹ 停止生成
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => { if (isGenerating) stop(); setMessages([]); }} className="text-muted-foreground hover:text-foreground text-xs gap-1">
              <RefreshCw size={12} /> 🧹 新话题
            </Button>
          </div>

          <div className="flex items-end gap-3 max-w-4xl mx-auto w-full relative">
            {showCommands && <CommandPanel filterText={commandFilter} selectedIndex={selectedCmdIndex} onSelect={handleSelectCommand} />}
            <textarea value={input} onChange={handleInputChange} onKeyDown={handleKeyDown}
              placeholder="输入分析指令，或键入 / 呼出模板..." rows={1}
              className="flex-1 max-h-48 min-h-[56px] resize-none rounded-xl border border-input bg-background px-4 py-4 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-sm"
            />
            <Button onClick={() => aiHandleSubmit({ preventDefault: () => {} } as any)}
              disabled={!(input || '').trim() || isGenerating} className="h-12 w-12 shrink-0 rounded-xl shadow-md">
              <svg className="w-5 h-5 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
              </svg>
            </Button>
          </div>
        </div>
      </main>
      <RightPanel />
    </div>
  );
};

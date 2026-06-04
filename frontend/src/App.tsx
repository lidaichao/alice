import React, { useEffect, useState, useRef, useCallback } from 'react';
import { COMMANDS, type Command, useChatStore } from '@/store/useChatStore';
import { Header } from '@/Header';
import { Sidebar } from '@/Sidebar';
import { RightPanel } from '@/RightPanel';
import { Button } from '@/components/ui/button';
import { CommandPanel } from '@/components/CommandPanel';
import ConfirmCard from '@/components/ConfirmCard';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { ThemeProvider } from '@lobehub/ui';
import { Square } from 'lucide-react';

export const App: React.FC = () => {
  // ═══ 统一数据源：useChatStore（chatSlice + agentSlice + uiSlice + memorySlice）═══
  const initDB = useChatStore((s) => s.initDB);
  const isDbLoaded = useChatStore((s) => s.isDbLoaded);
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const stopGenerating = useChatStore((s) => s.stopGenerating);
  const pendingConfirmations = useChatStore((s) => s.pendingConfirmations);

  const currentSession = sessions.find((s) => s.id === activeSessionId);
  const messages = currentSession?.messages || [];

  // ── 初始化：加载 DB + 首次启动自动建会话 ──
  useEffect(() => {
    initDB();
  }, []); // initDB ref stable from zustand

  useEffect(() => {
    if (isDbLoaded && sessions.length === 0 && !activeSessionId) {
      useChatStore.getState().addSession();
    }
  }, [isDbLoaded, sessions.length, activeSessionId]);

  // ── UI-only 本地状态（输入框、命令面板、滚动感知）──
  const [myInput, setMyInput] = useState('');
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [selectedCmdIndex, setSelectedCmdIndex] = useState(0);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // ── 自动滚动 ──
  useEffect(() => {
    if (isGenerating && userScrolledUp) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating, userScrolledUp]);

  const handleChatScroll = () => {
    if (!chatContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
    setUserScrolledUp((scrollHeight - scrollTop - clientHeight > 80) && isGenerating);
  };

  // ── 发送：委托给 chatSlice.sendMessage（含 agent/systemPrompt/citations 全链路）──
  const handleSend = useCallback(() => {
    if (!myInput.trim() || isGenerating || !activeSessionId) return;
    const text = myInput;
    setMyInput('');
    sendMessage(text);
  }, [myInput, isGenerating, activeSessionId, sendMessage]);

  // ── Jira 确认卡回调 ──
  const handleConfirm = useCallback(async (opId: string) => {
    try {
      await fetch(`/operations/${opId}/confirm`, { method: 'POST' });
    } catch (e) {
      console.error('[ConfirmCard] confirm POST failed:', e);
    }
    useChatStore.setState((s) => ({
      pendingConfirmations: s.pendingConfirmations.filter((c) => c.op_id !== opId),
    }));
  }, []);

  const handleReject = useCallback(async (opId: string) => {
    try {
      await fetch(`/operations/${opId}/reject`, { method: 'POST' });
    } catch (e) {
      console.error('[ConfirmCard] reject POST failed:', e);
    }
    useChatStore.setState((s) => ({
      pendingConfirmations: s.pendingConfirmations.filter((c) => c.op_id !== opId),
    }));
  }, []);

  // ── 命令面板 ──
  const filteredCmds = COMMANDS.filter(c =>
    c.key.toLowerCase().includes(commandFilter.toLowerCase()) ||
    c.label.toLowerCase().includes(commandFilter.toLowerCase())
  );

  const handleSelectCommand = (cmd: Command) => {
    setMyInput(cmd.template);
    setShowCommands(false);
    setSelectedCmdIndex(0);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target?.value ?? (e as any);
    setMyInput(typeof val === 'string' ? val : String(val || ''));
    const el = e.target as HTMLTextAreaElement;
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 200) + 'px'; }
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
      handleSend();
    }
  };

  // ═══ 加载中 ═══
  if (!isDbLoaded) {
    return (
      <ThemeProvider themeMode="dark">
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
          <Sidebar />
          <main className="flex-1 flex flex-col items-center justify-center text-muted-foreground">
            加载会话中...
          </main>
        </div>
      </ThemeProvider>
    );
  }

  // ═══ 无会话 ═══
  if (!activeSessionId || !currentSession) {
    return (
      <ThemeProvider themeMode="dark">
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
          <Sidebar />
          <main className="flex-1 flex flex-col items-center justify-center text-muted-foreground">
            请创建或选择一个会话
          </main>
        </div>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider themeMode="dark">
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0 bg-muted/10 relative border-r border-border">
          <Header />

          {/* ── 消息列表 ── */}
          <div ref={chatContainerRef} onScroll={handleChatScroll} className="flex-1 overflow-y-auto p-4 space-y-6">
            {messages.map((m) => {
              const isUser = m.role === 'user';
              return (
                <div key={m.id} className={`flex gap-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                  {/* 头像 */}
                  <div className="w-10 h-10 rounded-full flex items-center justify-center bg-muted text-xl shrink-0 shadow-sm">
                    {isUser ? '🧑‍💻' : '🐰'}
                  </div>

                  {/* 气泡 */}
                  <div className={`max-w-[75%] p-4 rounded-2xl ${
                    isUser
                      ? 'bg-blue-600 text-white rounded-tr-none'
                      : 'bg-muted text-foreground rounded-tl-none'
                  }`}>
                    {m.role === 'assistant' && m.content ? (
                      <MarkdownRenderer content={m.content} citations={m.citations} />
                    ) : m.content ? (
                      <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">{m.content}</div>
                    ) : (
                      <span className="text-muted-foreground italic text-sm">正在思考...</span>
                    )}
                  </div>
                </div>
              );
            })}

            {/* ── Jira 确认卡（内联在消息流末尾）── */}
            {pendingConfirmations.map((card) => (
              <div key={card.op_id} className="flex gap-4 flex-row">
                <div className="w-10 h-10 shrink-0" />
                <div className="max-w-[75%] flex-1">
                  <ConfirmCard card={card} onConfirm={handleConfirm} onReject={handleReject} />
                </div>
              </div>
            ))}

            {isGenerating && <span className="blinking-cursor" />}
            <div ref={messagesEndRef} className="h-1" />
          </div>

          {/* ── 输入区 ── */}
          <div className="p-4 bg-background border-t border-border flex-shrink-0 flex flex-col gap-2 relative">
            <div className="flex justify-center gap-2 mb-2">
              {isGenerating && (
                <Button variant="ghost" size="sm" onClick={stopGenerating} className="text-red-500 hover:text-red-700 text-xs gap-1">
                  <Square size={12} /> ⏹ 停止生成
                </Button>
              )}
            </div>

            <div className="flex items-end gap-3 max-w-4xl mx-auto w-full relative">
              {showCommands && <CommandPanel filterText={commandFilter} selectedIndex={selectedCmdIndex} onSelect={handleSelectCommand} />}
              <textarea
                value={myInput}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="输入分析指令，或键入 / 呼出模板..." rows={1}
                className="flex-1 max-h-48 min-h-[56px] resize-none rounded-xl border border-input bg-background px-4 py-4 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-sm"
              />
              <Button onClick={handleSend}
                disabled={isGenerating || !myInput || myInput.trim() === ''} className="h-12 w-12 shrink-0 rounded-xl shadow-md">
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

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { COMMANDS, type Command, useChatStore } from '@/store/useChatStore';
import { Header } from '@/Header';
import { Sidebar } from '@/Sidebar';
import { RightPanel } from '@/RightPanel';
import { Button } from '@/components/ui/button';
import { CommandPanel } from '@/components/CommandPanel';
import ConfirmCard from '@/components/ConfirmCard';
import DraftCard from '@/components/DraftCard';
import JiraSearchSupplement from '@/components/JiraSearchSupplement';
import type { DraftCardItem } from '@/store/slices/chatSlice';
import { buildJiraWriteRequestBody } from '@/lib/runtimeConfig';
import { buildConfirmCardFromApi, formatOperationResultMessage } from '@/lib/jiraConfirm';
import { confirmOperationWithProgress } from '@/lib/operationConfirmStream';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { PluginToolCard } from '@/components/MarkdownRenderer';
import { OperationsConsole } from '@/components/OperationsConsole';
import { syncHubConfigFromHealth } from '@/lib/hubConfig';
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
  const pendingDraftCards = useChatStore((s) => s.pendingDraftCards);
  const pendingJiraSupplements = useChatStore((s) => s.pendingJiraSupplements);
  const mainView = useChatStore((s) => s.mainView);
  const setMainView = useChatStore((s) => s.setMainView);

  const currentSession = sessions.find((s) => s.id === activeSessionId);
  const messages = currentSession?.messages || [];

  // ── 初始化：加载 DB + 首次启动自动建会话 ──
  useEffect(() => {
    initDB();
    syncHubConfigFromHealth();
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
  const [confirmProgress, setConfirmProgress] = useState<Record<string, string>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isInitialMount = useRef(true);

  // ── 滚动到底部（isInstant: 瞬间闪现；否则平滑动画）──
  const scrollToBottom = useCallback((isInstant?: boolean) => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({
        behavior: isInstant ? 'auto' : 'smooth',
      });
    });
  }, []);

  // ── 首次加载：瞬间闪现到底部（不走平滑动画）──
  useEffect(() => {
    if (isInitialMount.current && messages.length > 0) {
      scrollToBottom(true);
      isInitialMount.current = false;
      return;
    }
    // 流式输出 + 非手动上滚：平滑跟底
    if (isGenerating && userScrolledUp) return;
    scrollToBottom();
  }, [messages, isGenerating, userScrolledUp, scrollToBottom]);

  // ── 会话切换：瞬间闪现到底部 ──
  useEffect(() => {
    if (!activeSessionId) return;
    scrollToBottom(true);
  }, [activeSessionId]); // eslint-disable-line react-hooks/exhaustive-deps

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
    // 发送后平滑滚到底部 + 保持输入框焦点
    scrollToBottom();
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  }, [myInput, isGenerating, activeSessionId, sendMessage, scrollToBottom]);

  const appendAssistantMessage = useChatStore((s) => s.appendAssistantMessage);

  const handleDraftSubmit = useCallback(
    async (draftId: string, items: DraftCardItem[]) => {
      const res = await fetch(`/drafts/${draftId}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || res.statusText || '提交草稿失败');
      }
      const opId = data.operation_id as string;
      const opPayload = {
        ...(data.operation as Record<string, unknown>),
        warnings: [
          ...((data.warnings as string[]) || []),
          ...(((data.operation as Record<string, unknown>)?.warnings as string[]) || []),
        ],
      };
      const card = buildConfirmCardFromApi(opId, opPayload);
      useChatStore.setState((s) => ({
        pendingDraftCards: s.pendingDraftCards.filter((d) => d.draft_id !== draftId),
        pendingConfirmations: s.pendingConfirmations.some((c) => c.op_id === opId)
          ? s.pendingConfirmations
          : [...s.pendingConfirmations, card],
      }));
      if (data.message) {
        await appendAssistantMessage(String(data.message));
      }
    },
    [appendAssistantMessage],
  );

  const handleDraftCancel = useCallback(async (draftId: string) => {
    const res = await fetch(`/drafts/${draftId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildJiraWriteRequestBody()),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || '取消草稿失败');
    }
    useChatStore.setState((s) => ({
      pendingDraftCards: s.pendingDraftCards.filter((d) => d.draft_id !== draftId),
    }));
  }, []);

  const handleConfirm = useCallback(
    async (
      opId: string,
      opts?: { recoveryAction?: string; supplement?: Record<string, string> },
    ) => {
      const extra: Record<string, unknown> = {};
      if (opts?.recoveryAction) extra.recovery_action = opts.recoveryAction;
      if (opts?.supplement) extra.supplement = opts.supplement;
      const body = buildJiraWriteRequestBody(extra);
      setConfirmProgress((p) => ({ ...p, [opId]: '开始执行…' }));
      const data = await confirmOperationWithProgress(opId, body, (ev) => {
        setConfirmProgress((p) => ({ ...p, [opId]: ev.message || ev.phase }));
      });
      setConfirmProgress((p) => {
        const next = { ...p };
        delete next[opId];
        return next;
      });
      const msg = formatOperationResultMessage(data);
      await appendAssistantMessage(msg);
      if (data.ok === false) {
        throw new Error(data.error || '操作失败');
      }
      useChatStore.setState((s) => ({
        pendingConfirmations: s.pendingConfirmations.filter((c) => c.op_id !== opId),
      }));
    },
    [appendAssistantMessage],
  );

  const handleReject = useCallback(
    async (opId: string) => {
      const res = await fetch(`/operations/${opId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildJiraWriteRequestBody()),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || '拒绝失败');
      }
      await appendAssistantMessage('已拒绝该 Jira 写操作，未对 Jira 做任何修改。');
      useChatStore.setState((s) => ({
        pendingConfirmations: s.pendingConfirmations.filter((c) => c.op_id !== opId),
      }));
    },
    [appendAssistantMessage],
  );

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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // 命令面板导航
    if (showCommands && filteredCmds.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedCmdIndex(p => (p + 1) % filteredCmds.length); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedCmdIndex(p => (p - 1 + filteredCmds.length) % filteredCmds.length); return; }
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSelectCommand(filteredCmds[selectedCmdIndex]); return; }
      if (e.key === 'Escape') { e.preventDefault(); setShowCommands(false); return; }
    }
    // Shift+Enter → 正常换行，不做任何拦截
    if (e.key === 'Enter' && e.shiftKey) return;
    // Enter 发送（排除 IME 组合态，避免中文输入时误触）
    if (e.key === 'Enter' && !e.shiftKey && !showCommands) {
      if (e.nativeEvent.isComposing) return;
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
        {mainView === 'operations' ? (
          <main className="flex-1 flex flex-col min-w-0 border-r border-border">
            <OperationsConsole onBack={() => setMainView('chat')} />
          </main>
        ) : (
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
                      <MarkdownRenderer content={m.content} citations={m.citations} plugin={m.plugin} />
                    ) : m.role === 'assistant' && m.plugin ? (
                      <div className="space-y-2">
                        <PluginToolCard plugin={m.plugin} />
                        <span className="text-muted-foreground italic text-sm">正在思考...</span>
                      </div>
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
            {pendingDraftCards.map((draft) => (
              <div key={draft.draft_id} className="flex gap-4 flex-row">
                <div className="w-10 h-10 shrink-0" />
                <div className="max-w-[75%] flex-1">
                  <DraftCard
                    draft={draft}
                    onSubmit={handleDraftSubmit}
                    onCancel={handleDraftCancel}
                  />
                </div>
              </div>
            ))}

            {pendingConfirmations.map((card) => (
              <div key={card.op_id} className="flex gap-4 flex-row">
                <div className="w-10 h-10 shrink-0" />
                <div className="max-w-[75%] flex-1">
                  <ConfirmCard
                    card={card}
                    progressMessage={confirmProgress[card.op_id]}
                    onConfirm={handleConfirm}
                    onReject={handleReject}
                  />
                </div>
              </div>
            ))}

            {pendingJiraSupplements.map((card) => (
              <div key={card.id} className="flex gap-4 flex-row">
                <div className="w-10 h-10 shrink-0" />
                <div className="max-w-[75%] flex-1">
                  <JiraSearchSupplement
                    card={card}
                    onSelect={(value) => {
                      useChatStore.setState((s) => ({
                        pendingJiraSupplements: s.pendingJiraSupplements.filter((c) => c.id !== card.id),
                      }));
                      const label = card.choices.find((c) => c.value === value)?.label || value;
                      const msg =
                        card.kind === 'intent'
                          ? `[INTENT:${value}] 请按「${label}」处理我上一条需求。`
                          : `JIRA_USER:${value} ${label} 本周未完成的 Jira 任务`;
                      useChatStore.getState().sendMessage(msg);
                    }}
                    onDismiss={() => {
                      useChatStore.setState((s) => ({
                        pendingJiraSupplements: s.pendingJiraSupplements.filter((c) => c.id !== card.id),
                      }));
                    }}
                  />
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
                ref={inputRef}
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
        )}
      </div>
    </ThemeProvider>
  );
};

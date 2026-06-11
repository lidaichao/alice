import React, { useEffect, useState, useRef, useCallback } from 'react';
import { COMMANDS, type Command, useChatStore } from '@/store/useChatStore';
import { Header } from '@/Header';
import { Sidebar } from '@/Sidebar';
import { RightPanel } from '@/RightPanel';
import { Button } from '@/components/ui/button';
import { CommandPanel } from '@/components/CommandPanel';
import ConfirmCard from '@/components/ConfirmCard';
import JiraSearchSupplement from '@/components/JiraSearchSupplement';
import LoginPanel from '@/components/LoginPanel';
import { buildAliceUserHeaders } from '@/lib/runtimeConfig';
import { formatOperationResultMessage } from '@/lib/jiraConfirm';
import { useOperationActions } from '@/hooks/useOperationActions';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { PluginToolCard } from '@/components/MarkdownRenderer';
import { OperationsConsole } from '@/components/OperationsConsole';
import { EnginePicker } from '@/components/EnginePicker';
import { ModelPicker } from '@/components/ModelPicker';
import { CursorSettings } from '@/components/CursorSettings';
import { SettingsCenter } from '@/components/SettingsCenter';
import { syncHubConfigFromHealth } from '@/lib/hubConfig';
import { ThemeProvider } from '@lobehub/ui';
import { useToast } from '@/components/Toast';
import { Square, Copy, Check, User, Bot, Settings, RefreshCcw, Pencil, X, Plus, Activity } from 'lucide-react';

export const App: React.FC = () => {
  // ═══ 统一数据源：useChatStore（chatSlice + agentSlice + uiSlice + memorySlice）═══
  const initDB = useChatStore((s) => s.initDB);
  const isDbLoaded = useChatStore((s) => s.isDbLoaded);
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isGenerating = useChatStore((s) => s.generatingSessions[activeSessionId || ''] || false);
  const stopGenerating = useChatStore((s) => s.stopGenerating);
  const pendingConfirmations = useChatStore((s) => s.pendingConfirmations);
  const pendingJiraSupplements = useChatStore((s) => s.pendingJiraSupplements);
  const mainView = useChatStore((s) => s.mainView);
  const setMainView = useChatStore((s) => s.setMainView);

  const currentSession = sessions.find((s) => s.id === activeSessionId);
  const messages = currentSession?.messages || [];
  const isLoggedIn = useChatStore((s) => s.user.isLoggedIn);

  // ── 引擎与模型选择状态 ──
  const [currentEngine, setCurrentEngine] = useState<string>(() => {
    const pref = JSON.parse(localStorage.getItem('alice_engine_pref') || '{}');
    return pref.engine || 'auto';
  });
  const [currentCursorMode, setCurrentCursorMode] = useState<string>(() => {
    const pref = JSON.parse(localStorage.getItem('alice_engine_pref') || '{}');
    return pref.mode || '';
  });
  const [deepseekModelName, setDeepseekModelName] = useState('');
  const [cursorModelName, setCursorModelName] = useState<string>(() => {
    const cfg = JSON.parse(localStorage.getItem('alice_cursor_config') || '{}');
    return cfg.model || 'composer-2.5';
  });
  const [cursorAvailableModels, setCursorAvailableModels] = useState<string[]>(['composer-2.5', 'auto']);

  // ── 工作流模板（从 Sidebar 搬入，融入 Slash 命令面板）──
  const [wfTemplates, setWfTemplates] = useState<Array<{id:string;name:string;description:string}>>([]);

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

  // ── 加载引擎配置（供 ModelPicker 使用）──
  useEffect(() => {
    fetch('/v1/config/engines')
      .then((res) => res.json())
      .then((data: { deepseek?: { model?: string } }) => {
        if (data?.deepseek?.model) setDeepseekModelName(data.deepseek.model);
      })
      .catch(() => {});
    // 加载当前 cursor 配置中的 model
    try {
      const cfg = JSON.parse(localStorage.getItem('alice_cursor_config') || '{}');
      if (cfg.model) setCursorModelName(cfg.model);
      if (cfg.key) {
        fetch(`/v1/admin/cursor-sdk/models?api_key=${encodeURIComponent(cfg.key)}`)
          .then((r) => r.json())
          .then((d) => { if (d.ok && d.models?.length) setCursorAvailableModels(d.models.map((m: any) => m.id)); })
          .catch(() => {});
      }
    } catch {}
  }, []);

  // ── UI-only 本地状态（输入框、命令面板、滚动感知）──
  const [myInput, setMyInput] = useState('');
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [selectedCmdIndex, setSelectedCmdIndex] = useState(0);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const [showCursorSettings, setShowCursorSettings] = useState(false);
  const [copiedMessages, setCopiedMessages] = useState<Record<string, boolean>>({});
  // ── 消息就地编辑状态 ──
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [onboardingStep, setOnboardingStep] = useState(0);
  const [onboardingDone, setOnboardingDone] = useState(() => {
    return localStorage.getItem('alice_onboarding_done') === '1';
  });
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

  // ── 权限变更 Toast ──
  const lastSystemMsgRef = useRef('');
  useEffect(() => {
    const sysMsg = messages.filter(m => m.role === 'system').slice(-1)[0];
    if (sysMsg && sysMsg.content !== lastSystemMsgRef.current) {
      lastSystemMsgRef.current = sysMsg.content;
      toast(sysMsg.content, { type: 'info', duration: 3000 });
    }
  }, [messages]);

  const handleChatScroll = () => {
    if (!chatContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
    setUserScrolledUp((scrollHeight - scrollTop - clientHeight > 80) && isGenerating);
  };

  // ── 工作流模板加载（融入 Slash 命令面板）──
  const loadWorkflowTemplates = async () => {
    try {
      const res = await fetch('/v1/workflow/templates');
      if (res.ok) {
        const data = await res.json();
        setWfTemplates(data?.templates || []);
      }
    } catch {
      // 端点可能未就绪，静默降级
    }
  };

  // ── 发送：委托给 chatSlice.sendMessage（含 agent/systemPrompt/citations 全链路）──
  const handleSend = useCallback(() => {
    if (!myInput.trim() || isGenerating || !activeSessionId) return;
    const text = myInput;
    setMyInput('');
    // 重置 textarea 高度
    if (inputRef.current) {
      inputRef.current.style.height = '';
    }
    sendMessage(text);
    // 发送后平滑滚到底部 + 保持输入框焦点
    scrollToBottom();
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  }, [myInput, isGenerating, activeSessionId, sendMessage, scrollToBottom]);

  const appendAssistantMessage = useChatStore((s) => s.appendAssistantMessage);

  const { confirm: handleConfirm, reject: handleReject, progressByOpId: confirmProgress } =
    useOperationActions({
      onConfirmSuccess: async (data) => {
        await appendAssistantMessage(formatOperationResultMessage(data));
      },
      onRejectSuccess: async () => {
        await appendAssistantMessage('已拒绝该 Jira 写操作，未对 Jira 做任何修改。');
      },
    });

  const onConfirmResolved = useCallback((opId: string, status: 'confirmed' | 'rejected') => {
    useChatStore.setState((s) => ({
      pendingConfirmations: s.pendingConfirmations.filter((c) => c.op_id !== opId),
      sessions: s.sessions.map(sess => ({
        ...sess,
        messages: sess.messages.map(msg =>
          msg.pendingCard?.op_id === opId
            ? { ...msg, pendingCard: { ...msg.pendingCard, resolved: true, status } }
            : msg
        ),
      })),
    }));
  }, []);

  const { toast } = useToast();

  const wrappedHandleConfirm = useCallback(
    async (
      opId: string,
      opts?: { recoveryAction?: string; supplement?: Record<string, string> },
    ) => {
      try {
        await handleConfirm(opId, opts);
        onConfirmResolved(opId, 'confirmed');
        toast('✅ 已放行操作', { type: 'success' });
      } catch (e: any) {
        toast(`放行失败：${e?.message || '请重试'}`, { type: 'error' });
      }
    },
    [handleConfirm, onConfirmResolved, toast],
  );

  const wrappedHandleReject = useCallback(
    async (opId: string) => {
      try {
        await handleReject(opId);
        onConfirmResolved(opId, 'rejected');
        toast('❌ 已拒绝', { type: 'error' });
      } catch (e: any) {
        toast(`拒绝失败：${e?.message || '请重试'}`, { type: 'error' });
      }
    },
    [handleReject, onConfirmResolved, toast],
  );

  // ── 命令面板 ──
  const filteredCmds = [
    ...COMMANDS.filter(c =>
      c.key.toLowerCase().includes(commandFilter.toLowerCase()) ||
      c.label.toLowerCase().includes(commandFilter.toLowerCase())
    ),
    ...wfTemplates
      .filter(tpl =>
        tpl.name.toLowerCase().includes(commandFilter.toLowerCase()) ||
        (tpl.description || '').toLowerCase().includes(commandFilter.toLowerCase())
      )
      .map(tpl => ({
        key: `wf:${tpl.id}`,
        label: tpl.name,
        icon: '⚡',
        description: tpl.description || '工作流模板',
        template: `[WORKFLOW:${tpl.id}]`,
        type: 'workflow' as const,
      }))
  ];

  const handleSelectCommand = (cmd: Command) => {
    if ((cmd as any).type === 'workflow') {
      sendMessage(cmd.template);
      setShowCommands(false);
      setSelectedCmdIndex(0);
      scrollToBottom();
    } else {
      setMyInput(cmd.template);
      setShowCommands(false);
      setSelectedCmdIndex(0);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target?.value ?? (e as any);
    setMyInput(typeof val === 'string' ? val : String(val || ''));
    const el = e.target as HTMLTextAreaElement;
    if (el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 200) + 'px'; }
    const v = typeof val === 'string' ? val : '';
    if (v.endsWith('/')) { setShowCommands(true); setCommandFilter(''); setSelectedCmdIndex(0); loadWorkflowTemplates(); }
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

  const approvalPanelOpen = useChatStore((s) => s.approvalPanelOpen);
  const setApprovalPanelOpen = useChatStore((s) => s.setApprovalPanelOpen);

  // ── 审批面板快捷键 ──
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && approvalPanelOpen) {
        e.preventDefault();
        setApprovalPanelOpen(false);
      }
      if (e.ctrlKey && e.shiftKey && e.key === 'A') {
        e.preventDefault();
        setApprovalPanelOpen(p => !p);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [approvalPanelOpen, setApprovalPanelOpen]);

  // ═══ 加载中 ═══
  if (!isLoggedIn) {
    return <LoginPanel />;
  }

  if (!isDbLoaded) {
    return (
      <ThemeProvider themeMode="dark">
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
          <Sidebar />
          <main className="flex-1 flex flex-col gap-4 p-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex gap-4 animate-pulse">
                <div className="w-10 h-10 rounded-full bg-muted shrink-0" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-muted rounded w-3/4" />
                  <div className="h-4 bg-muted rounded w-1/2" />
                  {i === 1 && <div className="h-4 bg-muted rounded w-5/6" />}
                </div>
              </div>
            ))}
          </main>
        </div>
      </ThemeProvider>
    );
  }

  // ═══ 首次引导 ═══
  if (!onboardingDone) {
    return (
      <ThemeProvider themeMode="dark">
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
          <Sidebar />
          <main className="flex-1 flex flex-col items-center justify-center gap-6 p-8">
            {onboardingStep === 0 && (
              <div className="text-center space-y-4 max-w-md animate-in fade-in slide-in-from-bottom-4 duration-300">
                <Bot size={48} className="mx-auto text-primary" />
                <h2 className="text-2xl font-bold">认识 Alice</h2>
                <p className="text-muted-foreground">我是你的研发助手，连接 Jira / SVN / Notion / Google Drive</p>
                <Button onClick={() => setOnboardingStep(1)}>下一步 →</Button>
              </div>
            )}
            {onboardingStep === 1 && (
              <div className="text-center space-y-4 max-w-md animate-in fade-in slide-in-from-bottom-4 duration-300">
                <h2 className="text-2xl font-bold">试试这些</h2>
                <div className="grid grid-cols-2 gap-3">
                  {['查 Jira 任务', '分析 Bug', '生成周报', 'Code Review'].map(label => (
                    <div key={label} className="p-3 rounded-xl border border-border/50 bg-card text-sm">{label}</div>
                  ))}
                </div>
                <Button onClick={() => setOnboardingStep(2)}>下一步 →</Button>
              </div>
            )}
            {onboardingStep === 2 && (
              <div className="text-center space-y-4 max-w-md animate-in fade-in slide-in-from-bottom-4 duration-300">
                <h2 className="text-2xl font-bold">设置你的偏好</h2>
                <p className="text-muted-foreground">选择引擎、配置 API Key、设置记忆</p>
                <Button onClick={() => { localStorage.setItem('alice_onboarding_done', '1'); setOnboardingDone(true); }}>
                  开始使用 →
                </Button>
              </div>
            )}
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
          <main className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-4">
            <p>请创建或选择一个会话</p>
            <Button onClick={() => useChatStore.getState().addSession()}>
              <Plus size={14} className="mr-1.5" /> 新建会话
            </Button>
          </main>
        </div>
      </ThemeProvider>
    );
  }


  if (mainView === 'settings') {
    return (
      <ThemeProvider themeMode="dark">
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
          <Sidebar />
          <SettingsCenter onBack={() => setMainView('chat')} />
        </div>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider themeMode="dark">
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        <Sidebar />
        <>
        <main className="flex-1 flex flex-col min-w-0 bg-muted/10 relative border-r border-border">
          <Header />

          {/* ── 消息列表 ── */}
          <div ref={chatContainerRef} onScroll={handleChatScroll} className="flex-1 overflow-y-auto p-4 space-y-6">
            {messages.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-6 h-full min-h-[400px]">
                <div className="text-center">
                  <p className="text-lg font-medium text-foreground mb-2">👋 今天想做什么？</p>
                  <p className="text-sm text-muted-foreground">输入 / 试试快捷指令，或直接告诉我你需要什么</p>
                </div>
                <div className="grid grid-cols-2 gap-3 max-w-md">
                  {[
                    { icon: '📋', label: '查 Jira 任务', desc: '快速检索我的待办与进度', msg: '/jira 查我的任务' },
                    { icon: '🐛', label: '分析 Bug', desc: '输入报错日志自动定位原因', msg: '/analyze ' },
                    { icon: '📝', label: '生成周报', desc: '基于本周会话自动汇总', msg: '/weekly ' },
                    { icon: '🔍', label: 'Code Review', desc: '深度审查代码质量与隐患', msg: '/review ' },
                  ].map((item) => (
                    <button key={item.label}
                      onClick={() => sendMessage(item.msg)}
                      disabled={isGenerating}
                      className="flex flex-col items-start gap-1 p-3 rounded-xl border border-border/50 bg-card hover:bg-accent hover:shadow-sm hover:-translate-y-px transition-all text-sm text-left disabled:opacity-50 disabled:pointer-events-none"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{item.icon}</span>
                        <span className="font-medium">{item.label}</span>
                      </div>
                      <span className="text-[11px] text-muted-foreground leading-tight">{item.desc}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
            messages.map((m) => {
              const isUser = m.role === 'user';
              const isAssistant = m.role === 'assistant';
              const isSystem = m.role === 'system';
              const isStopped = isAssistant && m.content === '⏹ 已停止生成';
              const hasContent = isAssistant && m.content && !isStopped;
              const hasPluginOnly = isAssistant && !m.content && m.plugin;
              const isEmptyAssistant = isAssistant && !m.content && !m.plugin && !isStopped;
              const isCopied = copiedMessages[m.id] || false;

              const handleCopy = async () => {
                try {
                  await navigator.clipboard.writeText(m.content);
                  setCopiedMessages((prev) => ({ ...prev, [m.id]: true }));
                  setTimeout(() => setCopiedMessages((prev) => ({ ...prev, [m.id]: false })), 2000);
                } catch {}
              };

              if (isSystem) {
                return (
                  <div key={m.id} className="flex justify-center w-full">
                    <div className="max-w-[75%] bg-amber-50 border border-amber-200 text-amber-800 px-4 py-2 rounded-xl text-sm text-center">
                      {m.content}
                    </div>
                  </div>
                );
              }

              return (
                <div key={m.id} className={`flex gap-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                  {/* 头像 */}
                  <div className="w-10 h-10 rounded-full flex items-center justify-center bg-secondary text-muted-foreground shrink-0 shadow-sm">
                    {isUser ? <User size={20} /> : <Bot size={20} />}
                  </div>

                  {/* 气泡 */}
                  <div className={isUser ? 'max-w-[70%]' : 'max-w-[80%]'}>
                    <div className={`p-4 rounded-2xl ${
                      isUser
                        ? 'bg-primary/90 text-primary-foreground rounded-tr-none'
                        : isStopped
                          ? 'bg-card/60 text-muted-foreground/60 rounded-tl-none border border-border/30'
                          : 'bg-card text-foreground rounded-tl-none border border-border/30'
                    }`}>
                      {hasContent ? (
                        <MarkdownRenderer content={m.content} citations={m.citations} plugin={m.plugin} />
                      ) : hasPluginOnly ? (
                        <div className="space-y-2">
                          <PluginToolCard plugin={m.plugin} />
                          <span className="text-muted-foreground italic text-sm">正在思考...</span>
                        </div>
                      ) : m.content ? (
                        <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">{m.content}</div>
                      ) : isEmptyAssistant ? (
                        <span className="text-muted-foreground italic text-sm">正在思考...</span>
                    ) : null}

                    {/* 内联确认卡 */}
                    {isAssistant && m.pendingCard && (
                      <div className="mt-3 pt-3 border-t border-border/50">
                        <ConfirmCard
                          card={m.pendingCard}
                          progressMessage={confirmProgress[m.pendingCard.op_id]}
                          permissionMode={m.pendingCard.permissionMode || 'approval'}
                          onConfirm={wrappedHandleConfirm}
                          onReject={wrappedHandleReject}
                          resolved={m.pendingCard.resolved}
                          resolvedText={m.pendingCard.op_id
                            ? (m.pendingCard.status === 'rejected' ? '❌ 已拒绝' : '✅ 已通过')
                            : undefined}
                        />
                      </div>
                    )}
                  </div>

                    {/* 操作栏 */}
                    {(isAssistant ? (hasContent || isStopped) : !!m.content) && (
                      <div className="flex items-center gap-3 mt-1.5 px-1">
                        <button
                          onClick={handleCopy}
                          className="text-muted-foreground/60 hover:text-muted-foreground transition-colors p-0.5 rounded"
                          title="复制"
                        >
                          {isCopied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
                        </button>
                        {hasContent && (
                          <button
                            onClick={() => {
                              const msgIdx = messages.findIndex(x => x.id === m.id);
                              const lastUserMsg = messages.slice(0, msgIdx).reverse().find(x => x.role === 'user');
                              if (lastUserMsg) sendMessage(lastUserMsg.content);
                            }}
                            className="p-1 rounded-md hover:bg-muted text-muted-foreground/60 hover:text-muted-foreground transition-colors"
                            title="重新生成"
                          >
                            <RefreshCcw className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {isUser && (
                          editingMsgId === m.id ? (
                            <div className="flex items-center gap-1">
                              <textarea
                                autoFocus
                                value={editingContent}
                                onChange={e => {
                                  setEditingContent(e.target.value);
                                  const el = e.target;
                                  el.style.height = 'auto';
                                  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
                                }}
                                onKeyDown={e => {
                                  if (e.key === 'Enter' && !e.shiftKey) {
                                    e.preventDefault();
                                    if (editingContent.trim()) {
                                      sendMessage(editingContent.trim());
                                      setEditingMsgId(null);
                                      setEditingContent('');
                                    }
                                  }
                                  if (e.key === 'Escape') {
                                    setEditingMsgId(null);
                                    setEditingContent('');
                                  }
                                }}
                                className="w-full min-h-[36px] max-h-[120px] resize-none rounded-lg border border-primary/30 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                                rows={1}
                              />
                              <button
                                onClick={() => {
                                  if (editingContent.trim()) {
                                    sendMessage(editingContent.trim());
                                    setEditingMsgId(null);
                                    setEditingContent('');
                                  }
                                }}
                                className="p-1 rounded hover:bg-primary/20 text-green-500"
                                title="发送编辑"
                              >
                                <Check className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => { setEditingMsgId(null); setEditingContent(''); }}
                                className="p-1 rounded hover:bg-muted text-muted-foreground"
                                title="取消"
                              >
                                <X className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => { setEditingMsgId(m.id); setEditingContent(m.content); }}
                              className="p-1 rounded-md hover:bg-primary/20 text-muted-foreground/60 hover:text-muted-foreground transition-colors"
                              title="编辑"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                          )
                        )}
                        <div className="flex-1" />
                        {isAssistant && m.source === 'cursor' && (
                          <span className="text-[11px] text-muted-foreground/70 select-none">🔬 Cursor SDK</span>
                        )}
                        {isAssistant && m.source === 'deepseek' && (
                          <span className="text-[11px] text-muted-foreground/70 select-none">🐰 DeepSeek</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })
            )}

            {/* ── Jira 搜索补充卡 ── */}
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
          <div className="p-4 bg-background/60 backdrop-blur-sm border-t border-border flex-shrink-0 flex flex-col gap-1 max-w-4xl mx-auto w-full relative">
            {showCommands && <CommandPanel filterText={commandFilter} selectedIndex={selectedCmdIndex} onSelect={handleSelectCommand} />}
            <div className="flex items-center gap-2 w-full relative">
              {/* 输入框包裹层（内含浮动 Settings 图标） */}
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={myInput}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder="输入分析指令，或键入 / 呼出模板..." rows={1}
                  className="w-full max-h-48 min-h-[56px] resize-none rounded-xl border border-input bg-background/50 backdrop-blur-sm px-4 py-4 pr-12 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-sm"
                />
                <button
                  onClick={() => setShowCursorSettings(true)}
                  className="absolute right-3 top-4 p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                  title="引擎设置"
                >
                  <Settings size={16} />
                </button>
              </div>
              {/* 停止 + 发送 并排 */}
              <div className="flex items-center gap-1 shrink-0">
                {isGenerating && (
                  <Button variant="ghost" size="sm" onClick={stopGenerating}
                    className="h-10 w-10 p-0 text-destructive hover:text-destructive/70 rounded-lg" title="停止生成">
                    <Square size={16} />
                  </Button>
                )}
                <Button onClick={handleSend}
                  disabled={isGenerating || !myInput || myInput.trim() === ''}
                  className="h-12 w-12 shrink-0 rounded-xl shadow-md">
                  <svg className="w-5 h-5 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
                  </svg>
                </Button>
              </div>
            </div>
            {/* 引擎标签在输入框下方 */}
            <div className="flex items-center gap-1">
              <EnginePicker
                compact
                onOpenSettings={() => setShowCursorSettings(true)}
                onEngineChange={(engine, mode) => {
                  setCurrentEngine(engine);
                  setCurrentCursorMode(mode || '');
                  if (engine === 'cursor') {
                    const cfg = JSON.parse(localStorage.getItem('alice_cursor_config') || '{}');
                    if (cfg.model) setCursorModelName(cfg.model);
                    if (cfg.key) {
                      fetch(`/v1/admin/cursor-sdk/models?api_key=${encodeURIComponent(cfg.key)}`)
                        .then((r) => r.json())
                        .then((d) => { if (d.ok && d.models?.length) setCursorAvailableModels(d.models.map((m: any) => m.id)); })
                        .catch(() => {});
                    }
                  }
                }}
              />
              {currentEngine !== 'auto' && (
                <ModelPicker
                  engine={currentEngine}
                  cursorMode={currentCursorMode}
                  deepseekModel={deepseekModelName}
                  cursorModel={cursorModelName}
                  cursorAvailableModels={cursorAvailableModels}
                  onModelChange={(model) => setCursorModelName(model)}
                />
              )}
            </div>
          </div>
        </main>
        <RightPanel />

        {/* 审批中心 — 右侧固定面板 */}
        {approvalPanelOpen && (
          <aside className="w-[380px] border-l border-border bg-background flex flex-col transition-all duration-200 overflow-hidden shrink-0">
            <div className="h-16 border-b border-border flex items-center justify-between px-4 shrink-0 bg-muted/10">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-primary" />
                <h2 className="text-sm font-semibold">审批中心</h2>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setApprovalPanelOpen(false)} className="h-8 w-8">
                <X size={16} />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <OperationsConsole
                embedded
                onBack={() => setApprovalPanelOpen(false)}
              />
            </div>
          </aside>
        )}
        </>
      </div>
      <CursorSettings open={showCursorSettings} onClose={() => setShowCursorSettings(false)} />
    </ThemeProvider>
  );
};

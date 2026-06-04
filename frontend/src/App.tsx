import React, { useEffect, useState, useRef } from 'react';
import { COMMANDS, type Command } from '@/store/useChatStore';
import { useSessionStore, type ChatMessage } from '@/store/useSessionStore';
import { Header } from '@/Header';
import { Sidebar } from '@/Sidebar';
import { RightPanel } from '@/RightPanel';
import { Button } from '@/components/ui/button';
import { CommandPanel } from '@/components/CommandPanel';
import ConfirmCard from '@/components/ConfirmCard';
import { ChatList } from '@lobehub/ui/chat';
import { ThemeProvider } from '@lobehub/ui';
import { Square } from 'lucide-react';

export const App: React.FC = () => {
  // ═══ 所有 Hook 必须在最顶层，无条件调用 ═══
  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeId);
  const updateMessages = useSessionStore((s) => s.updateMessages);

  // ── 消息数据流：直接从 Zustand 状态机读取，不经过任何中间 SDK ──
  const currentSession = sessions?.find((s) => s.id === activeId);
  const messages: ChatMessage[] = currentSession?.messages || [];

  // ── 本地引擎状态：UI 与网络彻底解耦 ──
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── UI 状态与发送引擎彻底解耦 ──
  const [myInput, setMyInput] = useState('');

  const isGenerating = isLoading;
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [selectedCmdIndex, setSelectedCmdIndex] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);

  useEffect(() => {
    if (isGenerating && userScrolledUp) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating, userScrolledUp]);

  const handleChatScroll = () => {
    if (!chatContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
    setUserScrolledUp((scrollHeight - scrollTop - clientHeight > 80) && isGenerating);
  };

  // ── 原生 fetch + SSE 流式引擎（零中间 SDK）──
  const doSendMessage = async () => {
    if (!myInput || myInput.trim() === '' || isLoading || !activeId) return;

    const text = myInput;
    console.log('📤 准备发送的用户消息内容:', text);
    setMyInput('');      // 1. UI 瞬间清空
    setError(null);
    setIsLoading(true);

    // 2. 先斩后奏：用户消息立即上屏
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: text };
    const withUser = [...messages, userMsg];
    updateMessages(activeId, withUser);

    // 3. 预创建 AI 气泡空壳
    const aiMsgId = (Date.now() + 1).toString();
    const withAi = [...withUser, { id: aiMsgId, role: 'assistant' as const, content: '' }];
    updateMessages(activeId, withAi);

    // 4. AbortController 用于停止
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: withUser.map(m => ({ role: m.role, content: m.content })),
          config: {}
        }),
        signal: ctrl.signal
      });

      if (!res.ok) { setError(`HTTP ${res.status}`); return; }
      if (!res.body) { setError('ReadableStream 不可用'); return; }

      // 5. SSE 逐行解析 — 严谨提取 content，错误隔离
      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let aiContent = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.trim() === '' || !line.startsWith('data: ')) continue;
          if (line.includes('[DONE]')) continue;

          try {
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;

            const data = JSON.parse(jsonStr);

            // 1. 提取大模型回复文本
            if (data.choices && data.choices[0]?.delta?.content) {
              aiContent += data.choices[0].delta.content;
            }

            // 2. Agent 状态日志
            if (data.custom_type === 'agent_step') {
              console.log(`🤖 Agent 思考中: 步骤 ${data.step}/${data.max_steps}`);
            }

            // 3. 实时更新气泡
            useSessionStore.getState().updateMessages(activeId, [
              ...withUser,
              { id: aiMsgId, role: 'assistant' as const, content: aiContent }
            ]);

          } catch {
            // 非标准 JSON / 截断数据 → 静默跳过，不污染 UI
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return; // 用户主动停止，不报错
      setError(err.message || String(err));
    } finally {
      setIsLoading(false);
      abortRef.current = null;
    }
  };

  const stopGeneration = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsLoading(false);
  };

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

  console.log('📊 喂给 ChatList 的全量数据:', messages);

  return (
    <ThemeProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0 bg-muted/10 relative border-r border-border">
          <Header />
          <div ref={chatContainerRef} onScroll={handleChatScroll} className="flex-1 overflow-y-auto p-4 md:p-6">
            <ChatList
              data={messages.map(m => ({
                id: String(m.id || Date.now()),
                role: m.role || 'user',
                content: m.content || '',
                meta: {
                  title: m.role === 'user' ? '用户' : 'Alice',
                  avatar: m.role === 'user' ? '🧑‍💻' : '🐰'
                }
              })) as any}
            />
            {isGenerating && <span className="blinking-cursor" />}
            <div ref={messagesEndRef} className="h-1" />
          </div>

          {/* ── LobeUI 恢复：UI 状态与引擎已解耦，绑定到 myInput ── */}
          <div className="p-4 bg-background border-t border-border flex-shrink-0 flex flex-col gap-2 relative">
            {/* 错误守卫 — 暴露网络死因 */}
            {error && <div className="text-red-500 text-xs mb-1 px-1">后端通信异常: {error}</div>}

            <div className="flex justify-center gap-2 mb-2">
              {isGenerating && (
                <Button variant="ghost" size="sm" onClick={stopGeneration} className="text-red-500 hover:text-red-700 text-xs gap-1">
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
              <Button onClick={doSendMessage}
                disabled={isLoading || !myInput || myInput.trim() === ''} className="h-12 w-12 shrink-0 rounded-xl shadow-md">
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

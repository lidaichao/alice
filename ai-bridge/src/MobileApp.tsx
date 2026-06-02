import React, { useEffect, useState, useRef } from 'react';
import { useChatStore, AGENTS } from '@/store/useChatStore';
import { Button } from '@/components/ui/button';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { Send, Plus, Menu, User as UserIcon, ChevronLeft } from 'lucide-react';

export const MobileApp: React.FC = () => {
  const initDB = useChatStore((s) => s.initDB);
  const loadMemories = useChatStore((s) => s.loadMemories);
  const isDbLoaded = useChatStore((s) => s.isDbLoaded);
  const sessions = useChatStore((s) => s.sessions);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const setActiveSession = useChatStore((s) => s.setActiveSession);
  const addSession = useChatStore((s) => s.addSession);
  const sendMessage = useChatStore((s) => s.sendMessage);
  const isGenerating = useChatStore((s) => s.isGenerating);
  const stopGenerating = useChatStore((s) => s.stopGenerating);

  const [input, setInput] = useState('');
  const [showDrawer, setShowDrawer] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find(s => s.id === activeSessionId);
  const agent = AGENTS.find(a => a.id === activeSession?.agentId) || AGENTS[0];

  useEffect(() => { initDB(); loadMemories(); }, [initDB, loadMemories]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages]);

  const handleSend = () => {
    if (!input.trim() || isGenerating) return;
    sendMessage(input); setInput('');
  };

  if (!isDbLoaded) {
    return <div className="h-screen flex items-center justify-center text-muted-foreground">加载中...</div>;
  }

  return (
    <div className="flex flex-col h-[100dvh] bg-background text-foreground">
      {/* Header */}
      <header className="h-14 shrink-0 flex items-center justify-between px-4 border-b border-border bg-background/95 backdrop-blur-sm">
        <button onClick={() => setShowDrawer(true)} className="p-1.5 -ml-1 rounded-md hover:bg-muted">
          <Menu size={20} />
        </button>
        <div className="text-sm font-semibold truncate mx-2">{activeSession?.title || 'Alice'}</div>
        <button onClick={() => addSession()} className="p-1.5 -mr-1 rounded-md hover:bg-muted text-primary">
          <Plus size={20} />
        </button>
      </header>

      {/* Sidebar Drawer */}
      {showDrawer && (
        <div className="fixed inset-0 z-50 flex" onClick={() => setShowDrawer(false)}>
          <div className="absolute inset-0 bg-black/40" />
          <div className="relative w-72 max-w-[80vw] bg-background border-r border-border h-full animate-in slide-in-from-left" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 p-4 border-b border-border">
              <span className="text-xl">⚛️</span>
              <span className="font-semibold">Alice</span>
            </div>
            <div className="overflow-y-auto h-[calc(100%-60px)] p-2 space-y-1">
              {sessions.map(s => {
                const a = AGENTS.find(x => x.id === s.agentId) || AGENTS[0];
                return (
                  <div key={s.id} onClick={() => { setActiveSession(s.id); setShowDrawer(false); }}
                    className={`px-3 py-2.5 rounded-md cursor-pointer text-sm flex items-center gap-2 ${s.id === activeSessionId ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground'}`}>
                    <span>{a.avatar}</span><span className="truncate">{s.title}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {!activeSession?.messages.length ? (
          <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
            <span className="text-3xl mb-2">⚛️</span>
            <p className="text-sm">有什么可以帮你的？</p>
          </div>
        ) : (
          activeSession.messages.map(msg => (
            <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[90%] rounded-xl px-4 py-2.5 text-sm ${msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-foreground'}`}>
                {msg.content.includes('\n\n[图片说明]:') ? (
                  <div className="whitespace-pre-wrap">{msg.content.split('\n\n[图片说明]:')[1]}</div>
                ) : msg.role === 'assistant' && msg.content ? (
                  <MarkdownRenderer content={msg.content} citations={msg.citations} />
                ) : msg.content === '' && msg.role === 'assistant' && isGenerating ? (
                  <span className="flex gap-1"><span className="animate-bounce">●</span><span className="animate-bounce delay-75">●</span><span className="animate-bounce delay-150">●</span></span>
                ) : (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-border p-3 bg-background">
        <form onSubmit={e => { e.preventDefault(); handleSend(); }} className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="输入消息..."
            className="flex-1 py-2.5 px-4 rounded-xl border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          {isGenerating ? (
            <Button type="button" variant="outline" size="icon" onClick={stopGenerating} className="h-11 w-11 rounded-xl shrink-0">■</Button>
          ) : (
            <Button type="submit" size="icon" disabled={!input.trim()} className="h-11 w-11 rounded-xl shrink-0">
              <Send size={18} />
            </Button>
          )}
        </form>
      </div>
    </div>
  );
};

import React, { useEffect, useState, useRef } from 'react';
import { useChatStore, COMMANDS, type Command } from '@/store/useChatStore';
import { Header } from '@/Header';
import { Sidebar } from '@/Sidebar';
import { RightPanel } from '@/RightPanel';
import { Button } from '@/components/ui/button';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { CommandPanel } from '@/components/CommandPanel';
import { Loader2, CheckCircle2, Blocks, Image as ImageIcon, X, Paperclip, Copy, Trash2 } from 'lucide-react';

export const App: React.FC = () => {
  const initDB = useChatStore((state) => state.initDB);
  const isDbLoaded = useChatStore((state) => state.isDbLoaded);
  const sessions = useChatStore((state) => state.sessions);
  const activeSessionId = useChatStore((state) => state.activeSessionId);
  const sendMessage = useChatStore((state) => state.sendMessage);
  const isGenerating = useChatStore((state) => state.isGenerating);
  const stopGenerating = useChatStore((state) => state.stopGenerating);
  const deleteMessage = useChatStore((state) => state.deleteMessage);
  const loadMemories = useChatStore((state) => state.loadMemories);

  const [input, setInput] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [attachedImage, setAttachedImage] = useState<string | null>(null);
  const [showCommands, setShowCommands] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [selectedCmdIndex, setSelectedCmdIndex] = useState(0);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeSession = sessions.find(s => s.id === activeSessionId);

  useEffect(() => {
    initDB();
    loadMemories();
  }, [initDB, loadMemories]);

  useEffect(() => {
    setInput('');
    setAttachedImage(null);
  }, [activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeSession?.messages]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const processFile = (file: File) => {
    if (!file.type.startsWith("image/")) {
      alert("当前版本仅支持多模态图片感知 (.png, .jpg, .jpeg)，更多格式扩展中！");
      return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
      if (event.target?.result) {
        setAttachedImage(event.target.result as string);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const handleSend = () => {
    if (!input.trim() && !attachedImage) return;
    if (isGenerating) return;
    
    sendMessage(input, attachedImage || undefined);
    setInput('');
    setAttachedImage(null);
  };

  const filteredCmds = COMMANDS.filter(cmd => 
    cmd.key.toLowerCase().includes(commandFilter.toLowerCase()) ||
    cmd.label.toLowerCase().includes(commandFilter.toLowerCase())
  );

  const handleSelectCommand = (cmd: Command) => {
    setInput(cmd.template);
    setShowCommands(false);
    setSelectedCmdIndex(0);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setInput(val);

    if (val.endsWith('/')) {
      setShowCommands(true);
      setCommandFilter('');
      setSelectedCmdIndex(0);
    } else if (showCommands) {
      const lastSlashIndex = val.lastIndexOf('/');
      if (lastSlashIndex !== -1) {
        const searchTxt = val.slice(lastSlashIndex + 1);
        if (searchTxt.includes(' ')) {
          setShowCommands(false);
        } else {
          setCommandFilter(searchTxt);
          setSelectedCmdIndex(0);
        }
      } else {
        setShowCommands(false);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showCommands && filteredCmds.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedCmdIndex(prev => (prev + 1) % filteredCmds.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedCmdIndex(prev => (prev - 1 + filteredCmds.length) % filteredCmds.length);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSelectCommand(filteredCmds[selectedCmdIndex]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowCommands(false);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isDbLoaded) {
    return <div className="h-screen w-screen flex items-center justify-center text-muted-foreground">加载会话中...</div>;
  }

  return (
    <div 
      className="flex h-screen w-screen overflow-hidden bg-background text-foreground"
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
    >
      <Sidebar />

      <main className="flex-1 flex flex-col min-w-0 bg-muted/10 relative border-r border-border">
        <Header />
        
        {dragActive && (
          <div className="absolute inset-0 bg-primary/10 border-4 border-dashed border-primary z-50 flex flex-col items-center justify-center backdrop-blur-sm pointer-events-none transition-all">
            <div className="bg-background p-6 rounded-2xl shadow-xl border border-border flex flex-col items-center gap-3">
              <ImageIcon className="w-12 h-12 text-primary animate-bounce" />
              <p className="font-semibold text-base">释放文件以导入图片感知</p>
              <p className="text-xs text-muted-foreground">支持 PNG, JPG, JPEG 等研发截图</p>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
          {!activeSession?.messages.length ? (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-70">
              <span className="text-4xl mb-4">⚛️</span>
              <p className="font-medium">爱丽丝研发中枢 (多模态感知已激活)</p>
              <p className="text-xs text-muted-foreground mt-1">支持拖拽缺陷截图、日志、设计稿进行跨系统分析</p>
            </div>
          ) : (
            activeSession.messages.map((msg, idx) => {
              const isLast = idx === activeSession.messages.length - 1;
              const isEmpty = !msg.content || msg.content.trim() === '';
              return (
              <div key={msg.id} className={`flex w-full group ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-2xl px-5 py-3 relative ${
                  msg.role === 'user' 
                    ? 'bg-primary text-primary-foreground rounded-tr-sm shadow-md' 
                    : 'bg-background border border-border text-foreground rounded-tl-sm shadow-sm'
                }`}>
                  {msg.role === 'user' && msg.content.startsWith('data:image') && (
                    <div className="mb-2 rounded-lg overflow-hidden border border-border/20 max-w-sm max-h-48">
                      <img src={msg.content.split('\n\n[图片说明]:')[0]} alt="Uploaded" className="w-full h-full object-cover" />
                    </div>
                  )}

                  <div className="text-[15px] break-words">
                    {msg.plugin && (() => {
                      const isActuallyRunning = isGenerating && isLast && msg.plugin.status === 'running';
                      return (
                      <div className="mb-3 flex items-center gap-3 p-2.5 rounded-lg border border-border bg-muted/30 text-sm w-fit">
                        {isActuallyRunning ? (
                          <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                        ) : (
                          <CheckCircle2 className="w-4 h-4 text-green-500" />
                        )}
                        <span className="font-medium text-foreground">
                          {isActuallyRunning ? '正在检索并读取数据...' : '插件执行完毕'}
                        </span>
                        <span className="text-muted-foreground font-mono text-[11px] bg-background px-1.5 py-0.5 rounded shadow-sm border border-border flex items-center gap-1">
                          <Blocks size={12} />
                          {msg.plugin.name === 'query_jira_issues' ? 'Jira System' : 'Knowledge Base'}
                        </span>
                      </div>
                      )})()}

                    {/* 思考中动画：仅最后一条 + 生成中 + 内容为空 */}
                    {isEmpty && msg.role === 'assistant' && isLast && isGenerating ? (
                      <span className="flex items-center gap-1 text-muted-foreground">
                        <span className="animate-bounce">●</span>
                        <span className="animate-bounce delay-75">●</span>
                        <span className="animate-bounce delay-150">●</span>
                        <span className="ml-2 text-sm">爱丽丝识别中...</span>
                      </span>
                    ) : isEmpty && msg.role === 'assistant' && !isGenerating ? (
                      /* 已停止生成占位符 */
                      <div className="text-gray-400 text-sm italic">[已停止生成]</div>
                    ) : (
                      msg.role === 'user' ? (
                        <div className="whitespace-pre-wrap leading-relaxed">
                          {msg.content.includes('\n\n[图片说明]:') ? msg.content.split('\n\n[图片说明]:')[1] : msg.content}
                        </div>
                    ) : (
                      <MarkdownRenderer content={msg.content} citations={msg.citations} />
                    )
                    )}
                  </div>

                  {/* hover 操作按钮：复制 + 删除 */}
                  <div className={`absolute -bottom-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ${
                    msg.role === 'user' ? '-left-16' : '-right-16'
                  }`}>
                    <button
                      onClick={() => navigator.clipboard.writeText(msg.content)}
                      className="p-1 rounded-md bg-background border border-border text-muted-foreground hover:text-foreground hover:border-primary/50 shadow-sm"
                      title="复制"
                    >
                      <Copy size={14} />
                    </button>
                    <button
                      onClick={() => deleteMessage(msg.id)}
                      className="p-1 rounded-md bg-background border border-border text-muted-foreground hover:text-red-500 hover:border-red-300 shadow-sm"
                      title="删除"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            )})
          )}
          <div ref={messagesEndRef} className="h-1" />
        </div>
        
        <div className="p-4 bg-background border-t border-border flex-shrink-0 flex flex-col gap-2 relative">
          {isGenerating && (
            <div className="absolute -top-12 left-1/2 -translate-x-1/2">
              <Button variant="outline" size="sm" onClick={stopGenerating} className="shadow-lg rounded-full bg-background">
                停止生成
              </Button>
            </div>
          )}

          {attachedImage && (
            <div className="max-w-4xl mx-auto w-full px-2">
              <div className="relative w-20 h-20 rounded-xl border border-border overflow-hidden group shadow-sm bg-muted">
                <img src={attachedImage} alt="Preview" className="w-full h-full object-cover" />
                <button 
                  onClick={() => setAttachedImage(null)}
                  className="absolute top-1 right-1 bg-black/50 text-white rounded-full p-0.5 hover:bg-black/70 transition-colors"
                >
                  <X size={12} />
                </button>
              </div>
            </div>
          )}

          <div className="flex items-end gap-3 max-w-4xl mx-auto w-full relative">
            {showCommands && (
              <CommandPanel filterText={commandFilter} selectedIndex={selectedCmdIndex} onSelect={handleSelectCommand} />
            )}
            <input type="file" ref={fileInputRef} onChange={handleFileChange} accept="image/*" className="hidden" />
            <Button type="button" variant="ghost" size="icon" onClick={() => fileInputRef.current?.click()} className="h-12 w-12 rounded-xl border border-input shadow-sm text-muted-foreground hover:text-foreground" title="上传截图">
              <Paperclip size={18} />
            </Button>

            <textarea
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="输入分析指令，或键入 / 呼出模板..."
              className="flex-1 max-h-48 min-h-[56px] resize-none rounded-xl border border-input bg-background px-4 py-4 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-sm"
              rows={1}
            />
            
            <Button 
              onClick={handleSend} 
              disabled={(!input.trim() && !attachedImage) || isGenerating}
              className="h-12 w-12 shrink-0 rounded-xl shadow-md"
            >
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

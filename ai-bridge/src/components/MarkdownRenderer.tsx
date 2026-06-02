import React, { useEffect, useRef, useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import mermaid from 'mermaid';
import { Check, Copy, FileText, ChevronDown, ChevronRight, Wrench, CheckSquare, Loader2 } from 'lucide-react';
import { useChatStore, Citation } from '@/store/useChatStore';

// ─── Thinking 折叠组件 ──────────────────────────
const ThinkingBlock = memo(({ content }: { content: string }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="my-3 border border-border/60 rounded-lg overflow-hidden bg-muted/20">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted/30 transition-colors">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>💭 思考过程</span>
        {!open && <span className="text-[10px] opacity-60 ml-2">{content.slice(0, 40)}...</span>}
      </button>
      {open && <div className="px-4 py-3 text-sm text-muted-foreground whitespace-pre-wrap border-t border-border/40 leading-relaxed">{content}</div>}
    </div>
  );
});

// ─── Tool 调用渲染组件 ──────────────────────────
const ToolCallBlock = memo(({ name, status, result }: { name: string; status: string; result?: string }) => {
  const isRunning = status === 'running';
  return (
    <div className="my-3 border border-blue-200/50 rounded-lg overflow-hidden bg-blue-50/30 dark:bg-blue-950/20">
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-medium">
        <Wrench size={14} className={isRunning ? 'text-blue-500 animate-spin' : 'text-green-500'} />
        <span className="text-blue-700 dark:text-blue-300">调用工具: {name}</span>
        <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${isRunning ? 'bg-blue-100 text-blue-600' : 'bg-green-100 text-green-600'}`}>
          {isRunning ? '执行中...' : '已完成'}
        </span>
      </div>
      {result && <div className="px-4 py-2 text-xs text-muted-foreground border-t border-blue-100/50 whitespace-pre-wrap leading-relaxed">{result}</div>}
    </div>
  );
});

// ─── Task 进度块组件 ────────────────────────────
const TaskBlock = memo(({ tasks }: { tasks: string[] }) => {
  const [done, setDone] = useState<Set<number>>(new Set());
  const toggle = (i: number) => {
    const next = new Set(done);
    next.has(i) ? next.delete(i) : next.add(i);
    setDone(next);
  };
  return (
    <div className="my-3 border border-border/60 rounded-lg overflow-hidden bg-muted/10">
      <div className="px-3 py-2 text-xs font-medium text-muted-foreground border-b border-border/40 flex items-center gap-1.5">
        <CheckSquare size={14} />
        <span>任务列表 ({done.size}/{tasks.length})</span>
      </div>
      <div className="p-2 space-y-1">
        {tasks.map((t, i) => (
          <button key={i} onClick={() => toggle(i)} className="w-full flex items-start gap-2 px-2 py-1.5 rounded text-sm text-left hover:bg-muted/30 transition-colors">
            <span className={`mt-0.5 shrink-0 w-4 h-4 rounded border flex items-center justify-center text-[10px] ${done.has(i) ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground/40'}`}>
              {done.has(i) ? '✓' : ''}
            </span>
            <span className={done.has(i) ? 'line-through text-muted-foreground' : 'text-foreground'}>{t}</span>
          </button>
        ))}
      </div>
    </div>
  );
});

// ─── Mermaid / 代码块 / Markdown 渲染 (保持不变) ──────
const MermaidBlock = ({ code }: { code: string }) => {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState(false);

  useEffect(() => {
    mermaid.initialize({ startOnLoad: false, theme: 'default' });
    const renderChart = async () => {
      try {
        setError(false);
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, code);
        setSvg(svg);
      } catch { setError(true); }
    };
    const timer = setTimeout(renderChart, 300);
    return () => clearTimeout(timer);
  }, [code]);

  if (error) return <div className="p-4 bg-red-50 text-red-500 rounded-md text-sm font-mono">{code}</div>;
  return svg ? <div dangerouslySetInnerHTML={{ __html: svg }} className="flex justify-center my-4 overflow-x-auto" /> : <div className="animate-pulse h-20 bg-muted/50 rounded my-4" />;
};

const CodeBlock = ({ inline, className, children, ...props }: any) => {
  const match = /language-(\w+)/.exec(className || '');
  const lang = match ? match[1] : '';
  const [copied, setCopied] = useState(false);
  const text = String(children).replace(/\n$/, '');

  if (inline) return <code className="bg-muted px-1.5 py-0.5 rounded-md text-[0.875em] text-primary" {...props}>{children}</code>;
  if (lang === 'mermaid') return <MermaidBlock code={text} />;

  return (
    <div className="relative group my-4 rounded-lg overflow-hidden bg-[#1E1E1E]">
      <div className="flex items-center justify-between px-4 py-1.5 bg-zinc-800/80 text-xs text-zinc-400">
        <span>{lang || 'text'}</span>
        <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }} className="hover:text-white transition-colors flex items-center gap-1.5">
          {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />} {copied ? '已复制' : '复制'}
        </button>
      </div>
      <SyntaxHighlighter style={vscDarkPlus as any} language={lang} PreTag="div" customStyle={{ margin: 0, borderRadius: '0 0 0.5rem 0.5rem' }}>{text}</SyntaxHighlighter>
    </div>
  );
};

// ─── 主渲染组件 (带三个插件) ────────────────────
export const MarkdownRenderer = memo(({ content, citations }: { content: string; citations?: Citation[] }) => {
  const setActiveCitation = useChatStore((s) => s.setActiveCitation);
  const activeCitation = useChatStore((s) => s.activeCitation);

  // 预处理：提取特殊块
  const thinkingRegex = /:::thinking\n([\s\S]*?):::/g;
  const toolRegex = /:::tool\s+(\w+)\s+(\w+)?\s*\n([\s\S]*?):::/g;
  const taskRegex = /:::tasks\n([\s\S]*?):::/g;

  let processedContent = content;

  // 第二道防泄漏：前端渲染层再次抹除底层标签
  if (/DSML|tool_calls|invoke|parameter/.test(processedContent)) {
    processedContent = processedContent
      .replace(/<\s*\|\s*\|\s*DSML\s*\|?\s*\|?\s*(?:tool_calls)?\s*>/gi, '')
      .replace(/<\s*\|?\s*DSML\s*\|?\s*>/gi, '')
      .replace(/<\s*\|?\s*tool_calls\s*\|?\s*>/gi, '')
      .replace(/<\/\s*\|?\s*tool_calls\s*\|?\s*>/gi, '')
      .replace(/<\s*\|?\s*invoke\s[^>]*>/gi, '')
      .replace(/<\s*\/\s*\|?\s*invoke\s*\|?\s*>/gi, '')
      .replace(/<\s*\|?\s*parameter\s[^>]*>/gi, '');
  }
  const thinkingBlocks: { matched: string; component: React.ReactNode }[] = [];
  const toolBlocks: { matched: string; component: React.ReactNode }[] = [];
  const taskBlocks: { matched: string; component: React.ReactNode }[] = [];

  let match;
  while ((match = thinkingRegex.exec(content)) !== null) {
    thinkingBlocks.push({ matched: match[0], component: <ThinkingBlock content={match[1].trim()} /> });
  }
  while ((match = toolRegex.exec(content)) !== null) {
    toolBlocks.push({ matched: match[0], component: <ToolCallBlock name={match[1]} status={match[2] || 'done'} result={match[3]?.trim() || undefined} /> });
  }
  while ((match = taskRegex.exec(content)) !== null) {
    const tasks = match[1].trim().split('\n').filter(Boolean).map(t => t.replace(/^[-*]\s*/, ''));
    taskBlocks.push({ matched: match[0], component: <TaskBlock tasks={tasks} /> });
  }

  // 移除特殊块，剩余为标准 Markdown
  let cleanContent = content;
  for (const b of [...thinkingBlocks, ...toolBlocks, ...taskBlocks]) {
    cleanContent = cleanContent.replace(b.matched, `<!-- BLOCK_${b.matched.slice(0,20)} -->`);
  }

  return (
    <div className="space-y-4">
      {thinkingBlocks.map((b, i) => <React.Fragment key={`think-${i}`}>{b.component}</React.Fragment>)}
      {toolBlocks.map((b, i) => <React.Fragment key={`tool-${i}`}>{b.component}</React.Fragment>)}
      {taskBlocks.map((b, i) => <React.Fragment key={`task-${i}`}>{b.component}</React.Fragment>)}

      <div className="prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:p-0">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          code: CodeBlock as any,
          table: ({node, ...props}) => <div className="overflow-x-auto"><table className="border-collapse border border-border w-full" {...props} /></div>,
          th: ({node, ...props}) => <th className="border border-border bg-muted/50 px-4 py-2 font-semibold text-left" {...props} />,
          td: ({node, ...props}) => <td className="border border-border px-4 py-2" {...props} />,
          a: ({node, ...props}) => <a className="text-blue-500 hover:underline cursor-pointer" target="_blank" rel="noreferrer" {...props} />,
        }}>
          {cleanContent}
        </ReactMarkdown>
      </div>

      {citations && citations.length > 0 && (
        <div className="mt-4 pt-3 border-t border-border/60 flex flex-wrap gap-2 items-center text-xs text-muted-foreground">
          <span className="font-medium">参考溯源:</span>
          {citations.map((cit) => (
            <button key={cit.index} onClick={() => setActiveCitation(cit)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border transition-all ${
                activeCitation?.index === cit.index && activeCitation?.title === cit.title
                  ? 'bg-primary/10 text-primary border-primary shadow-sm' : 'bg-muted/40 hover:bg-muted border-border text-foreground/80'
              }`}>
              <FileText size={12} />
              <span className="max-w-[120px] truncate">{cit.title}</span>
              <span className="bg-background px-1 rounded text-[10px] font-mono border border-border">[{cit.index}]</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

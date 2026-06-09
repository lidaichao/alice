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
        {!open && <span className="text-[11px] opacity-60 ml-2">{content.slice(0, 40)}...</span>}
      </button>
      {open && <div className="px-4 py-3 text-sm text-muted-foreground whitespace-pre-wrap border-t border-border/40 leading-relaxed">{content}</div>}
    </div>
  );
});

// ── 工具名 → 中文描述映射 ───────────────────
const TOOL_LABELS: Record<string, string> = {
  query_jira_metadata: '检索 Jira 任务元数据',
  query_jira_issues: '搜索 Jira 任务',
  search_jira_issues: '搜索 Jira 任务',
  get_issue_commits: '拉取代码提交记录',
  get_single_commit_diff: '解析代码变更差异',
  search_docs_catalog: '检索知识库文档',
  read_specific_doc: '细读关联文档',
  jira_test_connection: '测试 Jira 连通性',
  jira_list_projects: '列出 Jira 项目',
  jira_search: 'JQL 高级搜索',
  jira_my_open_issues: '查询我的未完成任务',
  jira_this_week_issues: '查询本周未完成任务',
  jira_get_issue: '获取任务详情',
  jira_get_commits: '获取关联提交',
  jira_get_svn_diff: '解析 SVN 代码差异',
};

const formatToolName = (raw: string): string => TOOL_LABELS[raw] || raw.replace(/_/g, ' ');

// ─── Tool 调用渲染组件 ──────────────────────────
const ToolCallBlock = memo(({ name, status, result }: { name: string; status: string; result?: string }) => {
  const isRunning = status === 'running';
  return (
    <div className="my-3 border border-blue-200/50 rounded-lg overflow-hidden bg-blue-50/30 dark:bg-blue-950/20">
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-medium">
        <Wrench size={14} className={isRunning ? 'text-blue-500 animate-spin' : 'text-green-500'} />
        <span className="text-blue-700 dark:text-blue-300">调用工具: {name}</span>
        <span className={`ml-auto text-[11px] px-1.5 py-0.5 rounded ${isRunning ? 'bg-blue-100 text-blue-600' : 'bg-green-100 text-green-600'}`}>
          {isRunning ? '执行中...' : '已完成'}
        </span>
      </div>
      {result && <div className="px-4 py-2 text-xs text-muted-foreground border-t border-blue-100/50 whitespace-pre-wrap leading-relaxed">{result}</div>}
    </div>
  );
});

// ─── SSE 插件状态卡片（极客化呼吸灯）────────────
export const PluginToolCard = memo(({ plugin }: { plugin?: { name: string; status: 'running' | 'done' } }) => {
  if (!plugin) return null;
  const isRunning = plugin.status === 'running';
  const label = formatToolName(plugin.name);

  return (
    <div className={`mb-4 rounded-xl border overflow-hidden transition-all duration-500 ${
      isRunning
        ? 'border-blue-400/40 bg-blue-50/40 dark:bg-blue-950/30 shadow-[0_0_16px_rgba(59,130,246,0.12)]'
        : 'border-emerald-400/30 bg-emerald-50/30 dark:bg-emerald-950/20'
    }`}>
      <div className="flex items-center gap-3 px-4 py-3">
        {/* 极客化旋转齿轮 / 完成标记 */}
        <div className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
          isRunning ? 'bg-blue-100 dark:bg-blue-900/50' : 'bg-emerald-100 dark:bg-emerald-900/50'
        }`}>
          {isRunning ? (
            <Loader2 size={18} className="text-blue-600 dark:text-blue-400 animate-spin" />
          ) : (
            <Check size={18} className="text-emerald-600 dark:text-emerald-400" />
          )}
        </div>

        {/* 文案 */}
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-medium leading-tight ${
            isRunning ? 'text-blue-800 dark:text-blue-200' : 'text-emerald-800 dark:text-emerald-200'
          }`}>
            {isRunning ? `🔍 正在穿透检索：${label}...` : `✓ ${label} 完成`}
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
            {isRunning ? '后端 Agent 正在执行，预计耗时 5-15 秒' : '结果已纳入上方分析'}
          </p>
        </div>

        {/* 状态胶囊 */}
        <span className={`shrink-0 text-[11px] px-2.5 py-1 rounded-full font-medium animate-in fade-in ${
          isRunning
            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800'
            : 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
        }`}>
          {isRunning ? '⌛ 执行中' : '✅ 已完成'}
        </span>
      </div>

      {/* 呼吸灯进度条（仅 running 时显示） */}
      {isRunning && (
        <div className="h-0.5 bg-blue-100 dark:bg-blue-900/50">
          <div className="h-full bg-gradient-to-r from-blue-400 via-blue-500 to-blue-400 animate-pulse w-2/3" />
        </div>
      )}
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
            <span className={`mt-0.5 shrink-0 w-4 h-4 rounded border flex items-center justify-center text-[11px] ${done.has(i) ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground/40'}`}>
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

  // 严格区分 inline vs block：
  // 1) react-markdown 传入 inline=true → 行内
  // 2) 无 language 且单行短文本 → 降级为行内（防误判为代码块）
  const isSingleLine = text.indexOf('\n') === -1;
  const isInline = inline || (!lang && isSingleLine && text.length < 200);

  if (isInline) {
    return (
      <code
        className="bg-rose-50 dark:bg-rose-950/30 text-rose-600 dark:text-rose-400 px-1.5 py-0.5 rounded text-[0.875em] font-mono break-all"
        {...props}
      >
        {children}
      </code>
    );
  }

  if (lang === 'mermaid') return <MermaidBlock code={text} />;

  return (
    <div className="relative group my-4 rounded-lg overflow-hidden bg-[#1E1E1E] border border-border/20">
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
export const MarkdownRenderer = memo(({ content, citations, plugin }: { content: string; citations?: Citation[]; plugin?: { name: string; status: 'running' | 'done' } }) => {
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

      <PluginToolCard plugin={plugin} />

      <div className="prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-pre:p-0">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
          code: CodeBlock as any,
          table: ({node, ...props}) => (
            <div className="overflow-x-auto my-4 rounded-lg border border-border">
              <table className="w-full text-sm" {...props} />
            </div>
          ),
          th: ({node, ...props}) => (
            <th className="border-b border-border bg-muted/60 px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider" {...props} />
          ),
          td: ({node, ...props}) => (
            <td className="border-b border-border/60 px-4 py-2.5 text-sm leading-relaxed" {...props} />
          ),
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
              <span className="bg-background px-1 rounded text-[11px] font-mono border border-border">[{cit.index}]</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

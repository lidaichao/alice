import React from 'react';
import { useChatStore } from '@/store/useChatStore';
import { Button } from '@/components/ui/button';
import { X, ExternalLink, Network } from 'lucide-react';

export const RightPanel: React.FC = () => {
  const isRightPanelOpen = useChatStore((state) => state.isRightPanelOpen);
  const toggleRightPanel = useChatStore((state) => state.toggleRightPanel);
  const activeCitation = useChatStore((state) => state.activeCitation);

  if (!isRightPanelOpen) return null;

  return (
    <aside className="w-80 border-l border-border bg-background flex flex-col transition-all duration-300 shadow-2xl z-20">
      <div className="h-16 border-b border-border flex items-center justify-between px-4 shrink-0 bg-muted/10">
        <h3 className="font-semibold text-foreground text-sm flex items-center gap-2">
          {activeCitation ? '📄 原始文献深度溯源' : '🔍 上下文流审查'}
        </h3>
        <Button variant="ghost" size="icon" onClick={toggleRightPanel} className="h-8 w-8 rounded-md">
          <X size={16} />
        </Button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
        {activeCitation ? (
          <div className="space-y-5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">
                {activeCitation.source} 节点
              </span>
              <span className="font-mono text-xs text-muted-foreground">
                索引编号: #{activeCitation.index}
              </span>
            </div>
            <h4 className="font-bold text-base text-foreground leading-snug">
              {activeCitation.title}
            </h4>
            <a 
              href={activeCitation.url} 
              target="_blank" 
              rel="noreferrer"
              className="flex items-center justify-center gap-2 w-full py-2 rounded-xl text-xs font-medium bg-muted hover:bg-primary hover:text-primary-foreground transition-all border border-border shadow-sm text-foreground"
            >
              打开外部集成原文 <ExternalLink size={12} />
            </a>
            <hr className="border-border/60" />
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground block">命中高亮摘要 (Matched Snippet):</label>
              <div className="p-4 rounded-xl bg-muted/40 border border-border/80 text-sm leading-relaxed text-foreground font-normal whitespace-pre-wrap relative italic">
                " {activeCitation.snippet} "
              </div>
            </div>
            <div className="text-[11px] text-muted-foreground bg-muted/30 p-3 rounded-lg border border-dashed border-border leading-normal">
              💡 提示：此片段是网关底层 RAG 机制根据你提问的向量相似度自动召回的。
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-muted-foreground opacity-60">
            <Network className="w-12 h-12 stroke-[1.5] text-muted-foreground mb-3" />
            <p className="text-sm font-medium text-foreground">暂无活跃溯源</p>
            <p className="text-xs mt-1 max-w-[200px] leading-relaxed">当你在对话中点击 AI 回复下方的【参考溯源】胶囊标签时，原文内容会在此同步呈现。</p>
          </div>
        )}
      </div>
    </aside>
  );
};

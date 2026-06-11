import React, { useState } from 'react';
import { Check, Play, X, ListChecks, Square, CheckSquare } from 'lucide-react';

interface PlanCardProps {
  steps: string[];
  onExecute: (selectedSteps: string[]) => void;
  onCancel: () => void;
}

const PlanCard: React.FC<PlanCardProps> = ({ steps, onExecute, onCancel }) => {
  const [selected, setSelected] = useState<Set<number>>(
    new Set(steps.map((_, i) => i))
  );

  const toggle = (i: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected((prev) =>
      prev.size === steps.length ? new Set() : new Set(steps.map((_, i) => i))
    );
  };

  const allSelected = selected.size === steps.length;

  return (
    <div className="my-4 rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      {/* 标题栏 */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-muted/30">
        <ListChecks size={16} className="text-primary" />
        <h3 className="text-sm font-semibold">📋 执行计划</h3>
        <span className="text-[11px] text-muted-foreground ml-auto">
          {selected.size}/{steps.length} 已选
        </span>
      </div>

      {/* 步骤列表 */}
      <div className="divide-y divide-border/50">
        {steps.map((step, i) => (
          <button
            key={i}
            onClick={() => toggle(i)}
            className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-muted/20 transition-colors"
          >
            <span className="mt-0.5 shrink-0 text-primary">
              {selected.has(i) ? (
                <CheckSquare size={16} />
              ) : (
                <Square size={16} className="text-muted-foreground" />
              )}
            </span>
            <div className="flex items-baseline gap-2 min-w-0">
              <span className="text-[11px] font-mono text-muted-foreground shrink-0">
                {String(i + 1).padStart(2, '0')}
              </span>
              <span className={`text-sm ${selected.has(i) ? 'text-foreground' : 'text-muted-foreground line-through'}`}>
                {step}
              </span>
            </div>
          </button>
        ))}
      </div>

      {/* 底部操作栏 */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-border bg-muted/10">
        <button
          onClick={() => onExecute(steps.filter((_, i) => selected.has(i)))}
          disabled={selected.size === 0}
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:pointer-events-none"
        >
          <Play size={13} />
          开始执行
        </button>
        <button
          onClick={toggleAll}
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-xs font-medium border border-border hover:bg-muted transition-colors"
        >
          {allSelected ? (
            <>
              <Square size={13} />
              全不选
            </>
          ) : (
            <>
              <CheckSquare size={13} />
              全选
            </>
          )}
        </button>
        <button
          onClick={onCancel}
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors ml-auto"
        >
          <X size={13} />
          取消
        </button>
      </div>
    </div>
  );
};

export default PlanCard;

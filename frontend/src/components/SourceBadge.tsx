import React from 'react';
import { FileText } from 'lucide-react';

interface Source {
  source: string;
  updated?: string;
  chunk?: string;
}

interface SourceBadgeProps {
  sources: Source[];
}

export const SourceBadge: React.FC<SourceBadgeProps> = ({ sources }) => {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      <span className="text-[11px] text-muted-foreground/70 mr-1 self-center">
        <FileText size={12} className="inline mr-0.5" />
        来源
      </span>
      {sources.map((src, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-blue-50 text-blue-700 border border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800"
          title={src.updated ? `更新于 ${src.updated}` : undefined}
        >
          {src.source}
          {src.updated && (
            <span className="text-[10px] opacity-70">{src.updated}</span>
          )}
        </span>
      ))}
    </div>
  );
};

export default SourceBadge;

import type { DraftCardItem } from '@/store/slices/chatSlice';

interface Props {
  items: DraftCardItem[];
  editable?: boolean;
  onChange?: (index: number, field: keyof DraftCardItem, value: string) => void;
}

export default function IssueDraftList({ items, editable, onChange }: Props) {
  if (!items.length) {
    return <p className="text-xs text-muted-foreground">（无待创建条目）</p>;
  }

  return (
    <ul className="space-y-2 max-h-56 overflow-y-auto pr-1">
      {items.map((it) => (
        <li
          key={it.index}
          className="rounded-md border border-border/60 bg-background/50 p-2 text-xs"
        >
          <div className="text-[11px] text-muted-foreground mb-1">#{it.index + 1}</div>
          {editable && onChange ? (
            <div className="space-y-1.5">
              <input
                className="w-full rounded border border-input bg-background px-2 py-1 text-xs"
                value={it.summary}
                onChange={(e) => onChange(it.index, 'summary', e.target.value)}
                placeholder="标题 summary"
              />
              <div className="flex gap-1">
                <input
                  className="w-16 rounded border border-input bg-background px-2 py-1 text-xs font-mono"
                  value={it.projectKey}
                  onChange={(e) => onChange(it.index, 'projectKey', e.target.value)}
                  placeholder="CT"
                />
                <input
                  className="flex-1 rounded border border-input bg-background px-2 py-1 text-xs"
                  value={it.issueType}
                  onChange={(e) => onChange(it.index, 'issueType', e.target.value)}
                  placeholder="Task"
                />
              </div>
            </div>
          ) : (
            <div>
              <span className="font-mono text-[11px] text-primary">{it.projectKey}</span>
              <span className="mx-1 text-muted-foreground">·</span>
              <span className="text-[11px] text-muted-foreground">{it.issueType}</span>
              <div className="mt-0.5 font-medium text-foreground">{it.summary}</div>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

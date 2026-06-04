import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { FileStack, Loader2 } from 'lucide-react';
import type { DraftCard as DraftCardType, DraftCardItem } from '@/store/slices/chatSlice';
import IssueDraftList from '@/components/IssueDraftList';

interface Props {
  draft: DraftCardType;
  onSubmit: (draftId: string, items: DraftCardItem[]) => Promise<void>;
  onCancel: (draftId: string) => Promise<void>;
}

export default function DraftCard({ draft, onSubmit, onCancel }: Props) {
  const [items, setItems] = useState<DraftCardItem[]>(() =>
    draft.items.map((it) => ({ ...it })),
  );
  const [warnings] = useState<string[]>(() => draft.warnings ?? []);
  const [loading, setLoading] = useState<'submit' | 'cancel' | null>(null);
  const [error, setError] = useState('');

  const handleChange = (index: number, field: keyof DraftCardItem, value: string) => {
    setItems((prev) =>
      prev.map((row) => (row.index === index ? { ...row, [field]: value } : row)),
    );
  };

  const handleSubmit = async () => {
    if (loading) return;
    setLoading('submit');
    setError('');
    try {
      await onSubmit(draft.draft_id, items);
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败');
    } finally {
      setLoading(null);
    }
  };

  const handleCancel = async () => {
    if (loading) return;
    setLoading('cancel');
    setError('');
    try {
      await onCancel(draft.draft_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : '取消失败');
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
      <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-300 mb-2">
        <FileStack className="w-4 h-4 shrink-0" />
        草稿箱 · {items.length} 条待创建任务
      </div>
      {draft.preview && (
        <p className="text-xs text-muted-foreground mb-2">{draft.preview}</p>
      )}
      <IssueDraftList items={items} editable onChange={handleChange} />
      {(warnings.length > 0) && (
        <ul className="mt-2 text-xs text-amber-700 dark:text-amber-300 list-disc pl-4">
          {warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
      <div className="flex gap-2 justify-end mt-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleCancel}
          disabled={loading !== null}
        >
          {loading === 'cancel' ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
          取消
        </Button>
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={loading !== null}
          className="bg-amber-600 hover:bg-amber-700 text-white"
        >
          {loading === 'submit' ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : null}
          提交草稿
        </Button>
      </div>
    </div>
  );
}

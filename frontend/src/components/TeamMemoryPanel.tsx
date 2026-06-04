import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { ChevronDown, ChevronUp, Loader2, Pencil, Plus, Trash2 } from 'lucide-react';

interface MemoryEntry {
  id: string;
  text: string;
  source?: string;
  created_at?: string;
}

interface MemoryMeta {
  count: number;
  inject_char_budget: number;
  inject_note?: string;
  truncation_warning?: string;
}

export const TeamMemoryPanel: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [meta, setMeta] = useState<MemoryMeta | null>(null);
  const [loading, setLoading] = useState(false);
  const [newText, setNewText] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/memory/entries');
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || '加载失败');
      setEntries(data.entries || []);
      setMeta(data.meta || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  const handleAdd = async () => {
    const text = newText.trim();
    if (!text) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/memory/entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || '新增失败');
      setNewText('');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '新增失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveEdit = async (id: string) => {
    const text = editText.trim();
    if (!text) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/memory/entries/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || '保存失败');
      setEditingId(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除这条团队规则？')) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/memory/entries/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || '删除失败');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border-t border-border shrink-0">
      <button
        type="button"
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-foreground hover:bg-muted/50"
        onClick={() => setOpen((v) => !v)}
      >
        <span>团队规则（服务端）</span>
        {open ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>
      {open && (
        <div className="px-3 pb-3 max-h-48 overflow-y-auto space-y-2">
          <p className="text-[10px] text-muted-foreground leading-snug">
            对话里「请记住」与此处同步；与浏览器本地记忆无关。
          </p>
          {meta && (
            <p className="text-[10px] text-muted-foreground">
              共 {meta.count} 条 · {meta.inject_note}
              {meta.truncation_warning ? ` · ${meta.truncation_warning}` : ''}
            </p>
          )}
          {error && <p className="text-[10px] text-destructive">{error}</p>}
          {loading && <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />}
          <div className="flex gap-1">
            <input
              className="flex-1 text-[11px] rounded border border-input bg-background px-2 py-1"
              placeholder="新增团队规则…"
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
            />
            <Button size="sm" variant="outline" className="h-7 px-2" onClick={handleAdd} disabled={loading}>
              <Plus size={12} />
            </Button>
          </div>
          {entries.map((e) => (
            <div key={e.id} className="group rounded border border-border/50 p-1.5">
              {editingId === e.id ? (
                <div className="space-y-1">
                  <textarea
                    className="w-full text-[11px] rounded border border-input p-1 min-h-[48px]"
                    value={editText}
                    onChange={(ev) => setEditText(ev.target.value)}
                  />
                  <div className="flex gap-1 justify-end">
                    <Button size="sm" variant="ghost" className="h-6 text-[10px]" onClick={() => setEditingId(null)}>
                      取消
                    </Button>
                    <Button size="sm" className="h-6 text-[10px]" onClick={() => handleSaveEdit(e.id)}>
                      保存
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-1 items-start">
                  <p className="flex-1 text-[11px] leading-snug text-foreground/90">{e.text}</p>
                  <button
                    type="button"
                    className="opacity-60 hover:opacity-100 p-0.5"
                    onClick={() => {
                      setEditingId(e.id);
                      setEditText(e.text);
                    }}
                  >
                    <Pencil size={10} />
                  </button>
                  <button
                    type="button"
                    className="opacity-60 hover:opacity-100 text-destructive p-0.5"
                    onClick={() => handleDelete(e.id)}
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
              )}
            </div>
          ))}
          {!loading && entries.length === 0 && (
            <p className="text-[10px] text-muted-foreground text-center py-2">暂无团队规则</p>
          )}
        </div>
      )}
    </div>
  );
};

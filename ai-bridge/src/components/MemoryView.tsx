import React, { useEffect } from 'react';
import { useChatStore } from '@/store/useChatStore';
import { MemoryLayer } from '@/lib/db';
import { Layers, Activity, User, BookOpen, Star, Lightbulb, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

const LAYER_ICON: Record<MemoryLayer, React.ReactNode> = {
  activity: <Activity size={14} />,
  identity: <User size={14} />,
  context: <BookOpen size={14} />,
  preference: <Star size={14} />,
  experience: <Lightbulb size={14} />,
};

const LAYER_COLOR: Record<MemoryLayer, string> = {
  activity: 'text-blue-500 bg-blue-50 dark:bg-blue-950',
  identity: 'text-purple-500 bg-purple-50 dark:bg-purple-950',
  context: 'text-green-500 bg-green-50 dark:bg-green-950',
  preference: 'text-amber-500 bg-amber-50 dark:bg-amber-950',
  experience: 'text-rose-500 bg-rose-50 dark:bg-rose-950',
};

const LAYER_LABELS: Record<MemoryLayer, string> = {
  activity: '活动记录',
  identity: '身份信息',
  context: '上下文',
  preference: '偏好设置',
  experience: '经验教训',
};

export const MemoryView: React.FC = () => {
  const memories = useChatStore(s => s.memories);
  const loadMemories = useChatStore(s => s.loadMemories);
  const memoryDbLoaded = useChatStore(s => s.memoryDbLoaded);
  const deleteMemory = useChatStore(s => s.deleteMemory);
  const clearMemories = useChatStore(s => s.clearMemories);

  useEffect(() => { if (!memoryDbLoaded) loadMemories(); }, [memoryDbLoaded, loadMemories]);

  const layers: MemoryLayer[] = ['identity', 'preference', 'context', 'experience', 'activity'];

  return (
    <div className="space-y-4 p-4 text-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold flex items-center gap-2"><Layers size={16} /> 五层记忆 ({memories.length})</h3>
        {memories.length > 0 && (
          <Button variant="ghost" size="sm" onClick={clearMemories} className="text-xs h-7 text-destructive">
            <Trash2 size={12} className="mr-1" /> 清空
          </Button>
        )}
      </div>

      {layers.map(layer => {
        const items = memories.filter(m => m.layer === layer);
        if (!items.length) return null;
        return (
          <div key={layer} className="space-y-1">
            <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium ${LAYER_COLOR[layer]}`}>
              {LAYER_ICON[layer]}
              <span>{LAYER_LABELS[layer]}</span>
              <span className="ml-auto opacity-60">{items.length}</span>
            </div>
            {items.slice(0, 5).map(m => (
              <div key={m.id} className="flex items-start gap-2 pl-6 group">
                <span className="text-[11px] text-muted-foreground leading-relaxed flex-1 truncate">{m.content}</span>
                <button onClick={() => deleteMemory(m.id)} className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive shrink-0 mt-0.5">
                  <Trash2 size={10} />
                </button>
              </div>
            ))}
          </div>
        );
      })}

      {!memories.length && (
        <div className="text-xs text-muted-foreground text-center py-6">
          <Layers size={24} className="mx-auto mb-2 opacity-30" />
          <p>记忆为空</p>
          <p className="mt-1 opacity-60">对话完成后自动从5个维度提取记忆</p>
        </div>
      )}
    </div>
  );
};

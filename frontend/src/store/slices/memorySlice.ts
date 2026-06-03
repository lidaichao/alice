import { StateCreator } from 'zustand';
import { MemoryEntry, MemoryLayer, db } from '@/lib/db';

export interface MemorySlice {
  memories: MemoryEntry[];
  memoryDbLoaded: boolean;

  loadMemories: () => Promise<void>;
  addMemory: (entry: Omit<MemoryEntry, 'id'>) => Promise<void>;
  deleteMemory: (id: string) => Promise<void>;
  clearMemories: () => Promise<void>;
  getMemoriesByLayer: (layer: MemoryLayer) => MemoryEntry[];
  getMemoriesByCategory: (category: string) => MemoryEntry[];

  // 5层记忆提取辅助
  extractMemories: (messages: { role: string; content: string }[]) => Promise<void>;
}

const LAYER_ORDER: MemoryLayer[] = ['activity', 'identity', 'context', 'preference', 'experience'];

const LAYER_LABELS: Record<MemoryLayer, string> = {
  activity: '📋 活动记录',
  identity: '👤 身份信息',
  context: '📚 上下文',
  preference: '⭐ 偏好设置',
  experience: '💡 经验教训',
};

export const createMemorySlice: StateCreator<MemorySlice, [], [], MemorySlice> = (set, get) => ({
  memories: [],
  memoryDbLoaded: false,

  loadMemories: async () => {
    const all = await db.memories.orderBy('timestamp').reverse().toArray();
    set({ memories: all, memoryDbLoaded: true });
  },

  addMemory: async (entry) => {
    const newEntry: MemoryEntry = { ...entry, id: `mem-${Date.now()}` };
    await db.memories.add(newEntry);
    set((state) => ({ memories: [newEntry, ...state.memories] }));
  },

  deleteMemory: async (id) => {
    await db.memories.delete(id);
    set((state) => ({ memories: state.memories.filter(m => m.id !== id) }));
  },

  clearMemories: async () => {
    await db.memories.clear();
    set({ memories: [] });
  },

  getMemoriesByLayer: (layer) => get().memories.filter(m => m.layer === layer),
  getMemoriesByCategory: (category) => get().memories.filter(m => m.category === category),

  // 5层记忆提取 (基于对话内容)
  extractMemories: async (messages) => {
    const userMessages = messages.filter(m => m.role === 'user');
    if (!userMessages.length) return;

    const lastMsg = userMessages[userMessages.length - 1].content;
    const combined = userMessages.map(m => m.content).join('\n');

    // 活动层: 记录用户做了什么
    if (lastMsg.length > 10) {
      await get().addMemory({
        layer: 'activity', category: 'chat', source: 'conversation',
        content: `用户提问: ${lastMsg.slice(0, 200)}`, timestamp: Date.now(), confidence: 0.7,
      });
    }

    // 身份层: 检测角色关键词
    const identityPatterns = [
      { key: 'role', pattern: /(开发|前端|后端|测试|PM|产品|设计|运维|DBA|架构)/, content: '' },
      { key: 'project', pattern: /(项目|team|团队|Jira|迭代|sprint)/, content: '' },
    ];
    for (const p of identityPatterns) {
      const m = combined.match(p.pattern);
      if (m) {
        const existing = get().memories.filter(e => e.layer === 'identity' && e.key === p.key);
        if (!existing.length) {
          await get().addMemory({
            layer: 'identity', category: 'role', source: 'detected',
            content: m[0], key: p.key, timestamp: Date.now(), confidence: 0.6,
          });
        }
      }
    }

    // 上下文层: 保存技术栈和框架偏好
    const contextPatterns = [
      { key: 'tech_stack', pattern: /(React|Vue|Python|Java|Node|Go|Rust|TypeScript)/g },
      { key: 'domain', pattern: /(游戏|game|渲染|render|性能|performance|SQL|数据库)/g },
    ];
    for (const p of contextPatterns) {
      for (const m of combined.matchAll(p.pattern)) {
        const existing = get().memories.filter(e => e.layer === 'context' && e.key === p.key && e.content === m[0]);
        if (!existing.length) {
          await get().addMemory({
            layer: 'context', category: 'knowledge', source: 'detected',
            content: m[0], key: p.key, timestamp: Date.now(), confidence: 0.7,
          });
        }
      }
    }

    // 偏好层: 检测用户偏好关键词
    const prefPatterns = [
      { key: 'format', pattern: /(表格|列表|markdown|json|详细|简洁|brief|summary)/, content: '' },
    ];
    for (const p of prefPatterns) {
      const m = combined.match(p.pattern);
      if (m) {
        await get().addMemory({
          layer: 'preference', category: 'format', source: 'detected',
          content: `偏好输出格式: ${m[0]}`, key: p.key, timestamp: Date.now(), confidence: 0.5,
        });
      }
    }

    // 经验层: 保存问题-解决方案对
    if (lastMsg.includes('解决') || lastMsg.includes('修复') || lastMsg.includes('搞定')) {
      await get().addMemory({
        layer: 'experience', category: 'lesson', source: 'conversation',
        content: lastMsg.slice(0, 300), timestamp: Date.now(), confidence: 0.6,
      });
    }
  },
});

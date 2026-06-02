import { StateCreator } from 'zustand';
import { Message, Session } from '../useChatStore';
import { db } from '@/lib/db';
import { AGENTS } from '../useChatStore';

export interface ChatSlice {
  sessions: Session[];
  activeSessionId: string | null;
  isDbLoaded: boolean;
  isGenerating: boolean;
  abortController: AbortController | null;

  initDB: () => Promise<void>;
  setActiveSession: (id: string) => void;
  clearAllSessions: () => Promise<void>;
  stopGenerating: () => void;
  sendMessage: (content: string, imageBase64?: string) => Promise<void>;

  renameSession: (id: string, newTitle: string) => Promise<void>;
  togglePinSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  deleteMessage: (messageId: string) => Promise<void>;
}

export const createChatSlice: StateCreator<ChatSlice, [], [], ChatSlice> = (set, get) => ({
  sessions: [],
  activeSessionId: null,
  isDbLoaded: false,
  isGenerating: false,
  abortController: null,

  initDB: async () => {
    try {
      const [allSessions, myAgents] = await Promise.all([
        db.sessions.orderBy('updatedAt').reverse().toArray(),
        db.customAgents.toArray(),
      ]);
      set({
        sessions: allSessions.map(s => ({ ...s, agentId: s.agentId || 'default' })),
        customAgents: myAgents,
        activeSessionId: allSessions.length > 0 ? allSessions[0].id : null,
        isDbLoaded: true
      });
    } catch (error) {
      set({ isDbLoaded: true });
    }
  },

  renameSession: async (id, newTitle) => {
    set((state) => ({
      sessions: state.sessions.map(s => s.id === id ? { ...s, title: newTitle, updatedAt: Date.now() } : s)
    }));
    const updated = get().sessions.find(s => s.id === id);
    if (updated) await db.sessions.put(updated);
  },

  togglePinSession: async (id) => {
    set((state) => ({
      sessions: state.sessions.map(s => s.id === id ? { ...s, isPinned: !s.isPinned } : s)
    }));
    const updated = get().sessions.find(s => s.id === id);
    if (updated) await db.sessions.put(updated);
  },

  deleteSession: async (id) => {
    await db.sessions.delete(id);
    set((state) => {
      const nextSessions = state.sessions.filter(s => s.id !== id);
      let nextActiveId = state.activeSessionId;
      if (state.activeSessionId === id) {
        nextActiveId = nextSessions.length > 0 ? nextSessions[0].id : null;
      }
      return { sessions: nextSessions, activeSessionId: nextActiveId };
    });
  },

  deleteMessage: async (messageId) => {
    const state = get();
    const session = state.sessions.find(s => s.id === state.activeSessionId);
    if (!session) return;
    const updated = session.messages.filter(m => m.id !== messageId);
    await db.sessions.update(state.activeSessionId!, { messages: updated });
    set((s) => ({
      sessions: s.sessions.map(ss =>
        ss.id === state.activeSessionId ? { ...ss, messages: updated } : ss
      )
    }));
  },

  setActiveSession: (id) => set({ activeSessionId: id }),
  clearAllSessions: async () => {
    await db.sessions.clear();
    set({ sessions: [], activeSessionId: null });
  },
  stopGenerating: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
      set({ isGenerating: false, abortController: null });
    }
  },

  sendMessage: async (content: string, imageBase64?: string) => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;

    const msgContent = imageBase64 ? `${imageBase64}\n\n[图片说明]:${content}` : content;
    const userMsg: Message = { id: `u-${Date.now()}`, role: 'user', content: msgContent, timestamp: Date.now() };
    const aiMsgId = `a-${Date.now() + 1}`;
    const aiMsg: Message = { id: aiMsgId, role: 'assistant', content: '', timestamp: Date.now() };

    set((state) => ({
      isGenerating: true,
      sessions: state.sessions.map(s =>
        s.id === activeSessionId ? { ...s, messages: [...s.messages, userMsg, aiMsg], updatedAt: Date.now() } : s
      )
    }));

    const currentSession = get().sessions.find(s => s.id === activeSessionId);
    const allAvailableAgents = [...AGENTS, ...(get() as any).customAgents || []];
    const currentAgent = allAvailableAgents.find((a: any) => a.id === currentSession?.agentId) || allAvailableAgents[0];

    const messagesPayload: any[] = [];
    if (currentAgent.systemPrompt) {
      const date = new Date();
      const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
      const weekdayStr = weekdays[date.getDay()];
      const nowStr = date.toLocaleString('zh-CN', { hour12: false });
      
      const timeAwarePrompt = `${currentAgent.systemPrompt}\n\n[系统设定]: 绝对时间线校准！当前现实的系统时间是 ${nowStr} (${weekdayStr})。当用户询问"今天"、"本周"或特定日期时，你必须以此时间作为唯一的基准进行比对，严禁自己推算星期几。`;
      
      messagesPayload.push({ role: 'system', content: timeAwarePrompt });
    }

    if (currentSession) {
      currentSession.messages.slice(0, -2).forEach(m => {
        if (m.content.startsWith('data:image')) {
          const parts = m.content.split('\n\n[图片说明]:');
          messagesPayload.push({
            role: m.role,
            content: [
              { type: 'image_url', image_url: { url: parts[0] } },
              { type: 'text', text: parts[1] || '' }
            ]
          });
        } else {
          messagesPayload.push({ role: m.role, content: m.content });
        }
      });
    }

    if (imageBase64) {
      messagesPayload.push({
        role: 'user',
        content: [
          { type: 'image_url', image_url: { url: imageBase64 } },
          { type: 'text', text: content }
        ]
      });
    } else {
      messagesPayload.push({ role: 'user', content });
    }

    const ctrl = new AbortController();
    set({ abortController: ctrl });

    try {
      const res = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: messagesPayload,
          config: {
            tool_whitelist: currentAgent.allowedTools || ['query_jira_issues', 'search_knowledge_base']
          }
        }),
        signal: ctrl.signal
      });
      const reader = res.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      let done = false;

      while (reader && !done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ') && !line.includes('[DONE]')) {
              try {
                const data = JSON.parse(line.slice(6));
                
                if (data.custom_type === 'plugin_state') {
                  set((state) => ({
                    sessions: state.sessions.map(s => {
                      if (s.id !== activeSessionId) return s;
                      const lastMsg = s.messages[s.messages.length - 1];
                      if (lastMsg.id === aiMsgId) {
                        return { ...s, messages: [...s.messages.slice(0, -1), { ...lastMsg, plugin: data.plugin }] };
                      }
                      return s;
                    })
                  }));
                  continue;
                }

                if (data.custom_type === 'citations') {
                  set((state) => ({
                    sessions: state.sessions.map(s => {
                      if (s.id !== activeSessionId) return s;
                      const lastMsg = s.messages[s.messages.length - 1];
                      if (lastMsg.id === aiMsgId) {
                        return { ...s, messages: [...s.messages.slice(0, -1), { ...lastMsg, citations: data.citations }] };
                      }
                      return s;
                    })
                  }));
                  continue;
                }

                const deltaContent = data.choices?.[0]?.delta?.content || '';
                if (deltaContent) {
                  for (const ch of deltaContent) {
                    set((state) => ({
                      sessions: state.sessions.map(s => {
                        if (s.id !== activeSessionId) return s;
                        const lastMsg = s.messages[s.messages.length - 1];
                        if (lastMsg.id === aiMsgId) {
                          return { ...s, messages: [...s.messages.slice(0, -1), { ...lastMsg, content: lastMsg.content + ch }] };
                        }
                        return s;
                      })
                    }));
                    await new Promise(r => requestAnimationFrame(r));
                  }
                }
              } catch (e) {}
            }
          }
        }
      }
      const finalSession = get().sessions.find(s => s.id === activeSessionId);
      if (finalSession) {
        await db.sessions.put(finalSession);
        // 5层记忆自动提取
        if (finalSession.messages.length >= 2) {
          const msgs = finalSession.messages.map(m => ({ role: m.role, content: m.content }));
          (get() as any).extractMemories?.(msgs);
        }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        const abortedSession = get().sessions.find(s => s.id === activeSessionId);
        if (abortedSession) await db.sessions.put(abortedSession);
      }
    } finally {
      set({ isGenerating: false, abortController: null });
    }
  }
});

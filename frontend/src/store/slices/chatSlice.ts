import { StateCreator } from 'zustand';
import { Message, Session } from '../useChatStore';
import { db } from '@/lib/db';
import { AGENTS } from '../useChatStore';
import type { JiraSearchSupplementCard } from '@/components/JiraSearchSupplement';
import { buildConfirmCardFromApi } from '@/lib/jiraConfirm';

import { loadRuntimeConfig } from '@/lib/runtimeConfig';

async function restorePendingOperations(sessionId: string, set: (fn: (s: ChatSlice) => Partial<ChatSlice>) => void) {
  if (!sessionId) return;
  try {
    const res = await fetch(
      `/operations/pending?conversation_id=${encodeURIComponent(sessionId)}`,
    );
    const data = await res.json();
    if (!data.ok || !Array.isArray(data.operations)) return;
    set((state) => {
      const existing = new Set(state.pendingConfirmations.map((c) => c.op_id));
      const merged = [...state.pendingConfirmations];
      for (const row of data.operations) {
        const opId = row.id as string;
        if (!opId || existing.has(opId)) continue;
        merged.push(buildConfirmCardFromApi(opId, row.operation));
        existing.add(opId);
      }
      return { pendingConfirmations: merged };
    });
  } catch {
    /* 后端未启动时静默 */
  }
}

// ── 确认卡类型定义 ───────────────────────────
export interface DraftCardItem {
  index: number;
  summary: string;
  projectKey: string;
  issueType: string;
  description?: string;
  assignee?: string;
}

export interface DraftCard {
  draft_id: string;
  event: 'draft_card';
  items: DraftCardItem[];
  preview?: string;
  warnings?: string[];
  status?: 'pending' | 'submitted';
}

export interface ConfirmCard {
  op_id: string;
  event: 'confirm_card';
  operation: {
    type: string;
    issue_key?: string;
    summary?: string;
    description?: string;
    project?: string;
    drafts_count?: number;
    drafts?: DraftCardItem[];
    warnings?: string[];
  };
  created_at?: string;
  status?: 'pending' | 'confirmed' | 'rejected';
}

export interface ChatSlice {
  sessions: Session[];
  activeSessionId: string | null;
  isDbLoaded: boolean;
  isGenerating: boolean;
  abortController: AbortController | null;
  pendingConfirmations: ConfirmCard[];
  pendingDraftCards: DraftCard[];
  pendingJiraSupplements: JiraSearchSupplementCard[];

  initDB: () => Promise<void>;
  setActiveSession: (id: string) => void;
  clearAllSessions: () => Promise<void>;
  stopGenerating: () => void;
  sendMessage: (content: string, imageBase64?: string) => Promise<void>;

  renameSession: (id: string, newTitle: string) => Promise<void>;
  togglePinSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
  deleteMessage: (messageId: string) => Promise<void>;
  appendAssistantMessage: (content: string) => Promise<void>;
  restorePendingForSession: (sessionId: string) => Promise<void>;
}

export const createChatSlice: StateCreator<ChatSlice, [], [], ChatSlice> = (set, get) => ({
  sessions: [],
  activeSessionId: null,
  isDbLoaded: false,
  isGenerating: false,
  abortController: null,
  pendingConfirmations: [],
  pendingDraftCards: [],
  pendingJiraSupplements: [],

  initDB: async () => {
    try {
      const [allSessions, myAgents] = await Promise.all([
        db.sessions.orderBy('updatedAt').reverse().toArray(),
        db.customAgents.toArray(),
      ]);
      const activeId = allSessions.length > 0 ? allSessions[0].id : null;
      set({
        sessions: allSessions.map(s => ({ ...s, agentId: s.agentId || 'default' })),
        customAgents: myAgents,
        activeSessionId: activeId,
        isDbLoaded: true,
      });
      if (activeId) {
        await restorePendingOperations(activeId, set);
      }
    } catch (error) {
      set({ isDbLoaded: true });
    }
  },

  restorePendingForSession: async (sessionId: string) => {
    await restorePendingOperations(sessionId, set);
  },

  appendAssistantMessage: async (content: string) => {
    const { activeSessionId } = get();
    if (!activeSessionId || !content.trim()) return;
    const aiMsg: Message = {
      id: `a-sys-${Date.now()}`,
      role: 'assistant',
      content: content.trim(),
      timestamp: Date.now(),
    };
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.id === activeSessionId
          ? { ...s, messages: [...s.messages, aiMsg], updatedAt: Date.now() }
          : s,
      ),
    }));
    const updated = get().sessions.find((s) => s.id === activeSessionId);
    if (updated) await db.sessions.put(updated);
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

  setActiveSession: (id) => {
    set({ activeSessionId: id, pendingConfirmations: [], pendingDraftCards: [] });
    void restorePendingOperations(id, set);
  },
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
          conversation_id: activeSessionId,
          config: (() => {
            const rc = loadRuntimeConfig();
            return {
              jira_pat: rc.jira_pat || '',
              jira_projects: rc.jira_projects || rc.JIRA_PROJECTS || 'CT',
              jira_url: rc.jira_url || '',
            };
          })(),
          user_config: (() => {
            const rc = loadRuntimeConfig();
            return { jira_pat: rc.jira_pat || '' };
          })(),
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

                // ── 确认卡 SSE 事件（confirm_card 或 legacy confirm_required）──
                const isConfirmCard = data._event === 'confirm_card'
                  || data.custom_type === 'confirm_required';
                if (data._event === 'draft_card') {
                  const draftCard: DraftCard = {
                    draft_id: data.draft_id || '',
                    event: 'draft_card',
                    items: Array.isArray(data.items) ? data.items : [],
                    preview: data.preview || '',
                    warnings: Array.isArray(data.warnings) ? data.warnings : [],
                    status: 'pending',
                  };
                  set((state) => ({
                    pendingDraftCards: [...state.pendingDraftCards, draftCard],
                    sessions: state.sessions.map((s) => {
                      if (s.id !== activeSessionId) return s;
                      const lastMsg = s.messages[s.messages.length - 1];
                      if (lastMsg.id === aiMsgId) {
                        return {
                          ...s,
                          messages: [
                            ...s.messages.slice(0, -1),
                            { ...lastMsg, draftCard, content: (lastMsg.content || '') + (data.preview || '') },
                          ],
                        };
                      }
                      return s;
                    }),
                  }));
                  continue;
                }

                if (isConfirmCard) {
                  const rawOp = data.operation || {};
                  const opId = data.op_id || data.operation_id || rawOp.id || '';
                  const card = buildConfirmCardFromApi(opId, {
                    type: rawOp.type || rawOp.kind?.replace?.(/^jira_/, '') || 'unknown',
                    issue_key: rawOp.issue_key,
                    summary: rawOp.summary,
                    description: rawOp.description,
                    project: rawOp.project,
                    drafts_count: rawOp.drafts_count,
                    drafts: rawOp.drafts,
                    warnings: rawOp.warnings,
                  });
                  set((state) => ({
                    pendingConfirmations: [...state.pendingConfirmations, card],
                    sessions: state.sessions.map(s => {
                      if (s.id !== activeSessionId) return s;
                      const lastMsg = s.messages[s.messages.length - 1];
                      if (lastMsg.id === aiMsgId) {
                        return { ...s, messages: [...s.messages.slice(0, -1), { ...lastMsg, pendingCard: card }] };
                      }
                      return s;
                    })
                  }));
                  continue;
                }

                if (data._event === 'jira_search_supplement' && data.supplement) {
                  const sup = data.supplement;
                  const card: JiraSearchSupplementCard = {
                    id: `jira-sup-${Date.now()}`,
                    prompt: sup.prompt || '请选择 Jira 用户',
                    choices: sup.choices || [],
                  };
                  set((state) => ({
                    pendingJiraSupplements: [...state.pendingJiraSupplements, card],
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
              } catch (e) {
                if (line.startsWith('data: ') && !line.includes('[DONE]')) {
                  console.warn('[SSE] JSON parse failed:', line.slice(0, 120), e);
                }
              }
            }
          }
        }
      }
      const finalSession = get().sessions.find(s => s.id === activeSessionId);
      const lastAi = finalSession?.messages.filter(m => m.role === 'assistant').pop();
      if (lastAi && lastAi.id === aiMsgId) {
        const planningOnly = /先读取|我来拉取|第一步|让我先/.test(lastAi.content) && lastAi.content.length < 400;
        if (planningOnly && !lastAi.content.includes('##')) {
          const hint = '\n\n---\n⚠️ 回复在规划阶段中断，未生成完整结果。请重试；若仍失败请确认后端 :9099 已启动。';
          set((state) => ({
            sessions: state.sessions.map(s => {
              if (s.id !== activeSessionId) return s;
              const msgs = s.messages.map(m =>
                m.id === aiMsgId && !m.content.includes('回复在规划阶段中断')
                  ? { ...m, content: m.content + hint }
                  : m
              );
              return { ...s, messages: msgs };
            })
          }));
        }
      }
      if (finalSession) {
        await db.sessions.put(finalSession);
        // 5层记忆自动提取 (后端 API 未就绪, 暂时禁用)
        // if (finalSession.messages.length >= 2) {
        //   const msgs = finalSession.messages.map(m => ({ role: m.role, content: m.content }));
        //   (get() as any).extractMemories?.(msgs);
        // }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        const abortedSession = get().sessions.find(s => s.id === activeSessionId);
        if (abortedSession) await db.sessions.put(abortedSession);
      } else {
        // SSE 流异常中断: 注入错误气泡到当前会话最后一条消息
        console.error('[SSE] Stream error:', error.message || error);
        const errorSession = get().sessions.find(s => s.id === activeSessionId);
        if (errorSession) {
          const updated = {
            ...errorSession,
            messages: [
              ...errorSession.messages,
              {
                role: 'assistant',
                content: '⚠️ 后端服务连接中断或响应异常，请检查网络或重启服务。',
                error: true,
                timestamp: Date.now()
              }
            ]
          };
          set({ sessions: get().sessions.map(s => s.id === activeSessionId ? updated : s) });
          await db.sessions.put(updated);
        }
      }
    } finally {
      set({ isGenerating: false, abortController: null });
    }
  }
});

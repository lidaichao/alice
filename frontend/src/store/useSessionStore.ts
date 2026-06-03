import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { get, set, del } from 'idb-keyval';
import { v4 as uid } from 'uuid';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt?: number;
}

export interface Session {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

interface SessionState {
  sessions: Session[];
  activeId: string | null;
  // Actions
  createSession: () => string;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;
  updateMessages: (id: string, messages: ChatMessage[]) => void;
  getActiveMessages: () => ChatMessage[];
}

// ── idb-keyval async storage adapter for zustand persist ──
const idbStorage = createJSONStorage(() => ({
  getItem: async (name: string) => {
    const value = await get(name);
    return value ?? null;
  },
  setItem: async (name: string, value: string) => {
    await set(name, value);
  },
  removeItem: async (name: string) => {
    await del(name);
  },
}));

export const useSessionStore = create<SessionState>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeId: null,

      createSession: () => {
        const id = uid();
        const now = Date.now();
        const session: Session = {
          id,
          title: '新会话',
          createdAt: now,
          updatedAt: now,
          messages: [],
        };
        set((s) => ({ sessions: [...s.sessions, session], activeId: id }));
        return id;
      },

      switchSession: (id: string) => {
        set({ activeId: id });
      },

      deleteSession: (id: string) => {
        set((s) => {
          const sessions = s.sessions.filter((ss) => ss.id !== id);
          const activeId = s.activeId === id ? (sessions[0]?.id ?? null) : s.activeId;
          return { sessions, activeId };
        });
      },

      renameSession: (id: string, title: string) => {
        set((s) => ({
          sessions: s.sessions.map((ss) =>
            ss.id === id ? { ...ss, title, updatedAt: Date.now() } : ss
          ),
        }));
      },

      updateMessages: (id: string, messages: ChatMessage[]) => {
        set((s) => ({
          sessions: s.sessions.map((ss) =>
            ss.id === id ? { ...ss, messages, updatedAt: Date.now() } : ss
          ),
        }));
      },

      getActiveMessages: () => {
        const { sessions, activeId } = get();
        return sessions.find((s) => s.id === activeId)?.messages ?? [];
      },
    }),
    {
      name: 'alice-sessions',
      storage: idbStorage,
      partialize: (state) => ({
        sessions: state.sessions,
        activeId: state.activeId,
      }),
    }
  )
);

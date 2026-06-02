import { StateCreator } from 'zustand';
import { Agent, Session, AGENTS } from '../useChatStore';
import { db } from '@/lib/db';

export interface AgentSlice {
  customAgents: Agent[];

  addSession: (agentId?: string) => Promise<void>;
  addCustomAgent: (agent: Omit<Agent, 'id'>) => Promise<void>;
}

export const createAgentSlice: StateCreator<AgentSlice, [], [], AgentSlice> = (set, get) => ({
  customAgents: [],

  addSession: async (agentId = 'default') => {
    const allAgents = [...AGENTS, ...get().customAgents];
    const agent = allAgents.find(a => a.id === agentId) || allAgents[0];
    const newSession: Session = {
      id: `session-${Date.now()}`,
      title: `${agent.name}的新对话`,
      messages: [],
      updatedAt: Date.now(),
      agentId: agent.id,
    };
    await db.sessions.add(newSession);
    set((state: any) => ({
      sessions: [newSession, ...state.sessions],
      activeSessionId: newSession.id,
    }));
  },

  addCustomAgent: async (newAgentData) => {
    const newAgent: Agent = {
      ...newAgentData,
      id: `custom-${Date.now()}`
    };
    await db.customAgents.add(newAgent);
    set((state) => ({
      customAgents: [...state.customAgents, newAgent]
    }));
  },
});

import Dexie, { Table } from 'dexie';
import { Session, Agent } from '@/store/useChatStore';

export type MemoryLayer = 'activity' | 'identity' | 'context' | 'preference' | 'experience';

export interface MemoryEntry {
  id: string;
  layer: MemoryLayer;
  category: string;
  content: string;
  key?: string;
  timestamp: number;
  source: string;
  confidence?: number;
}

export class AliceDatabase extends Dexie {
  sessions!: Table<Session, string>;
  customAgents!: Table<Agent, string>;
  memories!: Table<MemoryEntry, string>;

  constructor() {
    super('AliceChatDB');
    this.version(4).stores({
      sessions: 'id, updatedAt',
      customAgents: 'id',
      memories: 'id, layer, category, timestamp'
    });
  }
}

export const db = new AliceDatabase();

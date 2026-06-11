import { create } from 'zustand';
import { createUISlice, UISlice } from './slices/uiSlice';
import { createChatSlice, ChatSlice } from './slices/chatSlice';
import { createAgentSlice, AgentSlice } from './slices/agentSlice';
import { createMemorySlice, MemorySlice } from './slices/memorySlice';
import { createUserSlice, UserSlice } from './slices/userSlice';

// ── 类型导出（保持向后兼容） ────────────────────────
export interface Agent {
  id: string;
  name: string;
  avatar: string;
  description: string;
  systemPrompt: string;
  allowedTools?: string[];
}

export const AGENTS: Agent[] = [
  { id: 'default', name: '爱丽丝 (Alice)', avatar: '⚛️', description: '你的全能 AI 工作助理', systemPrompt: '你是爱丽丝，一个乐于助人的 AI 工作助理。', allowedTools: ['query_jira_issues', 'search_knowledge_base'] },
  { id: 'code_reviewer', name: '代码审查大师', avatar: '💻', description: '严格找出代码中的坏味道与漏洞', systemPrompt: '你是一个拥有20年经验的高级架构师。', allowedTools: [] },
  { id: 'jira_master', name: '敏捷项目教练', avatar: '🎯', description: '专精于需求拆解与 Jira 管理', systemPrompt: '你是敏捷开发专家，请帮用户把需求拆解为标准的 Jira Epic/Story/Task 结构。', allowedTools: ['query_jira_issues'] },
  { id: 'doc_writer', name: '产品文档润色', avatar: '📝', description: '将草稿重写为高大上的专业文档', systemPrompt: '你是硅谷顶尖的 Tech Writer。', allowedTools: ['search_knowledge_base'] }
];

export interface Command {
  key: string;
  label: string;
  icon: string;
  description: string;
  template: string;
}

export const COMMANDS: Command[] = [
  { key: 'bug', label: '提交 Jira 缺陷 (Bug)', icon: '🐛', description: '快速生成包含环境、复现步骤的缺陷单模板', template: '【Jira 缺陷创建申请】\n- 项目模块: \n- 影响版本: \n- 测试环境: \n- 缺陷描述: \n- 【复现步骤】:\n  1. \n  2. \n- 预期结果: \n- 实际结果: \n[请在下方贴入报错日志或拖入截图]' },
  { key: 'review', label: '代码深度审查 (Review)', icon: '🔍', description: '快速构建代码坏味道与潜在漏洞的分析模版', template: '请帮我深度审查以下代码段。主要关注：\n1. 是否存在内存泄露或边界死循环？\n2. 并发场景下是否线程安全？\n3. 有无更优雅的重构或空间复杂度优化方案？\n\n【待审查代码】:\n```\n\n```' },
  { key: 'story', label: '拆解用户故事 (Story)', icon: '🎯', description: '将粗颗粒度的业务需求转化为标准敏捷故事', template: '请将以下业务需求转化为标准的敏捷用户故事(User Story)。\n要求输出格式满足：\n- 作为一个 [角色], 我希望 [功能], 以便能够 [业务价值]。\n- 【验收标准(AC)】: 满足 INVEST 原则，至少包含 3 个 Happy Pass 和 1 个异常分支。\n\n【原始需求描述】:\n' },
  { key: 'clear', label: '清空当前上下文', icon: '🧹', description: '快速斩断当前会话的上下文纽带', template: '请忘掉我们之前聊的所有关于技术细节和上下文的约束，从现在开始我们要开启一个全新的话题，请确认。' }
];

export interface Citation {
  index: number;
  title: string;
  source: 'notion' | 'svn' | 'gdrive';
  url: string;
  snippet: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  plugin?: { name: string; status: 'running' | 'done' };
  citations?: Citation[];
  source?: 'deepseek' | 'cursor';
  error?: boolean;
  kb_sources?: Array<{ source: string; updated?: string }>;
  pendingCard?: any;
  draftCard?: any;
}

export interface Session {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
  agentId: string;
  isPinned?: boolean;
}

// ── 组合 Store ────────────────────────
type FullStore = UISlice & ChatSlice & AgentSlice & MemorySlice & UserSlice;

export const useChatStore = create<FullStore>()((...a) => ({
  ...createUISlice(...a),
  ...createChatSlice(...a),
  ...createAgentSlice(...a),
  ...createMemorySlice(...a),
  ...createUserSlice(...a),
}));

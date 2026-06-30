'use strict';

const paths = require('../config/paths');
const { getCursorConfig, getGlobalConfig } = require('./config-service');

const CURSOR_ME_URL = 'https://api.cursor.com/v1/me';
const DEFAULT_MODEL = 'composer-2.5';
const MAX_HISTORY_MESSAGES = 15;  // AL-431: 缩减 historical context 体积

function configurationError(message) {
  const error = new Error(message);
  error.code = 'VALIDATION_ERROR';
  error.statusCode = 400;
  error.publicMessage = message;
  return error;
}

async function loadAgentClass() {
  const sdk = await import('@cursor/sdk');
  return sdk.Agent;
}

function formatKnowledgeContext(results = []) {
  if (results.length === 0) {
    return '本地知识库没有检索到相关内容。';
  }

  return results
    .map((result, index) => [
      `${index + 1}. ${result.title}`,
      `来源：${result.relativePath}`,
      `摘要：${result.snippet}`
    ].join('\n'))
    .join('\n\n');
}

function formatShallowMemoryContext(results = []) {
  if (!results || results.length === 0) {
    return '没有检索到相关浅层记忆。';
  }

  return results
    .map((result, index) => `${index + 1}. [${result.category}] ${result.line}`)
    .join('\n');
}

function formatContextEntries(entries, emptyText) {
  if (!entries || entries.length === 0) {
    return emptyText;
  }

  return entries
    .filter((entry) => entry.content && entry.content.trim() !== '')
    .map((entry, index) => [
      `${index + 1}. ${entry.category || entry.name || entry.id}`,
      `来源：${entry.relativePath}`,
      entry.content.trim()
    ].join('\n'))
    .join('\n\n') || emptyText;
}

function formatLogicContext(logicContext = {}) {
  return [
    `逻辑断言：\n${formatContextEntries(logicContext.assertions, '没有逻辑断言。')}`,
    `逻辑规则：\n${formatContextEntries(logicContext.rules, '没有逻辑规则。')}`,
    `可执行规则配置：\n${formatContextEntries(logicContext.executableRules, '没有可执行规则配置。')}`
  ].join('\n\n');
}

function formatSkillsContext(skillsContext = {}) {
  const registry = skillsContext.registry && skillsContext.registry.trim() !== ''
    ? skillsContext.registry.trim()
    : '没有 skills registry。';
  const skills = skillsContext.skills && skillsContext.skills.length > 0
    ? skillsContext.skills.map((skill, index) => [
      `${index + 1}. ${skill.id}`,
      `来源：${skill.relativePath}`,
      skill.skillMarkdown && skill.skillMarkdown.trim() !== '' ? `说明：\n${skill.skillMarkdown.trim()}` : '说明：未配置。',
      skill.configYaml && skill.configYaml.trim() !== '' ? `配置：\n${skill.configYaml.trim()}` : '配置：未配置。'
    ].join('\n')).join('\n\n')
    : '没有 skills。';

  return [`Skills registry：\n${registry}`, `Skills：\n${skills}`].join('\n\n');
}

function formatSystemPrompt({ markdown, config }) {
  const configText = Object.keys(config).length === 0 ? '' : JSON.stringify(config, null, 2);
  return [
    '你是Alice（AliceV2），一个运行在用户自有服务器上的项目智能中枢。',
    '你必须默认使用中文回答，并保持直接、可靠、面向执行的风格。',
    markdown.trim() === '' ? '' : `Alice全局设定：\n${markdown.trim()}`,
    configText === '' ? '' : `结构化配置：\n${configText}`
  ].filter(Boolean).join('\n\n');
}

function formatConversationHistory(messages = []) {
  return messages
    .filter((message) => ['user', 'assistant'].includes(message.role) && message.text)
    .slice(-MAX_HISTORY_MESSAGES)
    .map((message) => `${message.role === 'user' ? '用户' : '助手'}：${message.text}`)
    .join('\n');
}

async function buildUserPrompt(input = {}) {
  const {
    message,
    knowledgeResults = [],
    shallowMemoryResults = [],
    logicContext = {},
    skillsContext = {},
    conversationMessages = [],
    conversationSummary,
    routeType
  } = input;
  const globalConfig = await getGlobalConfig({ baizeRoot: input.baizeRoot });
  const summaryText = conversationSummary && conversationSummary.trim() !== ''
    ? conversationSummary.trim()
    : '暂无会话摘要。';
  const historyText = formatConversationHistory(conversationMessages);
  const isOrdinaryChat = routeType === 'ordinary_chat';
  return [
    formatSystemPrompt(globalConfig),
    `入口平台：${message.platform}`,
    `用户 ID：${message.userId || 'unknown'}`,
    `会话 ID：${message.conversationId || 'unknown'}`,
    `会话摘要：\n${summaryText}`,
    `本地知识库上下文：\n${formatKnowledgeContext(knowledgeResults)}`,
    `浅层记忆上下文：\n${formatShallowMemoryContext(shallowMemoryResults)}`,
    isOrdinaryChat ? '' : `逻辑断言与规则上下文：\n${formatLogicContext(logicContext)}`,
    isOrdinaryChat ? '' : `技能上下文：\n${formatSkillsContext(skillsContext)}`,
    historyText ? `会话历史：\n${historyText}` : '',
    `用户问题：${message.text}`,
    '请结合以上上下文，用中文直接回答当前用户问题。'
  ].filter(Boolean).join('\n\n');
}

async function verifyCursorApiKey(apiKey, fetchImpl = globalThis.fetch) {
  const response = await fetchImpl(CURSOR_ME_URL, {
    headers: { Authorization: `Bearer ${apiKey}` }
  });
  return response.ok;
}

async function generateCursorReply(input = {}) {
  const { onTiming } = input;
  const config = await getCursorConfig({ baizeRoot: input.baizeRoot });
  if (!config.apiKey) {
    return 'AI 引擎尚未配置密钥，暂时无法回答。请联系管理员完成 Cursor SDK 设置（详见 docs/SETUP.md）。';
  }

  const startedAt = Date.now();
  const Agent = await loadAgentClass();
  const prompt = await buildUserPrompt(input);
  const result = await Agent.prompt(prompt, {
    apiKey: config.apiKey,
    model: { id: config.model || DEFAULT_MODEL },
    local: { cwd: config.workspacePath || paths.BAIZE_ROOT },
    mode: 'agent'
  });

  if (typeof onTiming === 'function') {
    onTiming('cursorApiMs', Date.now() - startedAt);
  }

  const text = result && result.result ? String(result.result).trim() : '';
  return text || 'Alice：Cursor 已响应，但未返回有效文本。';
}

async function generateCursorReplyStream(input = {}) {
  const { onDelta, onTiming } = input;
  const config = await getCursorConfig({ baizeRoot: input.baizeRoot });
  if (!config.apiKey) {
    return 'AI 引擎尚未配置密钥，暂时无法回答。请联系管理员完成 Cursor SDK 设置（详见 docs/SETUP.md）。';
  }

  const startedAt = Date.now();
  const Agent = await loadAgentClass();
  const agent = await Agent.create({
    apiKey: config.apiKey,
    model: { id: config.model || DEFAULT_MODEL },
    local: { cwd: config.workspacePath || paths.BAIZE_ROOT },
    mode: 'agent'
  });

  try {
    const prompt = await buildUserPrompt(input);
    const run = await agent.send(prompt);
    let streamedText = '';

    for await (const event of run.stream()) {
      if (event.type === 'assistant' && event.message && Array.isArray(event.message.content)) {
        for (const block of event.message.content) {
          if (block.type === 'text' && block.text) {
            streamedText += block.text;
            if (typeof onDelta === 'function') {
              onDelta(block.text);
            }
          }
        }
      }
    }

    const finished = await run.wait();
    if (typeof onTiming === 'function') {
      onTiming('cursorApiMs', Date.now() - startedAt);
    }

    const finalText = finished && finished.result ? String(finished.result).trim() : streamedText.trim();
    return finalText || 'Alice：Cursor 已响应，但未返回有效文本。';
  } finally {
    if (typeof agent.close === 'function') {
      await agent.close();
    }
  }
}

module.exports = {
  CURSOR_ME_URL,
  buildUserPrompt,
  verifyCursorApiKey,
  generateCursorReply,
  generateCursorReplyStream
};

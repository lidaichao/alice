import { useRef, useEffect } from 'react';
import { Bubble } from '@ant-design/x';
import { XMarkdown } from '@ant-design/x-markdown';
import JiraOperationCard from './cards/JiraOperationCard.jsx';
import RequirementRunCard from './cards/RequirementRunCard.jsx';
import BugAnalysisCard from './cards/BugAnalysisCard.jsx';
import AttachmentCard from './cards/AttachmentCard.jsx';
import PatchApplyCard from './cards/PatchApplyCard.jsx';
import KBReferenceCard from './cards/KBReferenceCard.jsx';

const ROLE = {
  user: { placement: 'end' },
  ai: { placement: 'start' }
};

function parseEvent(msg) {
  if (!msg?.message?.eventType) return null;
  try {
    return JSON.parse(msg.message.content);
  } catch {
    return null;
  }
}

function getCardFromEvent(msg, conversationId, clientId) {
  const et = msg.message?.eventType;
  const event = parseEvent(msg);
  if (!event) return null;

  // Jira 卡片（波次 6）
  if ((et === 'jira_operation_required' || et === 'jira_operation_recovery_required') && event.operation) {
    return {
      key: msg.id,
      role: 'ai',
      content: <JiraOperationCard operation={event.operation} conversationId={conversationId} clientId={clientId} />,
      footer: `[${et}]`
    };
  }

  // 需求完成卡片（AL-466）
  if ((et === 'requirement_completion_required' || et === 'requirement_completion_started') && event.run) {
    return {
      key: msg.id,
      role: 'ai',
      content: <RequirementRunCard run={event.run} conversationId={conversationId} clientId={clientId} />,
      footer: `[${et}]`
    };
  }

  // BUG 分析卡片（AL-467）
  if (et === 'jira_bug_analysis_started' && event.run) {
    return {
      key: msg.id,
      role: 'ai',
      content: <BugAnalysisCard run={event.run} clientId={clientId} />,
      footer: `[${et}]`
    };
  }

  // 补丁应用卡片（AL-468）
  if (et === 'permission_required' && event.permission) {
    const operation = {
      id: event.permission.operationId,
      status: 'awaiting_confirmation',
      conversationId,
      clientId,
      permission: { mode: event.permission.requestedMode || 'write_proposal' },
      risk: { level: event.permission.riskLevel || 'medium' },
      proposal: { summary: null, patch: null, files: [], warnings: [] },
      expiresAt: event.permission.expiresAt
    };
    return {
      key: msg.id,
      role: 'ai',
      content: <PatchApplyCard operation={operation} />,
      footer: `[${et}]`
    };
  }

  return null;
}

/** 检查 message 是否含附件 */
function hasAttachment(msg) {
  return !!(msg?.message?.attachment);
}

/** 检查 message 是否含知识库引用 */
function hasSourceResults(msg) {
  const results = msg?.message?.results;
  return Array.isArray(results) && results.length > 0;
}

function ChatMessages({ messages, isRequesting, conversationId, clientId }) {
  const listRef = useRef(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  const items = messages.map((msg) => {
    const msgRole = msg.message?.role || 'user';
    const msgContent = msg.message?.content || '';
    const msgStatus = msg.message?.status;
    const msgEventType = msg.message?.eventType;

    const bubbleRole = msgRole === 'assistant' ? 'ai' : 'user';
    const isStreaming = msgRole === 'assistant' && msgStatus === 'updating';

    // 结构化事件 → 业务卡片
    const card = getCardFromEvent(msg, conversationId, clientId);
    if (card) return card;

    // 附件卡片（AL-468）
    if (hasAttachment(msg)) {
      return {
        key: msg.id,
        role: 'ai',
        content: <AttachmentCard attachment={msg.message.attachment} />
      };
    }

    // 知识库引用卡片（AL-468）
    if (hasSourceResults(msg)) {
      return {
        key: msg.id,
        role: 'ai',
        content: <KBReferenceCard sourceResults={msg.message.results} />,
        footer: '[source_results]'
      };
    }

    return {
      key: msg.id,
      role: bubbleRole,
      content: bubbleRole === 'ai'
        ? (
          <XMarkdown
            content={msgContent}
            streaming={{
              hasNextChunk: isStreaming,
              enableAnimation: true,
              tail: isStreaming
            }}
          />
        )
        : msgContent,
      footer: msgEventType
        ? `[${msgEventType}]`
        : undefined
    };
  });

  return (
    <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: '12px 0' }}>
      <Bubble.List items={items} role={ROLE} />
    </div>
  );
}

export default ChatMessages;

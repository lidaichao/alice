import type { ConfirmCard, DraftCardItem, RecoveryInfo } from '@/store/slices/chatSlice';

export function buildConfirmCardFromApi(
  opId: string,
  operation: Record<string, unknown> | undefined,
  extras?: {
    recovery?: RecoveryInfo;
    operation_status?: string;
  },
): ConfirmCard {
  const raw = operation || {};
  const type = String(raw.type || 'unknown');
  const recovery =
    extras?.recovery ||
    (raw.recovery as RecoveryInfo | undefined);
  return {
    op_id: opId,
    event: 'confirm_card',
    operation: {
      type,
      issue_key: raw.issue_key as string | undefined,
      summary: raw.summary as string | undefined,
      description: raw.description as string | undefined,
      project: raw.project as string | undefined,
      drafts_count: raw.drafts_count as number | undefined,
      drafts: raw.drafts as DraftCardItem[] | undefined,
      warnings: (raw.warnings as string[]) || [],
    },
    recovery,
    operation_status: extras?.operation_status,
    status: 'pending',
  };
}

export function formatOperationResultMessage(data: {
  ok?: boolean;
  message?: string;
  error?: string;
  operation?: { created_issues?: { key?: string }[] };
}): string {
  if (data.ok === false || data.error) {
    const err = data.error || '操作失败';
    return `${err}\n\n常见原因：标签字段不合法或 Jira 权限不足；可让 Alice 调整标签后重试，或联系管理员。`;
  }
  const keys = (data.operation?.created_issues || [])
    .map((i) => i.key)
    .filter(Boolean);
  if (keys.length) {
    return `${data.message || '操作已完成'}\n\n已创建：${keys.join(', ')}`;
  }
  return data.message || '操作已完成';
}

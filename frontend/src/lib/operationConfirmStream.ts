import { buildAliceUserHeaders } from '@/lib/runtimeConfig';

/** POST /operations/:id/confirm?stream=1 — operation_progress SSE (E2.2) */

export type OperationProgress = {
  phase: string;
  message: string;
  percent?: number;
  op_id?: string;
};

export type ConfirmStreamResult = {
  ok: boolean;
  message?: string;
  error?: string;
  error_code?: string;
  operation?: { created_issues?: { key?: string }[]; recovery?: unknown };
};

export async function confirmOperationWithProgress(
  opId: string,
  body: Record<string, unknown>,
  onProgress?: (p: OperationProgress) => void,
): Promise<ConfirmStreamResult> {
  const res = await fetch(`/operations/${opId}/confirm?stream=1`, {
    method: 'POST',
    headers: buildAliceUserHeaders({
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    }),
    body: JSON.stringify({ ...body, stream: true }),
  });

  if (!res.ok && !(res.headers.get('content-type') || '').includes('text/event-stream')) {
    const data = await res.json().catch(() => ({}));
    return { ok: false, error: (data as { error?: string }).error || res.statusText, error_code: (data as { error_code?: string }).error_code };
  }

  const reader = res.body?.getReader();
  if (!reader) {
    const data = await res.json().catch(() => ({}));
    return data as ConfirmStreamResult;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let finalPayload: ConfirmStreamResult = { ok: false, error: '无响应' };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const block of parts) {
      for (const line of block.split('\n')) {
        if (!line.startsWith('data: ') || line.includes('[DONE]')) continue;
        try {
          const data = JSON.parse(line.slice(6)) as Record<string, unknown>;
          const ev = data._event as string | undefined;
          if (ev === 'operation_progress') {
            onProgress?.({
              phase: String(data.phase || ''),
              message: String(data.message || ''),
              percent: data.percent as number | undefined,
              op_id: data.op_id as string | undefined,
            });
          } else if (ev === 'operation_complete') {
            finalPayload = { ok: true, ...(data as ConfirmStreamResult) };
          } else if (ev === 'operation_error') {
            finalPayload = { ok: false, ...(data as ConfirmStreamResult) };
          }
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  }
  return finalPayload;
}

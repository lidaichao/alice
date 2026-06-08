/** sessionStorage 中的 Jira / 运行时配置（与 chatSlice 一致） */
export const ALICE_USER_ID_HEADER = 'X-Alice-User-Id';

export function loadRuntimeConfig(): Record<string, string> {
  try {
    const raw = sessionStorage.getItem('alice_runtime_config');
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function saveRuntimeConfig(patch: Record<string, string>): void {
  const rc = { ...loadRuntimeConfig(), ...patch };
  sessionStorage.setItem('alice_runtime_config', JSON.stringify(rc));
}

export function getAliceUserId(): string {
  return (loadRuntimeConfig().user_id || '').trim();
}

/** M4.1 — 统一注入用户身份请求头（禁止各 fetch 手搓 header） */
export function buildAliceUserHeaders(
  extra: Record<string, string> = {},
): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  const uid = getAliceUserId();
  if (uid) {
    headers[ALICE_USER_ID_HEADER] = uid;
  }
  return headers;
}

/** E4.1：Hub 独占凭据时客户端可不填 jira_pat；M4.1 同时注入 user_id */
export function buildJiraWriteRequestBody(extra: Record<string, unknown> = {}): Record<string, unknown> {
  const rc = loadRuntimeConfig();
  const jira_pat = (rc.jira_pat || '').trim();
  const hubOnly = rc.hub_only_jira === '1' || rc.hub_only_jira === 'true' || !jira_pat;
  const body: Record<string, unknown> = { ...extra };
  const uid = getAliceUserId();
  if (uid) {
    body.user_id = uid;
  }
  if (!hubOnly && jira_pat) {
    body.jira_pat = jira_pat;
    body.user_config = { jira_pat, ...(uid ? { user_id: uid } : {}) };
  } else if (uid) {
    body.user_config = { user_id: uid };
  }
  return body;
}

/** sessionStorage 中的 Jira / 运行时配置（与 chatSlice 一致） */
export function loadRuntimeConfig(): Record<string, string> {
  try {
    const raw = sessionStorage.getItem('alice_runtime_config');
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

/** E4.1：Hub 独占凭据时客户端可不填 jira_pat */
export function buildJiraWriteRequestBody(extra: Record<string, unknown> = {}): Record<string, unknown> {
  const rc = loadRuntimeConfig();
  const jira_pat = (rc.jira_pat || '').trim();
  const hubOnly = rc.hub_only_jira === '1' || rc.hub_only_jira === 'true' || !jira_pat;
  const body: Record<string, unknown> = { ...extra };
  if (!hubOnly && jira_pat) {
    body.jira_pat = jira_pat;
    body.user_config = { jira_pat };
  }
  return body;
}

/** sessionStorage 中的 Jira / 运行时配置（与 chatSlice 一致） */
export function loadRuntimeConfig(): Record<string, string> {
  try {
    const raw = sessionStorage.getItem('alice_runtime_config');
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function buildJiraWriteRequestBody(extra: Record<string, unknown> = {}): Record<string, unknown> {
  const rc = loadRuntimeConfig();
  const jira_pat = rc.jira_pat || '';
  return {
    jira_pat,
    user_config: { jira_pat },
    ...extra,
  };
}

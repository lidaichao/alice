/** Sync Hub capabilities (E4 hub-only Jira) into sessionStorage for runtimeConfig. */
export async function syncHubConfigFromHealth(baseUrl = ''): Promise<void> {
  try {
    const res = await fetch(`${baseUrl}/health`);
    if (!res.ok) return;
    const data = await res.json();
    const raw = sessionStorage.getItem('alice_runtime_config');
    const rc = raw ? JSON.parse(raw) : {};
    if (data.hub_only_jira === true) {
      rc.hub_only_jira = '1';
    }
    if (data.api_version) {
      rc.api_version = String(data.api_version);
    }
    sessionStorage.setItem('alice_runtime_config', JSON.stringify(rc));
  } catch {
    /* Hub offline — keep existing config */
  }
}

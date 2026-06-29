// Browser Adapter: 将 window.baize API 桥接到服务端 REST API
// 替代 Electron preload，使得 index.html + renderer.js 可在浏览器中直接运行
(function () {
  'use strict';

  const BASE = 'http://127.0.0.1:3000';
  let clientId = localStorage.getItem('baize_client_id') || '';
  if (!clientId) {
    clientId = 'browser-' + crypto.randomUUID();
    localStorage.setItem('baize_client_id', clientId);
  }

  async function apiFetch(path, options = {}) {
    const url = BASE + path;
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const err = new Error(body.error?.message || res.statusText);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return res.json();
  }

  // SSE Stream adapter
  function createSSEStream(path, body, onEvent) {
    const controller = new AbortController();
    fetch(BASE + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal
    }).then(async (res) => {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') { onEvent({ type: 'done' }); return; }
            try { onEvent(JSON.parse(data)); } catch (e) { /* skip */ }
          }
        }
      }
    }).catch((err) => {
      if (err.name !== 'AbortError') {
        onEvent({ type: 'error', error: err.message });
      }
    });
    return controller;
  }

  let activeSSE = null;

  window.baize = {
    getServerUrl: () => Promise.resolve(BASE),
    setServerUrl: (url) => { localStorage.setItem('baize_server_url', url); return Promise.resolve(url); },
    getClientId: () => Promise.resolve(clientId),
    getShowServerActivity: () => Promise.resolve(true),
    setShowServerActivity: () => Promise.resolve(true),
    debugLog: (line) => { console.log('[baize]', line); return Promise.resolve(null); },
    getUpdateStatus: () => Promise.resolve({ status: 'not_available', message: '浏览器模式不支持自动更新' }),
    checkForUpdate: () => Promise.resolve({ status: 'not_available' }),
    downloadUpdate: () => Promise.resolve({ status: 'not_available' }),
    installUpdate: () => Promise.resolve(true),
    minimizeWindow: () => Promise.resolve(),
    toggleMaximizeWindow: () => Promise.resolve(),
    closeWindow: () => Promise.resolve(),
    onUpdateState: () => () => {},
    health: () => apiFetch('/health'),
    getClaudeConfig: () => apiFetch('/config/claude-code'),
    getKnowledgeBaseStatus: () => Promise.resolve({ ok: true }),
    chat: (input) => apiFetch('/chat', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    beginCancellableRequest: () => Date.now() + '-' + Math.random(),
    chatStream: function (input, onEvent, requestId) {
      if (activeSSE) { activeSSE.abort(); }
      activeSSE = createSSEStream('/chat/stream', { ...input, clientId }, onEvent);
      return Promise.resolve();
    },
    cancelChatStream: () => {
      if (activeSSE) { activeSSE.abort(); activeSSE = null; }
      return Promise.resolve(true);
    },
    listConversations: () => apiFetch('/conversations'),
    createConversation: (input) => apiFetch('/conversations', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    getConversation: (id) => apiFetch('/conversations/' + encodeURIComponent(id)),
    updateConversation: (id, patch) => apiFetch('/conversations/' + encodeURIComponent(id), { method: 'PATCH', body: JSON.stringify(patch) }),
    deleteConversation: (id) => apiFetch('/conversations/' + encodeURIComponent(id), { method: 'DELETE' }),
    appendConversationMessage: (id, msg) => apiFetch('/conversations/' + encodeURIComponent(id) + '/messages', { method: 'POST', body: JSON.stringify(msg) }),
    listServerConversations: () => apiFetch('/conversations'),
    getServerConversation: (id) => apiFetch('/conversations/' + encodeURIComponent(id)),
    createServerConversation: (input) => apiFetch('/conversations', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    renameServerConversation: (id, input) => apiFetch('/conversations/' + encodeURIComponent(id), { method: 'PATCH', body: JSON.stringify(input) }),
    getClaudeCodeOperation: (id) => apiFetch('/claude-code/operations/' + encodeURIComponent(id)),
    confirmClaudeCodeOperation: (id, input) => apiFetch('/claude-code/operations/' + encodeURIComponent(id) + '/confirm', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    rejectClaudeCodeOperation: (id, input) => apiFetch('/claude-code/operations/' + encodeURIComponent(id) + '/reject', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    reportClaudeCodeApplicationResult: (id, input) => apiFetch('/claude-code/operations/' + encodeURIComponent(id) + '/result', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    getDroppedFilePath: (file) => Promise.resolve(null),
    uploadAttachmentFile: (filePath, input) => Promise.reject(new Error('浏览器模式请使用粘贴上传')),
    uploadAttachmentData: async (input) => {
      const formData = new FormData();
      const blob = new Blob([Uint8Array.from(atob(input.contentBase64), c => c.charCodeAt(0))], { type: input.mimeType || 'application/octet-stream' });
      formData.append('file', blob, input.fileName || 'attachment');
      formData.append('conversationId', input.conversationId || '');
      formData.append('clientId', clientId);
      const res = await fetch(BASE + '/attachments/upload', { method: 'POST', body: formData });
      return res.json();
    },
    rememberAttachment: (id, input) => apiFetch('/attachments/' + encodeURIComponent(id) + '/remember', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    createJiraImportDrafts: (input) => apiFetch('/plugins/jira/import-drafts', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    getJiraOperation: (id) => apiFetch('/plugins/jira/operations/' + encodeURIComponent(id)),
    confirmJiraOperation: function (id, input, onEvent) {
      return apiFetch('/plugins/jira/operations/' + encodeURIComponent(id) + '/confirm', { method: 'POST', body: JSON.stringify({ ...input, clientId }) });
    },
    updateJiraOperationDrafts: (id, input) => apiFetch('/plugins/jira/operations/' + encodeURIComponent(id) + '/drafts', { method: 'PATCH', body: JSON.stringify({ ...input, clientId }) }),
    rejectJiraOperation: (id, input) => apiFetch('/plugins/jira/operations/' + encodeURIComponent(id) + '/reject', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    recoverJiraOperation: (id, input) => apiFetch('/plugins/jira/operations/' + encodeURIComponent(id) + '/recover', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    getBugAnalysisRun: (runId) => apiFetch('/jira/bug-analysis/runs/' + encodeURIComponent(runId)),
    resumeBugAnalysisRun: (runId, input) => apiFetch('/jira/bug-analysis/runs/' + encodeURIComponent(runId) + '/resume', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    confirmBugAnalysisComment: (runId, itemId, input) => apiFetch('/jira/bug-analysis/runs/' + encodeURIComponent(runId) + '/items/' + encodeURIComponent(itemId) + '/confirm-comment', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    applyBugAnalysisRecovery: (runId, itemId, input) => apiFetch('/jira/bug-analysis/runs/' + encodeURIComponent(runId) + '/items/' + encodeURIComponent(itemId) + '/recover', { method: 'POST', body: JSON.stringify({ ...input, clientId }) }),
    confirmPluginAudit: (auditId) => apiFetch('/audit/' + encodeURIComponent(auditId) + '/confirm', { method: 'POST', body: JSON.stringify({ clientId }) }),
    rejectPluginAudit: (auditId) => apiFetch('/audit/' + encodeURIComponent(auditId) + '/reject', { method: 'POST', body: JSON.stringify({ clientId }) }),
    listWorkspaces: () => Promise.resolve([]),
    authorizeWorkspace: () => Promise.resolve(null),
    setActiveWorkspace: () => Promise.resolve(),
    revokeWorkspace: () => Promise.resolve(),
    previewPatch: () => Promise.resolve(null),
    applyPatch: () => Promise.resolve(null)
  };

  console.log('[Baize Browser Adapter] Ready. Server:', BASE);
})();

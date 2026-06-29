const { verifyCursorApiKey, buildUserPrompt, CURSOR_ME_URL } = require('../src/services/cursor-service');
const { getCursorConfig, getPublicCursorConfig } = require('../src/services/config-service');
const { createTestRoot } = require('./helpers/test-root');
const fs = require('fs/promises');
const path = require('path');

describe('cursor service', () => {
  it('verifies Cursor API key via /v1/me', async () => {
    const fetchImpl = async (url, options) => ({
      ok: url === CURSOR_ME_URL && options.headers.Authorization === 'Bearer test-key'
    });

    await expect(verifyCursorApiKey('test-key', fetchImpl)).resolves.toBe(true);
    await expect(verifyCursorApiKey('bad-key', async () => ({ ok: false }))).resolves.toBe(false);
  });

  it('builds a prompt that includes the user question and knowledge context', async () => {
    const { baizeRoot } = await createTestRoot();
    const prompt = await buildUserPrompt({
      baizeRoot,
      message: { text: '白泽你好', platform: 'client', userId: 'u1', conversationId: 'c1' },
      knowledgeResults: [{ title: 'Doc', relativePath: 'kb/doc.md', snippet: 'hello world' }],
      conversationMessages: [{ role: 'user', text: '上一轮' }]
    });

    expect(prompt).toContain('白泽你好');
    expect(prompt).toContain('Doc');
    expect(prompt).toContain('hello world');
    expect(prompt).toContain('上一轮');
  });

  it('reads Cursor config from env and yaml without exposing secrets in public config', async () => {
    const { baizeRoot } = await createTestRoot();
    await fs.mkdir(path.join(baizeRoot, 'config'), { recursive: true });
    await fs.writeFile(path.join(baizeRoot, 'config', 'cursor.yaml'), [
      'cursor:',
      '  model: composer-2.5',
      '  workspacePath: /tmp/baize-workspace'
    ].join('\n'), 'utf8');

    const previousKey = process.env.CURSOR_SDK_KEY;
    process.env.CURSOR_SDK_KEY = 'secret-cursor-key';
    try {
      const config = await getCursorConfig({ baizeRoot });
      expect(config.apiKey).toBe('secret-cursor-key');
      expect(config.model).toBe('composer-2.5');
      expect(config.workspacePath).toBe('/tmp/baize-workspace');

      const publicConfig = await getPublicCursorConfig({ baizeRoot });
      expect(publicConfig).toEqual({
        apiKeyConfigured: true,
        model: 'composer-2.5',
        workspaceConfigured: true
      });
      expect(JSON.stringify(publicConfig)).not.toContain('secret-cursor-key');
    } finally {
      if (previousKey === undefined) {
        delete process.env.CURSOR_SDK_KEY;
      } else {
        process.env.CURSOR_SDK_KEY = previousKey;
      }
    }
  });
});

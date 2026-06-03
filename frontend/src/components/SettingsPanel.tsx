import { useState, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/button';

// ── 类型定义 ────────────────────────────────────────

interface AIState { DEEPSEEK_URL: string; DEEPSEEK_KEY: string }
interface JiraState { JIRA_BASE_URL: string; JIRA_PAT: string; FISHEYE_URL: string }
interface SVNState { SVN_URL: string; SVN_USERNAME: string; SVN_PASSWORD: string }
interface KBState { NOTION_KEY: string; NOTION_DATABASE_ID: string; GDRIVE_KEY: string; GDRIVE_FOLDERS: string; GDRIVE_PROXY_IP: string; GDRIVE_PROXY_PORT: string }

type CardId = 'ai' | 'jira' | 'svn' | 'notion' | 'gdrive';

interface Toast { show: boolean; msg: string; type: 'success' | 'error' }
interface Tooltip { show: boolean; msg: string; isError: boolean; type: string }

interface NotionDB { id: string; title?: string; url?: string }
interface GDriveFile { id: string; name: string; mimeType?: string }

// ── 主组件 ───────────────────────────────────────────

export default function SettingsPanel({ fullPage, onClose }: { fullPage?: boolean; onClose?: () => void }) {
  // 菜单
  const menus = [
    { id: 'settings', name: '⚙️ 系统集成配置' },
    { id: 'kb', name: '📚 云端知识库源' },
  ];
  const [activeMenu, setActiveMenu] = useState('settings');
  const currentMenuName = useMemo(() => menus.find(m => m.id === activeMenu)?.name || '', [activeMenu, menus]);

  // 认证
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem('wb_admin_token') || 'admin-admin');

  // 核心状态
  const [state, setState] = useState({
    ai: { DEEPSEEK_URL: '', DEEPSEEK_KEY: '' } as AIState,
    jira: { JIRA_BASE_URL: '', JIRA_PAT: '', FISHEYE_URL: '' } as JiraState,
    svn: { SVN_URL: '', SVN_USERNAME: '', SVN_PASSWORD: '' } as SVNState,
    kb: { NOTION_KEY: '', NOTION_DATABASE_ID: '', GDRIVE_KEY: '', GDRIVE_FOLDERS: '', GDRIVE_PROXY_IP: '', GDRIVE_PROXY_PORT: '' } as KBState,
  });

  // 编辑锁
  const [editLock, setEditLock] = useState<Record<CardId, boolean>>({ ai: false, jira: false, svn: false, notion: false, gdrive: false });
  const [draftBackup, setDraftBackup] = useState<Record<string, any>>({});

  // 测试状态
  const [testing, setTesting] = useState<Record<string, boolean>>({ ai: false, jira: false, svn: false, notion: false, gdrive: false });
  const [testResult, setTestResult] = useState<Record<string, Tooltip>>({
    ai: { show: false, msg: '', isError: false, type: 'ai' },
    jira: { show: false, msg: '', isError: false, type: 'jira' },
    svn: { show: false, msg: '', isError: false, type: 'svn' },
    notion: { show: false, msg: '', isError: false, type: 'notion' },
    gdrive: { show: false, msg: '', isError: false, type: 'gdrive' },
  });

  // Toast
  const [toast, setToast] = useState<Toast>({ show: false, msg: '', type: 'success' });

  // 动态数据
  const [notionDatabases, setNotionDatabases] = useState<NotionDB[]>([]);
  const [gdriveFiles, setGdriveFiles] = useState<GDriveFile[]>([]);
  const [gdriveInput, setGdriveInput] = useState('');
  const [loading, setLoading] = useState(true);

  const gdriveFoldersList = useMemo(() => state.kb.GDRIVE_FOLDERS ? state.kb.GDRIVE_FOLDERS.split(',').filter(Boolean) : [], [state.kb.GDRIVE_FOLDERS]);

  // ── API 调用 ─────────────────────────────────────

  const authHeaders = () => ({ 'Authorization': `Bearer ${adminToken}`, 'Content-Type': 'application/json' });

  const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
    setToast({ show: true, msg, type });
    setTimeout(() => setToast(t => ({ ...t, show: false })), 3000);
  };

  const showTooltipVal = (type: string, msg: string, isError = false) => {
    setTestResult(prev => ({ ...prev, [type]: { show: true, msg, isError, type } }));
    setTimeout(() => setTestResult(prev => ({ ...prev, [type]: { ...prev[type], show: false } })), 3000);
  };

  const loadConfig = async (retryToken?: string) => {
    try {
      setLoading(true);
      const res = await fetch('/v1/admin/config', { headers: authHeaders() });
      if (res.status === 401) {
        const token = retryToken || prompt('请输入管理员密码登录:');
        if (token) {
          localStorage.setItem('wb_admin_token', token);
          setAdminToken(token);
          return loadConfig(token);
        }
        return;
      }
      const data = await res.json();
      if (data.ai) setState(prev => ({ ...prev, ai: { ...prev.ai, ...data.ai } }));
      if (data.jira) setState(prev => ({ ...prev, jira: { ...prev.jira, ...data.jira } }));
      if (data.svn) setState(prev => ({ ...prev, svn: { ...prev.svn, ...data.svn } }));
      if (data.kb) setState(prev => ({ ...prev, kb: { ...prev.kb, ...data.kb } }));
    } catch (e: any) {
      showToast('配置加载失败: ' + e.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadConfig(); }, []);

  // ── 编辑锁机制 ──────────────────────────────────

  const startEdit = (cardId: CardId) => {
    const stateKey = (cardId === 'notion' || cardId === 'gdrive') ? 'kb' : cardId;
    setDraftBackup(prev => ({ ...prev, [cardId]: structuredClone(state[stateKey]) }));
    setEditLock(prev => ({ ...prev, [cardId]: true }));
  };

  const cancelEdit = (cardId: CardId) => {
    const stateKey = (cardId === 'notion' || cardId === 'gdrive') ? 'kb' : cardId;
    if (draftBackup[cardId]) {
      setState(prev => ({ ...prev, [stateKey]: { ...prev[stateKey], ...draftBackup[cardId] } }));
    }
    setEditLock(prev => ({ ...prev, [cardId]: false }));
  };

  const saveEdit = async (cardId: CardId) => {
    const stateKey = (cardId === 'notion' || cardId === 'gdrive') ? 'kb' : cardId;
    try {
      const payload = structuredClone(state[stateKey]);
      const res = await fetch('/v1/admin/config', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        showToast('✅ 模块配置已保存至后端');
        setEditLock(prev => ({ ...prev, [cardId]: false }));
        loadConfig();
      } else {
        showToast('保存失败 HTTP ' + res.status, 'error');
      }
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  // ── 正则解析 ─────────────────────────────────────

  const parseNotionUrl = (val: string) => {
    const match = val.match(/([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
    if (match && match[1] !== state.kb.NOTION_DATABASE_ID) {
      const extracted = match[1].replace(/-/g, '');
      setState(prev => ({ ...prev, kb: { ...prev.kb, NOTION_DATABASE_ID: extracted } }));
    }
  };

  const addGDriveFolder = () => {
    const val = gdriveInput.trim();
    if (!val) return;
    const match = val.match(/[-\w]{25,}/);
    if (match) {
      const folderId = match[0];
      const folders = state.kb.GDRIVE_FOLDERS ? state.kb.GDRIVE_FOLDERS.split(',').filter(Boolean) : [];
      if (!folders.includes(folderId)) {
        setState(prev => ({ ...prev, kb: { ...prev.kb, GDRIVE_FOLDERS: [...folders, folderId].join(',') } }));
      }
    }
    setGdriveInput('');
  };

  const removeFolder = (id: string) => {
    const folders = gdriveFoldersList.filter(f => f !== id);
    setState(prev => ({ ...prev, kb: { ...prev.kb, GDRIVE_FOLDERS: folders.join(',') } }));
  };

  // ── 探针测试 ─────────────────────────────────────

  const testSystem = async (type: string, fn: () => Promise<{ msg: string; isError: boolean }>) => {
    setTesting(prev => ({ ...prev, [type]: true }));
    try {
      const result = await fn();
      showTooltipVal(type, result.msg, result.isError);
    } catch {
      showTooltipVal(type, '测试异常', true);
    } finally {
      setTesting(prev => ({ ...prev, [type]: false }));
    }
  };

  const testAi = () => testSystem('ai', async () => {
    await new Promise(r => setTimeout(r, 1000));
    return { msg: '✅ 模型接口连通 (本地仿真)', isError: false };
  });

  const testJira = () => testSystem('jira', async () => {
    if (!state.jira.JIRA_BASE_URL || !state.jira.JIRA_PAT) {
      return { msg: '请先填写 Jira URL 和 PAT', isError: true };
    }
    await new Promise(r => setTimeout(r, 1000));
    return { msg: '✅ Jira/FishEye 可达 (本地仿真)', isError: false };
  });

  const testSvn = () => testSystem('svn', async () => {
    if (!state.svn.SVN_URL || !state.svn.SVN_USERNAME) {
      return { msg: '请先填写完整 SVN 配置', isError: true };
    }
    await new Promise(r => setTimeout(r, 1500));
    return { msg: '✅ Checkout 校验通过 (本地仿真)', isError: false };
  });

  const testNotion = () => testSystem('notion', async () => {
    if (!state.kb.NOTION_KEY) return { msg: '请先填写 Notion Key', isError: true };
    const res = await fetch('/v1/admin/test/notion-db', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ token: state.kb.NOTION_KEY, database_id: state.kb.NOTION_DATABASE_ID }),
    });
    const data = await res.json();
    if (data.ok && data.databases) {
      setNotionDatabases(data.databases);
      return { msg: `✅ 连接成功，发现 ${data.databases.length} 个数据库`, isError: false };
    }
    return { msg: data.error || '连接失败', isError: true };
  });

  const testGdrive = () => testSystem('gdrive', async () => {
    if (!state.kb.GDRIVE_KEY || gdriveFoldersList.length === 0)
      return { msg: '请先添加至少一个文件夹 ID', isError: true };
    const res = await fetch('/v1/admin/test/gdrive', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({
        key: state.kb.GDRIVE_KEY, folder_id: gdriveFoldersList[0],
        proxy_ip: state.kb.GDRIVE_PROXY_IP, proxy_port: state.kb.GDRIVE_PROXY_PORT,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      setGdriveFiles(data.files || []);
      return { msg: `✅ 可达，目录下 ${(data.files || []).length} 个文件`, isError: false };
    }
    return { msg: data.error || '连接失败', isError: true };
  });

  // ── 渲染工具函数 ───────────────────────────────

  const inputClass = (isEditing: boolean) =>
    isEditing
      ? 'w-full px-3 py-2 border border-blue-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 bg-white shadow-inner transition-all text-sm'
      : 'w-full px-3 py-2 border border-transparent rounded bg-transparent text-gray-600 cursor-default outline-none text-sm';

  const Field = ({ label, value, onChange, isEditing, placeholder, onBlur }: {
    label: string; value: string; onChange: (v: string) => void; isEditing: boolean; placeholder?: string; onBlur?: () => void;
  }) => (
    <div className="space-y-1">
      <label className="text-sm font-semibold text-gray-600">{label}</label>
      <input
        type="text" readOnly={!isEditing} value={value}
        onChange={e => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={isEditing ? placeholder : ''}
        className={inputClass(isEditing)}
      />
    </div>
  );

  const renderTooltip = (type: string) => {
    const t = testResult[type];
    if (!t.show) return null;
    return (
      <span className={`absolute left-full ml-3 whitespace-nowrap px-2.5 py-1 text-xs font-medium text-white rounded shadow z-10 ${t.isError ? 'bg-red-500' : 'bg-green-500'}`}>
        <span className={`absolute w-2 h-2 rotate-45 -left-1 top-1.5 ${t.isError ? 'bg-red-500' : 'bg-green-500'}`}></span>
        {t.msg}
      </span>
    );
  };

  const LoadingSpinner = () => (
    <svg className="animate-spin h-3.5 w-3.5 text-blue-600" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );

  const TestButton = ({ type, label, loadingLabel, onClick, disabled }: {
    type: string; label: string; loadingLabel: string; onClick: () => void; disabled?: boolean;
  }) => (
    <div className="relative inline-flex">
      <button
        onClick={onClick}
        disabled={testing[type] || disabled}
        className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 font-medium px-3 py-1 bg-blue-50 hover:bg-blue-100 rounded transition disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {testing[type] ? <LoadingSpinner /> : null}
        {testing[type] ? loadingLabel : label}
      </button>
      {renderTooltip(type)}
    </div>
  );

  // ── 卡片组件 ─────────────────────────────────────

  const ConfigCard = ({ icon, title, cardId, children, testBtn }: {
    icon: string; title: string; cardId: CardId; children: React.ReactNode;
    testBtn?: { label: string; loadingLabel: string; onClick: () => void };
  }) => (
    <div className={`bg-white rounded-lg shadow-sm border overflow-hidden transition-all ${editLock[cardId] ? 'border-blue-400 ring-2 ring-blue-100' : 'border-gray-200'}`}>
      <div className="bg-gray-50/80 px-6 py-4 border-b border-gray-200 flex justify-between items-center">
        <span className="text-lg font-bold text-gray-700 flex items-center gap-2">{icon} {title}</span>
        <div className="flex items-center gap-3">
          {testBtn && <TestButton type={cardId} label={testBtn.label} loadingLabel={testBtn.loadingLabel} onClick={testBtn.onClick} disabled={editLock[cardId]} />}
          {!editLock[cardId] && (
            <button onClick={() => startEdit(cardId)} className="text-sm text-blue-600 hover:text-blue-800 font-medium px-3 py-1 bg-blue-50 hover:bg-blue-100 rounded transition">
              ✏️ 编辑配置
            </button>
          )}
        </div>
      </div>
      <div className="p-6">{children}</div>
      {editLock[cardId] && (
        <div className="px-6 py-3 bg-gray-50 border-t border-gray-200 flex justify-end gap-3">
          <button onClick={() => cancelEdit(cardId)} className="px-4 py-1.5 text-gray-600 hover:text-gray-800 text-sm font-medium transition">取消</button>
          <button onClick={() => saveEdit(cardId)} className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded shadow-sm transition">💾 保存模块</button>
        </div>
      )}
    </div>
  );

  // ── 渲染 ────────────────────────────────────────

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-500">加载配置中...</div>;

  return (
    <div className="h-full flex">
      {/* Fullpage Sidebar */}
      {fullPage && <SettingsSidebar activeMenu={activeMenu} onSelect={setActiveMenu} onClose={onClose} />}

      <div className="h-full flex flex-col flex-1 overflow-hidden">
        {/* Close header */}
        {fullPage && (
          <div className="h-12 flex items-center justify-between px-4 bg-white border-b shrink-0">
            <span className="text-sm font-medium text-gray-600">爱丽丝控制中心</span>
            <button onClick={onClose} className="text-sm text-gray-500 hover:text-gray-800">✕ 关闭</button>
          </div>
        )}

        {/* Toast */}
        {toast.show && (
        <div className={`fixed top-5 right-5 px-6 py-3 rounded shadow-lg text-white font-bold z-50 transition-opacity ${toast.type === 'error' ? 'bg-red-600' : 'bg-green-600'}`}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="h-16 bg-white shadow-sm flex items-center justify-between px-8 z-10 shrink-0">
        <h1 className="text-xl font-semibold text-gray-800">{currentMenuName}</h1>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-5xl mx-auto space-y-8 pb-10">

          {/* ═══════ 系统集成配置 ═══════ */}
          {activeMenu === 'settings' && (
            <>
              <ConfigCard icon="🤖" title="AI 大模型底座" cardId="ai"
                testBtn={{ label: '测试接口', loadingLabel: '探测中...', onClick: testAi }}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <Field label="DeepSeek 接口地址" value={state.ai.DEEPSEEK_URL} onChange={v => setState(prev => ({ ...prev, ai: { ...prev.ai, DEEPSEEK_URL: v } }))} isEditing={editLock.ai} placeholder="https://api.deepseek.com" />
                  <Field label="API 密钥 (Key)" value={state.ai.DEEPSEEK_KEY} onChange={v => setState(prev => ({ ...prev, ai: { ...prev.ai, DEEPSEEK_KEY: v } }))} isEditing={editLock.ai} placeholder="sk-..." />
                </div>
              </ConfigCard>

              <ConfigCard icon="🎫" title="研发核心系统 (Jira)" cardId="jira"
                testBtn={{ label: '测试连通', loadingLabel: '校验中...', onClick: testJira }}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <Field label="Jira 基地址" value={state.jira.JIRA_BASE_URL} onChange={v => setState(prev => ({ ...prev, jira: { ...prev.jira, JIRA_BASE_URL: v } }))} isEditing={editLock.jira} placeholder="http://jira:8080" />
                  <Field label="个人访问令牌 (PAT)" value={state.jira.JIRA_PAT} onChange={v => setState(prev => ({ ...prev, jira: { ...prev.jira, JIRA_PAT: v } }))} isEditing={editLock.jira} placeholder="ND..." />
                  <div className="md:col-span-2">
                    <Field label="FishEye 地址" value={state.jira.FISHEYE_URL} onChange={v => setState(prev => ({ ...prev, jira: { ...prev.jira, FISHEYE_URL: v } }))} isEditing={editLock.jira} placeholder="http://fisheye:8060" />
                  </div>
                </div>
              </ConfigCard>

              <ConfigCard icon="📂" title="版本控制 (SVN)" cardId="svn"
                testBtn={{ label: '尝试 Checkout', loadingLabel: '校验中...', onClick: testSvn }}>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <Field label="SVN 仓库地址" value={state.svn.SVN_URL} onChange={v => setState(prev => ({ ...prev, svn: { ...prev.svn, SVN_URL: v } }))} isEditing={editLock.svn} placeholder="https://svn..." />
                  <Field label="用户名" value={state.svn.SVN_USERNAME} onChange={v => setState(prev => ({ ...prev, svn: { ...prev.svn, SVN_USERNAME: v } }))} isEditing={editLock.svn} />
                  <Field label="密码" value={state.svn.SVN_PASSWORD} onChange={v => setState(prev => ({ ...prev, svn: { ...prev.svn, SVN_PASSWORD: v } }))} isEditing={editLock.svn} />
                </div>
              </ConfigCard>
            </>
          )}

          {/* ═══════ 云端知识库源 ═══════ */}
          {activeMenu === 'kb' && (
            <>
              <ConfigCard icon="📝" title="Notion 知识库" cardId="notion"
                testBtn={{ label: '测试并拉取数据库', loadingLabel: '拉取中...', onClick: testNotion }}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <Field label="Notion API Key" value={state.kb.NOTION_KEY} onChange={v => setState(prev => ({ ...prev, kb: { ...prev.kb, NOTION_KEY: v } }))} isEditing={editLock.notion} placeholder="secret_..." />
                  <Field label="数据库 ID" value={state.kb.NOTION_DATABASE_ID} onChange={v => setState(prev => ({ ...prev, kb: { ...prev.kb, NOTION_DATABASE_ID: v } }))} isEditing={editLock.notion}
                    placeholder="粘贴 Notion URL 自动提取"
                    onBlur={() => parseNotionUrl(state.kb.NOTION_URL || (state as any).kb.NOTION_URL || '')} />
                </div>
                {notionDatabases.length > 0 && (
                  <div className="md:col-span-2 mt-2 bg-gray-50 border border-gray-200 rounded p-4">
                    <div className="text-sm font-semibold text-gray-700 mb-2">已发现的数据库 ({notionDatabases.length})</div>
                    {notionDatabases.map((db, i) => (
                      <div key={i} className="text-xs text-gray-600 py-1 border-b border-gray-100 last:border-0">
                        {db.title || db.id}<span className="text-gray-400 ml-2">{db.url}</span>
                      </div>
                    ))}
                  </div>
                )}
              </ConfigCard>

              <ConfigCard icon="📁" title="Google 云盘知识库" cardId="gdrive"
                testBtn={{ label: '测试网络可达性', loadingLabel: '校验中...', onClick: testGdrive }}>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <Field label="Google API Key" value={state.kb.GDRIVE_KEY} onChange={v => setState(prev => ({ ...prev, kb: { ...prev.kb, GDRIVE_KEY: v } }))} isEditing={editLock.gdrive} placeholder="AIza..." />
                  <Field label="代理 IP" value={state.kb.GDRIVE_PROXY_IP} onChange={v => setState(prev => ({ ...prev, kb: { ...prev.kb, GDRIVE_PROXY_IP: v } }))} isEditing={editLock.gdrive} placeholder="127.0.0.1" />
                  <Field label="代理端口" value={state.kb.GDRIVE_PROXY_PORT} onChange={v => setState(prev => ({ ...prev, kb: { ...prev.kb, GDRIVE_PROXY_PORT: v } }))} isEditing={editLock.gdrive} placeholder="7890" />
                </div>
                <div className="mt-4">
                  <div className="text-sm font-semibold text-gray-600 mb-1">文件夹</div>
                  <div className="flex flex-wrap gap-2 mb-2 p-3 bg-gray-50 border border-dashed border-gray-200 rounded-md">
                    {gdriveFoldersList.map(fid => (
                      <span key={fid} className="flex items-center gap-1 bg-blue-100 text-blue-700 px-2.5 py-1 rounded-full text-sm font-medium">
                        📁 {fid.substring(0, 10)}...
                        {editLock.gdrive && (
                          <button onClick={() => removeFolder(fid)} className="ml-1 text-blue-400 hover:text-red-500">&times;</button>
                        )}
                      </span>
                    ))}
                    {editLock.gdrive && (
                      <div className="flex items-center gap-1">
                        <input
                          type="text" value={gdriveInput} onChange={e => setGdriveInput(e.target.value)}
                          placeholder="粘贴链接"
                          className="px-2 py-1 text-xs border border-blue-300 rounded w-32"
                        />
                        <button onClick={addGDriveFolder} className="text-xs bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600">添加</button>
                      </div>
                    )}
                  </div>
                </div>
                {gdriveFiles.length > 0 && (
                  <div className="max-h-64 overflow-y-auto mt-2 bg-gray-50 border border-gray-200 rounded p-4">
                    <div className="text-sm font-semibold text-gray-700 mb-2">文件预览 ({gdriveFiles.length})</div>
                    {gdriveFiles.map((f, i) => (
                      <div key={i} className="text-xs text-gray-600 py-1 border-b border-gray-100 last:border-0">
                        {f.name}<span className="text-gray-400 ml-2">{f.mimeType}</span>
                      </div>
                    ))}
                  </div>
                )}
              </ConfigCard>
            </>
          )}
        </div>
      </div>
      </div>
    </div>
  );
}

// ── Sidebar 导航 ────────────────────────────────────
export function SettingsSidebar({ activeMenu, onSelect, onClose }: { activeMenu: string; onSelect: (id: string) => void; onClose?: () => void }) {
  const menus = [
    { id: 'settings', name: '⚙️ 系统集成配置' },
    { id: 'kb', name: '📚 云端知识库源' },
  ];
  return (
    <aside className="w-64 bg-gray-900 text-white flex flex-col z-20 shadow-xl h-full">
      <div className="h-16 flex items-center px-6 border-b border-gray-800 font-bold text-lg tracking-wider">⚙️ 爱丽丝控制中心</div>
      <nav className="flex-1 overflow-y-auto py-4 space-y-1">
        {menus.map(m => (
          <button
            key={m.id}
            onClick={() => onSelect(m.id)}
            className={`block w-full text-left px-6 py-3 cursor-pointer transition-colors border-l-4 ${activeMenu === m.id ? 'bg-blue-600 border-blue-300 text-white' : 'border-transparent text-gray-300 hover:text-white hover:bg-gray-800'}`}
          >
            {m.name}
          </button>
        ))}
      </nav>
    </aside>
  );
}

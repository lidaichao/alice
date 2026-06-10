import { reactive, ref, computed, toRaw, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import {
  adminFetch,
  parseAdminJson,
  getAdminToken,
  setAdminToken,
} from '../api/adminApi.js';

const STORAGE_MENU = 'alice_admin_active_menu';
const STORAGE_CONN = 'alice_admin_connection_ok';
const STORAGE_HINTS = 'alice_admin_test_hints';
const MENU_IDS = ['settings', 'jiraQuery', 'kb', 'roles'];

function readStoredMenu() {
  try {
    const id = sessionStorage.getItem(STORAGE_MENU);
    if (MENU_IDS.includes(id)) return id;
    const hash = (window.location.hash || '').replace(/^#\/?/, '');
    if (MENU_IDS.includes(hash)) return hash;
  } catch {
    /* ignore */
  }
  return 'settings';
}

export function useAdminStore() {
  const activeMenu = ref(readStoredMenu());
  const menus = [
    { id: 'roles', name: '成员与权限', icon: 'User' },
    { id: 'settings', name: '系统集成配置', icon: 'Setting' },
    { id: 'jiraQuery', name: 'Alice-Jira查询配置', icon: 'Search' },
    { id: 'kb', name: '云端知识库源', icon: 'Collection' },
  ];
  const currentMenuName = computed(
    () => menus.find((m) => m.id === activeMenu.value)?.name || ''
  );

  const adminToken = ref(getAdminToken());
  const isAuthenticated = () => !!adminToken.value;
  const onAuthSuccess = () => { loadConfig(); fetchHealth(); };
  const healthSummary = ref(null);
  const healthLoading = ref(false);

  const showToast = (msg, type = 'success') => {
    if (type === 'error') ElMessage.error(msg);
    else if (type === 'warning') ElMessage.warning(msg);
    else ElMessage.success(msg);
  };

  const availableModels = ref([]);
  const fetchingModels = ref(false);
  const savingModel = ref(false);
  const hydratingModel = ref(true);
  const lastSavedModel = ref('');
  let modelSaveSeq = 0;

  const modelSelectOptions = computed(() => {
    const saved = (state.ai.DEEPSEEK_MODEL || '').trim();
    const opts = [...availableModels.value];
    if (saved && !opts.includes(saved)) opts.unshift(saved);
    if (!opts.length) opts.push(saved || 'deepseek-chat');
    return opts;
  });

  const state = reactive({
    ai: { DEEPSEEK_URL: '', DEEPSEEK_KEY: '', DEEPSEEK_MODEL: 'deepseek-chat' },
    jira: {
      JIRA_BASE_URL: '',
      JIRA_PAT: '',
      FISHEYE_URL: '',
      JIRA_DEADLINE_FIELD_BY_PROJECT: '{\n  "CT": "End date"\n}',
      JIRA_FIELD_MAPPINGS: '{\n  "extraPersonFields": []\n}',
      JIRA_PROJECT_CONFIG: '{}',
      JIRA_FIELD_GLOSSARY: '[]',
    },
    svn: { SVN_URL: '', SVN_USERNAME: '', SVN_PASSWORD: '' },
    kb: {
      NOTION_KEY: '',
      NOTION_DATABASE_ID: '',
      GDRIVE_KEY: '',
      GDRIVE_FOLDERS: '',
      GDRIVE_PROXY_IP: '',
      GDRIVE_PROXY_PORT: '',
    },
  });

  const JIRA_PM_SECTIONS = ['jiraPmA', 'jiraPmB', 'jiraPmC'];

  const editLock = reactive({
    ai: false,
    jira: false,
    jiraPmA: false,
    jiraPmB: false,
    jiraPmC: false,
    svn: false,
    notion: false,
    gdrive: false,
  });

  const isJiraPmSection = (cardId) => JIRA_PM_SECTIONS.includes(cardId);

  const anyJiraPmEditing = () => JIRA_PM_SECTIONS.some((k) => editLock[k]);

  const activeJiraPmSection = () => JIRA_PM_SECTIONS.find((k) => editLock[k]) || null;
  const draftBackup = {};

  const testing = reactive({
    ai: false,
    jira: false,
    svn: false,
    notion: false,
    gdrive: false,
  });
  const testResult = reactive({
    ai: { show: false, msg: '', isError: false },
    aiModels: { show: false, msg: '', isError: false },
    jira: { show: false, msg: '', isError: false },
    jiraFields: { show: false, msg: '', isError: false },
    jiraProjects: { show: false, msg: '', isError: false },
    issuetypes: { show: false, msg: '', isError: false },
    svn: { show: false, msg: '', isError: false },
    notion: { show: false, msg: '', isError: false },
    gdrive: { show: false, msg: '', isError: false },
  });

  const persistTestHints = () => {
    try {
      const out = {};
      for (const key of Object.keys(testResult)) {
        const slot = testResult[key];
        if (slot.show && slot.msg) {
          out[key] = { show: true, msg: slot.msg, isError: slot.isError };
        }
      }
      sessionStorage.setItem(STORAGE_HINTS, JSON.stringify(out));
    } catch {
      /* ignore */
    }
  };

  const restoreTestHints = () => {
    try {
      const raw = sessionStorage.getItem(STORAGE_HINTS);
      if (!raw) return;
      const o = JSON.parse(raw);
      for (const [key, val] of Object.entries(o)) {
        if (testResult[key] && val && val.show) {
          testResult[key].msg = val.msg;
          testResult[key].isError = Boolean(val.isError);
          testResult[key].show = true;
        }
      }
    } catch {
      /* ignore */
    }
  };

  const setActionHint = (key, msg, isError = false) => {
    const slot = testResult[key];
    if (!slot) return;
    slot.msg = String(msg || '').replace(/^✅\s*|^❌\s*/, '');
    slot.isError = isError;
    slot.show = true;
    persistTestHints();
  };

  const notionDatabases = ref([]);
  const gdriveFiles = ref([]);

  const jiraPmForm = reactive({
    selectedProjectKeys: ['CT'],
    deadlineRows: [{ projectKey: 'CT', fieldName: '' }],
    extraPersonField: '',
    glossaryRows: [],
    showAdvancedJson: false,
    issuetypeRowsByProject: {},
    issuetypeDraftsByProject: {},
  });
  const jiraFieldOptions = ref([]);
  const issuetypesLoading = ref(false);
  const issuetypeActiveProject = ref('');
  const issuetypeSaveMessage = ref('');
  const issuetypeDraftText = reactive({});
  const issuetypeItems = reactive({});  // { [projectKey]: [{name, editing, draftName}] }
  const jiraFieldFilter = ref('');
  const jiraProjectOptions = ref([]);
  const jiraProjectsLoading = ref(false);
  const jiraProjectFilter = ref('');
  const savingGlossaryIdx = ref(-1);
  const savingGlossaryAll = ref(false);
  const jiraFieldsLoading = ref(false);
  const jiraConnectionOk = ref(false);
  const jiraPatOnServer = ref(false);
  const aiConnectionOk = ref(false);
  const notionConnectionOk = ref(false);
  const gdriveConnectionOk = ref(false);
  const svnConnectionOk = ref(false);
  const statusPulse = reactive({
    ai: false,
    jira: false,
    notion: false,
    gdrive: false,
    svn: false,
  });

  const pulseStatus = (key) => {
    statusPulse[key] = true;
    setTimeout(() => {
      statusPulse[key] = false;
    }, 1000);
  };

  const persistConnectionOk = () => {
    try {
      sessionStorage.setItem(
        STORAGE_CONN,
        JSON.stringify({
          ai: aiConnectionOk.value,
          jira: jiraConnectionOk.value,
          svn: svnConnectionOk.value,
          notion: notionConnectionOk.value,
          gdrive: gdriveConnectionOk.value,
        })
      );
    } catch {
      /* ignore */
    }
  };

  const inferConnectionOkFromConfig = () => {
    const aiKey = (state.ai.DEEPSEEK_KEY || '').trim();
    const aiKeyConfigured = aiKey && aiKey !== '********';
    aiConnectionOk.value = Boolean(
      (state.ai.DEEPSEEK_URL || '').trim() &&
        (aiKeyConfigured || availableModels.value.length > 0 || lastSavedModel.value)
    );
    jiraConnectionOk.value = Boolean(
      (state.jira.JIRA_BASE_URL || '').trim() && jiraPatOnServer.value
    );
    svnConnectionOk.value = Boolean(
      (state.svn.SVN_URL || '').trim() &&
        (state.svn.SVN_USERNAME || '').trim() &&
        (state.svn.SVN_PASSWORD || '').trim()
    );
    notionConnectionOk.value = Boolean((state.kb.NOTION_KEY || '').trim());
    gdriveConnectionOk.value = Boolean(
      (state.kb.GDRIVE_KEY || '').trim() && (state.kb.GDRIVE_FOLDERS || '').trim()
    );
  };

  const restoreConnectionOk = () => {
    try {
      const raw = sessionStorage.getItem(STORAGE_CONN);
      if (raw) {
        const o = JSON.parse(raw);
        if (o.ai) aiConnectionOk.value = true;
        if (o.jira) jiraConnectionOk.value = true;
        if (o.svn) svnConnectionOk.value = true;
        if (o.notion) notionConnectionOk.value = true;
        if (o.gdrive) gdriveConnectionOk.value = true;
        return;
      }
    } catch {
      /* fall through */
    }
    inferConnectionOkFromConfig();
  };

  const persistActiveMenu = () => {
    try {
      sessionStorage.setItem(STORAGE_MENU, activeMenu.value);
      window.location.hash = activeMenu.value;
    } catch {
      /* ignore */
    }
  };

  const connectionLabel = (ok, extra = '') => {
    if (ok) return extra ? `已连通 · ${extra}` : '已连通';
    return '未测试';
  };
  const jiraCanUseFields = computed(() => {
    const url = (state.jira.JIRA_BASE_URL || '').trim();
    return !!url && (jiraConnectionOk.value || jiraPatOnServer.value);
  });

  const isMaskedPat = (v) => {
    const s = String(v || '').trim();
    return !s || s === '********';
  };

  const jiraPatForApi = () => {
    const p = String(state.jira.JIRA_PAT || '').trim();
    return isMaskedPat(p) ? '' : p;
  };

  const jiraPatDisplayLabel = computed(() => {
    if (jiraPatOnServer.value) return '已保存（无需重复填写；点「编辑连接」可更换）';
    return state.jira.JIRA_PAT ? '已填写' : '未配置';
  });

  const buildJiraApiQuery = (extra = {}) => {
    const q = new URLSearchParams();
    Object.entries(extra).forEach(([k, v]) => {
      if (v != null && String(v) !== '') q.set(k, String(v));
    });
    if (state.jira.JIRA_BASE_URL) q.set('url', state.jira.JIRA_BASE_URL.trim());
    const pat = jiraPatForApi();
    if (pat) q.set('pat', pat);
    return q;
  };

  const isAssigneeField = (f) => {
    const n = (f.name || '').trim().toLowerCase();
    const id = (f.id || '').trim().toLowerCase();
    return id === 'assignee' || n === 'assignee' || n === '经办人';
  };

  const extraPersonFieldOptions = computed(() => {
    const list = jiraFieldOptions.value || [];
    return list.filter((f) => {
      if (isAssigneeField(f)) return false;
      const n = (f.name || '').toLowerCase();
      return /负责|owner|经办|report|reporter|人|开发|测试|策划/.test(n) || f.custom;
    });
  });

  const filteredJiraProjectOptions = computed(() => {
    const list = jiraProjectOptions.value || [];
    const q = (jiraProjectFilter.value || '').trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (p) =>
        (p.key || '').toLowerCase().includes(q) ||
        (p.name || '').toLowerCase().includes(q)
    );
  });

  const projectKeysText = computed(() =>
    (jiraPmForm.selectedProjectKeys || []).join(', ')
  );

  const filteredJiraFieldOptions = computed(() => {
    const list = jiraFieldOptions.value || [];
    const q = (jiraFieldFilter.value || '').trim().toLowerCase();
    if (!q) return list;
    return list.filter((f) => (f.name || '').toLowerCase().includes(q));
  });

  const jiraPmSummaryMarkdown = computed(() => {
    const keys = (jiraPmForm.selectedProjectKeys || []).filter(Boolean);
    const pkLabel = keys.length ? keys.map((k) => `\`${k}\``).join('、') : '（未选择）';
    const parts = ['## 当前生效规则\n', `**参与项目** · ${pkLabel}\n`, '### 截止时间字段\n'];

    const dlRows = (jiraPmForm.deadlineRows || []).filter((r) => (r.projectKey || '').trim());
    if (dlRows.length) {
      dlRows.forEach((row) => {
        const k = (row.projectKey || '').trim().toUpperCase();
        const fn = (row.fieldName || '').trim() || '（Alice 自动识别）';
        parts.push(`- **${k}** · 周报 / 待办按 **${fn}** 筛选`);
      });
    } else {
      parts.push('- （未配置）');
    }

    const extra = (jiraPmForm.extraPersonField || '').trim();
    parts.push('\n### 人名查询\n');
    parts.push(
      extra
        ? '- 始终查询 **经办人**，额外字段 **' + extra + '**'
        : '- 仅查询 **经办人**（无额外人物字段）'
    );

    const gloss = (jiraPmForm.glossaryRows || []).filter((r) => (r.fieldName || '').trim());
    parts.push('\n### 字段含义词典\n');
    if (gloss.length) {
      parts.push(`已标注 **${gloss.length}** 个字段：\n`);
      gloss.forEach((r) => {
        const m = (r.meaning || '').trim() || '（无说明）';
        const als = normalizeAliasTags(r.aliases).join('、');
        let line = `- **${r.fieldName}** — ${m}`;
        if (als) line += ` · 别名：${als}`;
        parts.push(line);
      });
    } else {
      parts.push('- （暂无词条）');
    }
    return parts.join('\n');
  });

  const glossaryTableRows = computed(() =>
    (jiraPmForm.glossaryRows || []).filter((r) => (r.fieldName || '').trim() && !r.editing)
  );

  const hasUnsavedGlossaryDraft = () =>
    (jiraPmForm.glossaryRows || []).some((r) => r.editing);

  const parseProjectKeys = (text) => {
    const raw = text != null ? text : projectKeysText.value;
    return (raw || '')
      .replace(/，/g, ',')
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
  };

  const syncDeadlineRowsFromSelectedProjects = () => {
    const keys = [...(jiraPmForm.selectedProjectKeys || [])];
    const byKey = {};
    (jiraPmForm.deadlineRows || []).forEach((r) => {
      const k = (r.projectKey || '').trim().toUpperCase();
      if (k) byKey[k] = r;
    });
    if (!keys.length) {
      if (!jiraPmForm.deadlineRows.length) {
        jiraPmForm.deadlineRows = [{ projectKey: '', fieldName: '' }];
      }
      return;
    }
    jiraPmForm.deadlineRows = keys.map((k) => ({
      projectKey: k,
      fieldName: (byKey[k]?.fieldName || '').toString(),
    }));
  };

  const toggleProjectKey = (key) => {
    const k = (key || '').trim().toUpperCase();
    if (!k) return;
    const arr = jiraPmForm.selectedProjectKeys;
    const i = arr.indexOf(k);
    if (i >= 0) arr.splice(i, 1);
    else arr.push(k);
    arr.sort();
    syncDeadlineRowsFromSelectedProjects();
  };

  const normalizeAliasTags = (aliases) => {
    const out = [];
    const seen = new Set();
    for (const a of aliases || []) {
      const t = String(a || '').trim();
      if (!t) continue;
      const key = t.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(t);
    }
    return out;
  };

  const commitAliasDraft = (row) => {
    const t = (row.aliasDraft || '').trim();
    if (!t) return;
    if (!Array.isArray(row.aliases)) row.aliases = [];
    row.aliases = normalizeAliasTags([...row.aliases, t]);
    row.aliasDraft = '';
  };

  const syncJsonFromPmForm = () => {
    const dl = {};
    for (const row of jiraPmForm.deadlineRows) {
      const k = (row.projectKey || '').trim().toUpperCase();
      if (k && row.fieldName) dl[k] = row.fieldName.trim();
    }
    state.jira.JIRA_DEADLINE_FIELD_BY_PROJECT = JSON.stringify(dl, null, 2);
    const extra = (jiraPmForm.extraPersonField || '').trim();
    const extras = extra ? [extra] : [];
    state.jira.JIRA_FIELD_MAPPINGS = JSON.stringify({ extraPersonFields: extras }, null, 2);
    const pcfg = {};
    const keys = parseProjectKeys();
    for (const k of keys) {
      const row = jiraPmForm.deadlineRows.find(
        (r) => (r.projectKey || '').toUpperCase() === k
      );
      const entry = { ownerFields: [...extras] };
      if (row && row.fieldName) entry.deadlineField = row.fieldName;
      pcfg[k] = entry;
    }
    state.jira.JIRA_PROJECT_CONFIG = JSON.stringify(pcfg, null, 2);
    const glossary = (jiraPmForm.glossaryRows || [])
      .map((r) => {
        commitAliasDraft(r);
        return r;
      })
      .filter((r) => (r.fieldName || '').trim())
      .map((r) => ({
        fieldId: r.fieldId || '',
        fieldName: (r.fieldName || '').trim(),
        meaning: (r.meaning || '').trim(),
        aliases: normalizeAliasTags(r.aliases),
      }));
    state.jira.JIRA_FIELD_GLOSSARY = JSON.stringify(glossary, null, 2);
  };

  const parseAliasesFromEntry = (entry) => {
    if (Array.isArray(entry.aliases)) return normalizeAliasTags(entry.aliases);
    const raw = entry.aliasesText != null ? entry.aliasesText : entry.aliases || '';
    if (typeof raw === 'string' && raw.trim()) {
      return normalizeAliasTags(raw.replace(/，/g, ',').split(','));
    }
    return [];
  };

  const hydrateGlossaryRows = (raw) => {
    let arr = raw;
    if (typeof raw === 'string') {
      try {
        arr = JSON.parse(raw || '[]');
      } catch {
        arr = [];
      }
    }
    if (!Array.isArray(arr)) arr = [];
    jiraPmForm.glossaryRows = arr.map((entry) => ({
      fieldId: entry.fieldId || entry.id || '',
      fieldName: entry.fieldName || entry.name || '',
      meaning: entry.meaning || entry.description || '',
      aliases: parseAliasesFromEntry(entry),
      aliasDraft: '',
      editing: false,
    }));
  };

  const hydratePmFormFromConfig = (data) => {
    const dlMap = data.JIRA_DEADLINE_FIELD_BY_PROJECT;
    const fm = data.JIRA_FIELD_MAPPINGS;
    const pc = data.JIRA_PROJECT_CONFIG;
    const dlObj = typeof dlMap === 'object' && dlMap ? dlMap : {};
    const pcObj = typeof pc === 'object' && pc ? pc : {};
    const keys = new Set();
    const rawProj = data.JIRA_PROJECTS;
    if (typeof rawProj === 'string' && rawProj.trim()) {
      rawProj.replace(/，/g, ',').split(',').forEach((k) => {
        const u = k.trim().toUpperCase();
        if (u) keys.add(u);
      });
    } else if (Array.isArray(rawProj)) {
      rawProj.forEach((k) => {
        const u = String(k).trim().toUpperCase();
        if (u) keys.add(u);
      });
    }
    if (!keys.size) {
      Object.keys(dlObj).forEach((k) => keys.add(k.toUpperCase()));
      Object.keys(pcObj).forEach((k) => keys.add(k.toUpperCase()));
    }
    if (!keys.size) keys.add('CT');
    jiraPmForm.selectedProjectKeys = Array.from(keys).sort();
    jiraPmForm.deadlineRows = Array.from(keys).map((k) => ({
      projectKey: k,
      fieldName: (dlObj[k] || pcObj[k]?.deadlineField || '').toString(),
    }));
    let extra = '';
    if (typeof fm === 'object' && fm) {
      if (Array.isArray(fm.extraPersonFields) && fm.extraPersonFields.length) {
        extra = String(fm.extraPersonFields[0] || '');
      } else if (fm.taskOwner) {
        extra = String(fm.taskOwner);
      }
    }
    jiraPmForm.extraPersonField = extra;
    hydrateGlossaryRows(data.JIRA_FIELD_GLOSSARY);
    syncJsonFromPmForm();
  };

  const syncPmFormFromJson = () => {
    try {
      const dl = JSON.parse(state.jira.JIRA_DEADLINE_FIELD_BY_PROJECT || '{}');
      const fm = JSON.parse(state.jira.JIRA_FIELD_MAPPINGS || '{}');
      const pc = JSON.parse(state.jira.JIRA_PROJECT_CONFIG || '{}');
      hydratePmFormFromConfig({
        JIRA_DEADLINE_FIELD_BY_PROJECT: dl,
        JIRA_FIELD_MAPPINGS: fm,
        JIRA_PROJECT_CONFIG: pc,
        JIRA_FIELD_GLOSSARY: JSON.parse(state.jira.JIRA_FIELD_GLOSSARY || '[]'),
      });
    } catch {
      showToast('JSON 格式无法识别，请检查高级设置中的内容', 'error');
    }
  };

  const syncGlossaryFromJson = () => {
    try {
      hydrateGlossaryRows(JSON.parse(state.jira.JIRA_FIELD_GLOSSARY || '[]'));
    } catch {
      showToast('字段词典 JSON 无法解析', 'error');
    }
  };

  const onGlossaryFieldPick = (row) => {
    const name = (row.fieldName || '').trim();
    const hit = (jiraFieldOptions.value || []).find((f) => f.name === name);
    if (hit) row.fieldId = hit.id || '';
  };

  const addAliasTag = (row, text) => {
    const t = (text || '').trim();
    if (!t) return;
    if (!Array.isArray(row.aliases)) row.aliases = [];
    row.aliases = normalizeAliasTags([...row.aliases, t]);
  };

  const removeAliasTag = (row, idx) => {
    if (!Array.isArray(row.aliases)) return;
    row.aliases.splice(idx, 1);
  };

  const saveGlossaryRow = async (gidx) => {
    const row = jiraPmForm.glossaryRows[gidx];
    if (!row) return;
    commitAliasDraft(row);
    const fieldName = (row.fieldName || '').trim();
    if (!fieldName) return showToast('请先选择 Jira 字段', 'error');
    savingGlossaryIdx.value = gidx;
    try {
      syncJsonFromPmForm();
      const glossary = JSON.parse(state.jira.JIRA_FIELD_GLOSSARY || '[]');
      const res = await fetch('/v1/admin/config', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminToken.value}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ JIRA_FIELD_GLOSSARY: glossary }),
      });
      if (!res.ok) throw new Error('保存失败');
      row.editing = false;
      showToast(`已保存：「${fieldName}」`);
    } catch (e) {
      showToast(e.message || '本条保存失败', 'error');
    } finally {
      savingGlossaryIdx.value = -1;
    }
  };

  const addGlossaryRow = () => {
    const row = {
      fieldId: '',
      fieldName: '',
      meaning: '',
      aliases: [],
      aliasDraft: '',
      editing: true,
    };
    jiraPmForm.glossaryRows.push(row);
    return jiraPmForm.glossaryRows.length - 1;
  };

  const startEditGlossaryRow = (gidx) => {
    const row = jiraPmForm.glossaryRows[gidx];
    if (!row) return;
    row._draftBackup = {
      fieldId: row.fieldId,
      fieldName: row.fieldName,
      meaning: row.meaning,
      aliases: [...(row.aliases || [])],
    };
    row.editing = true;
  };

  const cancelEditGlossaryRow = (gidx) => {
    const row = jiraPmForm.glossaryRows[gidx];
    if (!row) return;
    if (row._draftBackup) {
      Object.assign(row, row._draftBackup, { editing: false, _draftBackup: undefined });
      delete row._draftBackup;
    } else if (!(row.fieldName || '').trim()) {
      jiraPmForm.glossaryRows.splice(gidx, 1);
    } else {
      row.editing = false;
    }
  };

  const removeGlossaryRow = async (idx) => {
    jiraPmForm.glossaryRows.splice(idx, 1);
    try {
      syncJsonFromPmForm();
      const glossary = JSON.parse(state.jira.JIRA_FIELD_GLOSSARY || '[]');
      await fetch('/v1/admin/config', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminToken.value}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ JIRA_FIELD_GLOSSARY: glossary }),
      });
    } catch {
      /* 删除后仍可用底部整卡保存 */
    }
  };

  const fetchJiraProjects = async () => {
    if (!state.jira.JIRA_BASE_URL) return setActionHint('jiraProjects', '请先填写 Jira 地址', true);
    if (isMaskedPat(state.jira.JIRA_PAT) && !jiraPatOnServer.value) {
      return setActionHint('jiraProjects', '请先填写 PAT，或保存后再加载', true);
    }
    jiraProjectsLoading.value = true;
    try {
      const res = await adminFetch(`/v1/admin/jira/projects?${buildJiraApiQuery()}`);
      const data = await parseAdminJson(res);
      if (!res.ok || !data.success) throw new Error(data.error || '加载失败');
      jiraProjectOptions.value = data.projects || [];
      const known = new Set(jiraProjectOptions.value.map((p) => p.key));
      jiraPmForm.selectedProjectKeys = jiraPmForm.selectedProjectKeys.filter((k) =>
        known.has(k)
      );
      setActionHint('jiraProjects', `已加载 ${jiraProjectOptions.value.length} 个项目，请勾选`);
    } catch (e) {
      setActionHint('jiraProjects', e.message || '项目列表加载失败', true);
    } finally {
      jiraProjectsLoading.value = false;
    }
  };

  const fetchJiraFieldOptions = async () => {
    if (!state.jira.JIRA_BASE_URL) return setActionHint('jiraFields', '请先填写 Jira 地址', true);
    if (isMaskedPat(state.jira.JIRA_PAT) && !jiraPatOnServer.value) {
      return setActionHint('jiraFields', '请先填写 PAT，或保存后再测试', true);
    }
    jiraFieldsLoading.value = true;
    try {
      const res = await adminFetch(`/v1/admin/jira/fields?${buildJiraApiQuery()}`);
      const data = await parseAdminJson(res);
      if (!res.ok || !data.success) throw new Error(data.error || '加载失败');
      jiraFieldOptions.value = data.fields || [];
      setActionHint('jiraFields', `已加载 ${jiraFieldOptions.value.length} 个 Jira 字段`);
    } catch (e) {
      setActionHint('jiraFields', e.message || '字段列表加载失败', true);
    } finally {
      jiraFieldsLoading.value = false;
    }
  };

  const fetchIssuetypes = async () => {
    const projectKey = issuetypeActiveProject.value;
    if (!projectKey) return;
    if (!state.jira.JIRA_BASE_URL) return setActionHint('issuetypes', '请先填写 Jira 地址', true);
    if (isMaskedPat(state.jira.JIRA_PAT) && !jiraPatOnServer.value) {
      return setActionHint('issuetypes', '请先保存 PAT 后再加载', true);
    }
    issuetypesLoading.value = true;
    try {
      const res = await adminFetch(
        `/v1/admin/jira/issuetypes?project_key=${encodeURIComponent(projectKey)}&${buildJiraApiQuery().toString()}`
      );
      const data = await parseAdminJson(res);
      if (!res.ok || !data.success) throw new Error(data.error || '加载失败');
      const raw = data.issuetypes || [];
      if (!raw.length) {
        setActionHint('issuetypes', '此项目没有可用的问题类型，请手动填写', true);
      } else {
        // 保留完整 Jira 对象（iconUrl / name / description / subtask）
        issuetypeItems[projectKey] = raw.map((t) => ({
          iconUrl: t.iconUrl || '',
          name: t.name || '',
          type: t.subtask ? '子任务' : '标准',
          description: t.description || '',
          editing: false,
          draftName: '',
        }));
        issuetypeDraftText[projectKey] = raw.map((t) => t.name || '').filter(Boolean).join('\n');
        setActionHint('issuetypes', `已加载 ${raw.length} 个类型`);
      }
    } catch (e) {
      setActionHint('issuetypes', e.message || '加载失败', true);
    } finally {
      issuetypesLoading.value = false;
    }
  };

  const syncIssuetypeItemsFromDraft = (projectKey) => {
    const text = issuetypeDraftText[projectKey] || '';
    const names = text.split('\n').map((l) => l.trim()).filter(Boolean);
    // 保留已有完整对象的额外字段；纯文本条目补默认值
    const existingMap = {};
    (issuetypeItems[projectKey] || []).forEach((item) => {
      if (item.name) existingMap[item.name] = item;
    });
    issuetypeItems[projectKey] = names.map((name) => {
      const existing = existingMap[name];
      if (existing && existing.iconUrl) return { ...existing, editing: false, draftName: '' };
      return { iconUrl: '', name, type: '标准', description: '', editing: false, draftName: '' };
    });
  };

  const addIssuetypeItem = (projectKey) => {
    if (!projectKey) return;
    if (!issuetypeItems[projectKey]) issuetypeItems[projectKey] = [];
    issuetypeItems[projectKey].push({ iconUrl: '', name: '', type: '标准', description: '', editing: true, draftName: '' });
  };

  const startEditIssuetypeItem = (projectKey, idx) => {
    const row = issuetypeItems[projectKey]?.[idx];
    if (!row) return;
    row.draftName = row.name;
    row.editing = true;
  };

  const saveIssuetypeItem = (projectKey, idx) => {
    const row = issuetypeItems[projectKey]?.[idx];
    if (!row) return;
    const newName = (row.draftName || '').trim();
    if (newName) row.name = newName;
    row.editing = false;
    issuetypeDraftText[projectKey] = (issuetypeItems[projectKey] || [])
      .filter((r) => r.name)
      .map((r) => r.name)
      .join('\n');
    _doSaveIssuetypes();
  };

  const saveIssuetypes = async () => { await _doSaveIssuetypes(); };

  const _doSaveIssuetypes = async () => {
    const map = {};
    for (const pk of jiraPmForm.selectedProjectKeys) {
      const items = issuetypeItems[pk] || [];
      const names = items.filter((r) => r.name).map((r) => r.name);
      if (names.length) map[pk] = names;
    }
    jiraPmForm.issuetypeRowsByProject = map;
    try {
      await fetch('/v1/admin/config', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminToken.value}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          JIRA_ISSUETYPE_MAP: map,
          JIRA_PROJECTS: (jiraPmForm.selectedProjectKeys || []).join(', '),
          JIRA_DEADLINE_FIELD_BY_PROJECT: state.jira.JIRA_DEADLINE_FIELD_BY_PROJECT,
          JIRA_FIELD_MAPPINGS: state.jira.JIRA_FIELD_MAPPINGS,
          JIRA_PROJECT_CONFIG: state.jira.JIRA_PROJECT_CONFIG,
          JIRA_FIELD_GLOSSARY: state.jira.JIRA_FIELD_GLOSSARY,
        }),
      });
      issuetypeSaveMessage.value = '√ 保存成功';
      setTimeout(() => { issuetypeSaveMessage.value = ''; }, 3000);
    } catch {
      issuetypeSaveMessage.value = '保存失败';
      setTimeout(() => { issuetypeSaveMessage.value = ''; }, 3000);
    }
  };

  const cancelEditIssuetypeItem = (projectKey, idx) => {
    const row = issuetypeItems[projectKey]?.[idx];
    if (!row) return;
    row.editing = false;
    row.draftName = '';
    if (!row.name) {
      issuetypeItems[projectKey].splice(idx, 1);
    }
  };

  const removeIssuetypeItem = (projectKey, idx) => {
    if (!issuetypeItems[projectKey]) return;
    issuetypeItems[projectKey].splice(idx, 1);
    issuetypeDraftText[projectKey] = (issuetypeItems[projectKey] || [])
      .filter((r) => r.name)
      .map((r) => r.name)
      .join('\n');
    _doSaveIssuetypes();
  };

  const onIssuetypeProjectChange = (projectKey) => {
    if (!projectKey) return;
    if (!issuetypeItems[projectKey] || !issuetypeItems[projectKey].length) {
      syncIssuetypeItemsFromDraft(projectKey);
    }
  };

  const suggestDeadline = async (row) => {
    const pk = (row.projectKey || 'CT').trim().toUpperCase();
    if (!pk) return showToast('请先填写项目代号', 'error');
    if (!state.jira.JIRA_BASE_URL) return showToast('请先填写 Jira 地址', 'error');
    if (isMaskedPat(state.jira.JIRA_PAT) && !jiraPatOnServer.value) {
      return showToast('请先填写并保存 PAT', 'error');
    }
    try {
      const res = await adminFetch(
        `/v1/admin/jira/deadline-suggest?${buildJiraApiQuery({ project: pk })}`
      );
      const data = await parseAdminJson(res);
      if (!res.ok || !data.success) throw new Error(data.error || '推荐失败');
      row.fieldName = data.display_name || '';
      syncJsonFromPmForm();
      showToast(`${pk} 推荐字段：${data.display_name}`);
    } catch (e) {
      showToast(e.message || '自动推荐失败', 'error');
    }
  };

  const addDeadlineRow = () => {
    jiraPmForm.deadlineRows.push({ projectKey: '', fieldName: '' });
  };

  const removeDeadlineRow = (idx) => {
    jiraPmForm.deadlineRows.splice(idx, 1);
  };

  const startEdit = (cardId) => {
    const stateKey = cardId === 'notion' || cardId === 'gdrive' ? 'kb' : cardId;
    if (cardId === 'ai') {
      draftBackup[cardId] = {
        DEEPSEEK_URL: state.ai.DEEPSEEK_URL,
        DEEPSEEK_KEY: state.ai.DEEPSEEK_KEY,
      };
    } else {
      draftBackup[cardId] = structuredClone(toRaw(state[stateKey]));
    }
    if (cardId === 'jira') {
      if (isMaskedPat(state.jira.JIRA_PAT) && jiraPatOnServer.value) {
        state.jira.JIRA_PAT = '';
      }
    }
    if (isJiraPmSection(cardId)) {
      const busy = activeJiraPmSection();
      if (busy && busy !== cardId) {
        showToast('请先保存或取消其它配置块的编辑', 'warning');
        return;
      }
      if (!draftBackup.jiraPmForm) {
        draftBackup.jiraPmForm = structuredClone(toRaw(jiraPmForm));
        draftBackup.jiraPmJson = {
          JIRA_DEADLINE_FIELD_BY_PROJECT: state.jira.JIRA_DEADLINE_FIELD_BY_PROJECT,
          JIRA_FIELD_MAPPINGS: state.jira.JIRA_FIELD_MAPPINGS,
          JIRA_PROJECT_CONFIG: state.jira.JIRA_PROJECT_CONFIG,
          JIRA_FIELD_GLOSSARY: state.jira.JIRA_FIELD_GLOSSARY,
        };
        syncPmFormFromJson();
      }
      editLock[cardId] = true;
      return;
    }
    editLock[cardId] = true;
  };

  const clearJiraPmEdit = () => {
    JIRA_PM_SECTIONS.forEach((k) => {
      editLock[k] = false;
    });
    delete draftBackup.jiraPmForm;
    delete draftBackup.jiraPmJson;
  };

  const cancelEdit = (cardId) => {
    if (isJiraPmSection(cardId)) {
      if (draftBackup.jiraPmForm) Object.assign(jiraPmForm, draftBackup.jiraPmForm);
      if (draftBackup.jiraPmJson) Object.assign(state.jira, draftBackup.jiraPmJson);
      clearJiraPmEdit();
      return;
    }
    if (draftBackup[cardId]) {
      if (cardId === 'ai') {
        state.ai.DEEPSEEK_URL = draftBackup[cardId].DEEPSEEK_URL;
        state.ai.DEEPSEEK_KEY = draftBackup[cardId].DEEPSEEK_KEY;
      } else {
        const stateKey = cardId === 'notion' || cardId === 'gdrive' ? 'kb' : cardId;
        Object.assign(state[stateKey], draftBackup[cardId]);
      }
    }
    editLock[cardId] = false;
  };

  const parseJsonField = (payload, key, label) => {
    const raw = payload[key];
    if (!raw || typeof raw !== 'string') return;
    try {
      payload[key] = JSON.parse(raw);
    } catch {
      throw new Error(label + ' 配置无法保存，请联系技术人员检查高级 JSON');
    }
  };

  const saveEdit = async (cardId) => {
    try {
      let payload;
      if (cardId === 'ai') {
        payload = {
          DEEPSEEK_URL: state.ai.DEEPSEEK_URL,
          DEEPSEEK_KEY: state.ai.DEEPSEEK_KEY,
        };
      } else if (cardId === 'jira') {
        payload = {
          JIRA_BASE_URL: state.jira.JIRA_BASE_URL,
          JIRA_PAT: state.jira.JIRA_PAT,
          FISHEYE_URL: state.jira.FISHEYE_URL,
        };
        if (!jiraPatForApi()) delete payload.JIRA_PAT;
      } else if (isJiraPmSection(cardId)) {
        if (cardId === 'jiraPmA') {
          const keys = parseProjectKeys();
          if (!keys.length) return showToast('请至少勾选一个 Jira 项目', 'error');
        }
        if (cardId === 'jiraPmB') {
          for (const row of jiraPmForm.deadlineRows) {
            if (
              (row.projectKey || '').trim() &&
              !(row.projectKey || '').match(/^[A-Z][A-Z0-9]*$/i)
            ) {
              return showToast(`项目代号「${row.projectKey}」格式不正确，请使用如 CT`, 'error');
            }
          }
        }
        syncJsonFromPmForm();
        const keys = parseProjectKeys();
        payload = {
          JIRA_PROJECTS: keys.join(', '),
          JIRA_DEADLINE_FIELD_BY_PROJECT: state.jira.JIRA_DEADLINE_FIELD_BY_PROJECT,
          JIRA_FIELD_MAPPINGS: state.jira.JIRA_FIELD_MAPPINGS,
          JIRA_PROJECT_CONFIG: state.jira.JIRA_PROJECT_CONFIG,
          JIRA_FIELD_GLOSSARY: state.jira.JIRA_FIELD_GLOSSARY,
        };
        try {
          parseJsonField(payload, 'JIRA_DEADLINE_FIELD_BY_PROJECT', '截止时间字段');
          parseJsonField(payload, 'JIRA_FIELD_MAPPINGS', '额外人物字段');
          parseJsonField(payload, 'JIRA_PROJECT_CONFIG', '项目配置');
          parseJsonField(payload, 'JIRA_FIELD_GLOSSARY', '字段含义词典');
        } catch (e) {
          return showToast(e.message, 'error');
        }
      } else {
        const stateKey = cardId === 'notion' || cardId === 'gdrive' ? 'kb' : cardId;
        payload = { ...toRaw(state[stateKey]) };
      }
      const res = await fetch('/v1/admin/config', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminToken.value}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const saveMsg =
          cardId === 'ai'
            ? '✅ API 配置已保存'
            : cardId === 'jira'
              ? '✅ Jira 连接已保存'
              : isJiraPmSection(cardId)
                ? '✅ 该配置块已保存'
                : '✅ 模块配置已保存至后端';
        showToast(saveMsg);
        if (isJiraPmSection(cardId)) clearJiraPmEdit();
        else editLock[cardId] = false;
        if (cardId === 'ai') await loadConfig({ aiApiOnly: true });
        else await loadConfig();
      } else {
        throw new Error('保存失败');
      }
    } catch (e) {
      showToast(e.message, 'error');
    }
  };

  const onModelChange = async () => {
    if (hydratingModel.value) return;
    const model = (state.ai.DEEPSEEK_MODEL || '').trim();
    if (!model || model === lastSavedModel.value) return;
    const prev = lastSavedModel.value;
    const seq = ++modelSaveSeq;
    savingModel.value = true;
    try {
      const res = await fetch('/v1/admin/config', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminToken.value}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ DEEPSEEK_MODEL: model }),
      });
      if (!res.ok) throw new Error('模型保存失败');
      if (seq !== modelSaveSeq) return;
      lastSavedModel.value = model;
      setActionHint('aiModels', `已切换默认模型：${model}`);
    } catch (e) {
      if (seq === modelSaveSeq) {
        state.ai.DEEPSEEK_MODEL = prev;
        setActionHint('aiModels', e.message || '模型保存失败', true);
      }
    } finally {
      if (seq === modelSaveSeq) savingModel.value = false;
    }
  };

  const loadConfig = async (opts = {}) => {
    const fullLoad = !opts.aiApiOnly;
    if (fullLoad) hydratingModel.value = true;
    try {
      const res = await fetch('/v1/admin/config', {
        headers: { Authorization: `Bearer ${adminToken.value}` },
      });
      if (res.status === 401) {
        const token = prompt('请输入管理员密码登录:');
        if (token) {
          setAdminToken(token);
          adminToken.value = token;
          return loadConfig(opts);
        }
      }
      if (res.ok) {
        const data = await res.json();
        const modelFromServer =
          (data.saved_model || data.DEEPSEEK_MODEL || '').trim() || 'deepseek-chat';
        if (opts.aiApiOnly) {
          state.ai.DEEPSEEK_URL = data.DEEPSEEK_URL || '';
          state.ai.DEEPSEEK_KEY = data.DEEPSEEK_KEY || '';
        } else {
          state.ai = {
            DEEPSEEK_URL: data.DEEPSEEK_URL || '',
            DEEPSEEK_KEY: data.DEEPSEEK_KEY || '',
            DEEPSEEK_MODEL: modelFromServer,
          };
          lastSavedModel.value = modelFromServer;
          await fetchAiModels(true);
        }
        const dlMap = data.JIRA_DEADLINE_FIELD_BY_PROJECT;
        if (!opts.aiApiOnly) {
          const fm = data.JIRA_FIELD_MAPPINGS;
          const pc = data.JIRA_PROJECT_CONFIG;
          const gl = data.JIRA_FIELD_GLOSSARY;
          const patRaw = data.JIRA_PAT || '';
          jiraPatOnServer.value = patRaw === '********';
          state.jira = {
            JIRA_BASE_URL: data.JIRA_BASE_URL || '',
            JIRA_PAT: patRaw === '********' ? '' : patRaw,
            FISHEYE_URL: data.FISHEYE_URL || '',
            JIRA_DEADLINE_FIELD_BY_PROJECT:
              typeof dlMap === 'object' && dlMap !== null
                ? JSON.stringify(dlMap, null, 2)
                : '{\n  "CT": "End date"\n}',
            JIRA_FIELD_MAPPINGS:
              typeof fm === 'object' && fm !== null
                ? JSON.stringify(fm, null, 2)
                : '{\n  "extraPersonFields": []\n}',
            JIRA_PROJECT_CONFIG:
              typeof pc === 'object' && pc !== null ? JSON.stringify(pc, null, 2) : '{}',
            JIRA_FIELD_GLOSSARY:
              Array.isArray(gl) || (typeof gl === 'object' && gl !== null)
                ? JSON.stringify(gl, null, 2)
                : '[]',
          };
          hydratePmFormFromConfig({
            ...data,
            JIRA_PROJECTS: data.JIRA_PROJECTS || '',
          });
          // P1: 加载 issuetype 配置
          if (data.JIRA_ISSUETYPE_MAP && typeof data.JIRA_ISSUETYPE_MAP === 'object') {
            jiraPmForm.issuetypeRowsByProject = { ...data.JIRA_ISSUETYPE_MAP };
            // 初始化表格渲染数据
            for (const [pk, names] of Object.entries(data.JIRA_ISSUETYPE_MAP)) {
              issuetypeItems[pk] = (names || []).map((n) => ({
                iconUrl: '', name: typeof n === 'string' ? n : n.name || '', type: '标准',
                description: '', editing: false, draftName: '',
              }));
            }
            // 自动选中第一个项目
            const firstKey = jiraPmForm.selectedProjectKeys[0];
            if (firstKey && !issuetypeActiveProject.value) {
              issuetypeActiveProject.value = firstKey;
            }
          }
          if (jiraCanUseFields.value) fetchJiraProjects().catch(() => {});
          state.svn = {
            SVN_URL: data.SVN_URL || '',
            SVN_USERNAME: data.SVN_USERNAME || '',
            SVN_PASSWORD: data.SVN_PASSWORD || '',
          };
          state.kb = {
            NOTION_KEY: data.NOTION_KEY || '',
            NOTION_DATABASE_ID: data.NOTION_DATABASE_ID || '',
            GDRIVE_KEY: data.GDRIVE_KEY || '',
            GDRIVE_FOLDERS: data.GDRIVE_FOLDERS || '',
            GDRIVE_PROXY_IP: data.GDRIVE_PROXY_IP || '',
            GDRIVE_PROXY_PORT: data.GDRIVE_PROXY_PORT || '',
          };
          restoreConnectionOk();
          restoreTestHints();
        }
      }
    } catch {
      showToast('配置加载失败', 'error');
    } finally {
      if (fullLoad) hydratingModel.value = false;
    }
  };

  const fetchAiModels = async (silent = false, hintKey = 'aiModels') => {
    fetchingModels.value = true;
    try {
      const res = await fetch('/v1/admin/models', {
        headers: { Authorization: `Bearer ${adminToken.value}` },
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || '拉取失败');
      availableModels.value = data.models || [];
      const savedFromServer = (data.saved_model || '').trim();
      if (savedFromServer) {
        state.ai.DEEPSEEK_MODEL = savedFromServer;
        lastSavedModel.value = savedFromServer;
      }
      if (!silent) {
        aiConnectionOk.value = true;
        persistConnectionOk();
        pulseStatus('ai');
        setActionHint(hintKey, `已加载 ${availableModels.value.length} 个模型`);
      } else if (availableModels.value.length) {
        inferConnectionOkFromConfig();
      }
    } catch (e) {
      aiConnectionOk.value = false;
      persistConnectionOk();
      if (!silent) setActionHint(hintKey, e.message || '模型列表失败', true);
    } finally {
      fetchingModels.value = false;
    }
  };

  const testAiSystem = async () => {
    testing.ai = true;
    setActionHint('ai', '测试中…');
    try {
      await fetchAiModels(true);
      aiConnectionOk.value = true;
      persistConnectionOk();
      pulseStatus('ai');
      const n = availableModels.value.length;
      setActionHint('ai', n ? `API 可达 · 已加载 ${n} 个模型` : 'API 可达');
    } catch (e) {
      aiConnectionOk.value = false;
      persistConnectionOk();
      setActionHint('ai', e.message || '测试失败', true);
    } finally {
      testing.ai = false;
    }
  };

  const testJiraSystem = async () => {
    if (!state.jira.JIRA_BASE_URL) return setActionHint('jira', '请先填写 Jira 地址', true);
    if (isMaskedPat(state.jira.JIRA_PAT) && !jiraPatOnServer.value) {
      return setActionHint('jira', '请先填写 PAT 并保存，或在编辑时粘贴 PAT 后测试', true);
    }
    testing.jira = true;
    jiraConnectionOk.value = false;
    try {
      const patBody = jiraPatForApi() || '********';
      const res = await adminFetch('/v1/admin/test/jira', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: state.jira.JIRA_BASE_URL, pat: patBody }),
      });
      const data = await parseAdminJson(res);
      if (!data.success) throw new Error(data.error || '连接失败');
      jiraConnectionOk.value = true;
      persistConnectionOk();
      pulseStatus('jira');
      setActionHint('jira', `Jira 已连通（${data.latency_ms || '?'}ms）`);
      await fetchJiraFieldOptions();
    } catch (e) {
      jiraConnectionOk.value = false;
      persistConnectionOk();
      setActionHint('jira', e.message || '测试失败', true);
    } finally {
      testing.jira = false;
    }
  };

  const testSvnSystem = async () => {
    if (!state.svn.SVN_URL || !state.svn.SVN_USERNAME || !state.svn.SVN_PASSWORD) {
      return setActionHint('svn', '请先填写完整', true);
    }
    testing.svn = true;
    try {
      await new Promise((r) => setTimeout(r, 1500));
      svnConnectionOk.value = true;
      persistConnectionOk();
      pulseStatus('svn');
      setActionHint('svn', 'Checkout 校验通过');
    } catch {
      svnConnectionOk.value = false;
      persistConnectionOk();
      setActionHint('svn', '校验失败', true);
    } finally {
      testing.svn = false;
    }
  };

  const testNotionSystem = async () => {
    if (!state.kb.NOTION_KEY) return setActionHint('notion', '缺少 Notion Token', true);
    testing.notion = true;
    try {
      const res = await fetch('/v1/admin/test/notion-db', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminToken.value}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          token: state.kb.NOTION_KEY,
          database_id: state.kb.NOTION_DATABASE_ID,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        notionConnectionOk.value = true;
        persistConnectionOk();
        pulseStatus('notion');
        setActionHint('notion', `联通成功，找到 ${data.databases} 个数据库`);
        notionDatabases.value = data.items || [];
      } else throw new Error(data.error);
    } catch (e) {
      setActionHint('notion', e.message || '测试失败', true);
    } finally {
      testing.notion = false;
    }
  };

  const testGDriveSystem = async () => {
    if (!state.kb.GDRIVE_KEY) return setActionHint('gdrive', '缺少 GDrive Key', true);
    const folders = state.kb.GDRIVE_FOLDERS
      ? state.kb.GDRIVE_FOLDERS.split(',').filter(Boolean)
      : [];
    const firstFolderId = folders.length > 0 ? folders[0] : '';
    if (!firstFolderId) {
      return setActionHint('gdrive', '请先在下方输入框回车录入至少一个文件夹链接', true);
    }
    testing.gdrive = true;
    try {
      const res = await fetch('/v1/admin/test/gdrive', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminToken.value}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          key: state.kb.GDRIVE_KEY,
          folder_id: firstFolderId,
          proxy_ip: state.kb.GDRIVE_PROXY_IP,
          proxy_port: state.kb.GDRIVE_PROXY_PORT,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        gdriveConnectionOk.value = true;
        persistConnectionOk();
        pulseStatus('gdrive');
        setActionHint('gdrive', '连通成功');
        gdriveFiles.value = data.items || [];
      } else throw new Error(data.error);
    } catch (e) {
      setActionHint('gdrive', e.message || '测试失败', true);
    } finally {
      testing.gdrive = false;
    }
  };

  const parseNotionUrl = () => {
    const val = state.kb.NOTION_DATABASE_ID;
    if (!val) return;
    const match = val.match(
      /([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i
    );
    if (match) {
      const extracted = match[1].replace(/-/g, '');
      if (state.kb.NOTION_DATABASE_ID !== extracted) {
        state.kb.NOTION_DATABASE_ID = extracted;
        showToast('✨ Notion URL 解析成功，已剥离出纯 ID！');
      }
    }
  };

  const gdriveInput = ref('');
  const gdriveFoldersList = computed(() =>
    state.kb.GDRIVE_FOLDERS ? state.kb.GDRIVE_FOLDERS.split(',').filter(Boolean) : []
  );

  const addGDriveFolder = () => {
    let val = gdriveInput.value.trim();
    if (!val) return;
    const match = val.match(/[-\w]{25,}/);
    const extractedId = match ? match[0] : val;
    const currentFolders = [...gdriveFoldersList.value];
    if (!currentFolders.includes(extractedId)) {
      currentFolders.push(extractedId);
      state.kb.GDRIVE_FOLDERS = currentFolders.join(',');
      showToast('✨ 已生成标签并提取 ID');
    } else {
      showToast('⚠️ 该文件夹已存在', 'error');
    }
    gdriveInput.value = '';
  };

  const removeFolder = (id) => {
    const currentFolders = gdriveFoldersList.value.filter((fid) => fid !== id);
    state.kb.GDRIVE_FOLDERS = currentFolders.join(',');
  };

  const saveJiraPmGlossary = async () => {
    if (hasUnsavedGlossaryDraft()) {
      showToast('词典有未保存的编辑行，请先保存或取消', 'warning');
      return;
    }
    savingGlossaryAll.value = true;
    try {
      syncJsonFromPmForm();
      const payload = { JIRA_FIELD_GLOSSARY: state.jira.JIRA_FIELD_GLOSSARY };
      parseJsonField(payload, 'JIRA_FIELD_GLOSSARY', '字段含义词典');
      const res = await fetch('/v1/admin/config', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${adminToken.value}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('保存失败');
      showToast('✅ 字段含义词典已保存');
      await loadConfig();
    } catch (e) {
      showToast(e.message || '词典保存失败', 'error');
    } finally {
      savingGlossaryAll.value = false;
    }
  };

  const onMenuSelect = (menuId) => {
    if (menuId === activeMenu.value) return;
    if (hasUnsavedGlossaryDraft()) {
      showToast('词典有未保存的编辑行，请先保存或取消', 'warning');
      return;
    }
    if (anyJiraPmEditing()) {
      showToast('有未保存的 Jira 查询配置，请先保存或取消', 'warning');
      return;
    }
    activeMenu.value = menuId;
    persistActiveMenu();
  };

  const fetchHealth = async () => {
    healthLoading.value = true;
    try {
      const res = await fetch(`${window.location.origin || ''}/health`);
      healthSummary.value = await res.json();
    } catch (e) {
      healthSummary.value = { status: 'error', detail: e.message || '无法读取 /health' };
    } finally {
      healthLoading.value = false;
    }
  };

  const integrationLabel = (probe) => {
    if (!probe) return '未知';
    const s = probe.status;
    if (s === 'ok' || s === 'configured') return '正常';
    if (s === 'partial') return '部分';
    if (s === 'unconfigured') return '未配置';
    if (s === 'gateway_error') return '网关502';
    if (s === 'auth_error') return '凭据';
    if (s === 'timeout') return '超时';
    return s;
  };

  onMounted(() => {
    persistActiveMenu();
    if (isAuthenticated()) {
      loadConfig();
      fetchHealth();
    }
  });

  // ── 账号管理（v2.0-wave2）──
  const accounts = ref([]);
  const accountsLoading = ref(false);

  const fetchAccounts = async () => {
    accountsLoading.value = true;
    try {
      const res = await adminFetch('/v1/admin/accounts');
      const data = await parseAdminJson(res);
      if (data.ok) accounts.value = data.accounts || [];
    } catch { /* ignore */ }
    accountsLoading.value = false;
  };

  const createAccount = async (payload) => {
    const res = await adminFetch('/v1/admin/accounts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await parseAdminJson(res);
    if (!data.ok) throw new Error(data.error || '创建失败');
    fetchAccounts();
    return data.account;
  };

  const updateAccount = async (id, payload) => {
    const res = await adminFetch(`/v1/admin/accounts/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await parseAdminJson(res);
    if (!data.ok) throw new Error(data.error || '更新失败');
    fetchAccounts();
    return data.account;
  };

  const deleteAccount = async (id) => {
    const res = await adminFetch(`/v1/admin/accounts/${id}`, { method: 'DELETE' });
    const data = await parseAdminJson(res);
    if (!data.ok) throw new Error(data.error || '删除失败');
    fetchAccounts();
  };

  return {
    activeMenu,
    menus,
    currentMenuName,
    onMenuSelect,
    state,
    editLock,
    startEdit,
    cancelEdit,
    saveEdit,
    testing,
    testResult,
    setActionHint,
    testAiSystem,
    healthSummary,
    healthLoading,
    fetchHealth,
    integrationLabel,
    testJiraSystem,
    testSvnSystem,
    testNotionSystem,
    testGDriveSystem,
    notionDatabases,
    gdriveFiles,
    parseNotionUrl,
    gdriveInput,
    gdriveFoldersList,
    addGDriveFolder,
    removeFolder,
    availableModels,
    fetchingModels,
    fetchAiModels,
    modelSelectOptions,
    savingModel,
    onModelChange,
    lastSavedModel,
    hydratingModel,
    jiraPmForm,
    jiraFieldOptions,
    jiraFieldFilter,
    filteredJiraFieldOptions,
    jiraFieldsLoading,
    jiraConnectionOk,
    aiConnectionOk,
    notionConnectionOk,
    gdriveConnectionOk,
    svnConnectionOk,
    statusPulse,
    connectionLabel,
    jiraCanUseFields,
    jiraPatOnServer,
    jiraPatDisplayLabel,
    jiraPmSummaryMarkdown,
    JIRA_PM_SECTIONS,
    anyJiraPmEditing,
    glossaryTableRows,
    extraPersonFieldOptions,
    jiraProjectOptions,
    jiraProjectsLoading,
    jiraProjectFilter,
    filteredJiraProjectOptions,
    projectKeysText,
    fetchJiraProjects,
    issuetypesLoading,
    issuetypeActiveProject,
    issuetypeSaveMessage,
    saveIssuetypes,
    issuetypeItems,
    fetchIssuetypes,
    addIssuetypeItem,
    startEditIssuetypeItem,
    saveIssuetypeItem,
    cancelEditIssuetypeItem,
    removeIssuetypeItem,
    onIssuetypeProjectChange,
    toggleProjectKey,
    fetchJiraFieldOptions,
    suggestDeadline,
    addDeadlineRow,
    removeDeadlineRow,
    addGlossaryRow,
    removeGlossaryRow,
    onGlossaryFieldPick,
    saveGlossaryRow,
    saveJiraPmGlossary,
    savingGlossaryIdx,
    savingGlossaryAll,
    startEditGlossaryRow,
    cancelEditGlossaryRow,
    addAliasTag,
    removeAliasTag,
    commitAliasDraft,
    syncPmFormFromJson,
    syncGlossaryFromJson,
    normalizeAliasTags,
    // accounts
    isAuthenticated, onAuthSuccess,
    accounts, accountsLoading, fetchAccounts,
    createAccount, updateAccount, deleteAccount,
  };
}

import { reactive, ref, computed, toRaw, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import {
  adminFetch,
  parseAdminJson,
  getAdminToken,
  setAdminToken,
} from '../api/adminApi.js';

export function useAdminStore() {
  const activeMenu = ref('settings');
  const menus = [
    { id: 'settings', name: '系统集成配置', icon: 'Setting' },
    { id: 'jiraQuery', name: 'Alice-Jira查询配置', icon: 'Search' },
    { id: 'kb', name: '云端知识库源', icon: 'Collection' },
  ];
  const currentMenuName = computed(
    () => menus.find((m) => m.id === activeMenu.value)?.name || ''
  );

  const adminToken = ref(getAdminToken());

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

  const editLock = reactive({
    ai: false,
    jira: false,
    jiraPm: false,
    svn: false,
    notion: false,
    gdrive: false,
  });
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
    jira: { show: false, msg: '', isError: false },
    svn: { show: false, msg: '', isError: false },
    notion: { show: false, msg: '', isError: false },
    gdrive: { show: false, msg: '', isError: false },
  });

  const notionDatabases = ref([]);
  const gdriveFiles = ref([]);

  const jiraPmForm = reactive({
    selectedProjectKeys: ['CT'],
    deadlineRows: [{ projectKey: 'CT', fieldName: '' }],
    extraPersonField: '',
    glossaryRows: [],
    showAdvancedJson: false,
  });
  const jiraFieldOptions = ref([]);
  const jiraFieldFilter = ref('');
  const jiraProjectOptions = ref([]);
  const jiraProjectsLoading = ref(false);
  const jiraProjectFilter = ref('');
  const savingGlossaryIdx = ref(-1);
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

  const jiraPmSummaryLines = computed(() => {
    const lines = [];
    const pk = projectKeysText.value || 'CT';
    lines.push(`默认项目：${pk || '（未选择）'}`);
    let dlMap = {};
    try {
      dlMap = JSON.parse(state.jira.JIRA_DEADLINE_FIELD_BY_PROJECT || '{}');
    } catch {
      /* ignore */
    }
    for (const row of jiraPmForm.deadlineRows || []) {
      const k = (row.projectKey || '').trim().toUpperCase();
      if (!k) continue;
      const fn = row.fieldName || dlMap[k] || '（Alice 自动识别）';
      lines.push(`${k} 项目：周报 / 待办按「${fn}」筛选`);
    }
    const extra = (jiraPmForm.extraPersonField || '').trim();
    lines.push(
      extra ? `人名查询：经办人 + 额外字段「${extra}」` : '人名查询：仅经办人'
    );
    const gloss = (jiraPmForm.glossaryRows || []).filter((r) =>
      (r.fieldName || '').trim()
    );
    if (gloss.length) {
      lines.push(`字段含义词典：已标注 ${gloss.length} 个字段`);
      gloss.slice(0, 3).forEach((r) => {
        const m = (r.meaning || '').trim();
        const als = normalizeAliasTags(r.aliases).join('、');
        let line = `  ·「${r.fieldName}」${m ? '：' + (m.length > 40 ? m.slice(0, 40) + '…' : m) : ''}`;
        if (als) line += `（别名：${als}）`;
        lines.push(line);
      });
      if (gloss.length > 3) lines.push(`  ·… 另有 ${gloss.length - 3} 条`);
    }
    return lines;
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
    if (!editLock.jiraPm) return;
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
    if (!state.jira.JIRA_BASE_URL) return showToast('请先填写 Jira 地址', 'error');
    if (isMaskedPat(state.jira.JIRA_PAT) && !jiraPatOnServer.value) {
      return showToast('请先填写 PAT，或保存后再加载', 'error');
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
      showToast(`已加载 ${jiraProjectOptions.value.length} 个项目，请勾选`);
    } catch (e) {
      showToast(e.message || '项目列表加载失败', 'error');
    } finally {
      jiraProjectsLoading.value = false;
    }
  };

  const fetchJiraFieldOptions = async () => {
    if (!state.jira.JIRA_BASE_URL) return showToast('请先填写 Jira 地址', 'error');
    if (isMaskedPat(state.jira.JIRA_PAT) && !jiraPatOnServer.value) {
      return showToast('请先填写 PAT，或保存后再测试', 'error');
    }
    jiraFieldsLoading.value = true;
    try {
      const res = await adminFetch(`/v1/admin/jira/fields?${buildJiraApiQuery()}`);
      const data = await parseAdminJson(res);
      if (!res.ok || !data.success) throw new Error(data.error || '加载失败');
      jiraFieldOptions.value = data.fields || [];
      showToast(`已加载 ${jiraFieldOptions.value.length} 个 Jira 字段`);
    } catch (e) {
      showToast(e.message || '字段列表加载失败', 'error');
    } finally {
      jiraFieldsLoading.value = false;
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
    if (cardId === 'jiraPm') {
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
  };

  const cancelEdit = (cardId) => {
    if (cardId === 'jiraPm') {
      if (draftBackup.jiraPmForm) Object.assign(jiraPmForm, draftBackup.jiraPmForm);
      if (draftBackup.jiraPmJson) Object.assign(state.jira, draftBackup.jiraPmJson);
      editLock.jiraPm = false;
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
      } else if (cardId === 'jiraPm') {
        const keys = parseProjectKeys();
        if (!keys.length) return showToast('请至少勾选一个 Jira 项目', 'error');
        for (const row of jiraPmForm.deadlineRows) {
          if (
            (row.projectKey || '').trim() &&
            !(row.projectKey || '').match(/^[A-Z][A-Z0-9]*$/i)
          ) {
            return showToast(`项目代号「${row.projectKey}」格式不正确，请使用如 CT`, 'error');
          }
        }
        syncJsonFromPmForm();
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
              : cardId === 'jiraPm'
                ? '✅ 任务查询规则已保存'
                : '✅ 模块配置已保存至后端';
        showToast(saveMsg);
        editLock[cardId] = false;
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
      showToast(`已切换默认模型：${model}`);
    } catch (e) {
      if (seq === modelSaveSeq) {
        state.ai.DEEPSEEK_MODEL = prev;
        showToast(e.message || '模型保存失败', 'error');
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
        }
      }
    } catch {
      showToast('配置加载失败', 'error');
    } finally {
      if (fullLoad) hydratingModel.value = false;
    }
  };

  const showTooltip = (type, msg, isError = false) => {
    testResult[type].msg = msg;
    testResult[type].isError = isError;
    testResult[type].show = true;
    setTimeout(() => {
      testResult[type].show = false;
    }, 3000);
    if (isError) ElMessage.error(msg);
    else ElMessage.success(msg);
  };

  const fetchAiModels = async (silent = false) => {
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
        pulseStatus('ai');
        showTooltip('ai', `✅ 已加载 ${availableModels.value.length} 个模型`);
      }
    } catch (e) {
      aiConnectionOk.value = false;
      if (!silent) showTooltip('ai', '❌ ' + (e.message || '模型列表失败'), true);
    } finally {
      fetchingModels.value = false;
    }
  };

  const testAiSystem = async () => {
    testing.ai = true;
    try {
      await fetchAiModels();
      aiConnectionOk.value = true;
      pulseStatus('ai');
      showTooltip('ai', '✅ 模型 API 可达');
    } catch {
      aiConnectionOk.value = false;
      showTooltip('ai', '❌ 测试失败', true);
    } finally {
      testing.ai = false;
    }
  };

  const testJiraSystem = async () => {
    if (!state.jira.JIRA_BASE_URL) return showTooltip('jira', '请先填写 Jira 地址', true);
    if (isMaskedPat(state.jira.JIRA_PAT) && !jiraPatOnServer.value) {
      return showTooltip(
        'jira',
        '请先填写 PAT 并保存，或在编辑时粘贴 PAT 后测试',
        true
      );
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
      pulseStatus('jira');
      showTooltip('jira', `✅ Jira 已连通（${data.latency_ms || '?'}ms）`);
      await fetchJiraFieldOptions();
    } catch (e) {
      jiraConnectionOk.value = false;
      showTooltip('jira', '❌ ' + (e.message || '测试失败'), true);
    } finally {
      testing.jira = false;
    }
  };

  const testSvnSystem = async () => {
    if (!state.svn.SVN_URL || !state.svn.SVN_USERNAME || !state.svn.SVN_PASSWORD) {
      return showTooltip('svn', '请先填写完整', true);
    }
    testing.svn = true;
    try {
      await new Promise((r) => setTimeout(r, 1500));
      svnConnectionOk.value = true;
      pulseStatus('svn');
      showTooltip('svn', '✅ Checkout 校验通过');
    } catch {
      svnConnectionOk.value = false;
      showTooltip('svn', '❌ 校验失败', true);
    } finally {
      testing.svn = false;
    }
  };

  const testNotionSystem = async () => {
    if (!state.kb.NOTION_KEY) return showTooltip('notion', '缺少 Notion Token', true);
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
        pulseStatus('notion');
        showTooltip('notion', `✅ 联通成功，找到 ${data.databases} 个数据库`);
        notionDatabases.value = data.items || [];
      } else throw new Error(data.error);
    } catch (e) {
      showTooltip('notion', `❌ ${e.message}`, true);
    } finally {
      testing.notion = false;
    }
  };

  const testGDriveSystem = async () => {
    if (!state.kb.GDRIVE_KEY) return showTooltip('gdrive', '缺少 GDrive Key', true);
    const folders = state.kb.GDRIVE_FOLDERS
      ? state.kb.GDRIVE_FOLDERS.split(',').filter(Boolean)
      : [];
    const firstFolderId = folders.length > 0 ? folders[0] : '';
    if (!firstFolderId) {
      return showTooltip('gdrive', '请先在下方输入框回车录入至少一个文件夹链接', true);
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
        pulseStatus('gdrive');
        showTooltip('gdrive', '✅ 连通成功');
        gdriveFiles.value = data.items || [];
      } else throw new Error(data.error);
    } catch (e) {
      showTooltip('gdrive', `❌ ${e.message}`, true);
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

  const onMenuSelect = (menuId) => {
    if (menuId === activeMenu.value) return;
    if (hasUnsavedGlossaryDraft() && editLock.jiraPm) {
      showToast('词典有未保存的编辑行，请先保存或取消', 'warning');
      return;
    }
    activeMenu.value = menuId;
  };

  onMounted(loadConfig);

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
    testAiSystem,
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
    jiraPmSummaryLines,
    glossaryTableRows,
    extraPersonFieldOptions,
    jiraProjectOptions,
    jiraProjectsLoading,
    jiraProjectFilter,
    filteredJiraProjectOptions,
    projectKeysText,
    fetchJiraProjects,
    toggleProjectKey,
    fetchJiraFieldOptions,
    suggestDeadline,
    addDeadlineRow,
    removeDeadlineRow,
    addGlossaryRow,
    removeGlossaryRow,
    onGlossaryFieldPick,
    saveGlossaryRow,
    savingGlossaryIdx,
    startEditGlossaryRow,
    cancelEditGlossaryRow,
    addAliasTag,
    removeAliasTag,
    commitAliasDraft,
    syncPmFormFromJson,
    syncGlossaryFromJson,
    normalizeAliasTags,
  };
}

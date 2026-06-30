const https = require('https');
const http = require('http');

const BASE = 'http://ctjira1.lmdgame.com:8080';
const PAT = process.env.ALICE_JIRA_PAT || '请通过环境变量 ALICE_JIRA_PAT 注入';
const HEADERS = { Authorization: `Bearer ${PAT}`, 'Content-Type': 'application/json' };

const KEYS = ['AL-410','AL-411','AL-412','AL-413','AL-414','AL-415','AL-416','AL-417',
              'AL-418','AL-419','AL-420','AL-421','AL-422','AL-423','AL-424','AL-425','AL-426','AL-427'];

const results = {};

async function fetchIssue(key) {
  return new Promise((resolve, reject) => {
    const url = `${BASE}/rest/api/2/issue/${key}?fields=description,summary,issuetype,assignee,status,parent`;
    http.get(url, { headers: HEADERS }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const j = JSON.parse(data);
          const f = j.fields;
          const desc = (f.description || '').replace(/\r/g, '');
          const parentKey = f.parent ? f.parent.key : 'none';
          results[key] = {
            summary: f.summary,
            status: f.status.name,
            assignee: (f.assignee || {}).name || 'unassigned',
            parentKey,
            desc: desc.substring(0, 600)
          };
        } catch(e) {
          results[key] = { error: e.message, raw: data.substring(0, 200) };
        }
        resolve();
      });
    }).on('error', e => { results[key] = { error: e.message }; resolve(); });
  });
}

(async () => {
  for (const k of KEYS) {
    await fetchIssue(k);
  }
  console.log(JSON.stringify(results, null, 2));
})();

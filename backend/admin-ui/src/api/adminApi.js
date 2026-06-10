export function getAdminToken() {
  return sessionStorage.getItem('wb_admin_token') || '';
}

export function setAdminToken(token) {
  sessionStorage.setItem('wb_admin_token', token);
  localStorage.removeItem('wb_admin_token');
}

export function apiBase() {
  return window.location.origin || '';
}

export async function parseAdminJson(res) {
  const ct = (res.headers.get('content-type') || '').toLowerCase();
  const text = await res.text();
  if (!ct.includes('application/json')) {
    if (text.trim().toLowerCase().startsWith('<!doctype') || text.trim().startsWith('<html')) {
      throw new Error(
        '后端接口未找到（返回了网页而不是数据）。请确认通过 http://本机:9099/admin 打开，并已重启 ai_bridge 到最新版本。'
      );
    }
    throw new Error(text.slice(0, 120) || `HTTP ${res.status}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error('服务器返回了无法解析的内容，请稍后重试');
  }
}

export function adminFetch(path, options = {}) {
  const token = getAdminToken();
  const url = path.startsWith('http') ? path : `${apiBase()}${path}`;
  return fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
}

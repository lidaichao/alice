import { StateCreator } from 'zustand';

export interface UserState {
  username: string;
  displayName: string;
  roles: string[];
  permissions: string[];
  token: string;
  isLoggedIn: boolean;
  loginError: string;
  loggingIn: boolean;
}

export interface UserSlice {
  user: UserState;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
  checkLogin: () => void;
  setPermissions: (perms: string[]) => void;
}

const STORAGE_USER = 'alice_user_session';
const STORAGE_TOKEN = 'alice_user_token';

function loadSavedSession(): Partial<UserState> {
  try {
    const raw = localStorage.getItem(STORAGE_USER);
    const token = localStorage.getItem(STORAGE_TOKEN);
    if (raw && token) {
      const data = JSON.parse(raw);
      return {
        isLoggedIn: true,
        token,
        username: data.username || '',
        displayName: data.displayName || data.display_name || '',
        roles: data.roles || [],
        permissions: data.permissions || [],
        loginError: '',
        loggingIn: false,
      };
    }
  } catch { /* ignore */ }
  return {};
}

function saveSession(state: UserState) {
  try {
    localStorage.setItem(STORAGE_TOKEN, state.token);
    localStorage.setItem(STORAGE_USER, JSON.stringify({
      username: state.username,
      displayName: state.displayName,
      roles: state.roles,
      permissions: state.permissions,
    }));
    // Also set runtime config for existing user_id-based flow
    const rcRaw = localStorage.getItem('alice_runtime_config');
    const rc = rcRaw ? JSON.parse(rcRaw) : {};
    rc.user_id = state.username;
    localStorage.setItem('alice_runtime_config', JSON.stringify(rc));
  } catch { /* ignore */ }
}

function clearSession() {
  localStorage.removeItem(STORAGE_USER);
  localStorage.removeItem(STORAGE_TOKEN);
}

export const createUserSlice: StateCreator<UserSlice> = (set, get) => ({
  user: {
    username: '',
    displayName: '',
    roles: [],
    permissions: [],
    token: '',
    isLoggedIn: false,
    loginError: '',
    loggingIn: false,
    ...loadSavedSession(),
  },

  login: async (username: string, password: string) => {
    set((s) => ({ user: { ...s.user, loggingIn: true, loginError: '' } }));
    try {
      const res = await fetch('/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (data.ok) {
        const newState: UserState = {
          username: data.user?.username || username,
          displayName: data.user?.display_name || '',
          roles: data.roles || [],
          permissions: data.permissions || [],
          token: data.token || '',
          isLoggedIn: true,
          loginError: '',
          loggingIn: false,
        };
        saveSession(newState);
        set({ user: newState });
        return true;
      } else {
        set((s) => ({ user: { ...s.user, loginError: data.error || '用户名或密码错误', loggingIn: false } }));
        return false;
      }
    } catch {
      set((s) => ({ user: { ...s.user, loginError: '网络错误，请重试', loggingIn: false } }));
      return false;
    }
  },

  logout: () => {
    clearSession();
    set({
      user: {
        username: '', displayName: '', roles: [], permissions: [],
        token: '', isLoggedIn: false, loginError: '', loggingIn: false,
      },
    });
  },

  checkLogin: () => {
    const saved = loadSavedSession();
    if (saved.isLoggedIn) {
      set({ user: { ...get().user, ...saved } as UserState });
    }
  },

  setPermissions: (perms: string[]) => {
    set((s) => ({ user: { ...s.user, permissions: perms } }));
  },
});

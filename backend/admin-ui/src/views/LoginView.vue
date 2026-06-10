<template>
  <div class="login-wrapper">
    <div class="login-card">
      <div class="login-brand">
        <span class="login-mark">A</span>
        <div>
          <div class="login-title">Alice</div>
          <div class="login-sub">后台管理系统</div>
        </div>
      </div>
      <form class="login-form" @submit.prevent="doLogin">
        <input v-model="username" placeholder="admin" size="large" class="login-input" autocomplete="username" />
        <input v-model="password" type="password" placeholder="请输入密码" class="login-input" autocomplete="current-password" />
        <button type="submit" class="login-btn" :disabled="loggingIn">
          <span v-if="loggingIn" class="spinner"></span>
          {{ loggingIn ? '登录中...' : '登录' }}
        </button>
        <p v-if="errorMsg" class="login-error">{{ errorMsg }}</p>
        <p class="login-hint">默认账号: admin / admin</p>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const username = ref('');
const password = ref('');
const loggingIn = ref(false);
const errorMsg = ref('');

const doLogin = async () => {
  if (!username.value.trim() || !password.value) {
    errorMsg.value = '请输入用户名和密码';
    return;
  }
  loggingIn.value = true;
  errorMsg.value = '';
  try {
    const res = await fetch('/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value.trim(), password: password.value }),
    });
    const data = await res.json();
    if (data.ok) {
      sessionStorage.setItem('wb_admin_token', data.token);
      window.location.reload();
    } else {
      errorMsg.value = data.error || '用户名或密码错误';
      loggingIn.value = false;
    }
  } catch (e) {
    errorMsg.value = '网络错误，请重试';
    loggingIn.value = false;
  }
};
</script>

<style scoped>
.login-wrapper {
  display: flex; align-items: center; justify-content: center;
  height: 100vh; background: #f4f5f7;
}
.login-card {
  width: 440px; padding: 40px;
  background: #fff;
  border: 1px solid #dfe1e6;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.08);
}
.login-brand {
  display: flex; align-items: center; gap: 14px;
  margin-bottom: 32px; justify-content: center;
}
.login-mark {
  width: 44px; height: 44px; border-radius: 12px;
  background: linear-gradient(135deg, #0c66e4, #0855c2);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 20px; color: #fff;
}
.login-title { font-size: 20px; font-weight: 700; color: #172b4d; }
.login-sub { font-size: 13px; color: #8993a4; margin-top: 2px; }
.login-form { display: flex; flex-direction: column; gap: 14px; }
.login-input {
  height: 44px; padding: 0 16px;
  border: 1px solid #dfe1e6; border-radius: 8px;
  font-size: 14px; color: #172b4d; background: #fafbfc;
  outline: none; box-sizing: border-box;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.login-input:focus { border-color: #0c66e4; box-shadow: 0 0 0 3px rgba(12,102,228,0.12); }
.login-btn {
  height: 44px; width: 100%; font-size: 15px; font-weight: 600;
  background: #0c66e4; color: #fff; border: none;
  border-radius: 8px; cursor: pointer;
  box-shadow: 0 2px 8px rgba(12,102,228,0.28);
  transition: all 0.2s ease;
  display: flex; align-items: center; justify-content: center; gap: 8px;
}
.login-btn:hover:not(:disabled) { background: #0855c2; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(12,102,228,0.36); }
.login-btn:active:not(:disabled) { transform: scale(0.98); }
.login-btn:disabled { opacity: 0.7; cursor: not-allowed; }
.spinner {
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.login-error { color: #ae2a19; font-size: 13px; text-align: center; margin: 0; }
.login-hint { color: #8993a4; font-size: 12px; text-align: center; margin: 8px 0 0; }
</style>

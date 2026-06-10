import React, { useState } from 'react';
import { useChatStore } from '@/store/useChatStore';
import { Eye, EyeOff, LogIn, AlertCircle } from 'lucide-react';

const LoginPanel: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const { user, login } = useChatStore();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    await login(username, password);
  };

  return (
    <div className="min-h-screen flex items-center justify-center"
      style={{ background: 'linear-gradient(135deg, #f4f5f7 0%, #e9f2ff 100%)' }}>
      <div className="w-[440px] p-10 rounded-2xl shadow-lg backdrop-blur-sm"
        style={{ background: '#ffffff', border: '1px solid #dfe1e6' }}>
        {/* Brand */}
        <div className="flex items-center gap-3 justify-center mb-8">
          <div className="w-11 h-11 rounded-xl flex items-center justify-center text-white font-extrabold text-xl"
            style={{ background: 'linear-gradient(135deg, #0c66e4, #0855c2)' }}>
            A
          </div>
          <div>
            <div className="text-xl font-bold" style={{ color: '#172b4d' }}>Alice</div>
            <div className="text-xs" style={{ color: '#8993a4' }}>登录你的工作区</div>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <div>
            <input
              type="text"
              placeholder="请输入用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full h-11 px-4 rounded-lg text-sm outline-none transition-all duration-200"
              style={{
                border: '1px solid #dfe1e6',
                background: '#fafbfc',
                color: '#172b4d',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = '#0c66e4';
                e.target.style.boxShadow = '0 0 0 3px rgba(12, 102, 228, 0.12)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = '#dfe1e6';
                e.target.style.boxShadow = 'none';
              }}
            />
          </div>

          <div className="relative">
            <input
              type={showPw ? 'text' : 'password'}
              placeholder="请输入密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full h-11 px-4 pr-11 rounded-lg text-sm outline-none transition-all duration-200"
              style={{
                border: '1px solid #dfe1e6',
                background: '#fafbfc',
                color: '#172b4d',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = '#0c66e4';
                e.target.style.boxShadow = '0 0 0 3px rgba(12, 102, 228, 0.12)';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = '#dfe1e6';
                e.target.style.boxShadow = 'none';
              }}
            />
            <button
              type="button"
              onClick={() => setShowPw(!showPw)}
              className="absolute right-3 top-1/2 -translate-y-1/2"
              style={{ color: '#8993a4', background: 'none', border: 'none', cursor: 'pointer' }}
              tabIndex={-1}
            >
              {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          <button
            type="submit"
            disabled={user.loggingIn}
            className="w-full h-11 rounded-lg text-white font-semibold text-sm
                       flex items-center justify-center gap-2
                       transition-all duration-200 hover:shadow-md hover:-translate-y-px active:scale-[0.98]"
            style={{
              background: '#0c66e4',
              border: 'none',
              cursor: user.loggingIn ? 'not-allowed' : 'pointer',
              opacity: user.loggingIn ? 0.7 : 1,
              boxShadow: '0 2px 8px rgba(12, 102, 228, 0.28)',
            }}
          >
            {user.loggingIn ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                登录中...
              </>
            ) : (
              <>
                <LogIn size={16} />
                登录
              </>
            )}
          </button>

          {user.loginError && (
            <div className="flex items-center gap-2 justify-center text-sm" style={{ color: '#ae2a19' }}>
              <AlertCircle size={14} />
              {user.loginError}
            </div>
          )}

          <p className="text-center text-xs mt-2" style={{ color: '#8993a4' }}>
            默认账号: admin / admin
          </p>
        </form>
      </div>
    </div>
  );
};

export default LoginPanel;

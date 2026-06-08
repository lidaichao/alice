import React, { useState, useCallback, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Settings, Eye, EyeOff, Check, X } from 'lucide-react';

const LS_KEY = 'alice_cursor_config';

interface CursorConfig {
  key: string;
  model: string;
}

function loadConfig(): CursorConfig {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return { key: '', model: 'composer-2.5' };
    return JSON.parse(raw);
  } catch {
    return { key: '', model: 'composer-2.5' };
  }
}

function saveConfig(cfg: CursorConfig) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(cfg));
  } catch { /* ignore */ }
}

export const getCursorConfig = loadConfig;

interface Props {
  open: boolean;
  onClose: () => void;
}

export const CursorSettings: React.FC<Props> = ({ open, onClose }) => {
  const [config, setConfig] = useState<CursorConfig>(loadConfig);
  const [showKey, setShowKey] = useState(false);
  const [testResult, setTestResult] = useState<'idle' | 'loading' | 'ok' | 'fail'>('idle');
  const [testError, setTestError] = useState('');
  const [cursorModels, setCursorModels] = useState<string[]>(['composer-2.5', 'composer-2.5-fast', 'auto']);

  useEffect(() => {
    if (!config.key) return;
    fetch(`/v1/admin/cursor-sdk/models?api_key=${encodeURIComponent(config.key)}`)
      .then(res => res.json())
      .then(data => {
        if (data.ok && data.models?.length) setCursorModels(data.models.map((m: any) => m.id));
      })
      .catch(() => {});
  }, [config.key]);

  const handleSave = useCallback(() => {
    saveConfig(config);
  }, [config]);

  const handleTest = useCallback(async () => {
    setTestResult('loading');
    setTestError('');
    try {
      const res = await fetch('/v1/admin/cursor-sdk/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: config.key, model: config.model }),
      });
      const data = await res.json();
      if (data.ok) {
        setTestResult('ok');
      } else {
        setTestResult('fail');
        setTestError(data.error || '未知错误');
      }
    } catch (e: any) {
      setTestResult('fail');
      setTestError(e.message || '网络错误');
    }
  }, [config.key, config.model]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-background text-foreground border border-border rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2">
          <Settings size={20} className="text-muted-foreground" />
          <h2 className="text-lg font-semibold">Cursor SDK 配置</h2>
        </div>

        {/* API Key */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">API Key</label>
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              value={config.key}
              onChange={(e) => setConfig((c) => ({ ...c, key: e.target.value }))}
              placeholder="crsr_..."
              className="w-full rounded-lg border border-input bg-background text-foreground px-3 py-2 pr-10 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        {/* Model */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">模型</label>
          <select
            value={config.model}
            onChange={(e) => setConfig((c) => ({ ...c, model: e.target.value }))}
            className="w-full rounded-lg border border-input bg-background text-foreground px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {cursorModels.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        {/* Test result */}
        {testResult !== 'idle' && (
          <div className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
            testResult === 'loading' ? 'bg-muted text-muted-foreground' :
            testResult === 'ok' ? 'bg-green-500/10 text-green-600' :
            'bg-red-500/10 text-red-600'
          }`}>
            {testResult === 'loading' ? (
              <>⏳ 测试中...</>
            ) : testResult === 'ok' ? (
              <><Check size={16} /> 连通成功</>
            ) : (
              <><X size={16} /> {testError || '连通失败'}</>
            )}
          </div>
        )}

        {/* Buttons */}
        <div className="flex gap-3 pt-2">
          <Button variant="outline" onClick={handleTest} disabled={!config.key || testResult === 'loading'} className="flex-1">
            {testResult === 'loading' ? '测试中...' : '测试连通'}
          </Button>
          <Button onClick={() => { handleSave(); onClose(); }} disabled={!config.key} className="flex-1">
            保存
          </Button>
        </div>
      </div>
    </div>
  );
};

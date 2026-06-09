import React, { useEffect, useState, useCallback } from 'react';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { ChevronDown, Zap, Bot, MessageCircle } from 'lucide-react';
import { useChatStore } from '@/store/useChatStore';

interface CursorMode {
  id: string;
  label: string;
}

interface EnginesConfig {
  deepseek: { model: string; label: string };
  cursor: { modes: CursorMode[]; label: string };
}

const LS_KEY = 'alice_engine_pref';
const CURSOR_CFG_KEY = 'alice_cursor_config';

type EngineChoice =
  | { engine: 'auto' }
  | { engine: 'deepseek' }
  | { engine: 'cursor'; mode: string };

function loadPreference(): EngineChoice | null {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed.engine === 'auto') return { engine: 'auto' };
    if (parsed.engine === 'deepseek') return { engine: 'deepseek' };
    if (parsed.engine === 'cursor' && parsed.mode) return { engine: 'cursor', mode: parsed.mode };
    return null;
  } catch {
    return null;
  }
}

function savePreference(pref: EngineChoice) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(pref));
  } catch { /* ignore */ }
}

interface CursorConfig { key: string; model: string; }

function loadCursorConfig(): CursorConfig {
  try {
    const raw = localStorage.getItem(CURSOR_CFG_KEY);
    if (!raw) return { key: '', model: 'composer-2.5' };
    return JSON.parse(raw);
  } catch {
    return { key: '', model: 'composer-2.5' };
  }
}

export const EngineSelector: React.FC<{ onOpenSettings?: () => void; compact?: boolean }> = ({ onOpenSettings, compact }) => {
  const [engines, setEngines] = useState<EnginesConfig | null>(null);
  const [choice, setChoice] = useState<EngineChoice>(() => loadPreference() || { engine: 'auto' });
  const [hasCursorKey, setHasCursorKey] = useState(false);
  const [cursorModel, setCursorModel] = useState<string>(() => loadCursorConfig().model);
  const [modelOpen, setModelOpen] = useState(false);
  const [cursorAvailableModels, setCursorAvailableModels] = useState<string[]>(['composer-2.5', 'auto']);
  const setEngine = useChatStore((s) => s.setEngine);

  useEffect(() => {
    void (async () => {
    fetch('/v1/config/engines')
      .then((res) => res.json())
      .then((data: EnginesConfig) => setEngines(data))
      .catch(() => {});
    try {
      const raw = localStorage.getItem(CURSOR_CFG_KEY);
      if (raw) {
        const cfg = JSON.parse(raw);
        setHasCursorKey(!!cfg.key);
        if (cfg.model) setCursorModel(cfg.model);
      }
    } catch {}
    try {
      const cfgRaw = localStorage.getItem(CURSOR_CFG_KEY);
      if (cfgRaw) {
        const cfg = JSON.parse(cfgRaw);
        if (cfg.key) {
          const modelsRes = await fetch(`/v1/admin/cursor-sdk/models?api_key=${encodeURIComponent(cfg.key)}`);
          const modelsData = await modelsRes.json();
          if (modelsData.ok && modelsData.models?.length) {
            setCursorAvailableModels(modelsData.models.map((m: any) => m.id));
          }
        }
      }
    } catch {}
    })();
    // 同步 Zustand enginePreference（避免界面选 agent 但后端收不到）
    const pref = loadPreference();
    if (pref) {
      if (pref.engine === 'cursor' && 'mode' in pref) {
        setEngine('cursor', pref.mode);
      } else {
        setEngine(pref.engine);
      }
    }
  }, []);

  const handleSelect = useCallback(
    (newChoice: EngineChoice) => {
      setChoice(newChoice);
      savePreference(newChoice);
      setEngine(newChoice.engine === 'cursor' && 'mode' in newChoice ? 'cursor' : newChoice.engine, ('mode' in newChoice ? newChoice.mode : undefined));
    },
    [setEngine],
  );

  let engineIcon: React.ReactNode = <Zap size={13} />;
  let engineText = 'Auto';
  if (choice.engine === 'deepseek') { engineIcon = <MessageCircle size={13} />; engineText = 'DS'; }
  else if (choice.engine === 'cursor') { engineIcon = <Bot size={13} />; engineText = choice.mode; }

  let modelLabel = '';
  if (choice.engine === 'deepseek' && engines) {
    modelLabel = (engines.deepseek.model || 'deepseek').slice(0, 12);
  } else if (choice.engine === 'cursor') {
    modelLabel = cursorModel === 'auto' ? 'auto' : ((cursorModel || 'c-2.5').slice(0, 12));
  }

  const availableModels = (() => {
    if (choice.engine === 'deepseek' && engines) {
      return [engines.deepseek.model];
    }
    if (choice.engine === 'cursor') {
      return cursorAvailableModels;
    }
    return [];
  })();

  if (compact) {
    return (
      <Popover>
        <PopoverTrigger asChild>
          <span className="text-[11px] text-muted-foreground flex items-center gap-1 cursor-pointer hover:text-foreground transition-colors">
            {choice.engine === 'cursor' ? 'Cursor' : choice.engine === 'deepseek' ? 'DeepSeek' : 'Auto'}
            <ChevronDown size={10} />
          </span>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-44 p-1">
          <button onClick={() => handleSelect({ engine: 'auto' })} className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2">
            <Zap size={12} className="text-muted-foreground" />
            Auto（自动分流）
          </button>
          <button onClick={() => handleSelect({ engine: 'deepseek' })} className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2">
            <MessageCircle size={12} />
            DeepSeek
          </button>
          {engines && hasCursorKey && engines.cursor.modes.map((m) => (
            <button key={m.id} onClick={() => handleSelect({ engine: 'cursor', mode: m.id })} className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2">
              <Bot size={12} />
              Cursor · {m.label}
            </button>
          ))}
          {(!hasCursorKey || !engines) && (
            <button disabled className="w-full text-left px-2 py-1.5 text-xs rounded text-muted-foreground italic">
              🔒 请先配置 Cursor SDK
            </button>
          )}
          <div className="border-t border-border mt-1 pt-1">
            <button onClick={onOpenSettings} className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted">
              ⚙ 配置 Cursor SDK...
            </button>
          </div>
        </PopoverContent>
      </Popover>
    );
  }

  return (
    <div className="flex items-center gap-1">
      {/* 模式胶囊按钮 —— LobeHub AgentMode 风格 */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="inline-flex items-center gap-1 h-7 px-2 rounded-full text-xs font-medium bg-secondary hover:bg-secondary/80 transition-colors">
            {engineIcon}
            <span className="first-letter:uppercase">{engineText}</span>
            <ChevronDown size={11} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuItem onClick={() => handleSelect({ engine: 'auto' })} className="flex items-center gap-2">
            <Zap size={13} className="text-muted-foreground" />
            <span>Auto（自动分流）</span>
          </DropdownMenuItem>
          {engines && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled className="text-muted-foreground text-[11px] uppercase tracking-wider">
                DeepSeek
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleSelect({ engine: 'deepseek' })} className="flex items-center gap-2">
                <MessageCircle size={13} />
                <span>DeepSeek</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem disabled className="text-muted-foreground text-[11px] uppercase tracking-wider">
                Cursor SDK
              </DropdownMenuItem>
              {hasCursorKey ? (
                engines.cursor.modes.map((m) => (
                  <DropdownMenuItem key={m.id} onClick={() => handleSelect({ engine: 'cursor', mode: m.id })} className="flex items-center gap-2">
                    <Bot size={13} />
                    <span>Cursor · {m.label}</span>
                  </DropdownMenuItem>
                ))
              ) : (
                <DropdownMenuItem disabled className="flex items-center gap-2 text-muted-foreground text-xs italic">
                  <span>🔒</span>
                  <span>请先配置 Cursor SDK</span>
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onOpenSettings} className="flex items-center gap-2">
                <span>⚙</span>
                <span>配置 Cursor SDK...</span>
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* 模型文本徽章 —— LobeHub ModelLabel 风格 */}
      {modelLabel && availableModels.length > 1 ? (
        <DropdownMenu open={modelOpen} onOpenChange={setModelOpen}>
          <DropdownMenuTrigger asChild>
            <button className="inline-flex items-center gap-0.5 h-7 px-1.5 rounded-md text-[11px] font-mono text-muted-foreground hover:text-foreground bg-muted/30 hover:bg-muted/50 transition-colors max-w-[100px] truncate">
              <span className="truncate">{modelLabel}</span>
              <ChevronDown size={10} className="shrink-0" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-44">
            {availableModels.map((m) => (
              <DropdownMenuItem
                key={m}
                onClick={() => {
                  setCursorModel(m);
                  try {
                    const cfg = loadCursorConfig();
                    cfg.model = m;
                    localStorage.setItem(CURSOR_CFG_KEY, JSON.stringify(cfg));
                  } catch {}
                }}
                className="text-xs font-mono"
              >
                {m}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : modelLabel ? (
        <span className="text-[11px] font-mono text-muted-foreground/60 px-1 select-none max-w-[100px] truncate">
          {modelLabel}
        </span>
      ) : null}
    </div>
  );
};

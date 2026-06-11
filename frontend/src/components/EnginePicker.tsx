import React, { useEffect, useState, useCallback } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Settings, Zap, Bot, MessageCircle, ChevronDown, Check } from 'lucide-react';
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

export interface EnginePickerProps {
  onOpenSettings: () => void;
  onEngineChange?: (engine: string, mode?: string) => void;
  compact?: boolean;
}

export const EnginePicker: React.FC<EnginePickerProps> = ({ onOpenSettings, onEngineChange, compact }) => {
  const [engines, setEngines] = useState<EnginesConfig | null>(null);
  const [choice, setChoice] = useState<EngineChoice>(() => loadPreference() || { engine: 'auto' });
  const [hasCursorKey, setHasCursorKey] = useState(false);
  const setEngine = useChatStore((s) => s.setEngine);
  const [open, setOpen] = useState(false);

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
        }
      } catch {}
    })();
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
      const engine = newChoice.engine === 'cursor' && 'mode' in newChoice ? 'cursor' : newChoice.engine;
      const mode = 'mode' in newChoice ? newChoice.mode : undefined;
      setEngine(engine, mode);
      onEngineChange?.(engine, mode);
      setOpen(false);
    },
    [setEngine, onEngineChange],
  );

  const isSelected = (engine: string, mode?: string) => {
    if (choice.engine !== engine) return false;
    if (engine === 'cursor' && 'mode' in choice && mode) return choice.mode === mode;
    return !mode;
  };

  let label = 'Auto · composer-2.5';
  if (choice.engine === 'deepseek') label = 'DeepSeek · deepseek-chat';
  else if (choice.engine === 'cursor') label = 'Cursor';

  const buttonEl = compact ? (
    <button
      className="inline-flex items-center gap-1 h-7 px-2 rounded-full text-xs font-medium bg-secondary hover:bg-secondary/80 transition-colors border border-border/50 shadow-sm"
    >
      <Settings size={12} />
      <span>{label}</span>
      <ChevronDown size={11} />
    </button>
  ) : (
    <button
      className="inline-flex items-center gap-1 h-7 px-2 rounded-full text-xs font-medium bg-secondary hover:bg-secondary/80 transition-colors"
    >
      <Settings size={12} />
      <span>{label}</span>
      <ChevronDown size={11} />
    </button>
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {buttonEl}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-48 p-1">
        <button
          onClick={() => handleSelect({ engine: 'auto' })}
          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2"
        >
          <Zap size={12} className="text-muted-foreground" />
          <span>⚡ 自动分流</span>
          {isSelected('auto') && <Check size={12} className="ml-auto" />}
        </button>
        <button
          onClick={() => handleSelect({ engine: 'deepseek' })}
          className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2"
        >
          <MessageCircle size={12} />
          <span>💬 DeepSeek</span>
          {isSelected('deepseek') && <Check size={12} className="ml-auto" />}
        </button>
        {engines && hasCursorKey && engines.cursor.modes.map((m) => (
          <button
            key={m.id}
            onClick={() => handleSelect({ engine: 'cursor', mode: m.id })}
            className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2"
          >
            <Bot size={12} />
            <span>🤖 Cursor · {m.label}</span>
            {isSelected('cursor', m.id) && <Check size={12} className="ml-auto" />}
          </button>
        ))}
        {(!hasCursorKey || !engines) && (
          <button disabled className="w-full text-left px-2 py-1.5 text-xs rounded text-muted-foreground italic">
            🔒 请先配置 Cursor SDK
          </button>
        )}
        <div className="border-t border-border mt-1 pt-1">
          <button
            onClick={() => { setOpen(false); onOpenSettings(); }}
            className="w-full text-left px-2 py-1.5 text-xs rounded hover:bg-muted flex items-center gap-2"
          >
            <Settings size={12} className="text-muted-foreground" />
            <span>配置 Cursor SDK...</span>
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
};

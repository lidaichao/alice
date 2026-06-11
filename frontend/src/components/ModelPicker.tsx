import React, { useState } from 'react';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu';
import { ChevronDown } from 'lucide-react';

const CURSOR_CFG_KEY = 'alice_cursor_config';

export interface ModelPickerProps {
  engine: string;
  cursorMode?: string;
  deepseekModel?: string;
  cursorModel?: string;
  cursorAvailableModels?: string[];
  onModelChange?: (model: string) => void;
}

export const ModelPicker: React.FC<ModelPickerProps> = ({
  engine,
  cursorMode: _cursorMode,
  deepseekModel,
  cursorModel,
  cursorAvailableModels = ['composer-2.5', 'auto'],
  onModelChange,
}) => {
  const [open, setOpen] = useState(false);

  if (engine === 'auto') return null;

  if (engine === 'deepseek') {
    const label = (deepseekModel || 'deepseek').slice(0, 12);
    return (
      <span className="inline-flex items-center h-7 px-2 rounded-full text-xs font-mono bg-secondary text-muted-foreground max-w-[120px] truncate select-none">
        {label}
      </span>
    );
  }

  if (engine === 'cursor') {
    const available = cursorAvailableModels.length > 0 ? cursorAvailableModels : ['composer-2.5', 'auto'];
    const current = cursorModel || 'composer-2.5';
    const label = current === 'auto' ? 'auto' : current.slice(0, 14);

    return (
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <button className="inline-flex items-center gap-0.5 h-7 px-2 rounded-full text-xs font-mono bg-secondary hover:bg-secondary/80 transition-colors max-w-[140px] truncate">
            <span className="truncate">{label}</span>
            <ChevronDown size={11} className="shrink-0" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-44">
          {available.map((m) => (
            <DropdownMenuItem
              key={m}
              onClick={() => {
                try {
                  const cfg = JSON.parse(localStorage.getItem(CURSOR_CFG_KEY) || '{}');
                  cfg.model = m;
                  localStorage.setItem(CURSOR_CFG_KEY, JSON.stringify(cfg));
                } catch {}
                onModelChange?.(m);
              }}
              className={`text-xs font-mono ${m === current ? 'text-blue-500' : ''}`}
            >
              {m}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return null;
};

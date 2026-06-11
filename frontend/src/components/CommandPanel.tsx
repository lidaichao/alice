import React from 'react';
import { COMMANDS, Command } from '@/store/useChatStore';
import { Terminal } from 'lucide-react';

interface CommandPanelProps {
  filterText: string;
  selectedIndex: number;
  onSelect: (command: Command) => void;
}

export const CommandPanel: React.FC<CommandPanelProps> = ({ filterText, selectedIndex, onSelect }) => {
  const filtered = COMMANDS.filter(cmd => 
    cmd.key.toLowerCase().includes(filterText.toLowerCase()) ||
    cmd.label.toLowerCase().includes(filterText.toLowerCase())
  );

  if (filtered.length === 0) return null;

  return (
    <div className="absolute bottom-full left-0 mb-2 w-full max-w-md bg-popover text-popover-foreground rounded-xl shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-150">
      <div className="px-3 py-2 bg-muted/50 border-b border-border flex items-center gap-1.5 text-[11px] text-muted-foreground font-medium">
        <Terminal size={12} />
        <span>快捷指令面板 (使用键盘 ↑ ↓ 切换，Enter 确认)</span>
      </div>
      <div className="max-h-60 overflow-y-auto p-1">
        {filtered.map((cmd, index) => {
          const isSelected = index === selectedIndex;
          return (
            <div
              key={cmd.key}
              onClick={() => onSelect(cmd)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                isSelected 
                  ? 'bg-primary text-primary-foreground' 
                  : 'hover:bg-muted text-foreground'
              }`}
            >
              <div className="text-xl bg-background/20 p-1.5 rounded-md shrink-0">
                {cmd.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-semibold text-sm">/{cmd.key}</span>
                  <span className={`text-xs truncate ${isSelected ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>
                    {cmd.label}
                  </span>
                </div>
                <p className={`text-xs truncate mt-0.5 ${isSelected ? 'text-primary-foreground/70' : 'text-muted-foreground/80'}`}>
                  {cmd.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

import React, { useState } from 'react';
import { ArrowLeft, Sliders, MessageSquare, Activity, Info } from 'lucide-react';
import { TeamMemoryPanel } from '@/components/TeamMemoryPanel';
import { FeedbackPanel } from '@/components/FeedbackPanel';
import { DiagnosticsPanel } from '@/components/DiagnosticsPanel';

interface SettingsCenterProps {
  onBack: () => void;
}

const NAV_ITEMS = [
  { id: 'behaviors', label: '行为指令', icon: Sliders },
  { id: 'feedback', label: '反馈', icon: MessageSquare },
  { id: 'diagnostics', label: '诊断', icon: Activity },
  { id: 'about', label: '关于', icon: Info },
] as const;

type TabId = (typeof NAV_ITEMS)[number]['id'];

export const SettingsCenter: React.FC<SettingsCenterProps> = ({ onBack }) => {
  const [activeTab, setActiveTab] = useState<TabId>('behaviors');

  return (
    <main className="flex-1 flex min-w-0 bg-background">
      {/* 左侧导航栏 */}
      <nav className="w-52 border-r border-border flex flex-col bg-card/50">
        <div className="p-4 border-b border-border">
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground rounded-md hover:bg-muted px-2 py-1.5 transition-colors"
          >
            <ArrowLeft size={16} />
            <span>返回</span>
          </button>
        </div>
        <div className="flex-1 py-2">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-primary/10 text-primary font-medium border-r-2 border-primary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                }`}
              >
                <Icon size={16} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>

      {/* 右侧内容区 */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'behaviors' && <TeamMemoryPanel />}
        {activeTab === 'feedback' && <FeedbackPanel />}
        {activeTab === 'diagnostics' && <DiagnosticsPanel />}
      </div>
    </main>
  );
};

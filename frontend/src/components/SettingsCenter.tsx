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
        {activeTab === 'about' && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary text-xl font-bold">A</div>
              <div>
                <h2 className="text-lg font-semibold">Alice</h2>
                <p className="text-sm text-muted-foreground">AI 驱动的研发助手中枢</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between py-2 border-b border-border/50">
                <span className="text-sm text-muted-foreground">版本</span>
                <span className="text-sm font-mono">v3.1-rc17</span>
              </div>
              <div className="flex justify-between py-2 border-b border-border/50">
                <span className="text-sm text-muted-foreground">构建</span>
                <span className="text-sm font-mono">alice@749474f</span>
              </div>
              <div className="flex justify-between py-2 border-b border-border/50">
                <span className="text-sm text-muted-foreground">技术栈</span>
                <span className="text-sm">LangGraph · Dify · n8n · Flask</span>
              </div>
            </div>

            <div className="pt-4">
              <p className="text-xs text-muted-foreground leading-relaxed">
                Alice 是一个面向游戏研发团队的 AI 辅助平台，提供 Jira 自动化管理、知识库 RAG 检索、
                代码审查和团队协作工作流。由兔子（CTO）架构设计，杰尼龟开发实现，卡罗尔产品设计，夏洛克质量守护。
              </p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
};

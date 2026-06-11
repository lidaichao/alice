import React from 'react';
import { Link, Database, MessageSquare, ArrowRight, ExternalLink } from 'lucide-react';

interface OnboardingCardProps {
  onStartChat: () => void;
}

const STEPS = [
  {
    icon: Link,
    title: '连接 Jira',
    desc: '通过 Admin 后台配置 Jira 连接，让 Alice 访问你的项目数据。',
    action: '去配置',
    onClick: () => window.open('/admin-static/', '_blank'),
  },
  {
    icon: Database,
    title: '配置知识库',
    desc: '上传项目文档到 Dify 知识库，让 Alice 理解你的业务上下文。',
    action: '去配置',
    onClick: () => window.open('/admin-static/', '_blank'),
  },
  {
    icon: MessageSquare,
    title: '开始提问',
    desc: '一切就绪，使用自然语言向 Alice 提问，体验智能研发助手。',
    action: '开始',
    primary: true,
  },
];

const OnboardingCard: React.FC<OnboardingCardProps> = ({ onStartChat }) => {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 min-h-[400px]">
      <div className="max-w-2xl w-full">
        {/* 标题 */}
        <div className="text-center mb-8">
          <h2 className="text-xl font-semibold text-foreground mb-2">
            👋 欢迎使用 Alice
          </h2>
          <p className="text-sm text-muted-foreground">
            三步完成配置，解锁智能研发助手全部能力
          </p>
        </div>

        {/* 三栏步骤卡片 */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <div
                key={i}
                className="flex flex-col items-center text-center p-5 rounded-xl border border-border bg-card hover:shadow-md hover:-translate-y-0.5 transition-all"
              >
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center mb-3">
                  <Icon size={20} className="text-primary" />
                </div>
                <h3 className="text-sm font-semibold mb-1.5">{step.title}</h3>
                <p className="text-[11px] text-muted-foreground leading-relaxed mb-4 flex-1">
                  {step.desc}
                </p>
                <button
                  onClick={step.onClick ?? onStartChat}
                  className={`inline-flex items-center gap-1.5 h-8 px-4 rounded-md text-xs font-medium transition-colors ${
                    step.primary
                      ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                      : 'border border-border text-foreground hover:bg-muted'
                  }`}
                >
                  {step.action}
                  {step.primary ? (
                    <ArrowRight size={13} />
                  ) : (
                    <ExternalLink size={12} />
                  )}
                </button>
              </div>
            );
          })}
        </div>

        {/* 跳过引导 */}
        <div className="text-center">
          <button
            onClick={onStartChat}
            className="text-[12px] text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors"
          >
            已有配置？跳过引导，直接开始
          </button>
        </div>
      </div>
    </div>
  );
};

export default OnboardingCard;

import React, { useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AGENTS, useChatStore, Agent } from '@/store/useChatStore';
import { Store, Sparkles, User, CheckCircle2 } from 'lucide-react';

export const AgentMarket: React.FC = () => {
  const addSession = useChatStore((state) => state.addSession);
  const customAgents = useChatStore((state) => state.customAgents);
  const addCustomAgent = useChatStore((state) => state.addCustomAgent);
  
  const [open, setOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState({ name: '', avatar: '🤖', description: '', systemPrompt: '' });

  const handleSelectAgent = (agentId: string) => {
    addSession(agentId);
    setOpen(false);
  };

  const handleCreateGem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.systemPrompt) return alert('名称和核心系统提示词为必填项！');
    await addCustomAgent(formData);
    setFormData({ name: '', avatar: '🤖', description: '', systemPrompt: '' });
    setIsCreating(false); 
  };

  const allAgents = [...AGENTS, ...customAgents];

  return (
    <Dialog open={open} onOpenChange={(val) => { setOpen(val); if(!val) setIsCreating(false); }}>
      <DialogTrigger asChild>
        <Button variant="outline" className="w-full justify-start gap-2 bg-muted/30 hover:bg-muted text-muted-foreground border-dashed">
          <Store size={16} /> 角色市场 (Agent Market)
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[750px] max-h-[85vh] overflow-y-auto">
        
        <DialogHeader className="flex flex-row items-center justify-between border-b border-border pb-4">
          <div>
            <DialogTitle className="text-xl flex items-center gap-2">
              <Store className="text-primary" /> {isCreating ? '新建专属 Gem 角色' : '发现与创建 AI 助手'}
            </DialogTitle>
            <DialogDescription>
              {isCreating ? '定制专属的系统级约束，让 AI 完美契合特定的业务工作流。' : '一键选用系统预设角色，或亲自动手打磨专属的定制 Agent 资产。'}
            </DialogDescription>
          </div>
          <Button 
            variant={isCreating ? "ghost" : "default"} 
            size="sm" 
            onClick={() => setIsCreating(!isCreating)}
            className="gap-1.5 shrink-0 ml-4"
          >
            {isCreating ? '返回市场' : <><Sparkles size={14} /> 捏一个 Gem</>}
          </Button>
        </DialogHeader>

        {isCreating ? (
          <form onSubmit={handleCreateGem} className="space-y-4 py-4">
            <div className="grid grid-cols-4 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground">专属头像 (Emoji)</label>
                <input 
                  type="text" value={formData.avatar} maxLength={2}
                  onChange={e => setFormData({...formData, avatar: e.target.value || '🤖'})}
                  className="w-full border border-input rounded-lg p-2.5 bg-background text-center text-xl focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
              <div className="col-span-3 space-y-1.5">
                <label className="text-xs font-semibold text-muted-foreground">角色名称 (Name)</label>
                <input 
                  type="text" placeholder="例如：SQL 性能调优专家" required
                  value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})}
                  className="w-full border border-input rounded-lg p-2.5 bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground">功能简述 (Description)</label>
              <input 
                type="text" placeholder="一句话描述这个角色的核心擅长领域..."
                value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})}
                className="w-full border border-input rounded-lg p-2.5 bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground flex items-center justify-between">
                <span>核心设定系统 Prompt</span>
                <span className="text-[10px] text-primary bg-primary/10 px-1.5 rounded">最核心的灵魂设定</span>
              </label>
              <textarea 
                placeholder="在此输入你期望灌注给大模型的约束指令。例如：你是一个经验丰富的DBA..." required rows={5}
                value={formData.systemPrompt} onChange={e => setFormData({...formData, systemPrompt: e.target.value})}
                className="w-full border border-input rounded-xl p-3 bg-background text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <div className="pt-2 flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setIsCreating(false)}>取消</Button>
              <Button type="submit" className="gap-1.5"><CheckCircle2 size={14} /> 保存并发布我的 Gem</Button>
            </div>
          </form>
        ) : (
          <div className="py-4 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              {allAgents.map((agent) => {
                const isCustom = agent.id.startsWith('custom-');
                return (
                  <div 
                    key={agent.id}
                    onClick={() => handleSelectAgent(agent.id)}
                    className="flex items-start gap-4 p-4 rounded-xl border border-border bg-card hover:bg-accent hover:border-primary/50 transition-all cursor-pointer group relative overflow-hidden"
                  >
                    {isCustom && (
                      <span className="absolute top-0 right-0 text-[9px] bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold px-2 py-0.5 rounded-bl-lg border-l border-b border-amber-500/20 flex items-center gap-0.5">
                        <User size={10} /> GEM 资产
                      </span>
                    )}
                    <div className="text-4xl bg-muted/50 p-2 rounded-lg group-hover:scale-110 transition-transform shrink-0">
                      {agent.avatar}
                    </div>
                    <div className="flex-1 space-y-1 min-w-0 pr-6">
                      <h4 className="font-semibold text-foreground truncate">{agent.name}</h4>
                      <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                        {agent.description || '暂无描述信息。'}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

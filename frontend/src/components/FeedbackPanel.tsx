import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { MessageSquare } from 'lucide-react';

export const FeedbackPanel: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [sent, setSent] = useState(false);
  const submit = () => {
    const reports = JSON.parse(localStorage.getItem('alice_feedback') || '[]');
    reports.push({ text, time: Date.now() });
    localStorage.setItem('alice_feedback', JSON.stringify(reports));
    setSent(true);
    setTimeout(() => { setOpen(false); setSent(false); setText(''); }, 1500);
  };
  return (
    <div>
      <button onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors">
        <MessageSquare size={14} className="text-muted-foreground" /> 提交反馈
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setOpen(false)}>
          <div className="bg-background border border-border rounded-xl shadow-2xl p-5 w-[400px] max-w-[92vw]" onClick={e => e.stopPropagation()}>
            <div className="font-semibold mb-3">告诉我们你的想法</div>
            <textarea className="w-full h-20 text-sm border border-border rounded-lg p-3 resize-none bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 mb-3"
              placeholder="哪里让你觉得好用或不好用..." value={text} onChange={e => setText(e.target.value)} />
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <input type="checkbox" className="rounded" /> 附带诊断信息
              </label>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>取消</Button>
                <Button size="sm" onClick={submit} disabled={!text.trim()}>
                  {sent ? '已发送' : '发送'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

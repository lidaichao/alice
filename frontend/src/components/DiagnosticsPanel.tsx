import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Bug, Activity } from 'lucide-react';

export const DiagnosticsPanel: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [desc, setDesc] = useState('');
  const [sent, setSent] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [fullReport, setFullReport] = useState('');

  const clientInfo = [
    `OS: ${navigator.platform || 'unknown'}`,
    `UA: ${navigator.userAgent.substring(0, 80)}`,
    `Screen: ${window.screen.width}x${window.screen.height}`,
    `Lang: ${navigator.language}`,
    `Time: ${new Date().toISOString()}`,
  ].join('\n');

  const handleGenerate = async () => {
    setLogsLoading(true);
    let backendLogs = '';
    try {
      const res = await fetch('/api/diagnostics/logs');
      const data = await res.json();
      backendLogs = data.ok && data.lines?.length ? data.lines.join('\n') : (data.error || '(日志接口不可达)');
    } catch { backendLogs = '(后端不可达)'; }
    const report = [
      `=== Alice 灰度测试反馈报告 ===`,
      `时间: ${new Date().toISOString()}`,
      '', `## 用户描述`, desc || '(未填写)', '',
      `## 客户端环境`, clientInfo, '',
      `## 后端日志 (最近200行)`, backendLogs,
    ].join('\n');
    setFullReport(report);
    setLogsLoading(false);
    localStorage.setItem('alice_bug_reports', JSON.stringify(
      [...(JSON.parse(localStorage.getItem('alice_bug_reports') || '[]')), { desc, clientInfo, backendLogs, time: Date.now() }]
    ));
    setSent(true);
  };

  return (
    <div>
      <button onClick={() => { setOpen(true); setSent(false); setFullReport(''); }}
        className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-md border border-border/50 bg-muted/50 hover:bg-muted transition-colors" title="诊断工具">
        <Activity size={14} className="text-blue-500" /> 生成诊断报告
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setOpen(false)}>
          <div className="bg-background border border-border rounded-xl shadow-2xl p-5 w-[460px] max-w-[92vw] max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-4"><Bug className="w-5 h-5 text-amber-500" /><span className="font-semibold text-lg">🐞 灰度测试反馈</span></div>
            <div className="text-xs text-muted-foreground mb-3 p-2 bg-muted/30 rounded-md font-mono whitespace-pre-wrap">{clientInfo}</div>
            <textarea className="w-full h-20 text-sm border border-border rounded-lg p-3 resize-none bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 mb-3" placeholder="描述你遇到的问题..." value={desc} onChange={e => setDesc(e.target.value)} />
            {!sent && <Button size="sm" onClick={handleGenerate} disabled={logsLoading || !desc.trim()} className="w-full mb-2">{logsLoading ? '⏳ 抓取后端日志中...' : '生成诊断报告'}</Button>}
            {sent && fullReport && (
              <>
                <div className="text-xs text-muted-foreground mb-1">诊断报告已生成 ({fullReport.length} 字符)</div>
                <pre className="text-[11px] bg-muted/50 rounded-lg p-3 max-h-48 overflow-y-auto mb-3 whitespace-pre-wrap font-mono border border-border/30">{fullReport.substring(0, 800)}...</pre>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => navigator.clipboard.writeText(fullReport)} className="flex-1">📋 复制到剪贴板</Button>
                  <Button variant="outline" size="sm" onClick={() => { const b = new Blob([fullReport], { type: 'text/plain;charset=utf-8' }); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `alice_bug_report_${Date.now()}.txt`; a.click(); URL.revokeObjectURL(u); }} className="flex-1">💾 下载 .txt</Button>
                </div>
              </>
            )}
            <div className="flex justify-end mt-3"><Button variant="ghost" size="sm" onClick={() => setOpen(false)}>关闭</Button></div>
          </div>
        </div>
      )}
    </div>
  );
};

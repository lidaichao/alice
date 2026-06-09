import React, { createContext, useCallback, useContext, useState } from 'react';
import { X } from 'lucide-react';

interface ToastItem {
  id: number;
  message: string;
  type?: 'success' | 'error' | 'info';
  action?: { label: string; onClick: () => void };
}

const ToastCtx = createContext<{
  toast: (msg: string, opts?: { type?: 'success' | 'error' | 'info'; action?: { label: string; onClick: () => void }; duration?: number }) => void;
}>({ toast: () => {} });

export function useToast() {
  return useContext(ToastCtx);
}

let _nextId = 0;

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, opts?: { type?: 'success' | 'error' | 'info'; action?: { label: string; onClick: () => void }; duration?: number }) => {
    const id = ++_nextId;
    const item: ToastItem = { id, message, type: opts?.type || 'info', action: opts?.action };
    setItems((prev) => [...prev, item]);
    const dur = opts?.duration ?? 4000;
    setTimeout(() => {
      setItems((prev) => prev.filter((x) => x.id !== id));
    }, dur);
  }, []);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((x) => x.id !== id));
  }, []);

  return (
    <ToastCtx.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 pointer-events-none">
        {items.map((item) => {
          const bg = item.type === 'success' ? 'bg-emerald-600' : item.type === 'error' ? 'bg-red-600' : 'bg-foreground';
          return (
            <div
              key={item.id}
              className={`${bg} text-white text-sm rounded-lg px-4 py-3 shadow-lg pointer-events-auto flex items-center gap-3 animate-in slide-in-from-right-2 fade-in duration-300 max-w-sm`}
            >
              <span className="flex-1">{item.message}</span>
              {item.action && (
                <button
                  onClick={() => { item.action!.onClick(); dismiss(item.id); }}
                  className="font-medium underline text-white/90 hover:text-white shrink-0"
                >
                  {item.action.label}
                </button>
              )}
              <button onClick={() => dismiss(item.id)} className="text-white/60 hover:text-white shrink-0">
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
};

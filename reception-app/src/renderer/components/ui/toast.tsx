import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface Toast {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextType {
  addToast: (type: ToastType, message: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

const ICONS: Record<ToastType, string> = {
  success: '✓',
  error:   '✕',
  warning: '⚠',
  info:    'ℹ',
};

const STYLES: Record<ToastType, { border: string; icon: string }> = {
  success: { border: 'border-l-green-500',  icon: 'text-green-400'  },
  error:   { border: 'border-l-red-500',    icon: 'text-red-400'    },
  warning: { border: 'border-l-yellow-500', icon: 'text-yellow-400' },
  info:    { border: 'border-l-blue-400',   icon: 'text-blue-400'   },
};

const DURATION = 5000;

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Kratka odgoda za CSS transition entrance
    const showTimer = setTimeout(() => setVisible(true), 20);
    // Pokreni exit animaciju malo prije uklanjanja
    const hideTimer = setTimeout(() => setVisible(false), DURATION - 350);
    // Ukloni iz DOM-a
    const removeTimer = setTimeout(() => onRemove(toast.id), DURATION);

    return () => {
      clearTimeout(showTimer);
      clearTimeout(hideTimer);
      clearTimeout(removeTimer);
    };
  }, []);

  const handleClose = () => {
    setVisible(false);
    setTimeout(() => onRemove(toast.id), 350);
  };

  const { border, icon } = STYLES[toast.type];

  return (
    <div
      onClick={handleClose}
      style={{
        transition: 'opacity 350ms ease, transform 350ms ease',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateX(0)' : 'translateX(110%)',
      }}
      className={`
        flex items-start gap-3 min-w-[300px] max-w-[420px] cursor-pointer
        bg-zinc-900 border border-zinc-700 border-l-4 ${border}
        rounded-lg shadow-2xl px-4 py-3 select-none
      `}
    >
      <span className={`text-base font-bold mt-0.5 flex-shrink-0 ${icon}`}>
        {ICONS[toast.type]}
      </span>
      <span className="text-sm text-zinc-100 flex-1 leading-snug">{toast.message}</span>
      <button
        onClick={(e) => { e.stopPropagation(); handleClose(); }}
        className="text-zinc-500 hover:text-zinc-300 text-xs flex-shrink-0 mt-0.5 ml-1 leading-none"
        aria-label="Zatvori"
      >
        ✕
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((type: ToastType, message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts(prev => [...prev, { id, type, message }]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[200] flex flex-col gap-2 pointer-events-none"
        aria-live="polite"
        aria-atomic="false"
      >
        {toasts.map(t => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem toast={t} onRemove={removeToast} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast mora biti korišten unutar ToastProvider-a');
  return {
    toast: {
      success: (message: string) => context.addToast('success', message),
      error:   (message: string) => context.addToast('error',   message),
      warning: (message: string) => context.addToast('warning', message),
      info:    (message: string) => context.addToast('info',    message),
    },
  };
}

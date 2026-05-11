import React, { createContext, useContext, useState, useRef } from 'react';
import { Button } from './button';

interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | undefined>(undefined);

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ConfirmOptions>({ title: '', message: '' });
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const confirm: ConfirmFn = (opts) =>
    new Promise(resolve => {
      resolveRef.current = resolve;
      setOptions(opts);
      setOpen(true);
    });

  const handleConfirm = () => {
    resolveRef.current?.(true);
    setOpen(false);
  };

  const handleCancel = () => {
    resolveRef.current?.(false);
    setOpen(false);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {open && (
        <>
          <div
            className="fixed inset-0 z-[150] bg-black/80 backdrop-blur-sm"
            onClick={handleCancel}
          />
          <div className="fixed left-1/2 top-1/2 z-[160] -translate-x-1/2 -translate-y-1/2 w-full max-w-md px-4">
            <div className="bg-card border border-border rounded-lg shadow-2xl p-6">
              <h2 className="text-lg font-semibold text-foreground mb-2">{options.title}</h2>
              <p className="text-sm text-muted-foreground mb-6 leading-relaxed">{options.message}</p>
              <div className="flex gap-3 justify-end">
                <Button variant="outline" onClick={handleCancel}>
                  {options.cancelLabel ?? 'Odustani'}
                </Button>
                <Button
                  variant={options.destructive ? 'destructive' : 'default'}
                  onClick={handleConfirm}
                >
                  {options.confirmLabel ?? 'Potvrdi'}
                </Button>
              </div>
            </div>
          </div>
        </>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const context = useContext(ConfirmContext);
  if (!context) throw new Error('useConfirm mora biti korišten unutar ConfirmDialogProvider-a');
  return context;
}

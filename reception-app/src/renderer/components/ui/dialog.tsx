import * as React from "react"

interface DialogContextType {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const DialogContext = React.createContext<DialogContextType | undefined>(undefined)

interface DialogProps {
  children: React.ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
}

export function Dialog({ children, open: controlledOpen, onOpenChange }: DialogProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(false)
  
  const open = controlledOpen !== undefined ? controlledOpen : uncontrolledOpen
  const handleOpenChange = onOpenChange || setUncontrolledOpen

  return (
    <DialogContext.Provider value={{ open, onOpenChange: handleOpenChange }}>
      {children}
    </DialogContext.Provider>
  )
}

export function DialogTrigger({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) {
  const context = React.useContext(DialogContext)
  if (!context) throw new Error("DialogTrigger must be used within Dialog")

  const handleClick = () => context.onOpenChange(true)

  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children, { onClick: handleClick } as any)
  }

  return <div onClick={handleClick}>{children}</div>
}

export function DialogContent({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const context = React.useContext(DialogContext)
  if (!context) throw new Error("DialogContent must be used within Dialog")

  if (!context.open) return null

  return (
    <>
      <div 
        className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm"
        onClick={() => context.onOpenChange(false)}
      />
      <div className="fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%] w-full max-w-lg">
        <div className={`bg-card p-6 rounded-lg shadow-lg border border-border ${className}`}>
          {children}
        </div>
      </div>
    </>
  )
}

export function DialogHeader({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`flex flex-col space-y-1.5 text-center sm:text-left mb-4 ${className}`}>{children}</div>
}

export function DialogTitle({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <h2 className={`text-lg font-semibold leading-none tracking-tight ${className}`}>{children}</h2>
}

export function DialogDescription({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <p className={`text-sm text-muted-foreground ${className}`}>{children}</p>
}

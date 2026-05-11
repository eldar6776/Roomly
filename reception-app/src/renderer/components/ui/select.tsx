import * as React from "react"

interface SelectContextType {
  value: string
  onValueChange: (value: string) => void
  open: boolean
  setOpen: (open: boolean) => void
}

const SelectContext = React.createContext<SelectContextType | undefined>(undefined)

interface SelectProps {
  children: React.ReactNode
  value?: string
  onValueChange?: (value: string) => void
  defaultValue?: string
}

export function Select({ children, value: controlledValue, onValueChange, defaultValue }: SelectProps) {
  const [uncontrolledValue, setUncontrolledValue] = React.useState(defaultValue || "")
  const [open, setOpen] = React.useState(false)
  
  const value = controlledValue !== undefined ? controlledValue : uncontrolledValue
  const handleValueChange = onValueChange || setUncontrolledValue

  return (
    <SelectContext.Provider value={{ value, onValueChange: handleValueChange, open, setOpen }}>
      <div className="relative">{children}</div>
    </SelectContext.Provider>
  )
}

export function SelectTrigger({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const context = React.useContext(SelectContext)
  if (!context) throw new Error("SelectTrigger must be used within Select")

  return (
    <button
      type="button"
      className={`flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      onClick={() => context.setOpen(!context.open)}
    >
      {children}
      <svg className="h-4 w-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    </button>
  )
}

export function SelectValue({ placeholder }: { placeholder?: string }) {
  const context = React.useContext(SelectContext)
  if (!context) throw new Error("SelectValue must be used within Select")

  return <span>{context.value || placeholder}</span>
}

export function SelectContent({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const context = React.useContext(SelectContext)
  if (!context) throw new Error("SelectContent must be used within Select")

  if (!context.open) return null

  return (
    <>
      <div 
        className="fixed inset-0 z-40"
        onClick={() => context.setOpen(false)}
      />
      <div className={`absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border border-border bg-card shadow-lg ${className}`}>
        {children}
      </div>
    </>
  )
}

export function SelectItem({ children, value }: { children: React.ReactNode; value: string }) {
  const context = React.useContext(SelectContext)
  if (!context) throw new Error("SelectItem must be used within Select")

  const isSelected = context.value === value

  return (
    <div
      className={`relative flex w-full cursor-pointer select-none items-center rounded-sm py-2 px-3 text-sm outline-none hover:bg-accent hover:text-accent-foreground ${isSelected ? 'bg-accent' : ''}`}
      onClick={() => {
        context.onValueChange(value)
        context.setOpen(false)
      }}
    >
      {children}
      {isSelected && (
        <span className="absolute right-2">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </span>
      )}
    </div>
  )
}

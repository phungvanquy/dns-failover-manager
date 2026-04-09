import { createContext, useContext, useState, useCallback, useRef } from 'react'

interface Toast {
  id: number
  message: string
  type: 'error' | 'success'
}

interface ToastContextType {
  showError: (msg: string) => void
  showSuccess: (msg: string) => void
}

const ToastContext = createContext<ToastContextType>({ showError: () => {}, showSuccess: () => {} })

export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(0)

  const addToast = useCallback((message: string, type: 'error' | 'success') => {
    const id = nextId.current++
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000)
  }, [])

  const showError = useCallback((msg: string) => addToast(msg, 'error'), [addToast])
  const showSuccess = useCallback((msg: string) => addToast(msg, 'success'), [addToast])

  return (
    <ToastContext.Provider value={{ showError, showSuccess }}>
      {children}
      <div className="fixed bottom-4 right-4 flex flex-col gap-2 z-[100] max-w-md">
        {toasts.map(t => (
          <div
            key={t.id}
            onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
            className={`px-4 py-3 rounded-lg shadow-lg text-white text-sm cursor-pointer transition-opacity
              ${t.type === 'error' ? 'bg-red-600' : 'bg-green-600'}`}
          >
            {t.type === 'error' ? '❌ ' : '✅ '}{t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

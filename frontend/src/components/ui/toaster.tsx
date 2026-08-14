import { useToast } from "./use-toast"
import { CheckCircle, XCircle, Info, X } from "lucide-react"
import { cn } from "../../utils/cn"

export function Toaster() {
  const { toasts, dismiss } = useToast()

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-96 max-w-[calc(100vw-2rem)]">
      {toasts.map(t => (
        <div
          key={t.id}
          className={cn(
            "flex items-start gap-3 rounded-lg border p-4 shadow-lg animate-fade-in bg-white",
            t.variant === "destructive" && "border-red-200 bg-red-50",
            t.variant === "success" && "border-emerald-200 bg-emerald-50",
            t.variant === "default" && "border-slate-200",
            !t.open && "opacity-0 translate-x-4 transition-all duration-200"
          )}
        >
          {t.variant === "destructive" && <XCircle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />}
          {t.variant === "success" && <CheckCircle className="h-5 w-5 text-emerald-500 shrink-0 mt-0.5" />}
          {(!t.variant || t.variant === "default") && <Info className="h-5 w-5 text-indigo-500 shrink-0 mt-0.5" />}
          <div className="flex-1 min-w-0">
            {t.title && <p className={cn("font-semibold text-sm", t.variant === "destructive" ? "text-red-900" : t.variant === "success" ? "text-emerald-900" : "text-slate-900")}>{t.title}</p>}
            {t.description && <p className={cn("text-sm mt-0.5", t.variant === "destructive" ? "text-red-700" : t.variant === "success" ? "text-emerald-700" : "text-slate-600")}>{t.description}</p>}
          </div>
          <button onClick={() => dismiss(t.id)} className="text-slate-400 hover:text-slate-600 shrink-0">
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  )
}

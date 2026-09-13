import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app-store'

const TONE = {
  error: { icon: AlertTriangle, className: 'border-rose-400/30 text-rose-200' },
  success: { icon: CheckCircle2, className: 'border-accent/30 text-accent' },
  info: { icon: Info, className: 'border-neon/30 text-neon' },
} as const

export function NoticeToast() {
  const notice = useAppStore((s) => s.notice)
  const notify = useAppStore((s) => s.notify)

  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => notify(null), notice.tone === 'error' ? 8000 : 3500)
    return () => clearTimeout(timer)
  }, [notice, notify])

  const tone = notice ? TONE[notice.tone] : null

  return (
    <AnimatePresence>
      {notice && tone && (
        <motion.div
          initial={{ opacity: 0, transform: 'translateY(12px)' }}
          animate={{ opacity: 1, transform: 'translateY(0px)' }}
          exit={{ opacity: 0, transform: 'translateY(12px)' }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="pointer-events-none fixed inset-x-0 bottom-6 z-[60] flex justify-center px-6"
        >
          <div
            className={cn(
              'pointer-events-auto flex max-w-md items-start gap-2.5 rounded-xl border bg-void-deep/90 px-3.5 py-2.5 text-xs backdrop-blur-xl',
              'shadow-[0_16px_50px_-16px_rgba(0,0,0,0.9)]',
              tone.className
            )}
          >
            <tone.icon className="mt-0.5 size-4 shrink-0" />
            <p data-selectable className="break-words">
              {notice.message}
            </p>
            <button
              onClick={() => notify(null)}
              className="ml-1 shrink-0 rounded p-0.5 text-muted transition-colors hover:text-ink"
              aria-label="Dismiss"
            >
              <X className="size-3.5" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, ChevronDown, Loader2, Ban, XCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app-store'

const LEVEL_CLASS: Record<string, string> = {
  error: 'text-rose-400',
  warning: 'text-amber-300',
  warn: 'text-amber-300',
  success: 'text-accent',
}

export function TaskConsole() {
  const tasks = useAppStore((s) => s.tasks)
  const focusedTaskId = useAppStore((s) => s.focusedTaskId)
  const focusTask = useAppStore((s) => s.focusTask)
  const cancelTask = useAppStore((s) => s.cancelTask)
  const open = useAppStore((s) => s.consoleOpen)
  const setConsoleOpen = useAppStore((s) => s.setConsoleOpen)

  const list = Object.values(tasks)
  const task = focusedTaskId ? tasks[focusedTaskId] : undefined
  const streamRef = useRef<HTMLDivElement>(null)
  const pinnedRef = useRef(true)

  useEffect(() => {
    const el = streamRef.current
    if (!el || !pinnedRef.current) return
    el.scrollTop = el.scrollHeight
  }, [task?.logs.length, open])

  if (!open || !task) return null

  const pct = task.total > 0 ? Math.round((task.current / task.total) * 100) : 0

  return (
    <AnimatePresence>
      <motion.section
        initial={{ opacity: 0, transform: 'translateY(12px)' }}
        animate={{ opacity: 1, transform: 'translateY(0px)' }}
        exit={{ opacity: 0, transform: 'translateY(12px)' }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        className="shrink-0 border-t border-white/10 bg-white/[0.04] backdrop-blur-md"
      >
        <div className="flex items-center gap-2 px-4 py-2">
          {task.running ? (
            <Loader2 className="size-4 shrink-0 animate-spin text-neon" />
          ) : task.success ? (
            <CheckCircle2 className="size-4 shrink-0 text-accent" />
          ) : (
            <XCircle className="size-4 shrink-0 text-rose-400" />
          )}

          <div className="min-w-0">
            <div className="truncate text-xs font-medium">
              {task.instanceName}
              <span className="text-muted"> · {task.label}</span>
            </div>
          </div>

          {list.length > 1 && (
            <div className="ml-3 flex items-center gap-1 overflow-x-auto">
              {list.map((t) => (
                <button
                  key={t.id}
                  onClick={() => focusTask(t.id)}
                  className={cn(
                    'rounded-md border px-2 py-0.5 text-[10px] whitespace-nowrap transition-colors',
                    t.id === task.id
                      ? 'border-neon/40 bg-neon/10 text-neon'
                      : 'border-white/10 text-muted hover:text-ink'
                  )}
                >
                  {t.instanceName}
                </button>
              ))}
            </div>
          )}

          <div className="ml-auto flex items-center gap-3">
            {task.total > 0 && (
              <span className="font-mono text-[11px] text-muted">{pct}%</span>
            )}
            {/* Rule 1: a running task must always be escapable, never a dead end. */}
            {task.running && (
              <Button
                variant="danger"
                size="sm"
                disabled={task.cancelling}
                onClick={() => void cancelTask(task.id)}
              >
                {task.cancelling ? (
                  <Loader2 className="animate-spin" />
                ) : (
                  <Ban />
                )}
                {task.cancelling ? 'Cancelling…' : 'Cancel Task'}
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setConsoleOpen(false)}
              aria-label="Collapse console"
            >
              <ChevronDown className="size-4" />
            </Button>
          </div>
        </div>

        {task.running && (
          <div className="px-4 pb-2">
            <Progress value={pct} indeterminate={task.total === 0} />
          </div>
        )}

        <div className="px-4 pb-4">
          <div
            ref={streamRef}
            onScroll={(e) => {
              const el = e.currentTarget
              pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32
            }}
            data-selectable
            className="h-44 overflow-y-auto rounded-xl border border-white/10 bg-[#050811] p-3 font-mono text-[11px] leading-relaxed"
          >
            {task.logs.length === 0 ? (
              <p className="text-muted/60">Waiting for output…</p>
            ) : (
              task.logs.map((line) => (
                <div
                  key={line.id}
                  className={cn('break-words whitespace-pre-wrap', LEVEL_CLASS[line.level] ?? 'text-slate-300')}
                >
                  {line.message}
                </div>
              ))
            )}
          </div>
        </div>
      </motion.section>
    </AnimatePresence>
  )
}

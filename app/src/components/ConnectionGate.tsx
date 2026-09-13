import { AlertTriangle, Loader2, RefreshCw, Sparkles, Terminal } from 'lucide-react'
import { motion } from 'framer-motion'

import { Button } from '@/components/ui/button'
import { useAppStore } from '@/store/app-store'

export function ConnectionGate() {
  const connection = useAppStore((s) => s.connection)
  const error = useAppStore((s) => s.connectionError)
  const connect = useAppStore((s) => s.connect)
  const startupStep = useAppStore((s) => s.startupStep)
  const startupProgress = useAppStore((s) => s.startupProgress)

  return (
    <div className="relative grid h-full place-items-center overflow-hidden bg-void px-6">
      {/* Cyberpunk ambient neon glows */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-32 -left-20 size-[32rem] rounded-full bg-accent/20 blur-[140px]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-32 -right-20 size-[30rem] rounded-full bg-neon/20 blur-[150px]"
      />

      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.98 }}
        transition={{ duration: 0.3 }}
        className="relative z-10 flex w-full max-w-md flex-col items-center gap-6 text-center"
      >
        {/* Animated Cyberpunk Core Icon */}
        <div className="relative grid size-20 place-items-center rounded-3xl border border-white/15 bg-white/[0.05] shadow-[0_0_30px_rgba(16,185,129,0.2)] backdrop-blur-xl">
          <div className="relative">
            <Sparkles className="size-9 text-accent drop-shadow-[0_0_12px_rgba(16,185,129,0.8)]" />
          </div>
          {connection === 'connecting' && (
            <>
              <span className="absolute inset-0 animate-pulse-ring rounded-3xl border border-accent/50" />
              <span className="absolute -inset-1 animate-pulse rounded-3xl border border-neon/30 opacity-75" />
            </>
          )}
        </div>

        {connection === 'connecting' ? (
          <div className="flex w-full flex-col items-center gap-4">
            <div>
              <div className="flex items-center justify-center gap-2">
                <span className="text-xs font-mono tracking-widest text-accent uppercase">
                  PHANTOMX OS // v1.2.0
                </span>
              </div>
              <h1 className="mt-1 text-xl font-bold tracking-tight text-white drop-shadow-sm">
                Initializing Core Engines
              </h1>
            </div>

            {/* Cyberpunk Progress Bar */}
            <div className="w-full space-y-2">
              <div className="relative h-2 w-full overflow-hidden rounded-full bg-white/10 p-0.5 backdrop-blur-md">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-accent via-emerald-400 to-neon shadow-[0_0_12px_rgba(16,185,129,0.8)]"
                  initial={{ width: '10%' }}
                  animate={{ width: `${Math.max(10, Math.min(100, startupProgress))}%` }}
                  transition={{ ease: 'easeOut', duration: 0.25 }}
                />
              </div>

              <div className="flex items-center justify-between text-[11px] font-mono text-muted">
                <span className="flex items-center gap-1.5 truncate text-left text-neutral-300">
                  <Terminal className="size-3 text-accent shrink-0" />
                  <span className="truncate">{startupStep || 'Đang khởi tạo các module...'}</span>
                </span>
                <span className="shrink-0 font-semibold text-accent">{startupProgress}%</span>
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs text-muted/80">
              <Loader2 className="size-3 animate-spin text-accent" />
              <span>Chuẩn bị không gian chơi Minecraft của bạn...</span>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-center gap-2 text-rose-400">
              <AlertTriangle className="size-5" />
              <h1 className="text-base font-semibold">Không thể kết nối lõi Sidecar</h1>
            </div>
            <p data-selectable className="text-xs break-words text-muted">
              {error || 'Sidecar không phản hồi tín hiệu bắt tay trong thời gian quy định.'}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void connect()}
              className="border-white/15 hover:border-accent hover:text-accent"
            >
              <RefreshCw className="size-4" />
              Thử kết nối lại
            </Button>
          </div>
        )}
      </motion.div>
    </div>
  )
}

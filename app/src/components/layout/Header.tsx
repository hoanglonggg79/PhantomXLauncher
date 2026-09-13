import type { ReactNode } from 'react'
import { Bug, Coffee, RefreshCw, Terminal } from 'lucide-react'

import { AccountPill } from '@/components/layout/AccountPill'
import { BackgroundMusicPlayer } from '@/components/layout/BackgroundMusicPlayer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app-store'

const TITLES: Record<string, { title: string; subtitle: string }> = {
  instances: { title: 'Instances', subtitle: 'Quản lý và khởi chạy Minecraft profiles của bạn' },
  marketplace: { title: 'Chợ Mod', subtitle: 'Tìm kiếm, xem ảnh và cài đặt mod từ Modrinth & CurseForge' },
  settings: { title: 'Settings', subtitle: 'Java, Cài đặt, bộ nhớ và hành vi khởi chạy' },
  about: { title: 'About', subtitle: 'Thông tin về Launcher và vị trí lưu trữ' },
}

export function Header({ actions }: { actions?: ReactNode }) {
  const screen = useAppStore((s) => s.screen)
  const java = useAppStore((s) => s.java)
  const instancesLoading = useAppStore((s) => s.instancesLoading)
  const refreshInstances = useAppStore((s) => s.refreshInstances)
  const consoleOpen = useAppStore((s) => s.consoleOpen)
  const setConsoleOpen = useAppStore((s) => s.setConsoleOpen)
  const taskCount = useAppStore((s) => Object.keys(s.tasks).length)
  const setBugReportOpen = useAppStore((s) => s.setBugReportOpen)

  const meta = TITLES[screen] ?? TITLES.instances

  return (
    <header className="flex h-16 shrink-0 items-center gap-3 border-b border-white/10 bg-white/[0.04] px-6 backdrop-blur-md">
      <div className="min-w-0">
        <h1 className="truncate text-base font-semibold tracking-tight">{meta.title}</h1>
        <p className="truncate text-xs text-muted">{meta.subtitle}</p>
      </div>

      <div className="ml-auto flex items-center gap-2">
        {java && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant={java.ok ? 'accent' : 'warn'} className="h-7 px-2">
                <Coffee className="size-3" />
                {java.ok ? `Java ${java.major ?? '?'}` : 'No Java'}
              </Badge>
            </TooltipTrigger>
            <TooltipContent>
              <p className="font-medium">{java.message}</p>
              {java.path && <p className="mt-1 font-mono text-[10px] break-all opacity-70">{java.path}</p>}
            </TooltipContent>
          </Tooltip>
        )}

        {/* Background Music Player */}
        <BackgroundMusicPlayer />

        {/* Account Pill — always visible */}
        <AccountPill />

        <Button
          variant="outline"
          size="sm"
          onClick={() => setBugReportOpen(true)}
          className="h-8 gap-1.5 border-rose-500/30 text-xs text-rose-300 hover:bg-rose-500/10 hover:text-rose-200"
          id="btn-report-bug"
        >
          <Bug className="size-3.5 text-rose-400" />
          <span>Report lỗi</span>
        </Button>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => void refreshInstances()}
              disabled={instancesLoading}
              aria-label="Refresh instances"
            >
              <RefreshCw className={cn('size-4', instancesLoading && 'animate-spin')} />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Refresh</TooltipContent>
        </Tooltip>

        {taskCount > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={consoleOpen ? 'neon' : 'ghost'}
                size="icon-sm"
                onClick={() => setConsoleOpen(!consoleOpen)}
                aria-label="Toggle console"
              >
                <Terminal className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{consoleOpen ? 'Hide console' : 'Show console'}</TooltipContent>
          </Tooltip>
        )}

        {actions}
      </div>
    </header>
  )
}

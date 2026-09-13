import { LogOut, RefreshCw, Settings, UserCircle2, Users } from 'lucide-react'

import { ElybyLoginDialog } from '@/components/auth/ElybyLoginDialog'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { AuthMode } from '@/lib/types'
import { cn } from '@/lib/utils'
import { elybyAvatarUrl, useElybyAuthStore } from '@/store/elyby-auth-store'
import { useAppStore } from '@/store/app-store'
import { useSupporterStore } from '@/store/supporter-store'

export function AccountPill() {
  const settings = useAppStore((s) => s.settings)
  const saveSettings = useAppStore((s) => s.saveSettings)
  const setScreen = useAppStore((s) => s.setScreen)
  const notify = useAppStore((s) => s.notify)

  const profile = useElybyAuthStore((s) => s.profile)
  const setLoginDialogOpen = useElybyAuthStore((s) => s.setLoginDialogOpen)
  const logout = useElybyAuthStore((s) => s.logout)
  const refresh = useElybyAuthStore((s) => s.refresh)
  const isLoading = useElybyAuthStore((s) => s.isLoading)

  const supporterStatus = useSupporterStore((s) => s.status)
  const isSupporter = supporterStatus?.active === true

  const authMode = (settings?.auth_mode as AuthMode) || 'offline'
  const isElyby = authMode === 'elyby'
  const displayName = isElyby && profile ? profile.username : settings?.username || 'Player'

  const switchToOffline = async () => {
    await saveSettings({ auth_mode: 'offline' })
    notify({ tone: 'info', message: 'Đã chuyển sang tài khoản Offline' })
  }

  const switchToElyby = async () => {
    await saveSettings({ auth_mode: 'elyby' })
    if (!profile) {
      setLoginDialogOpen(true)
    } else {
      notify({ tone: 'info', message: 'Đã chuyển sang tài khoản Ely.by' })
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className={cn(
              'flex h-8 items-center gap-2 rounded-full border px-2.5 pr-3',
              'border-neon/40 bg-white/[0.06] backdrop-blur-md transition-all',
              'hover:border-neon/70 hover:bg-white/[0.1] hover:shadow-[0_0_12px_rgba(0,242,254,0.25)]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neon/50'
            )}
            aria-label="Tài khoản"
          >
            {isElyby && profile ? (
              // Ely.by avatar — với emerald ring nếu là supporter
              <div
                className={cn(
                  'relative size-7 rounded-full',
                  isSupporter && 'ring-2 ring-emerald-400 ring-offset-1 ring-offset-black/80'
                )}
                style={isSupporter ? { animation: 'supporter-glow 3s ease-in-out infinite' } : undefined}
                title={isSupporter ? 'PhantomX Supporter' : undefined}
              >
                <img
                  src={elybyAvatarUrl(profile.username, 32)}
                  alt=""
                  className="size-7 rounded-full border border-white/10 bg-black/30"
                />
                {isSupporter && (
                  <div className="absolute -bottom-0.5 -right-0.5 size-3 rounded-full bg-emerald-400 border border-black/50 grid place-items-center">
                    <span className="text-[6px] leading-none">💎</span>
                  </div>
                )}
              </div>
            ) : (
              <div
                className={cn(
                  'relative grid size-7 place-items-center rounded-full border border-white/10 bg-slate-800/80',
                  isSupporter && 'ring-2 ring-emerald-400 ring-offset-1 ring-offset-black/80'
                )}
                style={isSupporter ? { animation: 'supporter-glow 3s ease-in-out infinite' } : undefined}
                title={isSupporter ? 'PhantomX Supporter' : undefined}
              >
                <UserCircle2 className="size-4 text-muted" />
                {isSupporter && (
                  <div className="absolute -bottom-0.5 -right-0.5 size-3 rounded-full bg-emerald-400 border border-black/50 grid place-items-center">
                    <span className="text-[6px] leading-none">💎</span>
                  </div>
                )}
              </div>
            )}
            <span className="max-w-[8rem] truncate text-xs font-medium text-ink">{displayName}</span>
            <Badge variant={isElyby ? 'neon' : 'muted'} className="h-4 px-1 text-[9px] uppercase">
              {isElyby ? 'Ely' : 'Off'}
            </Badge>
          </button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuLabel className="text-xs font-normal text-muted">
            {isElyby ? 'Tài khoản Ely.by' : 'Tài khoản Offline'}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />

          {isElyby ? (
            <>
              <DropdownMenuItem
                className="text-xs gap-2"
                disabled={isLoading}
                onClick={() => void switchToOffline()}
              >
                <Users className="size-3.5" />
                Chuyển sang Offline
              </DropdownMenuItem>
              {!profile && (
                <DropdownMenuItem className="text-xs gap-2" onClick={() => setLoginDialogOpen(true)}>
                  <UserCircle2 className="size-3.5" />
                  Đăng nhập Ely.by
                </DropdownMenuItem>
              )}
              {profile && (
                <DropdownMenuItem
                  className="text-xs gap-2"
                  disabled={isLoading}
                  onClick={() =>
                    void refresh().then((ok) =>
                      ok && notify({ tone: 'success', message: 'Đã làm mới phiên' })
                    )
                  }
                >
                  <RefreshCw className="size-3.5" />
                  Làm mới phiên
                </DropdownMenuItem>
              )}
            </>
          ) : (
            <DropdownMenuItem className="text-xs gap-2" onClick={() => void switchToElyby()}>
              <Users className="size-3.5" />
              Chuyển sang Ely.by
            </DropdownMenuItem>
          )}

          <DropdownMenuItem className="text-xs gap-2" onClick={() => setScreen('settings')}>
            <Settings className="size-3.5" />
            Cài đặt tài khoản
          </DropdownMenuItem>

          {isElyby && profile && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-xs gap-2 text-rose-300 focus:text-rose-200"
                disabled={isLoading}
                onClick={() => void logout()}
              >
                <LogOut className="size-3.5" />
                Đăng xuất
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <ElybyLoginDialog />
    </>
  )
}

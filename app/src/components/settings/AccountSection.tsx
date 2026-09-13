import { Loader2, LogIn, LogOut, RefreshCw, UserCircle2 } from 'lucide-react'

import { ElybyLoginDialog } from '@/components/auth/ElybyLoginDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { AuthMode } from '@/lib/types'
import { elybyAvatarUrl, useElybyAuthStore } from '@/store/elyby-auth-store'
import { useAppStore } from '@/store/app-store'

export function AccountSection() {
  const settings = useAppStore((s) => s.settings)
  const saveSettings = useAppStore((s) => s.saveSettings)
  const notify = useAppStore((s) => s.notify)

  const profile = useElybyAuthStore((s) => s.profile)
  const isLoading = useElybyAuthStore((s) => s.isLoading)
  const error = useElybyAuthStore((s) => s.error)
  const setLoginDialogOpen = useElybyAuthStore((s) => s.setLoginDialogOpen)
  const logout = useElybyAuthStore((s) => s.logout)
  const refresh = useElybyAuthStore((s) => s.refresh)
  const loadProfile = useElybyAuthStore((s) => s.loadProfile)

  const authMode = (settings?.auth_mode as AuthMode) || 'offline'
  const offlineUsername = settings?.username ?? 'Player'

  const switchMode = async (mode: AuthMode) => {
    await saveSettings({ auth_mode: mode })
    if (mode === 'elyby') {
      await loadProfile()
    }
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Tài khoản</CardTitle>
          <CardDescription>
            Chọn cách xác thực khi khởi động Minecraft: Offline hoặc Ely.by.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs
            value={authMode}
            onValueChange={(v) => void switchMode(v as AuthMode)}
            className="w-full"
          >
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="offline" className="text-xs">
                Offline
              </TabsTrigger>
              <TabsTrigger value="elyby" className="text-xs">
                Ely.by
              </TabsTrigger>
            </TabsList>

            <TabsContent value="offline" className="mt-4 space-y-2">
              <p className="text-xs text-muted">
                Dùng tên người chơi tùy ý (không skin online). Chỉnh username ở mục Player bên dưới.
              </p>
              <div className="flex items-center gap--2 rounded-lg border border-white/10 bg-white/[0.03] p-3">
                <UserCircle2 className="size-8 text-muted" />
                <div>
                  <p className="text-xs text-muted">Đang dùng</p>
                  <p className="font-semibold text-ink">{offlineUsername}</p>
                </div>
                <Badge variant="muted" className="ml-auto text-[10px]">
                  Offline
                </Badge>
              </div>
            </TabsContent>

            <TabsContent value="elyby" className="mt-4 space-y-3">
              {profile ? (
                <div className="flex items-center gap-3 rounded-xl border border-neon/30 bg-neon/5 p-3">
                  <img
                    src={elybyAvatarUrl(profile.username, 48)}
                    alt={profile.username}
                    className="size-12 rounded-lg border border-white/10 bg-black/40"
                    onError={(e) => {
                      ; (e.target as HTMLImageElement).style.display = 'none'
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-muted">Đã đăng nhập</p>
                    <p className="truncate font-semibold text-ink">{profile.username}</p>
                    <p className="font-mono text-[10px] text-muted truncate">{profile.uuid}</p>
                  </div>
                  <Badge variant="neon" className="shrink-0 text-[10px]">
                    Ely.by
                  </Badge>
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-white/15 p-4 text-center">
                  <p className="text-xs text-muted">Chưa đăng nhập Ely.by</p>
                  <Button
                    variant="play"
                    size="sm"
                    className="mt-3 gap-1.5"
                    onClick={() => setLoginDialogOpen(true)}
                  >
                    <LogIn className="size-3.5" />
                    Đăng nhập Ely.by
                  </Button>
                </div>
              )}

              {error && (
                <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                  {error}
                </p>
              )}

              {profile && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5 text-xs"
                    disabled={isLoading}
                    onClick={() => void refresh().then((ok) => ok && notify({ tone: 'success', message: 'Đã làm mới phiên Ely.by' }))}
                  >
                    {isLoading ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3.5" />
                    )}
                    Làm mới phiên
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="gap-1.5 text-xs text-rose-300 hover:text-rose-200"
                    disabled={isLoading}
                    onClick={() => void logout()}
                  >
                    <LogOut className="size-3.5" />
                    Đăng xuất
                  </Button>
                </div>
              )}

              {!profile && (
                <p className="text-[11px] text-muted leading-relaxed">
                  Khi chơi với Ely.by, launcher tự tải authlib-injector và inject vào JVM để skin
                  hiển thị trên server online-mode (nếu server cũng dùng authlib-injector).
                </p>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <ElybyLoginDialog />
    </>
  )
}

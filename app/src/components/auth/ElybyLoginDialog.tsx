import { useEffect, useState } from 'react'
import { Loader2, ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useElybyAuthStore } from '@/store/elyby-auth-store'

export function ElybyLoginDialog() {
  const open = useElybyAuthStore((s) => s.loginDialogOpen)
  const setOpen = useElybyAuthStore((s) => s.setLoginDialogOpen)
  const login = useElybyAuthStore((s) => s.login)
  const isLoading = useElybyAuthStore((s) => s.isLoading)
  const error = useElybyAuthStore((s) => s.error)
  const is2FARequired = useElybyAuthStore((s) => s.is2FARequired)
  const clearError = useElybyAuthStore((s) => s.clearError)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totp, setTotp] = useState('')

  useEffect(() => {
    if (!open) {
      setUsername('')
      setPassword('')
      setTotp('')
      clearError()
    }
  }, [open, clearError])

  const submit = async () => {
    await login(username, password, is2FARequired ? totp : undefined)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md border-white/10 bg-slate-950/95 text-ink">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="size-5 text-neon" />
            Đăng nhập Ely.by
          </DialogTitle>
          <DialogDescription className="text-xs">
            Xác thực tài khoản Ely.by để chơi online với skin và cape. Mật khẩu không được lưu
            trên máy — chỉ access token được mã hóa.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 py-1">
          <div className="grid gap-1.5">
            <Label htmlFor="elyby-user">Tên đăng nhập / Email</Label>
            <Input
              id="elyby-user"
              value={username}
              autoComplete="username"
              disabled={isLoading || is2FARequired}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void submit()}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="elyby-pass">Mật khẩu</Label>
            <Input
              id="elyby-pass"
              type="password"
              value={password}
              autoComplete="current-password"
              disabled={isLoading}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && void submit()}
            />
          </div>

          {is2FARequired && (
            <div className="grid gap-1.5">
              <Label htmlFor="elyby-totp">Mã xác thực 2 bước (6 số)</Label>
              <Input
                id="elyby-totp"
                inputMode="numeric"
                maxLength={6}
                value={totp}
                autoComplete="one-time-code"
                disabled={isLoading}
                placeholder="123456"
                onChange={(e) => setTotp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                onKeyDown={(e) => e.key === 'Enter' && void submit()}
              />
            </div>
          )}

          {error && (
            <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
              {error}
            </p>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="ghost" size="sm" disabled={isLoading} onClick={() => setOpen(false)}>
            Hủy
          </Button>
          <Button variant="play" size="sm" disabled={isLoading} onClick={() => void submit()}>
            {isLoading ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                Đang xác thực…
              </>
            ) : (
              'Đăng nhập'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

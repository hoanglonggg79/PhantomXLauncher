import { useState, useRef, useCallback } from 'react'
import { CheckCircle2, Gem, Loader2, AlertCircle, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { useSupporterStore, type SupporterTheme } from '@/store/supporter-store'

// ── Helper ────────────────────────────────────────────────────────────────────

function formatRedeemedAt(iso?: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

/** State A — chưa nhập key */
function IdleState({
  tokenInput,
  onTokenChange,
  onSubmit,
}: {
  tokenInput: string
  onTokenChange: (v: string) => void
  onSubmit: () => void
}) {
  return (
    <div className="grid gap-3">
      <p className="text-sm text-ink/80 leading-relaxed">
        PhantomX là mã nguồn mở &amp; miễn phí hoàn toàn.
        Nếu bạn nhận được key từ nhà phát triển,
        nhập vào đây để mở khóa huy hiệu tri ân.
      </p>
      <div className="flex gap-2">
        <Input
          id="supporter-key-input"
          value={tokenInput}
          onChange={(e) => onTokenChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
          placeholder="Dán Supporter Key vào đây..."
          className="flex-1 font-mono text-xs"
        />
        <Button
          id="supporter-activate-btn"
          variant="play"
          size="sm"
          disabled={!tokenInput.trim()}
          onClick={onSubmit}
          className="shrink-0"
        >
          Kích hoạt
        </Button>
      </div>
      <p className="flex items-start gap-1.5 text-[11px] text-muted leading-relaxed">
        <span className="mt-0.5 shrink-0">ℹ️</span>
        Key tri ân dành tặng những người ủng hộ dự án. Mở khóa huy hiệu và các tùy biến giao diện độc quyền mà không giới hạn bất kỳ tính năng nào của người chơi.
      </p>
    </div>
  )
}

/** State B — đang verify */
function LoadingState() {
  return (
    <div className="flex items-center gap-3 py-2">
      <Loader2 className="size-5 shrink-0 animate-spin text-accent" />
      <span className="text-sm text-muted">Đang xác thực key…</span>
    </div>
  )
}

/** State C — active supporter */
function ActiveState({
  discordId,
  redeemedAt,
  selectedTheme,
  onThemeChange,
  onRevoke,
}: {
  discordId?: string
  redeemedAt?: string
  selectedTheme: SupporterTheme
  onThemeChange: (t: SupporterTheme) => void
  onRevoke: () => void
}) {
  return (
    <div className="grid gap-4">
      {/* Badge row */}
      <div className="flex items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3.5 py-2.5">
        <div
          className="grid size-9 shrink-0 place-items-center rounded-full border border-emerald-400/40 bg-emerald-400/10"
          style={{ animation: 'supporter-pulse-ring 3s ease-in-out infinite' }}
        >
          <Gem className="size-5 text-emerald-400" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-emerald-300">💎 Supporter</p>
          <p className="text-[11px] text-muted truncate">
            {discordId ? `Discord: ${discordId}` : 'Badge đã kích hoạt'}
            {redeemedAt ? ` · ${formatRedeemedAt(redeemedAt)}` : ''}
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-emerald-400/70 font-medium">Active</span>
      </div>

      {/* Perks list */}
      <div className="grid gap-1.5">
        <p className="text-[11px] uppercase tracking-wider text-muted font-medium">Đặc quyền tri ân</p>
        {[
          { emoji: '💎', text: 'Huy hiệu trong launcher & AccountPill' },
          { emoji: '✨', text: 'Viền Emerald avatar animated' },
          { emoji: '🎨', text: 'Theme độc quyền (Cyberpunk Neon, Synthwave)' },
          { emoji: '🚀', text: 'Nhận các bản cập nhật và tính năng mới sớm nhất' },
          { emoji: '💖', text: 'Chân thành cảm ơn sự đồng hành và ủng hộ của bạn!' },
        ].map(({ emoji, text }) => (
          <div key={text} className="flex items-center gap-2 text-[12px] text-ink/75">
            <span className="w-5 text-center">{emoji}</span>
            <span>{text}</span>
          </div>
        ))}
      </div>

      {/* Theme selector + revoke */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Sparkles className="size-3.5 shrink-0 text-emerald-400" />
          <span className="text-xs text-muted shrink-0">Theme:</span>
          <Select
            value={selectedTheme}
            onValueChange={(v) => onThemeChange(v as SupporterTheme)}
          >
            <SelectTrigger id="supporter-theme-select" className="h-8 text-xs max-w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">Default</SelectItem>
              <SelectItem value="cyberpunk">Cyberpunk Neon</SelectItem>
              <SelectItem value="synthwave">Synthwave</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <button
          type="button"
          onClick={onRevoke}
          className="text-[11px] text-muted/60 hover:text-rose-400 transition-colors underline-offset-2 hover:underline shrink-0"
        >
          Thu hồi badge
        </button>
      </div>
    </div>
  )
}

/** State D — lỗi key */
function ErrorState({
  error,
  tokenInput,
  onTokenChange,
  onSubmit,
  shake,
}: {
  error: string
  tokenInput: string
  onTokenChange: (v: string) => void
  onSubmit: () => void
  shake: boolean
}) {
  return (
    <div className="grid gap-3">
      <div
        className={cn(
          'flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2.5',
          shake && '[animation:supporter-shake_0.5s_ease-in-out]'
        )}
      >
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-rose-400" />
        <p className="text-sm text-rose-300">{error}</p>
      </div>
      <div className="flex gap-2">
        <Input
          id="supporter-key-input"
          value={tokenInput}
          onChange={(e) => onTokenChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
          placeholder="Nhập lại Supporter Key..."
          className="flex-1 font-mono text-xs border-rose-500/30 focus:border-rose-400/50"
        />
        <Button
          id="supporter-activate-btn"
          variant="play"
          size="sm"
          disabled={!tokenInput.trim()}
          onClick={onSubmit}
          className="shrink-0"
        >
          Thử lại
        </Button>
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export function SupporterSection() {
  const status = useSupporterStore((s) => s.status)
  const isLoading = useSupporterStore((s) => s.isLoading)
  const verifyError = useSupporterStore((s) => s.verifyError)
  const selectedTheme = useSupporterStore((s) => s.selectedTheme)
  const verifyToken = useSupporterStore((s) => s.verifyToken)
  const revoke = useSupporterStore((s) => s.revoke)
  const setTheme = useSupporterStore((s) => s.setTheme)
  const clearVerifyError = useSupporterStore((s) => s.clearVerifyError)

  const [tokenInput, setTokenInput] = useState('')
  const [shake, setShake] = useState(false)
  const shakeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const isActive = status?.active === true

  const triggerShake = useCallback(() => {
    setShake(true)
    if (shakeTimer.current) clearTimeout(shakeTimer.current)
    shakeTimer.current = setTimeout(() => setShake(false), 600)
  }, [])

  const handleSubmit = useCallback(async () => {
    if (!tokenInput.trim()) return
    clearVerifyError()
    const ok = await verifyToken(tokenInput.trim())
    if (ok) {
      setTokenInput('')
    } else {
      triggerShake()
    }
  }, [tokenInput, verifyToken, clearVerifyError, triggerShake])

  const handleTokenChange = useCallback((v: string) => {
    setTokenInput(v)
    if (verifyError) clearVerifyError()
  }, [verifyError, clearVerifyError])

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <Card
      className={cn(
        'transition-all duration-500',
        isActive && [
          'border-emerald-500/30',
          'shadow-[0_0_24px_rgba(16,185,129,0.08)]',
        ]
      )}
      style={
        isActive
          ? {
            background:
              'linear-gradient(135deg, rgba(16,185,129,0.04) 0%, rgba(0,242,254,0.02) 100%)',
          }
          : undefined
      }
    >
      <CardHeader className="flex-row items-center gap-3 pb-3">
        <div
          className={cn(
            'grid size-10 shrink-0 place-items-center rounded-xl border transition-all duration-500',
            isActive
              ? 'border-emerald-500/40 bg-emerald-500/10'
              : 'border-white/10 bg-white/[0.04]'
          )}
        >
          {isActive ? (
            <CheckCircle2 className="size-5 text-emerald-400" />
          ) : (
            <Gem className="size-5 text-muted" />
          )}
        </div>
        <div>
          <CardTitle className="text-base">
            {isActive ? 'Huy hiệu Supporter đang hoạt động' : '💎 Hỗ trợ dự án'}
          </CardTitle>
          <CardDescription>
            {isActive
              ? 'Cảm ơn bạn đã ủng hộ PhantomX!'
              : 'Nhập key để mở khóa huy hiệu tri ân'}
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <LoadingState />
        ) : isActive ? (
          <ActiveState
            discordId={status?.discord_id}
            redeemedAt={status?.redeemed_at}
            selectedTheme={selectedTheme}
            onThemeChange={setTheme}
            onRevoke={() => void revoke()}
          />
        ) : verifyError ? (
          <ErrorState
            error={verifyError}
            tokenInput={tokenInput}
            onTokenChange={handleTokenChange}
            onSubmit={() => void handleSubmit()}
            shake={shake}
          />
        ) : (
          <IdleState
            tokenInput={tokenInput}
            onTokenChange={handleTokenChange}
            onSubmit={() => void handleSubmit()}
          />
        )}
      </CardContent>
    </Card>
  )
}

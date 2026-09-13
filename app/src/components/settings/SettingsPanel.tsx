import { useEffect, useState } from 'react'
import { Music, RotateCcw, Save } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { AccountSection } from '@/components/settings/AccountSection'
import { JavaManagerSection } from '@/components/settings/JavaManagerSection'
import type { SettingsPatch } from '@/lib/types'
import { useAppStore } from '@/store/app-store'

const RAM_MIN = 512
const RAM_MAX = 16384
const RAM_STEP = 512

type Draft = Required<Pick<SettingsPatch, 'username' | 'ram' | 'java_path' | 'extra_jvm' | 'snapshots' | 'close_on_launch' | 'bg_music_enabled' | 'bg_music_volume' | 'discord_rpc_enabled'>>

const EMPTY: Draft = {
  username: 'Player',
  ram: 2048,
  java_path: '',
  extra_jvm: '',
  snapshots: false,
  close_on_launch: false,
  bg_music_enabled: true,
  bg_music_volume: 0.7,
  discord_rpc_enabled: true,
}

export function SettingsPanel() {
  const settings = useAppStore((s) => s.settings)
  const saveSettings = useAppStore((s) => s.saveSettings)
  const setBgMusicMuted = useAppStore((s) => s.setBgMusicMuted)
  const setBgMusicVolume = useAppStore((s) => s.setBgMusicVolume)

  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!settings) return
    setDraft({
      username: settings.username ?? 'Player',
      ram: settings.ram ?? 2048,
      java_path: settings.java_path ?? '',
      extra_jvm: settings.extra_jvm ?? '',
      snapshots: Boolean(settings.snapshots),
      close_on_launch: Boolean(settings.close_on_launch),
      bg_music_enabled: settings.bg_music_enabled !== false,
      bg_music_volume: typeof settings.bg_music_volume === 'number' ? settings.bg_music_volume : 0.7,
      discord_rpc_enabled: settings.discord_rpc_enabled !== false,
    })
  }, [settings])

  const dirty =
    !!settings &&
    (draft.username !== (settings.username ?? '') ||
      draft.ram !== (settings.ram ?? 0) ||
      draft.java_path !== (settings.java_path ?? '') ||
      draft.extra_jvm !== (settings.extra_jvm ?? '') ||
      draft.snapshots !== Boolean(settings.snapshots) ||
      draft.close_on_launch !== Boolean(settings.close_on_launch) ||
      draft.bg_music_enabled !== (settings.bg_music_enabled !== false) ||
      draft.bg_music_volume !== (typeof settings.bg_music_volume === 'number' ? settings.bg_music_volume : 0.7) ||
      draft.discord_rpc_enabled !== (settings.discord_rpc_enabled !== false))

  const patch = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }))

  const submit = async () => {
    setSaving(true)
    await saveSettings(draft)
    // Sync audio player state live so it reflects immediately without reload
    setBgMusicMuted(!draft.bg_music_enabled)
    setBgMusicVolume(draft.bg_music_volume)
    setSaving(false)
  }

  return (
    <ScrollArea className="flex-1">
      <div className="mx-auto grid max-w-2xl gap-4 px-6 py-5">
        <AccountSection />

        <Card>
          <CardHeader>
            <CardTitle>Player</CardTitle>
            <CardDescription>Profile offline được sử dụng khi tạo lệnh khởi chạy.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-1.5">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              value={draft.username}
              maxLength={32}
              onChange={(e) => patch('username', e.target.value)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Memory</CardTitle>
            <CardDescription>Bộ nhớ RAM tối đa được cấp cho JVM (-Xmx).</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="ram">Allocation</Label>
              <span className="font-mono text-sm text-neon">
                {draft.ram} MB
                <span className="ml-2 text-xs text-muted">
                  ({(draft.ram / 1024).toFixed(1)} GB)
                </span>
              </span>
            </div>
            <Slider
              id="ram"
              min={RAM_MIN}
              max={RAM_MAX}
              step={RAM_STEP}
              value={[Math.min(RAM_MAX, Math.max(RAM_MIN, draft.ram))]}
              onValueChange={([value]) => patch('ram', value)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Java Runtime</CardTitle>
            <CardDescription>
              Quản lý các cài đặt và phiên bản Java được sử dụng để khởi chạy Minecraft. Để trống
              nếu muốn PhantomX tự động chọn phiên bản phù hợp.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <JavaManagerSection />
            <div className="grid gap-1.5 border-t border-white/5 pt-4">
              <Label htmlFor="java-path">Tùy chọn đường dẫn Java</Label>
              <Input
                id="java-path"
                value={draft.java_path}
                placeholder="C:/Program Files/Java/jdk-21/bin/java.exe"
                onChange={(e) => patch('java_path', e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="extra-jvm">Tham số JVM bổ sung</Label>
              <Input
                id="extra-jvm"
                value={draft.extra_jvm}
                placeholder="-XX:+UseG1GC -Dsun.stdout.encoding=UTF-8"
                onChange={(e) => patch('extra_jvm', e.target.value)}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Behaviour</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <ToggleRow
              id="snapshots"
              label="Hiển thị phiên bản snapshot"
              hint="Hiển thị các phiên bản snapshot trong danh sách phiên bản."
              checked={draft.snapshots}
              onChange={(v) => patch('snapshots', v)}
            />
            <ToggleRow
              id="close-on-launch"
              label="Đóng launcher sau khi khởi chạy game"
              hint="Tự động đóng PhantomX sau khi game Minecraft được khởi chạy."
              checked={draft.close_on_launch}
              onChange={(v) => patch('close_on_launch', v)}
            />
          </CardContent>
        </Card>

        {/* ── Audio & Discord Card ─────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Music className="size-4 text-accent" />
              Âm thanh & Discord
            </CardTitle>
            <CardDescription>
              Cài đặt nhạc nền PhantomX Theme và kết nối hiển thị trạng thái Discord Rich Presence.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <ToggleRow
              id="bg-music-enabled"
              label="Phát nhạc nền khi khởi động"
              hint="Tự động phát PhantomX Theme khi mở Launcher (có thể bật/tắt nhanh ở Header)."
              checked={draft.bg_music_enabled}
              onChange={(v) => patch('bg_music_enabled', v)}
            />

            <div className="rounded-lg border border-white/5 bg-slate-900/80 p-3 space-y-3">
              <div className="flex items-baseline justify-between">
                <Label htmlFor="bg-music-volume" className="text-ink normal-case">
                  Âm lượng nhạc nền
                </Label>
                <span className="font-mono text-sm text-neon">
                  {Math.round(draft.bg_music_volume * 100)}%
                </span>
              </div>
              <Slider
                id="bg-music-volume"
                min={0}
                max={100}
                step={5}
                disabled={!draft.bg_music_enabled}
                value={[Math.round(draft.bg_music_volume * 100)]}
                onValueChange={([v]) => patch('bg_music_volume', v / 100)}
                className="mt-1"
              />
              <p className="text-xs text-muted">Kéo thanh trượt để điều chỉnh âm lượng từ 0% đến 100%.</p>
            </div>

            <ToggleRow
              id="discord-rpc-enabled"
              label="Discord Rich Presence"
              hint="Hiển thị trạng thái Launcher (Idle / Marketplace / In-Game) lên profile Discord của bạn."
              checked={draft.discord_rpc_enabled}
              onChange={(v) => patch('discord_rpc_enabled', v)}
            />
          </CardContent>
        </Card>

        <div className="flex items-center justify-end gap-2 pb-2">
          <Button
            variant="ghost"
            disabled={!dirty || saving}
            onClick={() =>
              settings &&
              setDraft({
                username: settings.username ?? 'Player',
                ram: settings.ram ?? 2048,
                java_path: settings.java_path ?? '',
                extra_jvm: settings.extra_jvm ?? '',
                snapshots: Boolean(settings.snapshots),
                close_on_launch: Boolean(settings.close_on_launch),
                bg_music_enabled: settings.bg_music_enabled !== false,
                bg_music_volume: typeof settings.bg_music_volume === 'number' ? settings.bg_music_volume : 0.7,
                discord_rpc_enabled: settings.discord_rpc_enabled !== false,
              })
            }
          >
            <RotateCcw className="size-4" />
            Hoàn tác
          </Button>
          <Button variant="play" disabled={!dirty || saving} onClick={() => void submit()}>
            <Save className="size-4" />
            {saving ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      </div>
    </ScrollArea>
  )
}

function ToggleRow({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string
  label: string
  hint: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-white/5 bg-slate-900/80 p-3">
      <div className="min-w-0">
        <Label htmlFor={id} className="text-ink normal-case">
          {label}
        </Label>
        <p className="mt-0.5 text-xs text-muted">{hint}</p>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

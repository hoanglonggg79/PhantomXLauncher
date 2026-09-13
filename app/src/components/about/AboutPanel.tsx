import { Cpu, ExternalLink, FolderOpen, HardDrive, ScrollText, Zap } from 'lucide-react'

import { ChangelogSection } from '@/components/about/ChangelogSection'
import { SupporterSection } from '@/components/about/SupporterSection'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { openExternalUrl } from '@/lib/sidecar'
import { useAppStore } from '@/store/app-store'

export function AboutPanel() {
  const info = useAppStore((s) => s.info)
  const sidecar = useAppStore((s) => s.sidecar)

  const paths = info
    ? [
      { icon: HardDrive, label: 'Nơi lưu trữ', value: info.base_dir },
      { icon: FolderOpen, label: 'Instances', value: info.instances_dir },
      { icon: ScrollText, label: 'Logs', value: info.log_dir },
    ]
    : []

  return (
    <ScrollArea className="flex-1">
      <div className="mx-auto grid max-w-2xl gap-4 px-6 py-5">
        <Card>
          <CardHeader className="flex-row items-center gap-3">
            <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-accent/30 bg-accent/10">
              <Zap className="size-5 text-accent" />
            </div>
            <div>
              <CardTitle className="text-base">{info?.app_name ?? 'PhantomX'}</CardTitle>
              <CardDescription>
                {info ? `v${info.app_version} · ${info.app_author}` : 'Đang kết nối tới core…'}
              </CardDescription>
            </div>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Runtime</CardTitle>
            <CardDescription>Được Python core báo cáo thông qua local bridge.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-1.5">
            <Badge variant={info?.java_ok ? 'accent' : 'warn'}>
              <Cpu className="size-3" />
              {info?.java_status ?? 'Java unknown'}
            </Badge>
            <Badge variant={info?.qt_available ? 'neon' : 'muted'}>
              Qt {info?.qt_available ? 'available' : 'headless'}
            </Badge>
            <Badge variant={info?.keyring_available ? 'neon' : 'muted'}>
              Keyring {info?.keyring_available ? 'on' : 'off'}
            </Badge>
            <Badge variant={info?.psutil_available ? 'neon' : 'muted'}>
              psutil {info?.psutil_available ? 'on' : 'off'}
            </Badge>
            {sidecar && <Badge variant="muted">port {sidecar.port}</Badge>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Locations</CardTitle>
            <CardDescription>
              Tất cả dữ liệu của người dùng đều được lưu trữ bên ngoài thư mục hiện tại để giữ cho thư mục luôn gọn gàng.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {paths.map(({ icon: Icon, label, value }) => (
              <div
                key={label}
                className="flex items-start gap-2.5 rounded-lg border border-white/5 bg-slate-900/80 p-2.5"
              >
                <Icon className="mt-0.5 size-4 shrink-0 text-muted" />
                <div className="min-w-0">
                  <p className="text-[10px] tracking-wide text-muted uppercase">{label}</p>
                  <p data-selectable className="font-mono text-[11px] break-all">
                    {value}
                  </p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Community & Social Links */}
        <Card>
          <CardHeader>
            <CardTitle>Cộng đồng & Liên kết</CardTitle>
            <CardDescription>
              Theo dõi kênh của nhà phát triển, đóng góp mã nguồn và tham gia cộng đồng thảo luận.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            <Button
              variant="outline"
              className="h-11 justify-start gap-2.5 border-red-500/20 bg-red-500/5 text-ink hover:border-red-500/40 hover:bg-red-500/10"
              onClick={() => void openExternalUrl('https://www.Youtube.com/@LongHoang-2105/')}
            >
              <svg className="size-4 shrink-0 fill-red-500" viewBox="0 0 24 24">
                <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
              </svg>
              <div className="flex flex-col items-start text-left">
                <span className="text-xs font-semibold">Youtube</span>
                <span className="text-[10px] text-muted">Kênh của dev</span>
              </div>
              <ExternalLink className="ml-auto size-3 text-muted" />
            </Button>

            <Button
              variant="outline"
              className="h-11 justify-start gap-2.5 border-white/15 bg-white/[0.03] text-ink hover:border-white/30 hover:bg-white/[0.08]"
              onClick={() => void openExternalUrl('https://github.com/hoanglonggg79/PhantomXLauncher')}
            >
              <svg className="size-4 shrink-0 fill-white" viewBox="0 0 24 24">
                <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              <div className="flex flex-col items-start text-left">
                <span className="text-xs font-semibold">Github</span>
                <span className="text-[10px] text-muted">Star repo</span>
              </div>
              <ExternalLink className="ml-auto size-3 text-muted" />
            </Button>

            <Button
              variant="outline"
              className="h-11 justify-start gap-2.5 border-indigo-500/20 bg-indigo-500/5 text-ink hover:border-indigo-500/40 hover:bg-indigo-500/10"
              onClick={() => void openExternalUrl('https://discord.gg/PECavu2q4w')}
            >
              <svg className="size-4 shrink-0 fill-[#5865F2]" viewBox="0 0 24 24">
                <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994.021-.041.001-.09-.041-.106a13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.894.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
              </svg>
              <div className="flex flex-col items-start text-left">
                <span className="text-xs font-semibold">Server Discord</span>
                <span className="text-[10px] text-muted">Cộng đồng</span>
              </div>
              <ExternalLink className="ml-auto size-3 text-muted" />
            </Button>
          </CardContent>
        </Card>

        <ChangelogSection />

        <SupporterSection />
      </div>
    </ScrollArea>
  )
}


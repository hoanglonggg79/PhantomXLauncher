import { ExternalLink, Sparkles } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { openExternalUrl } from '@/lib/sidecar'
import { useAppStore } from '@/store/app-store'

export function UpdateDialog() {
  const updateInfo = useAppStore((s) => s.updateAvailable)
  const dismissed = useAppStore((s) => s.updateDismissed)
  const dismiss = useAppStore((s) => s.dismissUpdate)

  if (!updateInfo || !updateInfo.has_update || dismissed) {
    return null
  }

  const handleUpdateNow = () => {
    const url = updateInfo.releases_url || updateInfo.repo_url
    if (url) {
      void openExternalUrl(url)
    }
    dismiss()
  }

  return (
    <Dialog open={true} onOpenChange={(open) => !open && dismiss()}>
      <DialogContent className="max-w-md border-white/15 bg-slate-950/95 p-6 text-ink shadow-2xl backdrop-blur-2xl">
        <DialogHeader className="space-y-3">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl border border-accent/40 bg-accent/15 text-accent shadow-[0_0_15px_rgba(16,185,129,0.3)]">
              <Sparkles className="size-5 animate-pulse" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold text-ink">
                Đã có phiên bản mới!
              </DialogTitle>
              <div className="flex items-center gap-2 mt-0.5">
                <Badge variant="accent" className="font-mono text-[11px]">
                  v{updateInfo.latest_version}
                </Badge>
                <span className="text-xs text-muted">
                  (Hiện tại: v{updateInfo.current_version})
                </span>
              </div>
            </div>
          </div>

          <DialogDescription className="text-xs text-ink/80 leading-relaxed pt-1">
            Một bản cập nhật mới của <strong>PhantomX Launcher</strong> đã sẵn sàng trên GitHub với nhiều tính năng mới, cải thiện hiệu năng và sửa lỗi. Bạn có muốn cập nhật ngay bây giờ không?
          </DialogDescription>
        </DialogHeader>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={dismiss}
            className="text-xs text-muted hover:text-ink"
          >
            Ở lại dùng tiếp
          </Button>
          <Button
            type="button"
            variant="play"
            size="sm"
            onClick={handleUpdateNow}
            className="gap-1.5 text-xs shadow-[0_0_12px_rgba(16,185,129,0.4)]"
          >
            <span>Cập nhật ngay</span>
            <ExternalLink className="size-3.5" />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

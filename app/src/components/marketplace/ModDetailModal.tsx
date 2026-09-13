import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle,
  ArrowDownToLine,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Eye,
  Heart,
  Image as ImageIcon,
  Loader2,
  Package,
  Sparkles,
  X,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { openExternalUrl } from '@/lib/sidecar'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { MarketplaceGalleryImage } from '@/lib/types'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app-store'

export function ModDetailModal() {
  const open = useAppStore((s) => s.marketplaceDetailOpen)
  const close = useAppStore((s) => s.closeMarketplaceDetail)
  const project = useAppStore((s) => s.marketplaceSelectedProject)
  const loading = useAppStore((s) => s.marketplaceProjectLoading)
  const versions = useAppStore((s) => s.marketplaceVersions)
  const versionsLoading = useAppStore((s) => s.marketplaceVersionsLoading)
  const instances = useAppStore((s) => s.instances)
  const installMod = useAppStore((s) => s.installMarketplaceMod)

  const [selectedInstanceName, setSelectedInstanceName] = useState<string>('')
  const [selectedVersionId, setSelectedVersionId] = useState<string>('')
  const [activeImageIndex, setActiveImageIndex] = useState<number>(0)
  const [showRawIcon, setShowRawIcon] = useState<boolean>(false)
  const [lightboxImage, setLightboxImage] = useState<MarketplaceGalleryImage | null>(null)
  const [installing, setInstalling] = useState<boolean>(false)

  // Initialize selected instance
  useEffect(() => {
    if (instances.length > 0 && !selectedInstanceName) {
      setSelectedInstanceName(instances[0].name)
    }
  }, [instances, selectedInstanceName])

  // Select first primary or first available version
  useEffect(() => {
    if (versions.length > 0) {
      setSelectedVersionId(versions[0].id)
    } else {
      setSelectedVersionId('')
    }
  }, [versions])

  // Reset internal states whenever project changes or modal closes
  useEffect(() => {
    setLightboxImage(null)
    setActiveImageIndex(0)
    setShowRawIcon(false)
  }, [project?.id])

  useEffect(() => {
    if (!open) {
      setLightboxImage(null)
      setActiveImageIndex(0)
      setShowRawIcon(false)
    }
  }, [open])

  // Intercept Escape key when lightbox is open to close only the lightbox
  useEffect(() => {
    if (!lightboxImage) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        setLightboxImage(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [lightboxImage])

  const selectedInstance = instances.find((i) => i.name === selectedInstanceName)
  const isInstanceBusy = selectedInstance?.running === true
  const selectedVersion = versions.find((v) => v.id === selectedVersionId) || versions[0]
  const targetFile = selectedVersion?.files?.find((f) => f.primary) || selectedVersion?.files?.[0]

  const handleInstall = async () => {
    if (!project || !selectedInstanceName || !targetFile || !selectedVersion) return

    setInstalling(true)
    const success = await installMod({
      instanceName: selectedInstanceName,
      source: project.source,
      projectId: project.id,
      projectTitle: project.title,
      fileId: targetFile.id,
      downloadUrl: targetFile.download_url,
      filename: targetFile.filename,
    })
    setInstalling(false)

    if (success) {
      close()
    }
  }

  const images = project?.gallery || []

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && close()}>
        <DialogContent className="max-h-[90vh] max-w-4xl border-white/10 bg-slate-950/95 p-0 text-ink shadow-2xl backdrop-blur-2xl">
          {loading || !project ? (
            <div className="flex h-96 flex-col items-center justify-center gap-3">
              <Loader2 className="size-8 animate-spin text-accent" />
              <p className="text-xs text-muted">Đang tải thông tin chi tiết Mod…</p>
            </div>
          ) : (
            <div className="flex max-h-[90vh] flex-col">
              {/* Header section */}
              <DialogHeader className="border-b border-white/10 p-6 pb-4">
                <div className="flex items-start gap-4">
                  {/* Mod Icon with raw toggle */}
                  <div className="group relative size-16 shrink-0 overflow-hidden rounded-xl border border-white/10 bg-white/5 p-1">
                    <img
                      src={showRawIcon && project.raw_icon_url ? project.raw_icon_url : project.icon_url || '/icon.png'}
                      alt={project.title}
                      className="size-full rounded-lg object-contain"
                      onError={(e) => {
                        ;(e.target as HTMLImageElement).src = '/icon.png'
                      }}
                    />
                    {project.raw_icon_url && project.raw_icon_url !== project.icon_url && (
                      <button
                        type="button"
                        onClick={() => setShowRawIcon(!showRawIcon)}
                        title={showRawIcon ? 'Đang xem icon gốc (Raw)' : 'Xem icon gốc (Raw)'}
                        className="absolute right-1 bottom-1 rounded bg-black/70 p-0.5 text-[9px] text-neon opacity-0 transition-opacity group-hover:opacity-100"
                      >
                        <Eye className="size-3" />
                      </button>
                    )}
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <DialogTitle className="truncate text-lg font-bold text-ink">
                        {project.title}
                      </DialogTitle>
                      <Badge
                        variant={project.source === 'modrinth' ? 'accent' : 'warn'}
                        className="font-mono text-[10px] uppercase"
                      >
                        {project.source}
                      </Badge>
                    </div>

                    <p className="mt-1 line-clamp-2 text-xs text-muted">
                      {project.description}
                    </p>

                    <div className="mt-2.5 flex flex-wrap items-center gap-4 text-xs text-muted">
                      <span className="flex items-center gap-1">
                        <Package className="size-3.5 text-accent" />
                        Tác giả: <strong className="text-ink">{project.author}</strong>
                      </span>
                      <span className="flex items-center gap-1">
                        <Download className="size-3.5 text-neon" />
                        {project.downloads.toLocaleString()} lượt tải
                      </span>
                      {project.followers > 0 && (
                        <span className="flex items-center gap-1">
                          <Heart className="size-3.5 text-rose-400" />
                          {project.followers.toLocaleString()}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* External Link */}
                  {project.web_url && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 gap-1 text-xs text-muted hover:text-ink"
                      onClick={() => void openExternalUrl(project.web_url)}
                    >
                      <span>Web</span>
                      <ExternalLink className="size-3.5" />
                    </Button>
                  )}
                </div>
              </DialogHeader>

              {/* Scrollable Body */}
              <ScrollArea className="flex-1 p-6">
                <div className="space-y-6">
                  {/* Screenshots & Gallery Section */}
                  {images.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <h4 className="flex items-center gap-2 text-xs font-semibold tracking-wider text-muted uppercase">
                          <ImageIcon className="size-3.5 text-neon" />
                          Hình ảnh & Screenshots ({images.length})
                        </h4>
                        <span className="text-[11px] text-muted">
                          Click để phóng to ảnh
                        </span>
                      </div>

                      {/* Main Featured Carousel Preview */}
                      <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-white/10 bg-black/40">
                        <img
                          src={images[activeImageIndex]?.url || images[activeImageIndex]?.raw_url}
                          alt={images[activeImageIndex]?.title || 'Screenshot'}
                          className="size-full cursor-pointer object-contain transition-transform hover:scale-[1.01]"
                          onClick={() => setLightboxImage(images[activeImageIndex])}
                        />

                        {images.length > 1 && (
                          <>
                            <button
                              type="button"
                              onClick={() =>
                                setActiveImageIndex((prev) => (prev > 0 ? prev - 1 : images.length - 1))
                              }
                              className="absolute top-1/2 left-2 -translate-y-1/2 rounded-full border border-white/20 bg-black/60 p-1.5 text-white backdrop-blur hover:bg-black/80"
                            >
                              <ChevronLeft className="size-4" />
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                setActiveImageIndex((prev) => (prev < images.length - 1 ? prev + 1 : 0))
                              }
                              className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full border border-white/20 bg-black/60 p-1.5 text-white backdrop-blur hover:bg-black/80"
                            >
                              <ChevronRight className="size-4" />
                            </button>
                          </>
                        )}

                        {images[activeImageIndex]?.title && (
                          <div className="absolute right-0 bottom-0 left-0 bg-gradient-to-t from-black/80 to-transparent p-3 text-xs text-white">
                            {images[activeImageIndex]?.title}
                          </div>
                        )}
                      </div>

                      {/* Thumbnails Row */}
                      {images.length > 1 && (
                        <div className="flex gap-2 overflow-x-auto pb-1">
                          {images.map((img, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => setActiveImageIndex(idx)}
                              className={cn(
                                'relative h-14 w-24 shrink-0 overflow-hidden rounded-lg border transition-all',
                                activeImageIndex === idx
                                  ? 'border-accent ring-2 ring-accent/30'
                                  : 'border-white/10 opacity-60 hover:opacity-100'
                              )}
                            >
                              <img
                                src={img.url}
                                alt={img.title || `Thumbnail ${idx}`}
                                className="size-full object-cover"
                              />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Categories & Loaders Badges */}
                  <div className="flex flex-wrap gap-1.5">
                    {project.loaders.map((ldr) => (
                      <Badge key={ldr} variant="accent" className="text-[10px]">
                        {ldr}
                      </Badge>
                    ))}
                    {project.categories.map((cat) => (
                      <Badge key={cat} variant="muted" className="text-[10px]">
                        {cat}
                      </Badge>
                    ))}
                  </div>

                  {/* Installation Target Section */}
                  <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                    <h4 className="flex items-center gap-2 text-xs font-semibold text-ink">
                      <Sparkles className="size-3.5 text-accent" />
                      Cài đặt vào Instance Minecraft
                    </h4>

                    {instances.length === 0 ? (
                      <p className="mt-2 text-xs text-amber-300">
                        Chưa có instance nào. Vui lòng tạo instance ở màn hình chính trước khi cài đặt mod.
                      </p>
                    ) : (
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <div>
                          <label className="mb-1 block text-[11px] font-medium text-muted">
                            Chọn Instance đích:
                          </label>
                          <Select
                            value={selectedInstanceName}
                            onValueChange={setSelectedInstanceName}
                          >
                            <SelectTrigger className="h-9 text-xs">
                              <SelectValue placeholder="Chọn instance" />
                            </SelectTrigger>
                            <SelectContent>
                              {instances.map((inst) => (
                                <SelectItem key={inst.name} value={inst.name} className="text-xs">
                                  {inst.name} ({inst.loader} {inst.version_id})
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>

                        <div>
                          <label className="mb-1 block text-[11px] font-medium text-muted">
                            Phiên bản Mod tương thích:
                          </label>
                          {versionsLoading ? (
                            <div className="flex h-9 items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 text-xs text-muted">
                              <Loader2 className="size-3.5 animate-spin text-accent" />
                              Đang tải phiên bản…
                            </div>
                          ) : versions.length === 0 ? (
                            <div className="flex h-9 items-center rounded-lg border border-white/10 bg-white/5 px-3 text-xs text-muted">
                              Không tìm thấy file tương thích
                            </div>
                          ) : (
                            <Select
                              value={selectedVersionId}
                              onValueChange={setSelectedVersionId}
                            >
                              <SelectTrigger className="h-9 text-xs">
                                <SelectValue placeholder="Chọn phiên bản mod" />
                              </SelectTrigger>
                              <SelectContent>
                                {versions.map((ver) => {
                                  const f = ver.files[0]
                                  const sizeMb = f ? (f.size / (1024 * 1024)).toFixed(1) : '0'
                                  return (
                                    <SelectItem key={ver.id} value={ver.id} className="text-xs">
                                      {ver.name || ver.version_number} ({ver.loaders.join(', ')}) · {sizeMb}MB
                                    </SelectItem>
                                  )
                                })}
                              </SelectContent>
                            </Select>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Instance Busy Warning */}
                    {isInstanceBusy && (
                      <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5 text-xs text-amber-300">
                        <AlertTriangle className="size-4 shrink-0" />
                        <span>
                          Instance <strong>{selectedInstanceName}</strong> đang chạy game. Vui lòng tắt Minecraft trước khi cài đặt mod!
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Mod Description / Body */}
                  {project.body && (
                    <div className="space-y-2 border-t border-white/10 pt-4">
                      <h4 className="text-xs font-semibold text-muted uppercase">
                        Giới thiệu chi tiết
                      </h4>
                      <div className="rounded-xl border border-white/5 bg-slate-900/60 p-4 text-xs text-ink/80 leading-relaxed whitespace-pre-wrap font-sans">
                        {project.body.slice(0, 3000)}
                        {project.body.length > 3000 && '…'}
                      </div>
                    </div>
                  )}
                </div>
              </ScrollArea>

              {/* Footer */}
              <div className="flex items-center justify-between border-t border-white/10 bg-slate-950 p-4 px-6">
                <div className="text-xs text-muted">
                  {targetFile ? (
                    <span>
                      File: <strong className="text-ink">{targetFile.filename}</strong> ({(targetFile.size / (1024 * 1024)).toFixed(2)} MB)
                    </span>
                  ) : (
                    <span>Chưa chọn file tải</span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <Button variant="ghost" size="sm" onClick={close}>
                    Đóng
                  </Button>
                  <Button
                    variant="play"
                    size="sm"
                    disabled={
                      !targetFile ||
                      !selectedInstanceName ||
                      isInstanceBusy ||
                      installing
                    }
                    onClick={() => void handleInstall()}
                    className="gap-1.5"
                  >
                    {installing ? (
                      <>
                        <Loader2 className="size-3.5 animate-spin" />
                        <span>Đang bắt đầu…</span>
                      </>
                    ) : (
                      <>
                        <ArrowDownToLine className="size-3.5" />
                        <span>Cài đặt Mod</span>
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Fullscreen Lightbox for Screenshots — portal to body, outside Dialog tree */}
      {open && lightboxImage &&
        createPortal(
          <div
            className="fixed inset-0 z-[150] flex flex-col items-center justify-center bg-black/95 p-4 backdrop-blur-md"
            onClick={() => setLightboxImage(null)}
          >
            <div
              className="absolute top-4 right-4 left-4 z-20 flex items-center justify-between"
              onClick={(e) => e.stopPropagation()}
            >
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 border-white/20 bg-black/60 text-xs text-white backdrop-blur hover:bg-white/10"
                onClick={() => setLightboxImage(null)}
              >
                <ChevronLeft className="size-4" />
                <span>Quay lại</span>
              </Button>
              <button
                type="button"
                className="rounded-full border border-white/20 bg-black/60 p-2 text-white backdrop-blur transition-colors hover:bg-white/20"
                onClick={() => setLightboxImage(null)}
                title="Đóng xem ảnh (Esc)"
              >
                <X className="size-5" />
              </button>
            </div>

            <img
              src={lightboxImage.raw_url || lightboxImage.url}
              alt={lightboxImage.title || 'Fullscreen Preview'}
              className="max-h-[85vh] max-w-[90vw] rounded-xl object-contain shadow-2xl transition-transform"
              onClick={(e) => e.stopPropagation()}
            />

            {lightboxImage.title && (
              <div
                className="mt-3 max-w-lg rounded-lg bg-black/70 px-4 py-1.5 text-center text-xs text-white/90 backdrop-blur"
                onClick={(e) => e.stopPropagation()}
              >
                {lightboxImage.title}
              </div>
            )}
          </div>,
          document.body
        )}
    </>
  )
}

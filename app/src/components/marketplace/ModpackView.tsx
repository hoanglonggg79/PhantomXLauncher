import { useState, useRef, type DragEvent, type ChangeEvent } from 'react'
import {
  Archive,
  Download,
  FolderDown,
  Loader2,
  Sparkles,
  UploadCloud,
  X,
} from 'lucide-react'


import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app-store'

export function ModpackView() {
  const uploadModpack = useAppStore((s) => s.uploadModpack)
  const installModpack = useAppStore((s) => s.installModpack)
  const modpackUploadedFile = useAppStore((s) => s.modpackUploadedFile)
  const setModpackUploadedFile = useAppStore((s) => s.setModpackUploadedFile)
  const modpackUploading = useAppStore((s) => s.modpackUploading)
  const instances = useAppStore((s) => s.instances)

  const [isDragging, setIsDragging] = useState(false)
  const [instanceName, setInstanceName] = useState('')
  const [installing, setInstalling] = useState(false)
  const [nameError, setNameError] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = async (file: File) => {
    const ext = file.name.toLowerCase()
    if (!ext.endsWith('.zip') && !ext.endsWith('.mrpack')) {
      return
    }
    const success = await uploadModpack(file)
    if (success) {
      // Pre-populate instance name from detected manifest name or fallback to filename
      const uploaded = useAppStore.getState().modpackUploadedFile
      const rawName = uploaded?.detected_name || file.name.replace(/\.(zip|mrpack)$/i, '')
      const sanitized = rawName.replace(/[^a-zA-Z0-9 ._-]/g, '').trim()
      setInstanceName(sanitized || 'MyModpack')
      setNameError(null)
    }
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0]
      await handleFileSelect(file)
    }
  }

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      void handleFileSelect(e.target.files[0])
    }
  }

  const handleInstall = async () => {
    if (!modpackUploadedFile) return
    const clean = instanceName.trim()

    if (!clean) {
      setNameError('Vui lòng nhập tên cho Instance!')
      return
    }

    // Name regex matching backend NAME_PATTERN (^[a-zA-Z0-9 ._-]{1,64}$)
    if (!/^[a-zA-Z0-9 ._-]{1,64}$/.test(clean) || clean === '.' || clean === '..') {
      setNameError('Tên instance chỉ được dùng chữ, số, dấu cách, chấm, gạch ngang, gạch dưới (1-64 ký tự).')
      return
    }

    if (instances.some((i) => i.name.toLowerCase() === clean.toLowerCase())) {
      setNameError(`Instance '${clean}' đã tồn tại. Vui lòng chọn tên khác!`)
      return
    }

    setNameError(null)
    setInstalling(true)

    try {
      await installModpack({
        name: clean,
        source: modpackUploadedFile.format === 'modrinth' ? 'modrinth' : 'curseforge',
        local_path: modpackUploadedFile.temp_path,
      })
    } finally {
      setInstalling(false)
    }
  }

  const handleReset = () => {
    setModpackUploadedFile(null)
    setInstanceName('')
    setNameError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* Header Info */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <FolderDown className="size-6 text-accent" />
          <h2 className="text-xl font-bold tracking-tight text-ink">Cài đặt Modpack Tự Động</h2>
        </div>

        <p className="text-xs text-muted leading-relaxed">
          Nhập tệp modpack để Launcher tự động khởi tạo instance, tải dữ liệu Minecraft, thiết lập Mod Loader (Fabric / Forge / NeoForge / Quilt), tải song song toàn bộ mod và tự động cấu hình cho bạn.
        </p>
      </div>

      {/* Main Container */}
      {!modpackUploadedFile ? (
        /* Dropzone Card */
        <Card
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            'relative overflow-hidden border-2 border-dashed transition-all duration-200 cursor-pointer p-8 text-center',
            isDragging
              ? 'border-accent bg-accent/5 shadow-lg shadow-accent/10 scale-[1.005]'
              : 'border-border/60 hover:border-accent/50 hover:bg-surface/50'
          )}
          onClick={() => !modpackUploading && fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".zip,.mrpack"
            className="hidden"
            onChange={handleInputChange}
          />

          <div className="flex flex-col items-center justify-center gap-4 py-8">
            <div
              className={cn(
                'grid size-16 place-items-center rounded-2xl border transition-transform duration-300',
                isDragging
                  ? 'border-accent bg-accent/20 scale-110'
                  : 'border-white/10 bg-surface/80 text-muted'
              )}
            >
              {modpackUploading ? (
                <Loader2 className="size-8 animate-spin text-accent" />
              ) : (
                <UploadCloud className="size-8 text-accent" />
              )}
            </div>

            <div className="space-y-1.5">
              <h3 className="text-base font-semibold text-ink">
                {modpackUploading
                  ? 'Đang phân tích gói modpack…'
                  : 'Bấm để chọn file Modpack'}
              </h3>
              <p className="text-xs text-muted max-w-md mx-auto">
                Hỗ trợ định dạng <span className="font-semibold text-accent">CurseForge (.zip)</span> chứa{' '}
                <code className="text-[11px] font-mono bg-surface-muted px-1.5 py-0.5 rounded">manifest.json</code>{' '}
                hoặc <span className="font-semibold text-accent">Modrinth (.mrpack)</span>.
              </p>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={modpackUploading}
              className="mt-2 text-xs"
              onClick={(e) => {
                e.stopPropagation()
                fileInputRef.current?.click()
              }}
            >
              {modpackUploading ? (
                <>
                  <Loader2 className="mr-1.5 size-3.5 animate-spin" /> Đang tải…
                </>
              ) : (
                <>
                  <Archive className="mr-1.5 size-3.5" /> Chọn tệp từ máy tính
                </>
              )}
            </Button>
          </div>
        </Card>
      ) : (
        /* Preview & Configuration Card */
        <Card className="border-border/80 bg-surface/80 shadow-md">
          <CardHeader className="pb-4">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Badge
                    variant={modpackUploadedFile.format === 'modrinth' ? 'neon' : 'warn'}
                    className="text-[10px] font-bold uppercase tracking-wider"
                  >
                    {modpackUploadedFile.format === 'modrinth' ? 'Modrinth .mrpack' : 'CurseForge .zip'}
                  </Badge>

                  <span className="text-xs text-muted font-mono truncate max-w-[280px]">
                    {modpackUploadedFile.filename}
                  </span>
                </div>
                <CardTitle className="text-lg text-ink font-bold">
                  {modpackUploadedFile.detected_name || 'Gói Modpack Minecraft'}
                </CardTitle>
                <CardDescription className="text-xs text-muted">
                  Đã đọc cấu hình thành công từ tệp lưu trữ.
                </CardDescription>
              </div>

              <Button
                variant="ghost"
                size="icon"
                onClick={handleReset}
                className="size-8 text-muted hover:text-ink"
                title="Hủy và chọn file khác"
              >
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-5">
            {/* Metadata Badges Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-3.5 rounded-lg border border-border/50 bg-surface-muted/40">
              <div className="space-y-0.5">
                <span className="text-[10px] uppercase font-semibold text-muted tracking-wider">
                  Minecraft Version
                </span>
                <p className="text-sm font-bold text-accent">
                  {modpackUploadedFile.mc_version || 'Tự động'}
                </p>
              </div>

              <div className="space-y-0.5">
                <span className="text-[10px] uppercase font-semibold text-muted tracking-wider">
                  Mod Loader
                </span>
                <p className="text-sm font-bold text-ink capitalize">
                  {modpackUploadedFile.loader || 'Vanilla'}
                  {modpackUploadedFile.loader_version && (
                    <span className="text-[11px] font-normal text-muted ml-1 font-mono">
                      v{modpackUploadedFile.loader_version}
                    </span>
                  )}
                </p>
              </div>

              <div className="space-y-0.5 col-span-2 sm:col-span-1">
                <span className="text-[10px] uppercase font-semibold text-muted tracking-wider">
                  Số lượng Mods
                </span>
                <p className="text-sm font-bold text-ink">
                  {modpackUploadedFile.mod_count ?? 0} <span className="text-xs font-normal text-muted">tệp mod</span>
                </p>
              </div>
            </div>

            {/* Instance Name Input */}
            <div className="space-y-2">
              <label htmlFor="modpack-instance-name" className="text-xs font-medium text-ink flex items-center justify-between">
                <span>Tên Instance mới trong Launcher:</span>
                <span className="text-[11px] text-muted">Có thể chỉnh sửa</span>
              </label>
              <Input
                id="modpack-instance-name"
                value={instanceName}
                onChange={(e) => {
                  setInstanceName(e.target.value)
                  if (nameError) setNameError(null)
                }}
                placeholder="Nhập tên instance..."
                className="font-medium text-xs h-9"
              />
              {nameError && (
                <p className="text-[11px] text-rose-400 font-medium animate-shake">
                  {nameError}
                </p>
              )}
            </div>

            {/* Workflow steps reminder */}
            <div className="rounded-lg border border-border/40 bg-surface/40 p-3 space-y-1.5 text-[11px] text-muted">
              <p className="font-semibold text-ink flex items-center gap-1.5">
                <Sparkles className="size-3.5 text-accent" /> Quy trình tự động khi bạn bấm Cài đặt:
              </p>
              <ol className="list-decimal list-inside space-y-1 pl-1 text-[11px]">
                <li>Khởi tạo môi trường staging độc lập, chống xung đột tệp.</li>
                <li>Tải phiên bản Minecraft gốc {modpackUploadedFile.mc_version || ''} và nạp Mod Loader.</li>
                <li>Tải đồng thời tối đa 4 tệp mod cùng lúc với cơ chế thử lại tự động.</li>
                <li>Sao chép toàn bộ cấu hình (overrides, keybinds, shaderpacks) vào game.</li>
              </ol>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-2.5 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleReset}
                disabled={installing}
                className="text-xs"
              >
                Hủy
              </Button>

              <Button
                variant="play"
                size="sm"
                onClick={handleInstall}
                disabled={installing || !instanceName.trim()}
                className="text-xs font-semibold px-4"
              >
                {installing ? (
                  <>
                    <Loader2 className="mr-1.5 size-3.5 animate-spin" /> Đang khởi tạo…
                  </>
                ) : (
                  <>
                    <Download className="mr-1.5 size-3.5" /> Bắt đầu cài đặt Modpack
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

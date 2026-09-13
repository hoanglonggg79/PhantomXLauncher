import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AlertTriangle,
  CheckCircle2,
  FolderOpen,
  Loader2,
  Package,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { Mod } from '@/lib/types'
import { useAppStore } from '@/store/app-store'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / k ** i).toFixed(1)} ${units[i]}`
}

type FilterTab = 'all' | 'enabled' | 'disabled'

interface ModRowProps {
  mod: Mod
  instanceName: string
  pending: boolean
  onToggle: () => void
  onDelete: () => void
}

function ModRow({ mod, instanceName: _instanceName, pending, onToggle, onDelete }: ModRowProps) {
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <motion.div
      layout
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.15 }}
      className={cn(
        'group flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors',
        mod.enabled
          ? 'border-accent/15 bg-slate-900/60 hover:border-accent/30'
          : 'border-white/5 bg-slate-950/40 opacity-60 hover:opacity-80'
      )}
    >
      {/* Toggle Switch */}
      <button
        type="button"
        role="switch"
        aria-checked={mod.enabled}
        aria-label={mod.enabled ? 'Disable mod' : 'Enable mod'}
        disabled={pending}
        onClick={onToggle}
        className={cn(
          'relative h-5 w-9 shrink-0 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent',
          mod.enabled ? 'bg-accent' : 'bg-slate-700',
          pending && 'opacity-50 cursor-not-allowed'
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 size-4 rounded-full bg-white shadow-sm transition-transform',
            mod.enabled ? 'translate-x-4' : 'translate-x-0'
          )}
        />
      </button>

      {/* Mod Info */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-ink" title={mod.display_name}>
          {mod.display_name}
        </p>
        <p className="text-[11px] text-muted mt-0.5 truncate" title={mod.filename}>
          {mod.filename} · {formatBytes(mod.size)}
        </p>
      </div>

      {/* Status Badge */}
      <Badge
        variant={mod.enabled ? 'accent' : 'muted'}
        className="shrink-0 text-[10px] px-1.5 py-0.5"
      >
        {mod.enabled ? 'Enabled' : 'Disabled'}
      </Badge>

      {/* Delete */}
      <div className="shrink-0 flex items-center gap-1">
        {confirmDelete ? (
          <>
            <span className="text-[11px] text-amber-400 mr-1">Delete?</span>
            <Button
              variant="danger"
              size="icon-sm"
              className="size-6"
              disabled={pending}
              onClick={onDelete}
              aria-label="Confirm delete"
            >
              <CheckCircle2 className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              className="size-6 text-muted hover:text-ink"
              onClick={() => setConfirmDelete(false)}
              aria-label="Cancel delete"
            >
              <X className="size-3.5" />
            </Button>
          </>
        ) : (
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-6 opacity-0 group-hover:opacity-100 text-muted hover:text-red-400 transition-opacity"
            disabled={pending}
            onClick={() => setConfirmDelete(true)}
            aria-label="Delete mod"
          >
            <Trash2 className="size-3.5" />
          </Button>
        )}
      </div>
    </motion.div>
  )
}

export function ModManagerDialog() {
  const {
    modManagerOpen,
    modManagerInstance,
    mods,
    modsLoading,
    closeModManager,
    loadMods,
    toggleMod,
    deleteMod,
    uploadMod,
    openModsFolder,
    notify,
  } = useAppStore(
    useShallow((s) => ({
      modManagerOpen: s.modManagerOpen,
      modManagerInstance: s.modManagerInstance,
      mods: s.mods,
      modsLoading: s.modsLoading,
      closeModManager: s.closeModManager,
      loadMods: s.loadMods,
      toggleMod: s.toggleMod,
      deleteMod: s.deleteMod,
      uploadMod: s.uploadMod,
      openModsFolder: s.openModsFolder,
      notify: s.notify,
    }))
  )

  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<FilterTab>('all')
  const [pendingFiles, setPendingFiles] = useState<Set<string>>(new Set())
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const instanceName = modManagerInstance ?? ''

  useEffect(() => {
    if (modManagerOpen && instanceName) {
      void loadMods(instanceName)
    }
    if (!modManagerOpen) {
      setSearch('')
      setFilter('all')
      setPendingFiles(new Set())
    }
  }, [modManagerOpen, instanceName, loadMods])

  const filtered = useMemo(() => {
    let list = mods
    if (filter === 'enabled') list = list.filter((m) => m.enabled)
    if (filter === 'disabled') list = list.filter((m) => !m.enabled)
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(
        (m) => m.filename.toLowerCase().includes(q) || m.display_name.toLowerCase().includes(q)
      )
    }
    return list
  }, [mods, filter, search])

  const setPending = useCallback((filename: string, on: boolean) => {
    setPendingFiles((prev) => {
      const next = new Set(prev)
      on ? next.add(filename) : next.delete(filename)
      return next
    })
  }, [])

  const handleToggle = useCallback(
    async (mod: Mod) => {
      setPending(mod.filename, true)
      try {
        await toggleMod(instanceName, mod.filename, !mod.enabled)
      } finally {
        setPending(mod.filename, false)
      }
    },
    [instanceName, toggleMod, setPending]
  )

  const handleDelete = useCallback(
    async (mod: Mod) => {
      setPending(mod.filename, true)
      try {
        await deleteMod(instanceName, mod.filename)
      } finally {
        setPending(mod.filename, false)
      }
    },
    [instanceName, deleteMod, setPending]
  )

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      const valid = Array.from(files).filter((f) => f.name.toLowerCase().endsWith('.jar'))
      if (valid.length === 0) {
        notify({ tone: 'error', message: 'Chỉ chấp nhận file .jar' })
        return
      }
      setUploading(true)
      let failed = 0
      for (const file of valid) {
        const ok = await uploadMod(instanceName, file)
        if (!ok) failed++
      }
      setUploading(false)
      if (failed === 0 && valid.length > 0) {
        notify({
          tone: 'success',
          message: `${valid.length} mod${valid.length > 1 ? 's' : ''} đã được thêm vào`,
        })
      }
    },
    [instanceName, uploadMod, notify]
  )

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(true)
  }
  const onDragLeave = () => setDragging(false)
  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    await handleFiles(e.dataTransfer.files)
  }

  const enabledCount = mods.filter((m) => m.enabled).length
  const disabledCount = mods.filter((m) => !m.enabled).length

  const TABS: { id: FilterTab; label: string; count: number }[] = [
    { id: 'all', label: 'Tất Cả', count: mods.length },
    { id: 'enabled', label: 'Đã Bật', count: enabledCount },
    { id: 'disabled', label: 'Đã Tắt', count: disabledCount },
  ]

  return (
    <Dialog open={modManagerOpen} onOpenChange={(o) => !o && closeModManager()}>
      <DialogContent
        className="max-w-2xl h-[80vh] flex flex-col gap-0 p-0 overflow-hidden"
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        {/* Header */}
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-white/5 flex-none">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Package className="size-4 text-accent shrink-0" />
            Quản Lý Mods
            {instanceName && (
              <span className="text-muted font-normal">— {instanceName}</span>
            )}
            {mods.length > 0 && (
              <Badge variant="neon" className="ml-auto text-[11px]">
                {mods.length} mod{mods.length !== 1 ? 's' : ''}
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription className="text-xs mt-0.5">
            Bật, tắt, thêm, hoặc xóa mods. Kéo và thả file .jar để cài đặt.
          </DialogDescription>
        </DialogHeader>

        {/* Toolbar */}
        <div className="px-5 py-3 flex items-center gap-2 flex-none border-b border-white/5">
          {/* Search */}
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted pointer-events-none" />
            <Input
              id="mod-search"
              placeholder="Tìm Mods…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-8 text-sm"
            />
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center gap-0.5 rounded-lg border border-white/8 bg-slate-950/60 p-0.5">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setFilter(tab.id)}
                className={cn(
                  'px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                  filter === tab.id
                    ? 'bg-accent/20 text-accent'
                    : 'text-muted hover:text-ink'
                )}
              >
                {tab.label}
                {tab.count > 0 && (
                  <span
                    className={cn(
                      'ml-1.5 rounded-full px-1.5 py-0.5 text-[10px]',
                      filter === tab.id ? 'bg-accent/20 text-accent' : 'bg-white/5 text-muted'
                    )}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5 ml-auto">
            {/* Open Folder */}
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 h-8 text-xs"
              onClick={() => void openModsFolder(instanceName)}
            >
              <FolderOpen className="size-3.5" />
              Mở Thư Mục Mods
            </Button>

            {/* Add Mod */}
            <Button
              variant="play"
              size="sm"
              className="gap-1.5 h-8 text-xs"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploading ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Plus className="size-3.5" />
              )}
              {uploading ? 'Đang tải lên' : 'Thêm Mod'}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".jar"
              multiple
              className="hidden"
              onChange={(e) => void handleFiles(e.target.files)}
              aria-label="Select .jar mod files to upload"
            />
          </div>
        </div>

        {/* Mod List */}
        <div className="flex-1 overflow-y-auto px-5 py-3 min-h-0">
          {/* Drag & Drop Overlay */}
          <AnimatePresence>
            {dragging && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-accent/60 bg-slate-900/90 backdrop-blur-sm m-2"
              >
                <Upload className="size-10 text-accent/70" />
                <p className="text-sm font-semibold text-ink">Thả file .jar vào đây để cài</p>
                <p className="text-xs text-muted">Thả để thêm mod vào instance này</p>
              </motion.div>
            )}
          </AnimatePresence>

          {modsLoading ? (
            <div className="flex flex-col items-center justify-center h-40 gap-3">
              <Loader2 className="size-6 animate-spin text-accent/60" />
              <p className="text-sm text-muted">Đang tải mod…</p>
            </div>
          ) : mods.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 gap-3 text-center">
              <Package className="size-8 text-muted/40" />
              <p className="text-sm font-medium text-muted">Chưa có mod nào</p>
              <p className="text-xs text-muted/70 max-w-xs">
                Click <span className="text-ink font-medium">Thêm Mod</span> hoặc kéo thả file .jar
                vào đây để bắt đầu.
              </p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 gap-2">
              <AlertTriangle className="size-6 text-muted/40" />
              <p className="text-sm text-muted">Không tìm thấy mod nào phù hợp với bộ lọc</p>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5">
              <AnimatePresence initial={false}>
                {filtered.map((mod) => (
                  <ModRow
                    key={mod.filename}
                    mod={mod}
                    instanceName={instanceName}
                    pending={pendingFiles.has(mod.filename)}
                    onToggle={() => void handleToggle(mod)}
                    onDelete={() => void handleDelete(mod)}
                  />
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-white/5 flex-none flex items-center justify-between">
          <p className="text-xs text-muted">
            {enabledCount} enabled · {disabledCount} disabled
          </p>
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={closeModManager}
          >
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

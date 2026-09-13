import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  Clock,
  Copy,
  Edit3,
  FolderOpen,
  Hammer,
  MoreVertical,
  Package,
  Play,
  Square,
  StickyNote,
  Trash2,
  AlertCircle,
} from 'lucide-react'

import { CloneInstanceDialog } from '@/components/instances/CloneInstanceDialog'
import { DeleteInstanceDialog } from '@/components/instances/DeleteInstanceDialog'
import { EditInstanceDialog } from '@/components/instances/EditInstanceDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn, formatDate, formatLoader } from '@/lib/utils'
import type { Instance } from '@/lib/types'
import { useAppStore } from '@/store/app-store'

const LOADER_TONE: Record<string, 'neon' | 'muted'> = {
  vanilla: 'muted',
}

export function InstanceCard({ instance, index }: { instance: Instance; index: number }) {
  const launchInstance = useAppStore((s) => s.launchInstance)
  const stopInstance = useAppStore((s) => s.stopInstance)
  const openRepairDialog = useAppStore((s) => s.openRepairDialog)
  const openFolder = useAppStore((s) => s.openInstanceFolder)
  const openModManager = useAppStore((s) => s.openModManager)
  const busy = useAppStore((s) =>
    Object.values(s.tasks).some((t) => t.running && t.instanceName === instance.name)
  )

  const [cloneOpen, setCloneOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)

  return (
    <>
      <motion.div
        initial={{ opacity: 0, transform: 'translateY(10px)' }}
        animate={{ opacity: 1, transform: 'translateY(0px)' }}
        transition={{ duration: 0.22, delay: Math.min(index * 0.035, 0.3), ease: 'easeOut' }}
        className={cn(
          'group flex flex-col gap-3 rounded-xl border border-white/5 bg-slate-900/80 p-4 transition-colors hover:border-white/15',
          instance.running && 'border-accent/30'
        )}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-sm font-semibold text-ink" title={instance.name}>
                {instance.name}
              </h3>
              {instance.running && (
                <span className="size-1.5 shrink-0 rounded-full bg-accent shadow-[0_0_8px_rgba(16,185,129,0.9)]" />
              )}
            </div>
            <div className="mt-0.5 flex items-center gap-1 text-[11px] text-muted">
              <Clock className="size-3" />
              {formatDate(instance.last_played)}
              {instance.play_count > 0 && <span>· {instance.play_count} launches</span>}
            </div>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                className="size-7 text-muted hover:text-ink hover:bg-white/10"
                aria-label="Instance actions"
              >
                <MoreVertical className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={() => void openFolder(instance.name)}
                disabled={busy}
              >
                <FolderOpen className="size-3.5 text-muted" />
                Mở Thư Mục
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => openModManager(instance.name)}
                disabled={busy || instance.running}
              >
                <Package className="size-3.5 text-muted" />
                Quản Lý Mods
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => setEditOpen(true)}
                disabled={busy}
              >
                <Edit3 className="size-3.5 text-muted" />
                Chỉnh Sửa / Ghi Chú
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => setCloneOpen(true)}
                disabled={busy || instance.running}
              >
                <Copy className="size-3.5 text-muted" />
                Nhân Bản Instance
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => openRepairDialog(instance.name, 'verify')}
                disabled={busy || instance.running}
              >
                <Hammer className="size-3.5 text-muted" />
                Sửa Chữa & Chẩn Đoán
              </DropdownMenuItem>

              <DropdownMenuItem
                onClick={() => openRepairDialog(instance.name, 'crash')}
                disabled={busy}
              >
                <AlertCircle className="size-3.5 text-amber-400" />
                Phân Tích Crash Log
              </DropdownMenuItem>

              <DropdownMenuSeparator />

              <DropdownMenuItem
                variant="danger"
                onClick={() => setDeleteOpen(true)}
                disabled={busy || instance.running}
              >
                <Trash2 className="size-3.5" />
                Xoá Instance
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {instance.notes && (
          <div className="flex items-start gap-1.5 rounded-lg border border-white/5 bg-slate-950/40 px-2.5 py-1.5 text-[11px] text-muted">
            <StickyNote className="size-3 shrink-0 text-neon/70 mt-0.5" />
            <p className="line-clamp-2 leading-relaxed text-ink/80">{instance.notes}</p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="neon">{instance.version_id}</Badge>
          <Badge variant={LOADER_TONE[instance.loader] ?? 'accent'}>
            {formatLoader(instance.loader)}
            {instance.loader_version ? ` ${instance.loader_version}` : ''}
          </Badge>
          {instance.mod_count > 0 && (
            <Badge variant="muted">
              <Package className="size-3" />
              {instance.mod_count} mods
            </Badge>
          )}
          {!instance.installed && <Badge variant="warn">Chưa được Cài Đặt</Badge>}
        </div>

        <div className="mt-auto flex items-center gap-2 pt-1">
          {instance.running ? (
            <Button
              variant="danger"
              size="sm"
              className="flex-1"
              onClick={() => void stopInstance(instance.name)}
            >
              <Square className="size-3.5" />
              Stop
            </Button>
          ) : (
            <Button
              variant="play"
              size="sm"
              className="flex-1"
              disabled={busy}
              onClick={() => void launchInstance(instance.name)}
            >
              <Play className="size-3.5" />
              {busy ? 'Working…' : 'Play'}
            </Button>
          )}

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon-sm"
                disabled={busy || instance.running}
                onClick={() => openRepairDialog(instance.name, 'verify')}
                aria-label="Sửa Chữa Instance"
              >
                <Hammer className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Sửa Chữa & Chẩn Đoán</TooltipContent>
          </Tooltip>
        </div>
      </motion.div>

      <CloneInstanceDialog
        instance={instance}
        open={cloneOpen}
        onOpenChange={setCloneOpen}
      />

      <DeleteInstanceDialog
        instance={instance}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />

      <EditInstanceDialog
        instance={instance}
        open={editOpen}
        onOpenChange={setEditOpen}
      />
    </>
  )
}

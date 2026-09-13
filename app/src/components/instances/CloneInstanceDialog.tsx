import { useMemo, useState } from 'react'
import { Copy, Loader2 } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import type { Instance } from '@/lib/types'
import { useAppStore } from '@/store/app-store'

const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/

interface CloneInstanceDialogProps {
  instance: Instance
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CloneInstanceDialog({
  instance,
  open,
  onOpenChange,
}: CloneInstanceDialogProps) {
  const cloneInstance = useAppStore((s) => s.cloneInstance)
  const existingNames = useAppStore(useShallow((s) => s.instances.map((i) => i.name)))

  const defaultName = useMemo(() => {
    let candidate = `${instance.name} - Copy`
    let counter = 2
    while (existingNames.includes(candidate)) {
      candidate = `${instance.name} - Copy ${counter++}`
    }
    return candidate
  }, [instance.name, existingNames])

  const [newName, setNewName] = useState('')
  const [copySaves, setCopySaves] = useState(true)
  const [copyConfigs, setCopyConfigs] = useState(true)
  const [copyMods, setCopyMods] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  // Initialize or reset input value when dialog opens
  const activeName = newName || defaultName

  const nameError = useMemo(() => {
    const clean = activeName.trim()
    if (!clean) return 'Vui lòng nhập tên cho instance mới'
    if (!NAME_RE.test(clean)) return 'Chỉ cho phép chữ cái, số, dấu cách, dấu chấm, dấu gạch ngang hoặc dấu gạch dưới'
    if (existingNames.includes(clean)) return 'Đã tồn tại instance với tên này'
    return ''
  }, [activeName, existingNames])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (nameError || submitting) return

    setSubmitting(true)
    try {
      const ok = await cloneInstance(instance.name, {
        new_name: activeName.trim(),
        copy_saves: copySaves,
        copy_configs: copyConfigs,
        copy_mods: copyMods,
      })
      if (ok) {
        onOpenChange(false)
        setNewName('')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Copy className="size-4 text-accent" />
              Nhân bản Instance
            </DialogTitle>
            <DialogDescription>
              Tạo một bản sao của <span className="text-ink font-medium">{instance.name}</span> trên ổ cứng để bạn có thể tự do thử nghiệm mà không sợ nghịch hỏng instance hiện tại. Hoặc để bắt đầu một hành trình mới.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3 py-1">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="clone-name" className="text-xs font-semibold text-ink">
                Tên Instance Mới
              </Label>
              <Input
                id="clone-name"
                value={newName || defaultName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Instance name…"
                maxLength={64}
                autoFocus
              />
              {nameError && (
                <span className="text-[11px] text-red-400">{nameError}</span>
              )}
            </div>

            <div className="flex flex-col gap-2.5 rounded-xl border border-white/5 bg-slate-950/60 p-3 mt-1">
              <span className="text-xs font-semibold text-ink/90">Tuỳ chọn khi nhân bản</span>

              <label className="flex items-start gap-2.5 cursor-pointer">
                <Checkbox
                  checked={copySaves}
                  onCheckedChange={(c) => setCopySaves(c === true)}
                  className="mt-0.5"
                />
                <div className="flex flex-col">
                  <span className="text-xs font-medium text-ink">Copy Thế giới (Saves)</span>
                  <span className="text-[11px] text-muted">Sao chép thế giới singleplayer (<code className="text-muted/90">saves/</code>)</span>
                </div>
              </label>

              <label className="flex items-start gap-2.5 cursor-pointer">
                <Checkbox
                  checked={copyConfigs}
                  onCheckedChange={(c) => setCopyConfigs(c === true)}
                  className="mt-0.5"
                />
                <div className="flex flex-col">
                  <span className="text-xs font-medium text-ink">Copy Cấu Hình & Shader</span>
                  <span className="text-[11px] text-muted">Sao chép keybinds, cài đặt đồ họa, và cấu hình mod (<code className="text-muted/90">config/, options.txt</code>)</span>
                </div>
              </label>

              <label className="flex items-start gap-2.5 cursor-pointer">
                <Checkbox
                  checked={copyMods}
                  onCheckedChange={(c) => setCopyMods(c === true)}
                  className="mt-0.5"
                />
                <div className="flex flex-col">
                  <span className="text-xs font-medium text-ink">Copy Mods Đã Cài</span>
                  <span className="text-[11px] text-muted">Copy các file mod hiện tại. Bỏ chọn để bắt đầu với folder mod trống (<code className="text-muted/90">mods/</code>)</span>
                </div>
              </label>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={submitting}
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="play"
              size="sm"
              disabled={!!nameError || submitting}
            >
              {submitting && <Loader2 className="size-3.5 animate-spin" />}
              {submitting ? 'Cloning…' : 'Start Cloning'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

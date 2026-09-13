import { useEffect, useMemo, useState } from 'react'
import { Edit3, Loader2 } from 'lucide-react'
import { useShallow } from 'zustand/react/shallow'

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
import type { Instance } from '@/lib/types'
import { useAppStore } from '@/store/app-store'

const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/

interface EditInstanceDialogProps {
  instance: Instance
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditInstanceDialog({
  instance,
  open,
  onOpenChange,
}: EditInstanceDialogProps) {
  const updateInstance = useAppStore((s) => s.updateInstance)
  const existingNames = useAppStore(
    useShallow((s) => s.instances.map((i) => i.name).filter((n) => n !== instance.name))
  )

  const [name, setName] = useState(instance.name)
  const [notes, setNotes] = useState(instance.notes || '')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      setName(instance.name)
      setNotes(instance.notes || '')
    }
  }, [open, instance])

  const nameError = useMemo(() => {
    const clean = name.trim()
    if (!clean) return 'Tên Instance không thể để trống'
    if (!NAME_RE.test(clean)) return 'Tên Instance không thể chứa ký tự đặc biệt'
    if (existingNames.includes(clean)) return 'Tên Instance đã tồn tại'
    return ''
  }, [name, existingNames])

  const hasChanges = name.trim() !== instance.name || (notes || '') !== (instance.notes || '')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (nameError || !hasChanges || submitting) return

    setSubmitting(true)
    try {
      const ok = await updateInstance(instance.name, {
        name: name.trim() !== instance.name ? name.trim() : undefined,
        notes: notes.trim(),
      })
      if (ok) {
        onOpenChange(false)
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
              <Edit3 className="size-4 text-neon" />
              Chỉnh sửa thông tin Instance
            </DialogTitle>
            <DialogDescription>
              Thay đổi tên và ghi chú cho <span className="text-ink font-medium">{instance.name}</span>.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-3 py-1">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-name" className="text-xs font-semibold text-ink">
                Tên Instance
              </Label>
              <Input
                id="edit-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Instance name…"
                maxLength={64}
              />
              {nameError && (
                <span className="text-[11px] text-red-400">{nameError}</span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-notes" className="text-xs font-semibold text-ink">
                Ghi chú & Mô tả Instance
              </Label>
              <textarea
                id="edit-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Thêm ghi chú về modpack này, keybinds, server hoặc mục tiêu…"
                rows={3}
                maxLength={2000}
                className="w-full rounded-xl border border-white/10 bg-slate-950/60 p-3 text-xs text-ink placeholder:text-muted/60 focus:border-neon focus:outline-none focus:ring-1 focus:ring-neon transition-colors resize-none"
              />
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
              disabled={!!nameError || !hasChanges || submitting}
            >
              {submitting && <Loader2 className="size-3.5 animate-spin" />}
              {submitting ? 'Saving…' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

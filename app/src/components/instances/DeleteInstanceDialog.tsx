import { useState } from 'react'
import { AlertTriangle, Loader2, Trash2 } from 'lucide-react'

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
import type { Instance } from '@/lib/types'
import { useAppStore } from '@/store/app-store'

interface DeleteInstanceDialogProps {
  instance: Instance
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DeleteInstanceDialog({
  instance,
  open,
  onOpenChange,
}: DeleteInstanceDialogProps) {
  const deleteInstance = useAppStore((s) => s.deleteInstance)
  const [deleteFiles, setDeleteFiles] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleDelete = async () => {
    if (submitting) return
    setSubmitting(true)
    try {
      const ok = await deleteInstance(instance.name, deleteFiles)
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
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-400">
            <Trash2 className="size-4 text-red-400" />
            Delete Instance
          </DialogTitle>
          <DialogDescription>
            Are you sure you want to delete <span className="text-ink font-medium">{instance.name}</span>?
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 py-1">
          <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-xs text-red-200/90 flex items-start gap-2.5">
            <AlertTriangle className="size-4 text-red-400 shrink-0 mt-0.5" />
            <div>
              {deleteFiles ? (
                <p>
                  <strong>Permanent Data Deletion:</strong> All files, save worlds, shaders, and configs inside this instance folder will be deleted permanently.
                </p>
              ) : (
                <p>
                  This instance will be removed from your launcher list. Your world saves and files will stay intact on disk.
                </p>
              )}
            </div>
          </div>

          <label className="flex items-start gap-2.5 cursor-pointer rounded-xl border border-white/5 bg-slate-950/60 p-3 mt-1">
            <Checkbox
              checked={deleteFiles}
              onCheckedChange={(c) => setDeleteFiles(c === true)}
              className="mt-0.5 border-red-400/40 data-[state=checked]:border-red-500 data-[state=checked]:bg-red-500"
            />
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-red-300">
                Permanently delete all files from disk
              </span>
              <span className="text-[11px] text-muted">
                Wipes the entire instance directory ({instance.game_dir || instance.name})
              </span>
            </div>
          </label>
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
            type="button"
            variant="danger"
            size="sm"
            disabled={submitting}
            onClick={() => void handleDelete()}
          >
            {submitting && <Loader2 className="size-3.5 animate-spin" />}
            {submitting ? 'Deleting…' : deleteFiles ? 'Delete Everything' : 'Remove from List'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

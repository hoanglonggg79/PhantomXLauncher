import { useEffect, useState } from 'react'
import {
  Bug,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  Lock,
  Send,
  ShieldCheck,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { api, describeError } from '@/lib/api'
import type { DiagnosticsContext } from '@/lib/types'
import { useAppStore } from '@/store/app-store'

export function ReportBugDialog() {
  const open = useAppStore((s) => s.bugReportOpen)
  const setOpen = useAppStore((s) => s.setBugReportOpen)
  const notify = useAppStore((s) => s.notify)

  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [steps, setSteps] = useState('')
  const [includeLogs, setIncludeLogs] = useState(true) // Default checked
  const [includeSpecs, setIncludeSpecs] = useState(false) // Default unchecked

  const [submitting, setSubmitting] = useState(false)
  const [diagnostics, setDiagnostics] = useState<DiagnosticsContext | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      void api
        .getDiagnostics()
        .then((ctx) => setDiagnostics(ctx))
        .catch(() => undefined)
    }
  }, [open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setValidationError(null)

    if (description.trim().length < 10) {
      setValidationError('Mô tả chi tiết phải có tối thiểu 10 ký tự.')
      return
    }

    setSubmitting(true)
    try {
      const res = await api.reportBug({
        title: title.trim(),
        description: description.trim(),
        steps: steps.trim(),
        include_specs: includeSpecs,
        include_log: includeLogs,
        website: '',
      })

      if (res.status === 'success') {
        notify({
          tone: 'success',
          message: 'Đã gửi báo cáo lỗi thành công! Cảm ơn bạn đã đóng góp cho PhantomX Launcher. Chúng tôi sẽ sớm xem xét và khắc phục.',
        })

        setTitle('')
        setDescription('')
        setSteps('')
        setIncludeLogs(true)
        setIncludeSpecs(false)
        setShowPreview(false)
        setOpen(false)
      } else {
        notify({
          tone: 'error',
          message: res.message || 'Không thể gửi báo cáo lỗi.',
        })
      }
    } catch (err) {
      notify({
        tone: 'error',
        message: describeError(err),
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-h-[90vh] w-[95vw] max-w-2xl overflow-hidden border-white/10 bg-slate-950/95 p-0 text-ink shadow-2xl backdrop-blur-2xl">
        <DialogHeader className="border-b border-white/10 p-6 pb-4">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-400">
              <Bug className="size-5" />
            </div>
            <div>
              <DialogTitle className="text-base font-bold text-ink">
                Báo cáo lỗi (Report Bug)
              </DialogTitle>
              <DialogDescription className="text-xs text-muted">
                Giúp đội ngũ phát triển khắc phục sự cố nhanh chóng. Chúng tôi tuân thủ tiêu chuẩn an toàn GDPR & Bảo mật thông tin cá nhân của bạn.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex max-h-[calc(90vh-140px)] min-w-0 flex-col overflow-hidden">
          <ScrollArea className="flex-1 min-w-0 p-6">
            <div className="space-y-4 min-w-0">
              {/* Error Summary */}
              <div>
                <Label htmlFor="bug-title" className="text-xs font-semibold text-ink">
                  Bạn gặp lỗi gì?
                </Label>
                <Input
                  id="bug-title"
                  placeholder="Ví dụ: Văng game khi bấm Chơi, Lỗi tải mod Modrinth..."
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="mt-1 h-9 text-xs"
                />
              </div>

              {/* Detailed Description */}
              <div>
                <Label htmlFor="bug-desc" className="text-xs font-semibold text-ink">
                  Mô tả chi tiết <span className="text-rose-400">*</span>
                </Label>
                <textarea
                  id="bug-desc"
                  rows={4}
                  placeholder="Mô tả cụ thể sự cố bạn đang gặp phải (tối thiểu 10 ký tự)..."
                  value={description}
                  onChange={(e) => {
                    setDescription(e.target.value)
                    if (e.target.value.trim().length >= 10) setValidationError(null)
                  }}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-slate-900/60 p-3 text-xs text-ink placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
                {validationError && (
                  <p className="mt-1 text-[11px] text-rose-400">{validationError}</p>
                )}
              </div>

              {/* Steps to reproduce */}
              <div>
                <Label htmlFor="bug-steps" className="text-xs font-semibold text-ink">
                  Làm sao để gặp lỗi? (Các bước tái hiện sự cố)
                </Label>
                <textarea
                  id="bug-steps"
                  rows={2}
                  placeholder="Ví dụ: 1. Tạo instance Fabric 1.20.1 -> 2. Vào Chợ Mod cài Sodium -> 3. Khởi động thì bị văng..."
                  value={steps}
                  onChange={(e) => setSteps(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-white/10 bg-slate-900/60 p-3 text-xs text-ink placeholder:text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              {/* GDPR Privacy Opt-in Checkboxes */}
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                  <ShieldCheck className="size-4 text-accent" />
                  <span>Quyền riêng tư & Dữ liệu gửi đi (GDPR Opt-in)</span>
                </div>

                {/* Checkbox 1: Logs */}
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="include-logs"
                    checked={includeLogs}
                    onCheckedChange={(checked) => setIncludeLogs(!!checked)}
                    className="mt-0.5"
                  />
                  <div className="grid gap-0.5 leading-none">
                    <label
                      htmlFor="include-logs"
                      className="cursor-pointer text-xs font-medium text-ink"
                    >
                      Gửi Crash Log & Application Logs{' '}
                      <Badge variant="accent" className="ml-1 text-[9px] px-1 py-0">
                        Khuyên dùng
                      </Badge>
                    </label>
                    <p className="text-[11px] text-muted">
                      Dữ liệu này chỉ chứa log của sidecar, hoàn toàn không chứa thông tin cá nhân.
                    </p>
                  </div>
                </div>

                {/* Checkbox 2: Specs */}
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="include-specs"
                    checked={includeSpecs}
                    onCheckedChange={(checked) => setIncludeSpecs(!!checked)}
                    className="mt-0.5"
                  />
                  <div className="grid gap-0.5 leading-none">
                    <label
                      htmlFor="include-specs"
                      className="cursor-pointer text-xs font-medium text-ink"
                    >
                      Gửi thông tin cấu hình hệ sinh thái (System Specs){' '}
                      <Badge variant="muted" className="ml-1 text-[9px] px-1 py-0">
                        Tùy chọn
                      </Badge>
                    </label>
                    <p className="text-[11px] text-muted">
                      Bao gồm OS, Dung lượng RAM, CPU, GPU, phiên bản Java. Rất hữu ích để tìm nguyên nhân văng game do thiếu RAM hoặc thiếu driver OpenGL.
                    </p>
                  </div>
                </div>
              </div>

              {/* Collapsible Transparency Preview */}
              <div className="min-w-0 rounded-xl border border-white/5 bg-slate-900/40 p-3">
                <button
                  type="button"
                  onClick={() => setShowPreview(!showPreview)}
                  className="flex w-full items-center justify-between text-xs font-medium text-muted hover:text-ink"
                >
                  <span className="flex items-center gap-1.5">
                    <FileText className="size-3.5" />
                    Xem trước dữ liệu sẽ gửi đến máy chủ của chúng tôi
                  </span>
                  {showPreview ? (
                    <ChevronDown className="size-3.5" />
                  ) : (
                    <ChevronRight className="size-3.5" />
                  )}
                </button>

                {showPreview && diagnostics && (
                  <div className="mt-3 min-w-0 space-y-3 overflow-hidden border-t border-white/5 pt-3 text-[11px]">
                    {includeSpecs && (
                      <div className="min-w-0">
                        <strong className="block text-ink font-semibold mb-1">
                          Cấu hình máy (System Specs):
                        </strong>
                        <div className="min-w-0 break-all rounded bg-black/40 p-2 font-mono text-[10px] text-muted space-y-0.5">
                          <div>OS: {diagnostics.specs.os}</div>
                          <div>CPU: {diagnostics.specs.cpu}</div>
                          <div>RAM: {diagnostics.specs.ram}</div>
                          <div>GPU: {diagnostics.specs.gpu}</div>
                          <div>Java: {diagnostics.specs.java_version}</div>
                        </div>
                      </div>
                    )}

                    {includeLogs && (
                      <div className="min-w-0">
                        <strong className="block text-ink font-semibold mb-1">
                          Trích xuất Log gần nhất ({diagnostics.log_file_name || 'sidecar.log'}):
                        </strong>
                        <pre className="max-h-36 max-w-full overflow-x-auto whitespace-pre-wrap break-all rounded bg-black/40 p-2 font-mono text-[10px] text-muted">
                          {diagnostics.log_snippet}
                        </pre>
                      </div>
                    )}

                    {!includeSpecs && !includeLogs && (
                      <p className="text-muted italic">
                        Bạn đã bỏ chọn cả Log và Specs. Chỉ có nội dung văn bản bạn nhập được gửi đi.
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Honeypot hidden field for bot trap */}
              <input
                type="text"
                name="website"
                value=""
                readOnly
                tabIndex={-1}
                autoComplete="off"
                className="hidden"
                aria-hidden="true"
              />
            </div>
          </ScrollArea>

          {/* Footer Actions */}
          <div className="flex items-center justify-between border-t border-white/10 bg-slate-950 p-4 px-6">
            <div className="flex items-center gap-1 text-[11px] text-muted">
              <Lock className="size-3 text-accent" />
              <span>Chúng tôi đề cao bảo mật</span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setOpen(false)}
                disabled={submitting}
              >
                Hủy bỏ
              </Button>
              <Button
                type="submit"
                variant="play"
                size="sm"
                disabled={submitting}
                className="gap-1.5"
              >
                {submitting ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    <span>Đang gửi báo cáo…</span>
                  </>
                ) : (
                  <>
                    <Send className="size-3.5" />
                    <span>Gửi Báo Cáo</span>
                  </>
                )}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

import { useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileText,
  FolderOpen,
  HelpCircle,
  Loader2,
  MemoryStick,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Trash2,
  Wrench,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { CrashAnalysisResult } from '@/lib/types'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app-store'

export function RepairDialog() {
  const open = useAppStore((s) => s.repairDialogOpen)
  const instanceName = useAppStore((s) => s.repairDialogInstance)
  const defaultTab = useAppStore((s) => s.repairDialogTab)
  const closeDialog = useAppStore((s) => s.closeRepairDialog)
  const openModManager = useAppStore((s) => s.openModManager)
  const setScreen = useAppStore((s) => s.setScreen)
  const setBugReportOpen = useAppStore((s) => s.setBugReportOpen)
  const openInstanceFolder = useAppStore((s) => s.openInstanceFolder)

  const verifyInstanceIntegrity = useAppStore((s) => s.verifyInstanceIntegrity)
  const analyzeInstanceCrash = useAppStore((s) => s.analyzeInstanceCrash)
  const resetInstanceOptions = useAppStore((s) => s.resetInstanceOptions)
  const cleanSystemCache = useAppStore((s) => s.cleanSystemCache)

  const [activeTab, setActiveTab] = useState<'verify' | 'crash' | 'reset'>('verify')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<CrashAnalysisResult | null>(null)
  const [copied, setCopied] = useState(false)
  const [resettingOptions, setResettingOptions] = useState(false)
  const [cleaningCache, setCleaningCache] = useState(false)

  useEffect(() => {
    if (open) {
      setActiveTab(defaultTab || 'verify')
      if (defaultTab === 'crash' && instanceName) {
        void handleAnalyzeCrash()
      }
    } else {
      setAnalysis(null)
      setCopied(false)
    }
  }, [open, defaultTab, instanceName])

  const handleAnalyzeCrash = async () => {
    if (!instanceName) return
    setAnalyzing(true)
    const res = await analyzeInstanceCrash(instanceName)
    setAnalysis(res)
    setAnalyzing(false)
  }

  const handleCopyLog = async () => {
    if (!analysis) return
    const textToCopy = `=== PHANTOMX CRASH REPORT ===
Instance: ${instanceName}
Loại lỗi: ${analysis.category} (${analysis.title})
Chi tiết phát hiện: ${analysis.matched_detail || 'None'}
Gợi ý khắc phục: ${analysis.suggestion}
File nguồn: ${analysis.source_file}
-----------------------------
LOG SNIPPET:
${analysis.full_log || analysis.raw_snippet}
=============================`

    try {
      await navigator.clipboard.writeText(textToCopy)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      // Fallback
    }
  }

  const handleStartVerify = async () => {
    if (!instanceName) return
    closeDialog()
    await verifyInstanceIntegrity(instanceName)
  }

  const handleResetOptions = async () => {
    if (!instanceName) return
    setResettingOptions(true)
    await resetInstanceOptions(instanceName)
    setResettingOptions(false)
  }

  const handleCleanCache = async () => {
    setCleaningCache(true)
    await cleanSystemCache()
    setCleaningCache(false)
  }

  if (!instanceName) return null

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? closeDialog() : undefined)}>
      <DialogContent className="max-w-2xl gap-0 border-white/10 bg-[#0f1422] p-0 shadow-2xl backdrop-blur-2xl">
        <DialogHeader className="border-b border-white/10 px-6 pt-5 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="grid size-9 place-items-center rounded-xl border border-accent/30 bg-accent/10 text-accent">
              <Wrench className="size-4.5" />
            </div>
            <div>
              <DialogTitle className="text-base font-semibold text-white">
                Sửa chữa & Chẩn đoán — <span className="text-accent">{instanceName}</span>
              </DialogTitle>
              <DialogDescription className="text-xs text-muted">
                Kiểm tra tính toàn vẹn SHA-1, phân tích nguyên nhân crash và khôi phục cài đặt.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={(val) => setActiveTab(val as 'verify' | 'crash' | 'reset')}
          className="w-full"
        >
          <div className="border-b border-white/10 bg-white/[0.02] px-6">
            <TabsList className="h-11 bg-transparent p-0 gap-6">
              <TabsTrigger
                value="verify"
                className="relative h-11 rounded-none border-b-2 border-transparent bg-transparent px-1 pb-3 pt-3 font-medium text-xs text-muted transition-none data-[state=active]:border-accent data-[state=active]:text-white"
              >
                <ShieldCheck className="size-3.5 mr-1.5 text-accent" />
                Kiểm tra SHA-1 Toàn vẹn
              </TabsTrigger>
              <TabsTrigger
                value="crash"
                className="relative h-11 rounded-none border-b-2 border-transparent bg-transparent px-1 pb-3 pt-3 font-medium text-xs text-muted transition-none data-[state=active]:border-accent data-[state=active]:text-white"
              >
                <AlertCircle className="size-3.5 mr-1.5 text-amber-400" />
                Phân tích Crash Log (80/20)
              </TabsTrigger>
              <TabsTrigger
                value="reset"
                className="relative h-11 rounded-none border-b-2 border-transparent bg-transparent px-1 pb-3 pt-3 font-medium text-xs text-muted transition-none data-[state=active]:border-accent data-[state=active]:text-white"
              >
                <RotateCcw className="size-3.5 mr-1.5 text-neon" />
                Đặt lại & Dọn dẹp
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="p-6">
            {/* ── TAB 1: SHA-1 VERIFICATION ────────────────────────── */}
            <TabsContent value="verify" className="mt-0 space-y-4">
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-xs space-y-3">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="size-5 text-accent shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-semibold text-white">Kiểm tra tính toàn vẹn với mã băm SHA-1</h4>
                    <p className="mt-1 text-muted leading-relaxed">
                      Hệ thống sẽ đối chiếu mã SHA-1 của file <code>client.jar</code>, các thư viện
                      trong <code>libraries/</code> và file cấu hình tài nguyên (Asset Index).
                    </p>
                  </div>
                </div>

                <div className="rounded-lg border border-accent/20 bg-accent/5 p-3 text-[11px] text-accent/90">
                  ⚡ <strong>Tối ưu hóa thông minh:</strong> Chỉ hash file index và libraries quan trọng, không quét hàng nghìn file texture/âm thanh nếu không cần thiết. Quá trình chỉ mất vài giây và chỉ tải lại đúng các file bị hỏng!
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <Button variant="ghost" size="sm" onClick={closeDialog}>
                  Đóng
                </Button>
                <Button
                  variant="neon"
                  size="sm"
                  onClick={() => void handleStartVerify()}
                  className="gap-1.5 font-medium shadow-lg shadow-accent/20"
                >
                  <ShieldCheck className="size-4" />
                  Bắt đầu kiểm tra & Sửa chữa
                </Button>
              </div>
            </TabsContent>

            {/* ── TAB 2: CRASH LOG ANALYZER ────────────────────────── */}
            <TabsContent value="crash" className="mt-0 space-y-4">
              {!analysis && !analyzing && (
                <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 text-center space-y-3">
                  <div className="mx-auto grid size-12 place-items-center rounded-2xl border border-amber-500/20 bg-amber-500/10 text-amber-400">
                    <AlertTriangle className="size-6" />
                  </div>
                  <div>
                    <h4 className="font-semibold text-white">Phân tích nguyên nhân crash gần nhất</h4>
                    <p className="mt-1 text-xs text-muted max-w-md mx-auto">
                      Tự động quét file crash report và latest.log bằng bộ lọc Regex 80/20 để tìm ra nguyên nhân: thiếu RAM, lỗi mod, hay sai Java.
                    </p>
                  </div>
                  <Button
                    variant="neon"
                    size="sm"
                    onClick={() => void handleAnalyzeCrash()}
                    className="gap-2"
                  >
                    <Sparkles className="size-4" />
                    Bắt đầu phân tích
                  </Button>
                </div>
              )}

              {analyzing && (
                <div className="grid place-items-center py-12 text-center">
                  <Loader2 className="size-7 animate-spin text-accent" />
                  <p className="mt-3 text-xs text-muted font-mono">
                    Đang quét patterns: OOM, Mod Dependencies, Java Version…
                  </p>
                </div>
              )}

              {analysis && !analyzing && (
                <div className="space-y-3.5">
                  {/* Result Header Card */}
                  <div
                    className={cn(
                      'rounded-xl border p-4 text-xs space-y-2.5',
                      analysis.category === 'oom' && 'border-amber-500/30 bg-amber-500/10 text-amber-200',
                      analysis.category === 'mod_conflict' && 'border-rose-500/30 bg-rose-500/10 text-rose-200',
                      analysis.category === 'java_mismatch' && 'border-cyan-500/30 bg-cyan-500/10 text-cyan-200',
                      analysis.category === 'unknown' && 'border-white/15 bg-white/[0.04] text-neutral-200',
                      analysis.category === 'none' && 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {analysis.category === 'none' ? (
                          <CheckCircle2 className="size-5 text-emerald-400" />
                        ) : (
                          <AlertTriangle className="size-5 text-amber-400" />
                        )}
                        <h4 className="font-semibold text-sm text-white">{analysis.title}</h4>
                      </div>
                      <Badge variant="muted" className="border-white/20 font-mono text-[10px]">
                        {analysis.source_file}
                      </Badge>
                    </div>

                    <p className="text-neutral-300 leading-relaxed">{analysis.suggestion}</p>

                    {analysis.matched_detail && (
                      <div className="rounded border border-white/10 bg-black/40 p-2 font-mono text-[11px] text-accent break-words">
                        {analysis.matched_detail}
                      </div>
                    )}
                  </div>

                  {/* Quick Action suggestions */}
                  <div className="flex flex-wrap items-center gap-2">
                    {analysis.category === 'oom' && (
                      <Button
                        size="sm"
                        variant="neon"
                        className="h-7 text-xs gap-1.5"
                        onClick={() => {
                          closeDialog()
                          setScreen('settings')
                        }}
                      >
                        <MemoryStick className="size-3.5" />
                        Tới Cài đặt Memory
                      </Button>
                    )}

                    {analysis.category === 'mod_conflict' && (
                      <Button
                        size="sm"
                        variant="neon"
                        className="h-7 text-xs gap-1.5"
                        onClick={() => {
                          closeDialog()
                          openModManager(instanceName)
                        }}
                      >
                        <Wrench className="size-3.5" />
                        Mở Quản lý Mod
                      </Button>
                    )}

                    {analysis.category === 'java_mismatch' && (
                      <Button
                        size="sm"
                        variant="neon"
                        className="h-7 text-xs gap-1.5"
                        onClick={() => {
                          closeDialog()
                          setScreen('settings')
                        }}
                      >
                        <ExternalLink className="size-3.5" />
                        Tới Cài đặt Java
                      </Button>
                    )}

                    {/* Cute Copy Log Button */}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void handleCopyLog()}
                      className="h-7 gap-1.5 text-xs border-accent/40 text-accent hover:bg-accent/10"
                      id="btn-copy-crash-log"
                    >
                      {copied ? (
                        <>
                          <CheckCircle2 className="size-3.5 text-accent" />
                          <span>Đã sao chép!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="size-3.5" />
                          <span>Copy Log</span>
                        </>
                      )}
                    </Button>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void openInstanceFolder(instanceName, 'crash-reports')}
                      className="h-7 gap-1.5 text-xs text-muted hover:text-white"
                    >
                      <FolderOpen className="size-3.5" />
                      Mở thư mục Crash
                    </Button>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        closeDialog()
                        setBugReportOpen(true)
                      }}
                      className="h-7 gap-1.5 text-xs text-rose-300 hover:text-rose-200"
                    >
                      <HelpCircle className="size-3.5" />
                      Báo lỗi Discord
                    </Button>
                  </div>

                  {/* Raw Log Preview */}
                  {analysis.raw_snippet && (
                    <div>
                      <div className="mb-1 flex items-center justify-between text-[11px] font-mono text-muted">
                        <span className="flex items-center gap-1">
                          <FileText className="size-3" />
                          Đoạn trích Log:
                        </span>
                        <span>{analysis.source_file}</span>
                      </div>
                      <ScrollArea className="h-40 rounded-lg border border-white/10 bg-black/60 p-3 font-mono text-[11px] leading-relaxed text-neutral-300">
                        <pre className="whitespace-pre-wrap">{analysis.raw_snippet}</pre>
                      </ScrollArea>
                    </div>
                  )}
                </div>
              )}
            </TabsContent>

            {/* ── TAB 3: RESET OPTIONS & CLEAN CACHE ───────────────── */}
            <TabsContent value="reset" className="mt-0 space-y-4">
              <div className="grid gap-3">
                {/* Reset options.txt */}
                <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="space-y-0.5 max-w-sm">
                    <h4 className="text-xs font-semibold text-white">Đặt lại options.txt về mặc định</h4>
                    <p className="text-[11px] text-muted">
                      Khôi phục độ phân giải, FOV và các cài đặt đồ họa về chuẩn của game. File cũ sẽ được lưu tại <code>options.txt.bak</code>.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={resettingOptions}
                    onClick={() => void handleResetOptions()}
                    className="gap-1.5 text-xs"
                  >
                    {resettingOptions ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCcw className="size-3.5" />}
                    Đặt lại Options
                  </Button>
                </div>

                {/* Clean Cache */}
                <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="space-y-0.5 max-w-sm">
                    <h4 className="text-xs font-semibold text-white">Dọn dẹp bộ nhớ đệm (Cache)</h4>
                    <p className="text-[11px] text-muted">
                      Xóa bỏ các file tải dang dở (<code>.tmp</code>), các file cache log cũ để giải phóng dung lượng ổ cứng.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={cleaningCache}
                    onClick={() => void handleCleanCache()}
                    className="gap-1.5 text-xs border-rose-500/30 text-rose-300 hover:bg-rose-500/10"
                  >
                    {cleaningCache ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                    Dọn dẹp Cache
                  </Button>
                </div>
              </div>
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter className="border-t border-white/10 bg-white/[0.02] px-6 py-3">
          <Button variant="ghost" size="sm" onClick={closeDialog} className="text-xs text-muted">
            Đóng
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
